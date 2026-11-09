"""
Unit tests for the RAG (Retrieval-Augmented Generation) system.

Tests cover:
    - ChromaDB initialization
    - Pattern storage
    - Pattern retrieval with semantic search
    - Graceful fallback when ChromaDB unavailable
    - Statistics and utility functions
"""

import gc
import tempfile
from pathlib import Path

import pytest

from utils.rag import RAGMemory, get_rag_memory, CHROMADB_AVAILABLE


@pytest.fixture
def temp_rag_memory():
    """Create a temporary RAG memory instance for testing.

    ignore_cleanup_errors=True: on Windows, ChromaDB keeps the sqlite file
    locked at interpreter teardown, which would otherwise raise
    PermissionError during TemporaryDirectory cleanup.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        memory = RAGMemory(persist_directory=tmpdir)
        yield memory
    gc.collect()


class TestRAGInitialization:
    """Test suite for RAG memory initialization."""
    
    def test_initialization_creates_directory(self):
        """Test that initialization creates the persist directory."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            persist_dir = Path(tmpdir) / "chroma_test"
            memory = RAGMemory(persist_directory=str(persist_dir))
            
            if CHROMADB_AVAILABLE:
                assert persist_dir.exists()
                assert memory.enabled
            else:
                assert not memory.enabled
    
    def test_initialization_without_chromadb(self, monkeypatch):
        """Test graceful fallback when ChromaDB is not available."""
        # Temporarily disable chromadb
        import utils.rag as rag_module
        original_available = rag_module.CHROMADB_AVAILABLE
        monkeypatch.setattr(rag_module, "CHROMADB_AVAILABLE", False)
        
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            memory = RAGMemory(persist_directory=tmpdir)
            assert not memory.enabled
            assert memory.client is None
            assert memory.collection is None
        
        # Restore
        monkeypatch.setattr(rag_module, "CHROMADB_AVAILABLE", original_available)
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_collection_created(self, temp_rag_memory):
        """Test that the bug_patterns collection is created."""
        assert temp_rag_memory.collection is not None
        assert temp_rag_memory.collection.name == "bug_patterns"


class TestPatternStorage:
    """Test suite for pattern storage functionality."""
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_store_pattern_success(self, temp_rag_memory):
        """Test successful pattern storage."""
        result = temp_rag_memory.store_pattern(
            function_name="validate_email",
            function_signature="def validate_email(email: str) -> bool",
            error_type="AssertionError",
            root_cause="Missing validation for empty string",
            fix_applied="Added check for empty string before regex",
            complexity=5.0
        )
        
        assert result is True
        stats = temp_rag_memory.get_stats()
        assert stats["total_patterns"] == 1
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_store_multiple_patterns(self, temp_rag_memory):
        """Test storing multiple patterns."""
        patterns = [
            ("func1", "def func1(x: int) -> int", "KeyError", "Missing key check", "Added key validation"),
            ("func2", "def func2(y: str) -> str", "ValueError", "Invalid input", "Added input validation"),
            ("func3", "def func3(z: list) -> list", "IndexError", "Index out of range", "Added bounds check"),
        ]
        
        for name, sig, error, cause, fix in patterns:
            result = temp_rag_memory.store_pattern(
                function_name=name,
                function_signature=sig,
                error_type=error,
                root_cause=cause,
                fix_applied=fix,
                complexity=3.0
            )
            assert result is True
        
        stats = temp_rag_memory.get_stats()
        assert stats["total_patterns"] == 3
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_store_pattern_upsert(self, temp_rag_memory):
        """Test that storing same pattern twice upserts (doesn't duplicate)."""
        pattern_data = {
            "function_name": "test_func",
            "function_signature": "def test_func() -> None",
            "error_type": "TestError",
            "root_cause": "Test cause",
            "fix_applied": "Test fix",
            "complexity": 2.0
        }
        
        temp_rag_memory.store_pattern(**pattern_data)
        temp_rag_memory.store_pattern(**pattern_data)
        
        stats = temp_rag_memory.get_stats()
        # Should still be 1 because same pattern ID
        assert stats["total_patterns"] == 1
    
    def test_store_pattern_disabled(self, monkeypatch):
        """Test that storing patterns fails gracefully when disabled."""
        import utils.rag as rag_module
        monkeypatch.setattr(rag_module, "CHROMADB_AVAILABLE", False)
        
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            memory = RAGMemory(persist_directory=tmpdir)
            result = memory.store_pattern(
                function_name="test",
                function_signature="def test() -> None",
                error_type="Error",
                root_cause="cause",
                fix_applied="fix",
                complexity=1.0
            )
            assert result is False


