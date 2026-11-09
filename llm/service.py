"""
OpenRouter LLM Service — per-agent gateway with FIXED free models.

Architecture:
    Test Writer ─→ OpenRouterService(role="test_writer") ──→ cohere/north-mini-code:free
    Debugger   ─→ OpenRouterService(role="debugger")    ──→ nvidia/nemotron-3-super-120b-a12b:free

Each agent gets exactly ONE fixed model, bound at construction. There is no
automatic model selection, no random routing, and no fallback to another
model — if a selected model is unavailable, the call fails with a clear
LLMError naming the model.

Configuration (environment variables, no hardcoded credentials):
    OPENROUTER_API_KEY              — API key (required)
    OPENROUTER_BASE_URL             — defaults to https://openrouter.ai/api/v1
    OPENROUTER_TEST_WRITER_MODEL    — defaults to cohere/north-mini-code:free
    OPENROUTER_DEBUGGER_MODEL       — defaults to nvidia/nemotron-3-super-120b-a12b:free

Robustness guarantees (all retries are strictly bounded — no infinite loops):
    - 429 rate limits        → bounded retries honoring Retry-After
    - timeouts / conn errors → bounded retries with backoff
    - empty responses        → bounded retries
    - 401 / 402 / 403        → permanent, retried NEVER (auth/credits/forbidden
      never heal on retry — fail immediately with an actionable message)
    - model unavailable (404/400) → permanent LLMError naming the model
    - exhausted attempts     → LLMError with an actionable message
"""

import logging
import os
import re
import time
from dataclasses import dataclass

from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Fixed per-agent models ───────────────────────────────────────────────
ROLE_TEST_WRITER = "test_writer"
ROLE_DEBUGGER = "debugger"

_ROLE_MODEL_ENV = {
    ROLE_TEST_WRITER: "OPENROUTER_TEST_WRITER_MODEL",
    ROLE_DEBUGGER: "OPENROUTER_DEBUGGER_MODEL",
}

# Fixed defaults — free tiers only, never auto-selected, never swapped.
_ROLE_MODEL_DEFAULT = {
    ROLE_TEST_WRITER: "cohere/north-mini-code:free",
    ROLE_DEBUGGER: "nvidia/nemotron-3-super-120b-a12b:free",
}

# ── Bounded retry policy (never infinite) ────────────────────────────────
MAX_RATE_LIMIT_RETRIES = 5   # 429 responses allowed per call
MAX_TRANSIENT_RETRIES = 2    # timeouts / connection errors / empty bodies
MAX_TOTAL_ATTEMPTS = 15      # absolute ceiling across all retry kinds
MAX_RETRY_AFTER_WAIT = 60    # never sleep longer than this per retry (seconds)
DEFAULT_TIMEOUT = 90.0

# Reasoning-model control: these coding models burn the completion budget on
# hidden reasoning tokens, leaving `content` empty (finish_reason=length).
# Disabling reasoning keeps the whole output budget for the actual answer.
DISABLE_REASONING = {"reasoning": {"enabled": False}}


class LLMError(Exception):
    """Raised when the LLM service cannot produce a usable completion.

    The message is always actionable: it names the model and the stage
    that failed, and what the operator can do about it.
    """


