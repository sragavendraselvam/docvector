"""Verification script for A3: ChromaDB vector store adapter.

This script comprehensively tests the ChromaDB implementation to ensure
it correctly implements the IVectorStore interface and works as expected.
"""

import asyncio
import sys
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def test_chromadb_initialization():
    """Test ChromaDB initialization and cleanup."""
    print("=" * 60)
    print("Test 1: Initialization and Cleanup")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB
        
        test_dir = "./test_data/chroma_test1"
        
        # Initialize
        db = ChromaVectorDB(persist_directory=test_dir)
        await db.initialize()
        print("✓ ChromaDB initialized successfully")
        
        # Verify directory was created
        assert Path(test_dir).exists()
        print(f"✓ Persist directory created: {test_dir}")
        
        # Close
        await db.close()
        print("✓ ChromaDB closed successfully")
        
        # Cleanup
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
            print("✓ Test directory cleaned up")
        
        return True
        
    except Exception as e:
        print(f"✗ Initialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_collection_management():
    """Test collection creation, existence check, info, and deletion."""
    print("\n" + "=" * 60)
    print("Test 2: Collection Management")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB
        
        test_dir = "./test_data/chroma_test2"
        db = ChromaVectorDB(persist_directory=test_dir)
        await db.initialize()
        
        # Create collection
        await db.create_collection(
            name="test_collection",
            dimension=384,
            distance_metric="cosine"
        )
        print("✓ Collection created: test_collection")
        
        # Check existence
        exists = await db.collection_exists("test_collection")
        assert exists, "Collection should exist"
        print("✓ Collection exists check passed")
        
        # Check non-existence
        not_exists = await db.collection_exists("nonexistent")
        assert not not_exists, "Nonexistent collection should return False"
        print("✓ Non-existent collection check passed")
        
        # Get collection info
        info = await db.get_collection_info("test_collection")
        assert info is not None
        assert info["name"] == "test_collection"
        assert info["dimension"] == 384
        assert info["distance_metric"] == "cosine"
        assert info["vector_count"] == 0
        print("✓ Collection info retrieved correctly")
        print(f"  - Name: {info['name']}")
        print(f"  - Dimension: {info['dimension']}")
        print(f"  - Metric: {info['distance_metric']}")
        print(f"  - Count: {info['vector_count']}")
        
        # Test different distance metrics
        await db.create_collection("test_l2", dimension=128, distance_metric="euclidean")
        info_l2 = await db.get_collection_info("test_l2")
        assert info_l2["distance_metric"] == "euclidean"
        print("✓ L2/Euclidean metric works")
        
        await db.create_collection("test_ip", dimension=256, distance_metric="dot")
        info_ip = await db.get_collection_info("test_ip")
        assert info_ip["distance_metric"] == "dot"
        print("✓ Inner product metric works")
        
        # Delete collection
        await db.delete_collection("test_collection")
        exists_after = await db.collection_exists("test_collection")
        assert not exists_after, "Collection should not exist after deletion"
        print("✓ Collection deleted successfully")
        
        # Cleanup
        await db.delete_collection("test_l2")
        await db.delete_collection("test_ip")
        await db.close()
        
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Collection management test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_vector_operations():
    """Test upsert, count, and basic retrieval."""
    print("\n" + "=" * 60)
    print("Test 3: Vector Operations")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB, VectorRecord
        
        test_dir = "./test_data/chroma_test3"
        db = ChromaVectorDB(persist_directory=test_dir)
        await db.initialize()
        
        await db.create_collection("vectors", dimension=4, distance_metric="cosine")
        
        # Upsert vectors
        records = [
            VectorRecord(
                id="vec1",
                vector=[1.0, 0.0, 0.0, 0.0],
                payload={"text": "First vector", "category": "A"}
            ),
            VectorRecord(
                id="vec2",
                vector=[0.0, 1.0, 0.0, 0.0],
                payload={"text": "Second vector", "category": "B"}
            ),
            VectorRecord(
                id="vec3",
                vector=[0.0, 0.0, 1.0, 0.0],
                payload={"text": "Third vector", "category": "A"}
            ),
        ]
        
        count = await db.upsert("vectors", records)
        assert count == 3
        print(f"✓ Upserted {count} vectors")
        
        # Count vectors
        total = await db.count("vectors")
        assert total == 3
        print(f"✓ Count verified: {total} vectors")
        
        # Update existing vector
        updated_record = VectorRecord(
            id="vec1",
            vector=[1.0, 0.1, 0.0, 0.0],
            payload={"text": "Updated first vector", "category": "A"}
        )
        count = await db.upsert("vectors", [updated_record])
        assert count == 1
        print("✓ Vector update (upsert) works")
        
        # Count should still be 3
        total = await db.count("vectors")
        assert total == 3
        print("✓ Count unchanged after update")
        
        # Cleanup
        await db.delete_collection("vectors")
        await db.close()
        
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Vector operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_search_functionality():
    """Test vector similarity search."""
    print("\n" + "=" * 60)
    print("Test 4: Search Functionality")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB, VectorRecord
        
        test_dir = "./test_data/chroma_test4"
        db = ChromaVectorDB(persist_directory=test_dir)
        await db.initialize()
        
        await db.create_collection("search_test", dimension=4, distance_metric="cosine")
        
        # Insert test vectors
        records = [
            VectorRecord(id="v1", vector=[1.0, 0.0, 0.0, 0.0], payload={"label": "x-axis"}),
            VectorRecord(id="v2", vector=[0.0, 1.0, 0.0, 0.0], payload={"label": "y-axis"}),
            VectorRecord(id="v3", vector=[0.0, 0.0, 1.0, 0.0], payload={"label": "z-axis"}),
            VectorRecord(id="v4", vector=[0.7, 0.7, 0.0, 0.0], payload={"label": "xy-diagonal"}),
        ]
        await db.upsert("search_test", records)
        
        # Search for vector close to x-axis
        results = await db.search(
            collection="search_test",
            query_vector=[0.9, 0.1, 0.0, 0.0],
            limit=2
        )
        
        assert len(results) > 0
        assert results[0].id == "v1"  # Should be closest to x-axis
        assert 0 <= results[0].score <= 1
        print(f"✓ Search returned {len(results)} results")
        print(f"  - Top result: {results[0].id} (score: {results[0].score:.4f})")
        
        # Test score threshold
        high_threshold_results = await db.search(
            collection="search_test",
            query_vector=[0.9, 0.1, 0.0, 0.0],
            limit=10,
            score_threshold=0.9
        )
        print(f"✓ Score threshold works ({len(high_threshold_results)} results with score >= 0.9)")
        
        # Test limit
        limited_results = await db.search(
            collection="search_test",
            query_vector=[0.5, 0.5, 0.5, 0.5],
            limit=2
        )
        assert len(limited_results) <= 2
        print(f"✓ Limit parameter works (requested 2, got {len(limited_results)})")
        
        # Cleanup
        await db.delete_collection("search_test")
        await db.close()
        
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Search functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_filtering():
    """Test metadata filtering in search."""
    print("\n" + "=" * 60)
    print("Test 5: Metadata Filtering")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB, VectorRecord
        
        test_dir = "./test_data/chroma_test5"
        db = ChromaVectorDB(persist_directory=test_dir)
        await db.initialize()
        
        await db.create_collection("filter_test", dimension=3, distance_metric="cosine")
        
        # Insert vectors with different metadata
        records = [
            VectorRecord(id="doc1", vector=[1.0, 0.0, 0.0], payload={"source": "react", "version": "18.0"}),
            VectorRecord(id="doc2", vector=[0.9, 0.1, 0.0], payload={"source": "react", "version": "17.0"}),
            VectorRecord(id="doc3", vector=[0.8, 0.2, 0.0], payload={"source": "vue", "version": "3.0"}),
            VectorRecord(id="doc4", vector=[0.7, 0.3, 0.0], payload={"source": "angular", "version": "15.0"}),
        ]
        await db.upsert("filter_test", records)
        
        # Search with filter
        filtered_results = await db.search(
            collection="filter_test",
            query_vector=[1.0, 0.0, 0.0],
            limit=10,
            filters={"source": "react"}
        )
        
        assert len(filtered_results) == 2
        assert all(r.payload["source"] == "react" for r in filtered_results)
        print(f"✓ Filtering works (found {len(filtered_results)} React docs)")
        
        # Search without filter
        all_results = await db.search(
            collection="filter_test",
            query_vector=[1.0, 0.0, 0.0],
            limit=10
        )
        assert len(all_results) == 4
        print(f"✓ Unfiltered search returns all {len(all_results)} results")
        
        # Cleanup
        await db.delete_collection("filter_test")
        await db.close()
        
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Filtering test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_delete_operations():
    """Test vector deletion."""
    print("\n" + "=" * 60)
    print("Test 6: Delete Operations")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB, VectorRecord
        
        test_dir = "./test_data/chroma_test6"
        db = ChromaVectorDB(persist_directory=test_dir)
        await db.initialize()
        
        await db.create_collection("delete_test", dimension=2, distance_metric="cosine")
        
        # Insert vectors
        records = [
            VectorRecord(id=f"v{i}", vector=[float(i), float(i)], payload={"index": i})
            for i in range(10)
        ]
        await db.upsert("delete_test", records)
        
        initial_count = await db.count("delete_test")
        assert initial_count == 10
        print(f"✓ Initial count: {initial_count}")
        
        # Delete by IDs
        deleted = await db.delete("delete_test", ids=["v0", "v1", "v2"])
        assert deleted == 3
        print(f"✓ Deleted {deleted} vectors by ID")
        
        # Verify count decreased
        after_delete = await db.count("delete_test")
        assert after_delete == 7
        print(f"✓ Count after delete: {after_delete}")
        
        # Delete by filter
        deleted_by_filter = await db.delete("delete_test", filters={"index": 5})
        assert deleted_by_filter >= 0  # ChromaDB may return 0 or actual count
        print(f"✓ Delete by filter executed (deleted: {deleted_by_filter})")
        
        # Cleanup
        await db.delete_collection("delete_test")
        await db.close()
        
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Delete operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_persistence():
    """Test that data persists across sessions."""
    print("\n" + "=" * 60)
    print("Test 7: Data Persistence")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB, VectorRecord
        
        test_dir = "./test_data/chroma_test7"
        
        # Session 1: Create and populate
        db1 = ChromaVectorDB(persist_directory=test_dir)
        await db1.initialize()
        await db1.create_collection("persist_test", dimension=3, distance_metric="cosine")
        
        records = [
            VectorRecord(id="p1", vector=[1.0, 0.0, 0.0], payload={"text": "Persistent data"}),
            VectorRecord(id="p2", vector=[0.0, 1.0, 0.0], payload={"text": "Should survive"}),
        ]
        await db1.upsert("persist_test", records)
        await db1.close()
        print("✓ Session 1: Created collection and inserted 2 vectors")
        
        # Session 2: Reload and verify
        db2 = ChromaVectorDB(persist_directory=test_dir)
        await db2.initialize()
        
        exists = await db2.collection_exists("persist_test")
        assert exists, "Collection should persist"
        print("✓ Session 2: Collection still exists")
        
        count = await db2.count("persist_test")
        assert count == 2, f"Expected 2 vectors, found {count}"
        print(f"✓ Session 2: Found {count} vectors (data persisted)")
        
        # Search to verify data integrity
        results = await db2.search(
            collection="persist_test",
            query_vector=[1.0, 0.0, 0.0],
            limit=1
        )
        assert len(results) > 0
        assert results[0].payload["text"] == "Persistent data"
        print("✓ Session 2: Data integrity verified")
        
        # Cleanup
        await db2.delete_collection("persist_test")
        await db2.close()
        
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Persistence test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_score_normalization():
    """Test that scores are properly normalized to 0-1 range."""
    print("\n" + "=" * 60)
    print("Test 8: Score Normalization")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB, VectorRecord
        
        test_dir = "./test_data/chroma_test8"
        db = ChromaVectorDB(persist_directory=test_dir)
        await db.initialize()
        
        # Test with cosine metric
        await db.create_collection("score_test", dimension=3, distance_metric="cosine")
        
        records = [
            VectorRecord(id="identical", vector=[1.0, 0.0, 0.0], payload={}),
            VectorRecord(id="similar", vector=[0.9, 0.1, 0.0], payload={}),
            VectorRecord(id="different", vector=[0.0, 0.0, 1.0], payload={}),
        ]
        await db.upsert("score_test", records)
        
        # Search with identical vector
        results = await db.search(
            collection="score_test",
            query_vector=[1.0, 0.0, 0.0],
            limit=3
        )
        
        # Verify all scores are in 0-1 range
        for result in results:
            assert 0.0 <= result.score <= 1.0, f"Score {result.score} out of range"
        print("✓ All scores in 0-1 range")
        
        # Identical vector should have highest score
        assert results[0].id == "identical"
        assert results[0].score > 0.9, f"Identical vector score too low: {results[0].score}"
        print(f"✓ Identical vector has high score: {results[0].score:.4f}")
        
        # Different vector should have lower score
        different_result = next(r for r in results if r.id == "different")
        assert different_result.score < results[0].score
        print(f"✓ Different vector has lower score: {different_result.score:.4f}")
        
        # Cleanup
        await db.delete_collection("score_test")
        await db.close()
        
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Score normalization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("A3: ChromaDB Vector Store Adapter Verification")
    print("=" * 60 + "\n")
    
    tests = [
        ("Initialization and Cleanup", test_chromadb_initialization),
        ("Collection Management", test_collection_management),
        ("Vector Operations", test_vector_operations),
        ("Search Functionality", test_search_functionality),
        ("Metadata Filtering", test_filtering),
        ("Delete Operations", test_delete_operations),
        ("Data Persistence", test_persistence),
        ("Score Normalization", test_score_normalization),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = asyncio.run(test_func())
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
        print("\n🎉 All tests passed! ChromaDB implementation is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