class TestPatternRetrieval:
    """Test suite for pattern retrieval functionality."""
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_retrieve_patterns_empty_database(self, temp_rag_memory):
        """Test retrieval from empty database returns empty list."""
        patterns = temp_rag_memory.retrieve_similar_patterns(
            function_name="test_func",
            function_signature="def test_func() -> None",
            complexity=3.0
        )
        
        assert patterns == []
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_retrieve_similar_patterns(self, temp_rag_memory):
        """Test retrieval of semantically similar patterns."""
        # Store some patterns
        temp_rag_memory.store_pattern(
            function_name="validate_email",
            function_signature="def validate_email(email: str) -> bool",
            error_type="AssertionError",
            root_cause="Missing validation for empty string",
            fix_applied="Added empty string check",
            complexity=5.0
        )
        
        temp_rag_memory.store_pattern(
            function_name="validate_phone",
            function_signature="def validate_phone(phone: str) -> bool",
            error_type="AssertionError",
            root_cause="Missing validation for None input",
            fix_applied="Added None check",
            complexity=4.0
        )
        
        # Query for similar pattern
        patterns = temp_rag_memory.retrieve_similar_patterns(
            function_name="validate_username",
            function_signature="def validate_username(username: str) -> bool",
            complexity=4.5,
            n_results=2
        )
        
        assert len(patterns) <= 2
        assert all("pattern" in p for p in patterns)
        assert all("fix" in p for p in patterns)
        assert all("similarity" in p for p in patterns)
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_retrieve_patterns_with_limit(self, temp_rag_memory):
        """Test that n_results parameter limits returned patterns."""
        # Store 5 patterns
        for i in range(5):
            temp_rag_memory.store_pattern(
                function_name=f"func{i}",
                function_signature=f"def func{i}() -> None",
                error_type="Error",
                root_cause=f"Cause {i}",
                fix_applied=f"Fix {i}",
                complexity=float(i)
            )
        
        # Request only 2 patterns
        patterns = temp_rag_memory.retrieve_similar_patterns(
            function_name="test_func",
            function_signature="def test_func() -> None",
            n_results=2
        )
        
        assert len(patterns) <= 2
    
    def test_retrieve_patterns_disabled(self, monkeypatch):
        """Test that retrieval returns empty list when disabled."""
        import utils.rag as rag_module
        monkeypatch.setattr(rag_module, "CHROMADB_AVAILABLE", False)
        
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            memory = RAGMemory(persist_directory=tmpdir)
            patterns = memory.retrieve_similar_patterns(
                function_name="test",
                function_signature="def test() -> None",
                complexity=1.0
            )
            assert patterns == []


