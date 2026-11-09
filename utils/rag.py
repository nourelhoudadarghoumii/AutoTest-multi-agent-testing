"""
RAG (Retrieval-Augmented Generation) System using ChromaDB.

This module provides semantic memory for bug patterns discovered during debugging.
When tests fail and are fixed, patterns are stored. When generating new tests,
similar patterns are retrieved to improve test quality from the start.

Architecture:
    - ChromaDB: Vector database for semantic similarity search
    - Embeddings: Function signatures + error patterns
    - Storage: Debugger stores patterns after successful fixes
    - Retrieval: Test Writer retrieves similar patterns before generation

Collection Schema:
    - id: Unique pattern identifier (hash of function + error)
    - embedding: Vector representation of function signature + error pattern
    - metadata: {
        "function_name": str,
        "function_signature": str,
        "error_type": str,
        "root_cause": str,
        "fix_applied": str,
        "complexity": float,
        "timestamp": str
      }
"""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None


class RAGMemory:
    """
    Manages bug pattern storage and retrieval using ChromaDB.
    
    This class provides:
        - Pattern storage after successful debug fixes
        - Semantic search for similar patterns
        - Persistence across pipeline runs
        - Graceful fallback if ChromaDB is unavailable
    """
    
    def __init__(self, persist_directory: str = "./chroma_data"):
        """
        Initialize ChromaDB client and collection.
        
        Args:
            persist_directory: Directory for ChromaDB persistence
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = "bug_patterns"
        self.client = None
        self.collection = None
        self.enabled = False
        
        if not CHROMADB_AVAILABLE:
            print("[RAG] ChromaDB not available. Pattern storage disabled.")
            print("[RAG] Install with: pip install chromadb")
            return
        
        try:
            self._initialize_client()
            self.enabled = True
            print(f"[RAG] ChromaDB initialized at {self.persist_directory}")
        except Exception as e:
            print(f"[RAG] Failed to initialize ChromaDB: {e}")
            print("[RAG] Pattern storage disabled.")
    
    def _initialize_client(self) -> None:
        """Initialize ChromaDB client and get or create collection."""
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        # Create client with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False
            )
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Bug patterns from debugging cycles"}
        )
    
    def _generate_pattern_id(self, function_name: str, error_type: str, root_cause: str) -> str:
        """
        Generate unique ID for a bug pattern.
        
        Args:
            function_name: Name of the function
            error_type: Type of error encountered
            root_cause: Root cause description
        
        Returns:
            Unique hash-based identifier
        """
        content = f"{function_name}|{error_type}|{root_cause}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _create_pattern_text(
        self,
        function_name: str,
        function_signature: str,
        error_type: str,
        root_cause: str
    ) -> str:
        """
        Create searchable text representation of a pattern.
        
        This text is embedded for semantic similarity search.
        
        Args:
            function_name: Function name
            function_signature: Full function signature
            error_type: Type of error
            root_cause: Root cause description
        
        Returns:
            Formatted text for embedding
        """
        return (
            f"Function: {function_name}\n"
            f"Signature: {function_signature}\n"
            f"Error: {error_type}\n"
            f"Root Cause: {root_cause}"
        )
    
    def store_pattern(
        self,
        function_name: str,
        function_signature: str,
        error_type: str,
        root_cause: str,
        fix_applied: str,
        complexity: float = 0.0
    ) -> bool:
        """
        Store a bug pattern in ChromaDB after successful fix.
        
        Args:
            function_name: Name of the function that had the bug
            function_signature: Full function signature
            error_type: Type of error (e.g., "AssertionError", "KeyError")
            root_cause: Description of the root cause
            fix_applied: Description of the fix that resolved it
            complexity: Cyclomatic complexity of the function
        
        Returns:
            True if stored successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            pattern_id = self._generate_pattern_id(function_name, error_type, root_cause)
            pattern_text = self._create_pattern_text(
                function_name, function_signature, error_type, root_cause
            )
            
            # Store in ChromaDB with metadata
            self.collection.upsert(
                ids=[pattern_id],
                documents=[pattern_text],
                metadatas=[{
                    "function_name": function_name,
                    "function_signature": function_signature,
                    "error_type": error_type,
                    "root_cause": root_cause,
                    "fix_applied": fix_applied,
                    "complexity": complexity,
                    "timestamp": datetime.now().isoformat()
                }]
            )
            
            print(f"[RAG] Stored pattern for {function_name}: {error_type}")
            return True
            
        except Exception as e:
            print(f"[RAG] Failed to store pattern: {e}")
            return False
    
    def retrieve_similar_patterns(
        self,
        function_name: str,
        function_signature: str,
        complexity: float = 0.0,
        n_results: int = 3
    ) -> List[Dict[str, str]]:
        """
        Retrieve similar bug patterns for a function.
        
        Uses semantic similarity search to find patterns from similar functions
        that might be relevant for test generation.
        
        Args:
            function_name: Name of the function to generate tests for
            function_signature: Full function signature
            complexity: Cyclomatic complexity
            n_results: Maximum number of patterns to return
        
        Returns:
            List of pattern dictionaries with keys:
                - pattern: Description of the bug pattern
                - fix: Description of the fix
                - similarity: Similarity score (0-1)
        """
        if not self.enabled:
            return []
        
        try:
            # Check if collection is empty
            count = self.collection.count()
            if count == 0:
                return []
            
            # Create query text
            query_text = (
                f"Function: {function_name}\n"
                f"Signature: {function_signature}\n"
                f"Complexity: {complexity}"
            )
            
            # Query for similar patterns
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(n_results, count)
            )
            
            # Format results
            patterns = []
            if results and results['metadatas'] and results['metadatas'][0]:
                for metadata, distance in zip(results['metadatas'][0], results['distances'][0]):
                    # Convert distance to similarity (lower distance = higher similarity)
                    similarity = 1.0 / (1.0 + distance)
                    
                    patterns.append({
                        "pattern": f"{metadata['error_type']}: {metadata['root_cause']}",
                        "fix": metadata['fix_applied'],
                        "similarity": round(similarity, 3),
                        "function": metadata['function_name']
                    })
            
            if patterns:
                print(f"[RAG] Retrieved {len(patterns)} similar patterns for {function_name}")
            
            return patterns
            
        except Exception as e:
            print(f"[RAG] Failed to retrieve patterns: {e}")
            return []
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about stored patterns.
        
        Returns:
            Dictionary with statistics:
                - total_patterns: Total number of stored patterns
                - enabled: Whether RAG is enabled
        """
        if not self.enabled:
            return {"total_patterns": 0, "enabled": False}
        
        try:
            count = self.collection.count()
            return {
                "total_patterns": count,
                "enabled": True
            }
        except Exception as e:
            print(f"[RAG] Failed to get stats: {e}")
            return {"total_patterns": 0, "enabled": False}
    
    def clear_patterns(self) -> bool:
        """
        Clear all stored patterns (use with caution).
        
        Returns:
            True if cleared successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            # Delete and recreate collection
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Bug patterns from debugging cycles"}
            )
            print("[RAG] Cleared all patterns")
            return True
            
        except Exception as e:
            print(f"[RAG] Failed to clear patterns: {e}")
            return False


# Global singleton instance
_rag_memory: Optional[RAGMemory] = None


def get_rag_memory() -> RAGMemory:
    """
    Get or create the global RAG memory instance.
    
    Returns:
        RAGMemory singleton instance
    """
    global _rag_memory
    if _rag_memory is None:
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
        _rag_memory = RAGMemory(persist_directory=persist_dir)
    return _rag_memory
