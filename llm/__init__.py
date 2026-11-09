"""
LLM layer for AutoTest.

Each agent uses exactly one fixed OpenRouter model:
    Test Writer → cohere/north-mini-code:free
    Debugger    → nvidia/nemotron-3-super-120b-a12b:free
"""

from llm.service import (
    DISABLE_REASONING,
    LLMError,
    LLMResponse,
    OpenRouterService,
    ROLE_DEBUGGER,
    ROLE_TEST_WRITER,
    configured_models,
    get_llm_service,
)

__all__ = [
    "DISABLE_REASONING",
    "LLMError",
    "LLMResponse",
    "OpenRouterService",
    "ROLE_DEBUGGER",
    "ROLE_TEST_WRITER",
    "configured_models",
    "get_llm_service",
]