class TestUtilityFunctions:
    """Test suite for utility functions."""
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_get_stats(self, temp_rag_memory):
        """Test statistics retrieval."""
        stats = temp_rag_memory.get_stats()
        assert "total_patterns" in stats
        assert "enabled" in stats
        assert stats["total_patterns"] == 0
        assert stats["enabled"] is True
        
        # Add a pattern
        temp_rag_memory.store_pattern(
            function_name="test",
            function_signature="def test() -> None",
            error_type="Error",
            root_cause="cause",
            fix_applied="fix",
            complexity=1.0
        )
        
        stats = temp_rag_memory.get_stats()
        assert stats["total_patterns"] == 1
    
    def test_get_stats_disabled(self, monkeypatch):
        """Test stats when RAG is disabled."""
        import utils.rag as rag_module
        monkeypatch.setattr(rag_module, "CHROMADB_AVAILABLE", False)
        
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            memory = RAGMemory(persist_directory=tmpdir)
            stats = memory.get_stats()
            assert stats["total_patterns"] == 0
            assert stats["enabled"] is False
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_clear_patterns(self, temp_rag_memory):
        """Test clearing all patterns."""
        # Add patterns
        for i in range(3):
            temp_rag_memory.store_pattern(
                function_name=f"func{i}",
                function_signature=f"def func{i}() -> None",
                error_type="Error",
                root_cause=f"Cause {i}",
                fix_applied=f"Fix {i}",
                complexity=float(i)
            )
        
        stats = temp_rag_memory.get_stats()
        assert stats["total_patterns"] == 3
        
        # Clear
        result = temp_rag_memory.clear_patterns()
        assert result is True
        
        stats = temp_rag_memory.get_stats()
        assert stats["total_patterns"] == 0
    
    def test_clear_patterns_disabled(self, monkeypatch):
        """Test clear fails gracefully when disabled."""
        import utils.rag as rag_module
        monkeypatch.setattr(rag_module, "CHROMADB_AVAILABLE", False)
        
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            memory = RAGMemory(persist_directory=tmpdir)
            result = memory.clear_patterns()
            assert result is False


class TestSingleton:
    """Test suite for global singleton pattern."""
    
    def test_get_rag_memory_singleton(self):
        """Test that get_rag_memory returns same instance."""
        memory1 = get_rag_memory()
        memory2 = get_rag_memory()
        assert memory1 is memory2
    
    def test_singleton_uses_env_variable(self, monkeypatch):
        """Test that singleton respects CHROMA_PERSIST_DIR env variable."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            custom_dir = Path(tmpdir) / "custom_chroma"
            monkeypatch.setenv("CHROMA_PERSIST_DIR", str(custom_dir))
            
            # Reset singleton
            import utils.rag as rag_module
            rag_module._rag_memory = None
            
            memory = get_rag_memory()
            
            if CHROMADB_AVAILABLE:
                assert memory.persist_directory == custom_dir


class TestPatternIDGeneration:
    """Test suite for pattern ID generation."""
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_same_pattern_same_id(self, temp_rag_memory):
        """Test that identical patterns generate the same ID."""
        id1 = temp_rag_memory._generate_pattern_id("func", "Error", "Cause")
        id2 = temp_rag_memory._generate_pattern_id("func", "Error", "Cause")
        assert id1 == id2
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_different_pattern_different_id(self, temp_rag_memory):
        """Test that different patterns generate different IDs."""
        id1 = temp_rag_memory._generate_pattern_id("func1", "Error", "Cause")
        id2 = temp_rag_memory._generate_pattern_id("func2", "Error", "Cause")
        assert id1 != id2


class TestEdgeCases:
    """Test suite for edge cases and error handling."""
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_empty_function_name(self, temp_rag_memory):
        """Test handling of empty function name."""
        result = temp_rag_memory.store_pattern(
            function_name="",
            function_signature="def unknown() -> None",
            error_type="Error",
            root_cause="cause",
            fix_applied="fix",
            complexity=1.0
        )
        # Should still work
        assert result is True
    
    @pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not installed")
    def test_special_characters_in_pattern(self, temp_rag_memory):
        """Test handling of special characters in pattern data."""
        result = temp_rag_memory.store_pattern(
            function_name="test_func",
            function_signature="def test_func(x: List[Dict[str, Any]]) -> Optional[str]",
            error_type="TypeError: 'NoneType' object is not subscriptable",
            root_cause="Variable was None when trying to access [index]",
            fix_applied="Added None check: if x is not None",
            complexity=8.5
        )
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
