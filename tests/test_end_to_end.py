"""
End-to-End Integration Test for AutoTest Pipeline

Tests the complete workflow:
Input Python Project → Analysis → AI Test Generation → Test Execution → AI Debugging → Reporting

This is NOT a unit test. It tests the REAL pipeline with REAL LLM calls.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.graph import build_graph, setup_environment
from core.state import AgentState


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_project_simple():
    """Simple Python project with 2 basic functions."""
    code = '''"""Simple tax calculator module."""

def calculate_tax(amount: float, rate: float) -> float:
    """
    Calculate tax for a given amount and rate.
    
    Args:
        amount: Base amount before tax
        rate: Tax rate (0.0 to 1.0, e.g., 0.2 for 20%)
    
    Returns:
        Total amount including tax
    
    Example:
        >>> calculate_tax(100, 0.2)
        120.0
    """
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    if rate < 0 or rate > 1:
        raise ValueError("Rate must be between 0 and 1")
    return amount + (amount * rate)


def format_price(amount: float, currency: str = "USD") -> str:
    """
    Format price with currency symbol.
    
    Args:
        amount: Price amount
        currency: Currency code (USD, EUR, GBP)
    
    Returns:
        Formatted price string
    
    Example:
        >>> format_price(123.456, "USD")
        '$123.46'
    """
    symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
    symbol = symbols.get(currency, currency)
    return f"{symbol}{amount:.2f}"
'''
    
    # Create temporary project
    tmpdir = tempfile.mkdtemp(prefix="autotest_e2e_")
    project_dir = Path(tmpdir) / "tax_calculator"
    project_dir.mkdir()
    
    # Write __init__.py (required for package structure)
    (project_dir / "__init__.py").write_text("")
    
    # Write main module
    (project_dir / "calculator.py").write_text(code)
    
    yield project_dir
    
    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_project_class():
    """Python project with a class."""
    code = '''"""User authentication module."""

import hashlib
import re
from typing import Optional


class User:
    """User account representation."""
    
    def __init__(self, username: str, email: str):
        """
        Initialize user account.
        
        Args:
            username: User's unique username
            email: User's email address
        """
        self.username = username
        self.email = email
        self.password_hash: Optional[str] = None
    
    def validate_email(self) -> bool:
        """
        Validate email format.
        
        Returns:
            True if email is valid, False otherwise
        """
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, self.email))
    
    def set_password(self, password: str) -> None:
        """
        Hash and store password.
        
        Args:
            password: Plain text password
        """
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    def check_password(self, password: str) -> bool:
        """
        Verify password against stored hash.
        
        Args:
            password: Password to verify
        
        Returns:
            True if password matches, False otherwise
        """
        if not self.password_hash:
            return False
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()
'''
    
    # Create temporary project
    tmpdir = tempfile.mkdtemp(prefix="autotest_e2e_")
    project_dir = Path(tmpdir) / "user_auth"
    project_dir.mkdir()
    
    # Write __init__.py
    (project_dir / "__init__.py").write_text("")
    
    # Write module
    (project_dir / "auth.py").write_text(code)
    
    yield project_dir
    
    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestEndToEndPipeline:
    """
    Comprehensive end-to-end tests for AutoTest pipeline.
    
    These tests require:
    - OPENROUTER_API_KEY set in environment
    - Internet connection for LLM calls
    - ~2-5 minutes per test
    """
    
    def test_e2e_simple_functions(self, sample_project_simple):
        """
        Test complete pipeline with simple functions.
        
        Expected flow:
        1. Analyser parses 2 functions
        2. Test Writer generates pytest tests
        3. Executor runs tests
        4. Reporter generates quality report
        """
        # Skip if no API key
        if not os.getenv("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not set - skipping LLM test")
        
        # Setup
        setup_environment()
        app = build_graph()
        
        # Find source files
        source_files = [
            str(f) for f in sample_project_simple.glob("**/*.py")
            if f.name != "__pycache__"
        ]
        
        # Create initial state
        initial_state: AgentState = {
            "project_id": "e2e_test_simple",
            "base_dir": str(sample_project_simple),
            "test_dir": str(sample_project_simple / "tests"),
            "source_files": source_files,
            "code_context": {
                "functions": [],
                "classes": [],
                "imports": [],
                "complexity": {},
                "dependency_graph": {}
            },
            "patterns_retrieved": [],
            "test_files": [],
            "tests_generated_count": 0,
            "llm_api_calls": 0,
            "llm_retries": 0,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "llm_total_tokens": 0,
            "llm_success_rate": 0.0,
            "ast_validation_passed": False,
            "pytest_validation_passed": False,
            "functions_skipped_trivial": [],
            "functions_failed_generation": [],
            "execution_results": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "coverage_percent": 0.0,
                "stdout": "",
                "stderr": "",
                "failed_test_names": []
            },
            "failed_tests": [],
            "debug_report": {
                "root_cause": "",
                "fix_applied": "",
                "iterations": 0,
                "resolved": False
            },
            "iteration_count": 0,
            "total_fixes_applied": 0,
            "final_report": {
                "project_id": "",
                "summary": "",
                "quality_score": 0.0,
                "coverage_percent": 0.0,
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "complexity_avg": 0.0,
                "debug_iterations": 0,
                "recommendations": [],
                "risk_level": "unknown"
            },
            "status": "running"
        }
        
        # Run pipeline
        print("\n" + "="*70)
        print("RUNNING END-TO-END TEST: Simple Functions")
        print("="*70)
        
        final_state = app.invoke(initial_state)
        
        # Validate results
        print("\nValidating results...")
        
        # 1. Analyser should find 2 functions
        assert len(final_state["code_context"]["functions"]) >= 2, \
            f"Expected >= 2 functions, got {len(final_state['code_context']['functions'])}"
        print("✓ Analyser: Found functions")
        
        # 2. Test Writer should generate tests
        assert final_state["tests_generated_count"] > 0, \
            "No tests generated"
        assert len(final_state["test_files"]) > 0, \
            "No test files created"
        print(f"✓ Test Writer: Generated {final_state['tests_generated_count']} test(s)")
        
        # 3. Executor should run tests
        assert final_state["execution_results"]["total_tests"] > 0, \
            "No tests executed"
        print(f"✓ Executor: Ran {final_state['execution_results']['total_tests']} test(s)")
        
        # 4. Reporter should generate report
        assert final_state["final_report"]["project_id"] != "", \
            "Final report not generated"
        assert final_state["final_report"]["quality_score"] >= 0, \
            "Quality score not calculated"
        print(f"✓ Reporter: Quality score = {final_state['final_report']['quality_score']:.1f}")
        
        # 5. Pipeline should complete
        assert final_state["status"] == "completed", \
            f"Pipeline did not complete successfully: {final_state['status']}"
        print("✓ Pipeline: Completed successfully")
        
        # 6. LLM metrics
        print(f"\nLLM Metrics:")
        print(f"  • API calls: {final_state['llm_api_calls']}")
        print(f"  • Total tokens: {final_state['llm_total_tokens']}")
        print(f"  • Success rate: {final_state['llm_success_rate']:.1%}")
        
        print("\n" + "="*70)
        print("END-TO-END TEST PASSED ✓")
        print("="*70 + "\n")
    
    
    def test_e2e_class_methods(self, sample_project_class):
        """
        Test complete pipeline with class methods.
        
        Expected flow:
        1. Analyser parses 1 class with 4 methods
        2. Test Writer generates tests for class and methods
        3. Executor runs tests
        4. Reporter generates quality report
        """
        # Skip if no API key
        if not os.getenv("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not set - skipping LLM test")
        
        # Setup
        setup_environment()
        app = build_graph()
        
        # Find source files
        source_files = [
            str(f) for f in sample_project_class.glob("**/*.py")
            if f.name != "__pycache__"
        ]
        
        # Create initial state
        initial_state: AgentState = {
            "project_id": "e2e_test_class",
            "base_dir": str(sample_project_class),
            "test_dir": str(sample_project_class / "tests"),
            "source_files": source_files,
            "code_context": {
                "functions": [],
                "classes": [],
                "imports": [],
                "complexity": {},
                "dependency_graph": {}
            },
            "patterns_retrieved": [],
            "test_files": [],
            "tests_generated_count": 0,
            "llm_api_calls": 0,
            "llm_retries": 0,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "llm_total_tokens": 0,
            "llm_success_rate": 0.0,
            "ast_validation_passed": False,
            "pytest_validation_passed": False,
            "functions_skipped_trivial": [],
            "functions_failed_generation": [],
            "execution_results": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "coverage_percent": 0.0,
                "stdout": "",
                "stderr": "",
                "failed_test_names": []
            },
            "failed_tests": [],
            "debug_report": {
                "root_cause": "",
                "fix_applied": "",
                "iterations": 0,
                "resolved": False
            },
            "iteration_count": 0,
            "total_fixes_applied": 0,
            "final_report": {
                "project_id": "",
                "summary": "",
                "quality_score": 0.0,
                "coverage_percent": 0.0,
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "complexity_avg": 0.0,
                "debug_iterations": 0,
                "recommendations": [],
                "risk_level": "unknown"
            },
            "status": "running"
        }
        
        # Run pipeline
        print("\n" + "="*70)
        print("RUNNING END-TO-END TEST: Class with Methods")
        print("="*70)
        
        final_state = app.invoke(initial_state)
        
        # Validate results
        print("\nValidating results...")
        
        # 1. Analyser should find class
        assert len(final_state["code_context"]["classes"]) >= 1, \
            f"Expected >= 1 class, got {len(final_state['code_context']['classes'])}"
        print("✓ Analyser: Found class")
        
        # 2. Test Writer should generate tests
        assert final_state["tests_generated_count"] > 0, \
            "No tests generated"
        print(f"✓ Test Writer: Generated {final_state['tests_generated_count']} test(s)")
        
        # 3. Executor should run tests
        assert final_state["execution_results"]["total_tests"] > 0, \
            "No tests executed"
        print(f"✓ Executor: Ran {final_state['execution_results']['total_tests']} test(s)")
        
        # 4. Reporter should generate report
        assert final_state["final_report"]["quality_score"] >= 0, \
            "Quality score not calculated"
        print(f"✓ Reporter: Quality score = {final_state['final_report']['quality_score']:.1f}")
        
        # 5. Pipeline should complete
        assert final_state["status"] == "completed", \
            f"Pipeline did not complete successfully: {final_state['status']}"
        print("✓ Pipeline: Completed successfully")
        
        print("\n" + "="*70)
        print("END-TO-END TEST PASSED ✓")
        print("="*70 + "\n")


# =============================================================================
# Manual Test Runner (for debugging)
# =============================================================================

if __name__ == "__main__":
    """
    Run end-to-end tests manually.
    
    Usage:
        python tests/test_end_to_end.py
    """
    import sys
    
    # Check API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set")
        print("Set it in .env file to run end-to-end tests")
        sys.exit(1)
    
    # Run tests
    print("Running AutoTest End-to-End Tests")
    print("This will take 3-10 minutes (real LLM calls)\n")
    
    pytest.main([__file__, "-v", "-s"])
