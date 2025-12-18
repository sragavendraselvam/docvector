"""Verification script for A2: IVectorStore abstract interface.

This script verifies that the IVectorStore interface is properly defined
and can be used as intended.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_imports():
    """Test that all interface components can be imported."""
    print("=" * 60)
    print("Test 1: Importing Interface Components")
    print("=" * 60)
    
    try:
        from docvector.vectordb import IVectorStore, VectorRecord, VectorSearchResult
        print("✓ IVectorStore imported successfully")
        print("✓ VectorRecord imported successfully")
        print("✓ VectorSearchResult imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_data_classes():
    """Test that data classes work correctly."""
    print("\n" + "=" * 60)
    print("Test 2: Data Classes")
    print("=" * 60)
    
    try:
        from docvector.vectordb import VectorRecord, VectorSearchResult
        
        # Test VectorRecord
        record = VectorRecord(
            id="test_id_123",
            vector=[0.1, 0.2, 0.3, 0.4],
            payload={"text": "Test document", "source": "test", "index": 1}
        )
        
        assert record.id == "test_id_123"
        assert len(record.vector) == 4
        assert record.payload["text"] == "Test document"
        print("✓ VectorRecord creation and access works")
        print(f"  - ID: {record.id}")
        print(f"  - Vector dimension: {len(record.vector)}")
        print(f"  - Payload keys: {list(record.payload.keys())}")
        
        # Test VectorSearchResult
        result = VectorSearchResult(
            id="result_id_456",
            score=0.95,
            payload={"text": "Search result", "rank": 1},
            vector=[0.5, 0.6, 0.7, 0.8]
        )
        
        assert result.id == "result_id_456"
        assert result.score == 0.95
        assert result.vector is not None
        print("✓ VectorSearchResult creation and access works")
        print(f"  - ID: {result.id}")
        print(f"  - Score: {result.score}")
        print(f"  - Has vector: {result.vector is not None}")
        
        # Test optional vector
        result_no_vector = VectorSearchResult(
            id="result_id_789",
            score=0.85,
            payload={"text": "Another result"}
        )
        assert result_no_vector.vector is None
        print("✓ VectorSearchResult with optional vector works")
        
        return True
        
    except Exception as e:
        print(f"✗ Data class test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_interface_structure():
    """Test that the interface has all required methods."""
    print("\n" + "=" * 60)
    print("Test 3: Interface Structure")
    print("=" * 60)
    
    try:
        from docvector.vectordb import IVectorStore
        import inspect
        
        # Get all abstract methods
        abstract_methods = [
            name for name, method in inspect.getmembers(IVectorStore, predicate=inspect.isfunction)
            if getattr(method, '__isabstractmethod__', False)
        ]
        
        expected_methods = [
            'initialize',
            'close',
            'create_collection',
            'delete_collection',
            'collection_exists',
            'get_collection_info',
            'upsert',
            'search',
            'delete',
            'count'
        ]
        
        print(f"Expected methods: {len(expected_methods)}")
        print(f"Found abstract methods: {len(abstract_methods)}")
        
        for method in expected_methods:
            if method in abstract_methods:
                print(f"  ✓ {method}")
            else:
                print(f"  ✗ {method} - MISSING!")
                return False
        
        # Check for unexpected methods
        unexpected = set(abstract_methods) - set(expected_methods)
        if unexpected:
            print(f"\nUnexpected methods found: {unexpected}")
        
        print("\n✓ All required methods are present")
        return True
        
    except Exception as e:
        print(f"✗ Interface structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_interface_implementation():
    """Test that the interface can be implemented."""
    print("\n" + "=" * 60)
    print("Test 4: Interface Implementation")
    print("=" * 60)
    
    try:
        from docvector.vectordb import IVectorStore, VectorRecord, VectorSearchResult
        from typing import Dict, List, Optional, Any
        
        class MockVectorStore(IVectorStore):
            """Mock implementation for testing."""
            
            def __init__(self):
                self.initialized = False
                self.collections = {}
            
            async def initialize(self) -> None:
                self.initialized = True
            
            async def close(self) -> None:
                self.initialized = False
            
            async def create_collection(
                self, name: str, dimension: int, distance_metric: str = "cosine"
            ) -> None:
                self.collections[name] = {
                    "dimension": dimension,
                    "metric": distance_metric,
                    "vectors": []
                }
            
            async def delete_collection(self, name: str) -> None:
                if name in self.collections:
                    del self.collections[name]
            
            async def collection_exists(self, name: str) -> bool:
                return name in self.collections
            
            async def get_collection_info(self, name: str) -> Optional[Dict[str, Any]]:
                if name not in self.collections:
                    return None
                return {
                    "name": name,
                    "dimension": self.collections[name]["dimension"],
                    "vector_count": len(self.collections[name]["vectors"]),
                    "distance_metric": self.collections[name]["metric"]
                }
            
            async def upsert(
                self, collection: str, records: List[VectorRecord]
            ) -> int:
                if collection not in self.collections:
                    raise ValueError(f"Collection {collection} does not exist")
                self.collections[collection]["vectors"].extend(records)
                return len(records)
            
            async def search(
                self,
                collection: str,
                query_vector: List[float],
                limit: int = 10,
                filters: Optional[Dict[str, Any]] = None,
                score_threshold: Optional[float] = None,
            ) -> List[VectorSearchResult]:
                # Mock search - just return empty results
                return []
            
            async def delete(
                self,
                collection: str,
                ids: Optional[List[str]] = None,
                filters: Optional[Dict[str, Any]] = None,
            ) -> int:
                return 0
            
            async def count(self, collection: str) -> int:
                if collection not in self.collections:
                    raise ValueError(f"Collection {collection} does not exist")
                return len(self.collections[collection]["vectors"])
        
        # Test the mock implementation
        import asyncio
        
        async def test_mock():
            store = MockVectorStore()
            
            # Test initialization
            await store.initialize()
            assert store.initialized
            print("✓ initialize() works")
            
            # Test collection creation
            await store.create_collection("test", dimension=384, distance_metric="cosine")
            assert await store.collection_exists("test")
            print("✓ create_collection() and collection_exists() work")
            
            # Test collection info
            info = await store.get_collection_info("test")
            assert info is not None
            assert info["dimension"] == 384
            print("✓ get_collection_info() works")
            
            # Test upsert
            records = [
                VectorRecord(id="1", vector=[0.1] * 384, payload={"text": "test1"}),
                VectorRecord(id="2", vector=[0.2] * 384, payload={"text": "test2"}),
            ]
            count = await store.upsert("test", records)
            assert count == 2
            print("✓ upsert() works")
            
            # Test count
            total = await store.count("test")
            assert total == 2
            print("✓ count() works")
            
            # Test search
            results = await store.search("test", query_vector=[0.15] * 384, limit=5)
            assert isinstance(results, list)
            print("✓ search() works")
            
            # Test delete
            deleted = await store.delete("test", ids=["1"])
            assert deleted == 0  # Mock returns 0
            print("✓ delete() works")
            
            # Test close
            await store.close()
            assert not store.initialized
            print("✓ close() works")
        
        asyncio.run(test_mock())
        
        print("\n✓ Interface can be successfully implemented")
        return True
        
    except Exception as e:
        print(f"✗ Implementation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_real_implementations():
    """Test that real implementations exist and implement the interface."""
    print("\n" + "=" * 60)
    print("Test 5: Real Implementations")
    print("=" * 60)
    
    try:
        from docvector.vectordb import IVectorStore, ChromaVectorDB, QdrantVectorDB
        
        # Check ChromaDB
        assert issubclass(ChromaVectorDB, IVectorStore)
        print("✓ ChromaVectorDB implements IVectorStore")
        
        # Check Qdrant
        assert issubclass(QdrantVectorDB, IVectorStore)
        print("✓ QdrantVectorDB implements IVectorStore")
        
        # Verify they can be instantiated
        chroma = ChromaVectorDB()
        print(f"✓ ChromaVectorDB can be instantiated: {type(chroma).__name__}")
        
        qdrant = QdrantVectorDB()
        print(f"✓ QdrantVectorDB can be instantiated: {type(qdrant).__name__}")
        
        return True
        
    except Exception as e:
        print(f"✗ Real implementations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_type_hints():
    """Test that type hints are properly defined."""
    print("\n" + "=" * 60)
    print("Test 6: Type Hints")
    print("=" * 60)
    
    try:
        from docvector.vectordb import IVectorStore, VectorRecord, VectorSearchResult
        import inspect
        from typing import get_type_hints
        
        # Check VectorRecord type hints
        record_hints = get_type_hints(VectorRecord)
        assert 'id' in record_hints
        assert 'vector' in record_hints
        assert 'payload' in record_hints
        print("✓ VectorRecord has proper type hints")
        print(f"  - Fields: {list(record_hints.keys())}")
        
        # Check VectorSearchResult type hints
        result_hints = get_type_hints(VectorSearchResult)
        assert 'id' in result_hints
        assert 'score' in result_hints
        assert 'payload' in result_hints
        assert 'vector' in result_hints
        print("✓ VectorSearchResult has proper type hints")
        print(f"  - Fields: {list(result_hints.keys())}")
        
        # Check interface method signatures
        methods_with_hints = []
        for name, method in inspect.getmembers(IVectorStore, predicate=inspect.isfunction):
            if not name.startswith('_'):
                try:
                    hints = get_type_hints(method)
                    if hints:
                        methods_with_hints.append(name)
                except Exception:
                    # Skip methods where type hints cannot be retrieved
                    continue
        
        print(f"✓ {len(methods_with_hints)} methods have type hints")
        
        return True
        
    except Exception as e:
        print(f"✗ Type hints test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("A2: IVectorStore Interface Verification")
    print("=" * 60 + "\n")
    
    tests = [
        ("Imports", test_imports),
        ("Data Classes", test_data_classes),
        ("Interface Structure", test_interface_structure),
        ("Interface Implementation", test_interface_implementation),
        ("Real Implementations", test_real_implementations),
        ("Type Hints", test_type_hints),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The IVectorStore interface is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