@dataclass(frozen=True)
class LLMResponse:
    """One successful completion with its token accounting."""
    content: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class OpenRouterService:
    """
    Thin, failure-aware wrapper around the OpenRouter chat completions API,
    bound to ONE fixed model for ONE agent role.
    """

    def __init__(
        self,
        role: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if role is not None and role not in _ROLE_MODEL_ENV:
            raise ValueError(
                f"Unknown LLM role '{role}'. "
                f"Valid roles: {sorted(_ROLE_MODEL_ENV)}"
            )

        self.role = role or "unscoped"
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        # OPENROUTER_BASE_URL allows pointing at a proxy or self-hosted
        # OpenAI-compatible endpoint (defaults to OpenRouter's public API).
        self.base_url = base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        if model:
            # Explicit injection (used by tests); still bound to this role.
            self.model = model
        elif role:
            env_var = _ROLE_MODEL_ENV[role]
            self.model = os.getenv(env_var, "").strip() or _ROLE_MODEL_DEFAULT[role]
        else:
            raise ValueError(
                "OpenRouterService requires a role (test_writer | debugger) "
                "or an explicit model."
            )

        if not self.api_key or self.api_key.strip() in ("", "YOUR_KEY_HERE"):
            raise LLMError(
                "OPENROUTER_API_KEY is not configured. "
                "Set it in your .env file (get a key at https://openrouter.ai/keys)."
            )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "AutoTest",
            },
        )
        logger.info(
            "LLM service initialized — agent: %s, model: %s (OpenRouter, fixed)",
            self.role, self.model,
        )

    # ── Public API ───────────────────────────────────────────────────────

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: float = DEFAULT_TIMEOUT,
        extra_body: dict | None = None,
    ) -> LLMResponse:
        """Request one completion from this service's FIXED model.

        Strictly bounded retry budgets:
          - 429 rate limits: MAX_RATE_LIMIT_RETRIES, honoring Retry-After
          - transient failures (timeouts, connection errors, empty payloads):
            MAX_TRANSIENT_RETRIES
        401 / 402 / 403 and unavailable-model errors are PERMANENT: they are
        never retried (retrying them cannot succeed) and never trigger a
        model switch. The raised LLMError always names the exact model.
        """
        rate_limit_used = 0
        transient_used = 0
        calls = 0

        req_extra_body = extra_body
        if req_extra_body and "openrouter" not in self.base_url.lower():
            req_extra_body = {k: v for k, v in req_extra_body.items() if k != "reasoning"} or None

        while calls < MAX_TOTAL_ATTEMPTS:
            calls += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    extra_body=req_extra_body,
                )
                return self._extract(response)

            except LLMError as exc:
                # Empty/invalid response envelope — consumes transient budget.
                transient_used += 1
                if transient_used > MAX_TRANSIENT_RETRIES:
                    raise
                logger.warning(
                    "Empty/invalid LLM response (transient retry %d/%d)",
                    transient_used, MAX_TRANSIENT_RETRIES,
                )
                time.sleep(3 * transient_used)

            except Exception as exc:  # noqa: BLE001 — classified below
                kind, retry_after = self._classify(exc)

                if kind == "rate_limit":
                    rate_limit_used += 1
                    if rate_limit_used > MAX_RATE_LIMIT_RETRIES:
                        raise LLMError(
                            f"OpenRouter rate limit exceeded for model "
                            f"'{self.model}' after {MAX_RATE_LIMIT_RETRIES} "
                            f"retries. Last error: {exc}"
                        ) from exc
                    delay = min(retry_after if retry_after is not None else 10,
                                MAX_RETRY_AFTER_WAIT)
                    logger.warning(
                        "Rate limited on model '%s' — waiting %ds (retry %d/%d)",
                        self.model, delay, rate_limit_used, MAX_RATE_LIMIT_RETRIES,
                    )
                    time.sleep(delay)

                elif kind == "transient":
                    transient_used += 1
                    if transient_used > MAX_TRANSIENT_RETRIES:
                        raise LLMError(
                            f"LLM call to model '{self.model}' failed after "
                            f"{MAX_TRANSIENT_RETRIES + 1} attempts on transient "
                            f"errors: {exc}"
                        ) from exc
                    logger.warning(
                        "Transient LLM failure on model '%s' (%s) — retry %d/%d",
                        self.model, type(exc).__name__,
                        transient_used, MAX_TRANSIENT_RETRIES,
                    )
                    time.sleep(5 * transient_used)

                else:
                    # Permanent: 401 (auth), 402 (credits), 403 (forbidden),
                    # 404/400 (model unavailable/invalid), or other unrecoverable.
                    raise LLMError(
                        f"Permanent OpenRouter failure for model '{self.model}' "
                        f"({type(exc).__name__}): {exc}. "
                        f"No fallback model is used — check the model slug "
                        f"and your account, then retry."
                    ) from exc

        raise LLMError(
            f"LLM call to model '{self.model}' failed after the maximum "
            f"number of attempts. Check network connectivity and your "
            f"OpenRouter account quota."
        )

    # ── Internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _classify(exc: Exception) -> tuple[str, int | None]:
        """Map an exception to (kind, retry_after_seconds)."""
        text = str(exc)
        status = getattr(exc, "status_code", None)
        lowered = text.lower()

        if status == 429 or "429" in text or "rate limit" in lowered:
            return "rate_limit", OpenRouterService._parse_retry_after(text)

        # Permanent, never retried: auth, credits, forbidden, and any other
        # 4xx except 408 (request timeout, which is transient).
        if status in (401, 402, 403):
            return "permanent", None
        if status is not None and 400 <= status < 500 and status != 408:
            return "permanent", None
        if "invalid api key" in lowered or "no auth credentials" in lowered:
            return "permanent", None

        if (
            isinstance(exc, TimeoutError)
            or "timeout" in lowered
            or "timed out" in lowered
            or "connection" in lowered
            or "temporarily" in lowered
            or "502" in text
            or "503" in text
        ):
            return "transient", None

        return "transient", None

    @staticmethod
    def _parse_retry_after(text: str) -> int | None:
        match = re.search(r"'Retry-After':\s*'(\d+)'", text)
        if match:
            return int(match.group(1))
        match = re.search(r"retry[- ]after[:\s]*(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r"retry in (\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _extract(self, response) -> LLMResponse:
        """Validate the response envelope; raise LLMError on empty payloads.

        On HTTP-200-with-unusable-content, a full diagnostic (model,
        finish_reason, usage, provider, structure) is logged — never the
        API key or response body.
        """
        if response is None or not getattr(response, "choices", None):
            logger.error(
                "Empty/invalid LLM response envelope from model '%s'. Diagnostics: %s",
                self.model, self._diagnose_response(response),
            )
            raise LLMError("LLM returned an empty response envelope")

        message = response.choices[0].message if response.choices else None
        content = getattr(message, "content", None) if message else None

        if not content or not content.strip():
            logger.error(
                "Empty/invalid LLM content from model '%s'. Diagnostics: %s",
                self.model, self._diagnose_response(response),
            )
            raise LLMError("LLM returned an empty completion (no content)")

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _diagnose_response(self, response) -> str:
        """Build a secret-free diagnostic dump of an unusable response.

        Includes: model, provider, finish reasons, token usage, response
        structure and any provider error metadata. Never includes the API
        key, request headers, or message body content.
        """
        diag: dict = {"requested_model": self.model}
        try:
            dump = response.model_dump(exclude_none=True)
        except Exception:
            dump = None

        if isinstance(dump, dict):
            diag["response_id"] = dump.get("id")
            diag["returned_model"] = dump.get("model")
            diag["provider"] = dump.get("provider") or dump.get("native_provider")
            usage = dump.get("usage") or {}
            diag["usage"] = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cost": usage.get("cost"),
            }
            choices = dump.get("choices") or []
            diag["choices_count"] = len(choices)
            diag["choices"] = [
                {
                    "finish_reason": ch.get("finish_reason"),
                    "native_finish_reason": ch.get("native_finish_reason"),
                    "message_role": (ch.get("message") or {}).get("role"),
                    "content_chars": len((ch.get("message") or {}).get("content") or ""),
                    "reasoning_present": bool((ch.get("message") or {}).get("reasoning")),
                    "tool_calls_present": bool((ch.get("message") or {}).get("tool_calls")),
                    "error": ch.get("error"),
                }
                for ch in choices[:3]
            ]
            for key in ("error", "metadata", "native_finish_reason"):
                if dump.get(key):
                    diag[key] = dump[key]
        else:
            diag["unparseable_repr"] = repr(response)[:800]

        import json as _json
        try:
            return _json.dumps(diag, indent=2, default=str)
        except Exception:  # noqa: BLE001
            return str(diag)


# Per-role singletons — each agent's model is bound exactly once per process.
_services: dict[str, OpenRouterService] = {}


def get_llm_service(role: str) -> OpenRouterService:
    """
    Return the singleton OpenRouterService for an agent role.

    The model is bound per role at construction:
        get_llm_service("test_writer") → Test Writer model ONLY
        get_llm_service("debugger")    → Debugger model ONLY
    An unknown role raises immediately — agents cannot cross wires.
    """
    if role not in _ROLE_MODEL_ENV:
        raise ValueError(
            f"Unknown LLM role '{role}'. "
            f"Valid roles: {sorted(_ROLE_MODEL_ENV)}"
        )
    if role not in _services:
        _services[role] = OpenRouterService(role=role)
    return _services[role]


def configured_models() -> dict[str, str]:
    """Return the configured model per role (for health/status reporting)."""
    return {
        role: (os.getenv(env_var, "").strip() or default)
        for role, env_var, default in (
            (role, _ROLE_MODEL_ENV[role], _ROLE_MODEL_DEFAULT[role])
            for role in _ROLE_MODEL_ENV
        )
    }
