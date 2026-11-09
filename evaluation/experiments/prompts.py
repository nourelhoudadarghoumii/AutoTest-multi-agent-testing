"""
Prompt variants for the Test Writer prompt-engineering experiment.

P0 = production prompt (imported from agents.test_writer — never copied,
     so P0 always measures the real production prompt)
P1 = structured prompt (explicit sections: context, constraints, output contract)
P2 = P1 + few-shot examples (one good generated-style test pair)
P3 = P2 + RAG bug-pattern section (injected when RAG is ON)

Model, dataset, temperature, max_tokens and execution environment stay
identical across variants — only the prompt changes.
"""

from agents.test_writer import build_system_prompt as p0_system
from agents.test_writer import build_user_prompt as p0_user

PROMPT_VERSIONS = ("P0", "P1", "P2", "P3")

# ── P1: structured system prompt ──────────────────────────────────────────

P1_SYSTEM = """You are an expert Python test engineer generating pytest tests.

## CONTEXT
You receive one Python source file and the exact functions to test, including
their real source code and signatures.

## TASK
For EACH listed function, generate pytest test functions that verify its REAL
behavior as implemented in the source code.

## CONSTRAINTS
1. Only use names that appear in the provided source code — never invent
   functions, classes, modules or attributes.
2. Do NOT write import statements; imports are generated automatically.
3. Do NOT redefine or re-implement the functions under test.
4. Test the behavior the code actually has — including the exceptions it
   actually raises (check the source before asserting an exception type).
5. Every test must be complete and syntactically valid Python (ast.parse).
6. If testing a class method, instantiate the exact class and pass the
   arguments its __init__ requires (see the provided constructor source).

## COVERAGE REQUIREMENTS
For each function: at least one happy path, one edge/boundary case, and one
error path when the source raises.

## OUTPUT CONTRACT (MANDATORY)
First line: <tests>
Last line: </tests>
No markdown fences. No commentary. Nothing outside the tags."""


# ── P2: + few-shot ────────────────────────────────────────────────────────

FEW_SHOT = """## EXAMPLE

Source under test:
```python
def celsius_to_fahrenheit(c):
    if c < -273.15:
        raise ValueError("below absolute zero")
    return c * 9 / 5 + 32
```

Correct output:
<tests>
def test_celsius_to_fahrenheit_freezing():
    assert celsius_to_fahrenheit(0) == 32

def test_celsius_to_fahrenheit_boiling():
    assert celsius_to_fahrenheit(100) == 212

def test_celsius_to_fahrenheit_negative_valid():
    assert celsius_to_fahrenheit(-40) == -40

def test_celsius_to_fahrenheit_below_absolute_zero_raises():
    with pytest.raises(ValueError):
        celsius_to_fahrenheit(-300)
</tests>

Note how the error test asserts the exception the source ACTUALLY raises,
and boundaries use exact values from the real implementation.
"""


def p1_user(filename: str, functions_data: list[dict], available_names: list[str]) -> str:
    """Structured user prompt (same inputs as production build_user_prompt)."""
    sections = [
        f"# Target file\n{filename}",
        f"# Available names (the ONLY names you may use)\n{', '.join(available_names)}",
    ]
    blocks = []
    for data in functions_data:
        block = [
            f"## Function: {data['name']}",
            f"Signature: def {data['signature']} -> {data['return_type']}",
        ]
        if data.get("class_name"):
            block.append(f"Method of class: {data['class_name']}")
            if data.get("init_source"):
                block.append(f"Constructor:\n```python\n{data['init_source']}\n```")
        if data.get("docstring"):
            block.append(f"Docstring: {data['docstring']}")
        block.append(f"Source code:\n```python\n{data['function_source_code']}\n```")
        min_tests = 5 if data.get("is_risk_zone") else 3
        block.append(f"Generate at least {min_tests} tests for this function.")
        if data.get("is_async"):
            block.append("All tests must be async def (pytest-asyncio).")
        blocks.append("\n".join(block))
    sections.append("# Functions to test\n" + "\n\n".join(blocks))
    rag = next((d["rag_section"] for d in functions_data if d.get("rag_section")), None)
    if rag:
        sections.append(f"# Known bug patterns (avoid these failure modes)\n{rag}")
    sections.append(
        "# Output\nAll tests for ALL functions inside ONE <tests></tests> block. "
        "Only the exact names listed above. No imports. No commentary."
    )
    return "\n\n".join(sections)


def get_prompts(version: str):
    """Return (system_fn, user_fn) for a prompt version.

    P0 reuses the production builders directly.
    """
    if version == "P0":
        return p0_system, p0_user
    if version == "P1":
        return lambda: P1_SYSTEM, p1_user
    if version == "P2":
        def system_p2():
            return P1_SYSTEM + "\n\n" + FEW_SHOT
        return system_p2, p1_user
    if version == "P3":
        def system_p3():
            return P1_SYSTEM + "\n\n" + FEW_SHOT
        return system_p3, p1_user
    raise ValueError(f"Unknown prompt version: {version}")


def uses_rag(version: str) -> bool:
    """P3 injects retrieved bug patterns into the user prompt."""
    return version == "P3"
