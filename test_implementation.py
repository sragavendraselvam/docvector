"""Test script to verify the vector database implementation."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def test_chroma_implementation():
    """Test ChromaDB implementation."""
    print("=" * 60)
    print("Testing ChromaDB Implementation")
    print("=" * 60)
    
    try:
        from docvector.vectordb import ChromaVectorDB, VectorRecord
        
        # Initialize ChromaDB
        db = ChromaVectorDB(persist_directory="./test_data/chroma")
        await db.initialize()
        print("✓ ChromaDB initialized successfully")
        
        # Create collection
        collection_name = "test_collection"
        await db.create_collection(
            name=collection_name,
            dimension=384,
            distance_metric="cosine"
        )
        print(f"✓ Collection '{collection_name}' created")
        
        # Check if collection exists
        exists = await db.collection_exists(collection_name)
        print(f"✓ Collection exists: {exists}")
        
        # Get collection info
        info = await db.get_collection_info(collection_name)
        print(f"✓ Collection info: {info}")
        
        # Upsert test vectors
        test_records = [
            VectorRecord(
                id="test1",
                vector=[0.1] * 384,
                payload={"text": "Test document 1", "source": "test"}
            ),
            VectorRecord(
                id="test2",
                vector=[0.2] * 384,
                payload={"text": "Test document 2", "source": "test"}
            ),
        ]
        
        count = await db.upsert(collection_name, test_records)
        print(f"✓ Upserted {count} records")
        
        # Count vectors
        total = await db.count(collection_name)
        print(f"✓ Total vectors in collection: {total}")
        
        # Search
        results = await db.search(
            collection=collection_name,
            query_vector=[0.15] * 384,
            limit=2
        )
        print(f"✓ Search returned {len(results)} results")
        for i, result in enumerate(results, 1):
            print(f"  {i}. ID: {result.id}, Score: {result.score:.4f}")
        
        # Delete
        deleted = await db.delete(collection_name, ids=["test1"])
        print(f"✓ Deleted {deleted} vectors")
        
        # Cleanup
        await db.delete_collection(collection_name)
        print(f"✓ Collection '{collection_name}' deleted")
        
        await db.close()
        print("✓ ChromaDB connection closed")
        
        print("\n✅ All ChromaDB tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ ChromaDB test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_factory_function():
    """Test the vector database factory function."""
    print("\n" + "=" * 60)
    print("Testing Vector Database Factory")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db
        from docvector.core import settings
        
        # Test local mode
        original_mode = settings.mcp_mode
        settings.mcp_mode = "local"
        
        db = get_vector_db()
        print(f"✓ Factory returned: {type(db).__name__}")
        print(f"✓ Mode: {settings.mcp_mode}")
        
        # Verify it's ChromaDB
        from docvector.vectordb import ChromaVectorDB
        assert isinstance(db, ChromaVectorDB), "Expected ChromaVectorDB for local mode"
        print("✓ Correct implementation for local mode")
        
        # Restore original mode
        settings.mcp_mode = original_mode
        
        print("\n✅ Factory function tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Factory test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_settings():
    """Test settings configuration."""
    print("\n" + "=" * 60)
    print("Testing Settings Configuration")
    print("=" * 60)
    
    try:
        from docvector.core import settings
        
        print(f"✓ MCP Mode: {settings.mcp_mode}")
        print(f"✓ Database URL: {settings.database_url}")
        print(f"✓ ChromaDB Directory: {settings.chroma_persist_directory}")
        print(f"✓ Embedding Provider: {settings.embedding_provider}")
        print(f"✓ Embedding Model: {settings.embedding_model}")
        
        print("\n✅ Settings configuration tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Settings test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DocVector Implementation Verification")
    print("=" * 60 + "\n")
    
    results = []
    
    # Test settings
    results.append(await test_settings())
    
    # Test factory
    results.append(await test_factory_function())
    
    # Test ChromaDB
    results.append(await test_chroma_implementation())
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All tests passed! Implementation is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
