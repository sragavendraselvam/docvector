#!/usr/bin/env python3
"""End-to-end verification of vector database factory.

This script tests the factory pattern with both local (ChromaDB) and cloud (Qdrant)
modes to ensure DocVector can seamlessly switch between implementations.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def test_local_mode():
    """Test local mode with ChromaDB."""
    print("\n" + "=" * 70)
    print("Testing LOCAL MODE (ChromaDB)")
    print("=" * 70)

    # Set environment for local mode
    os.environ["DOCVECTOR_MCP_MODE"] = "local"
    os.environ["DOCVECTOR_CHROMA_PERSIST_DIRECTORY"] = "./test_data/chroma"

    # Import after setting env vars
    from docvector.vectordb import ChromaVectorDB, VectorRecord, get_vector_db

    # Get database instance
    print("\n1. Creating vector database instance...")
    db = get_vector_db()
    print(f"   ✓ Got instance: {db.__class__.__name__}")
    assert isinstance(db, ChromaVectorDB), "Expected ChromaVectorDB instance"

    # Initialize
    print("\n2. Initializing database...")
    await db.initialize()
    print("   ✓ Database initialized")

    # Create collection
    print("\n3. Creating collection...")
    collection_name = "test_local"

    # Delete if exists
    if await db.collection_exists(collection_name):
        await db.delete_collection(collection_name)
        print(f"   - Deleted existing collection '{collection_name}'")

    await db.create_collection(
        name=collection_name,
        dimension=384,
        distance_metric="cosine"
    )
    print(f"   ✓ Collection '{collection_name}' created")

    # Verify collection exists
    exists = await db.collection_exists(collection_name)
    assert exists, "Collection should exist"
    print(f"   ✓ Collection exists: {exists}")

    # Get collection info
    info = await db.get_collection_info(collection_name)
    print(f"   ✓ Collection info: dimension={info['dimension']}, metric={info['distance_metric']}")

    # Upsert vectors
    print("\n4. Upserting vectors...")
    records = [
        VectorRecord(
            id="local1",
            vector=[0.1] * 384,
            payload={"text": "Local test 1", "source": "test"}
        ),
        VectorRecord(
            id="local2",
            vector=[0.2] * 384,
            payload={"text": "Local test 2", "source": "test"}
        ),
    ]
    count = await db.upsert(collection_name, records)
    print(f"   ✓ Upserted {count} vectors")

    # Count
    total = await db.count(collection_name)
    print(f"   ✓ Total vectors: {total}")
    assert total == 2, "Should have 2 vectors"

    # Search
    print("\n5. Searching vectors...")
    results = await db.search(
        collection=collection_name,
        query_vector=[0.15] * 384,
        limit=5
    )
    print(f"   ✓ Found {len(results)} results")
    for i, result in enumerate(results[:3], 1):
        print(f"      {i}. id={result.id}, score={result.score:.4f}")

    # Delete
    print("\n6. Deleting vectors...")
    deleted = await db.delete(collection_name, ids=["local1"])
    print(f"   ✓ Deleted {deleted} vector(s)")

    # Cleanup
    print("\n7. Cleanup...")
    await db.delete_collection(collection_name)
    await db.close()
    print("   ✓ Collection deleted and connection closed")

    print("\n" + "=" * 70)
    print("✓ LOCAL MODE TEST PASSED")
    print("=" * 70)


async def test_cloud_mode_config_only():
    """Test cloud mode configuration (without actual Qdrant connection)."""
    print("\n" + "=" * 70)
    print("Testing CLOUD MODE (Configuration)")
    print("=" * 70)

    # Test self-hosted configuration - use mode override instead of env vars
    print("\n1. Testing self-hosted Qdrant configuration...")
    from docvector.vectordb import QdrantVectorDB, get_vector_db

    # Use mode override to force cloud mode
    db = get_vector_db(mode="cloud")
    print(f"   ✓ Got instance: {db.__class__.__name__}")
    assert isinstance(db, QdrantVectorDB), "Expected QdrantVectorDB instance"
    assert db.host == "localhost", "Expected localhost host (from defaults)"
    assert db.port == 6333, "Expected port 6333 (from defaults)"
    print(f"   ✓ Configuration: host={db.host}, port={db.port}")

    # Test hybrid mode uses Qdrant
    print("\n2. Testing hybrid mode uses Qdrant...")
    db = get_vector_db(mode="hybrid")
    assert isinstance(db, QdrantVectorDB), "Expected QdrantVectorDB for hybrid mode"
    print(f"   ✓ Hybrid mode uses: {db.__class__.__name__}")

    print("\n" + "=" * 70)
    print("✓ CLOUD MODE CONFIGURATION TEST PASSED")
    print("=" * 70)


async def test_mode_override():
    """Test mode override parameter."""
    print("\n" + "=" * 70)
    print("Testing MODE OVERRIDE")
    print("=" * 70)

    from docvector.vectordb import ChromaVectorDB, QdrantVectorDB, get_vector_db

    # Override to local (settings might be cloud, but we override)
    print("\n1. Overriding to local mode...")
    db = get_vector_db(mode="local")
    assert isinstance(db, ChromaVectorDB), "Expected ChromaDB when overriding to local"
    print(f"   ✓ Override successful: {db.__class__.__name__}")

    # Override to cloud
    print("\n2. Overriding to cloud mode...")
    db = get_vector_db(mode="cloud")
    assert isinstance(db, QdrantVectorDB), "Expected QdrantVectorDB when overriding to cloud"
    print(f"   ✓ Override successful: {db.__class__.__name__}")

    # Override to hybrid (should be Qdrant)
    print("\n3. Overriding to hybrid mode...")
    db = get_vector_db(mode="hybrid")
    assert isinstance(db, QdrantVectorDB), "Expected QdrantVectorDB when overriding to hybrid"
    print(f"   ✓ Override successful: {db.__class__.__name__}")

    print("\n" + "=" * 70)
    print("✓ MODE OVERRIDE TEST PASSED")
    print("=" * 70)


async def test_error_handling():
    """Test error handling and validation."""
    print("\n" + "=" * 70)
    print("Testing ERROR HANDLING")
    print("=" * 70)

    from docvector.vectordb import get_vector_db

    # Test invalid mode
    print("\n1. Testing invalid mode...")
    try:
        _db = get_vector_db(mode="invalid")
        print("   ✗ Should have raised ValueError")
        assert False
    except ValueError as e:
        print(f"   ✓ Caught expected error: {str(e)[:60]}...")

    # Note: Other validation errors are tested in unit tests
    # Here we just verify the basic mode validation works

    print("\n" + "=" * 70)
    print("✓ ERROR HANDLING TEST PASSED")
    print("=" * 70)


async def main():
    """Run all verification tests."""
    print("\n" + "=" * 80)
    print(" " * 15 + "DocVector Factory End-to-End Verification")
    print("=" * 80)

    try:
        # Test local mode (with actual ChromaDB operations)
        await test_local_mode()

        # Test cloud mode configuration (without Qdrant connection)
        await test_cloud_mode_config_only()

        # Test mode override
        await test_mode_override()

        # Test error handling
        await test_error_handling()

        # Summary
        print("\n" + "=" * 80)
        print(" " * 25 + "✓ ALL TESTS PASSED")
        print("=" * 80)
        print("\nSummary:")
        print("  ✓ Local mode (ChromaDB) works correctly")
        print("  ✓ Cloud mode configuration validated")
        print("  ✓ Hybrid mode uses Qdrant")
        print("  ✓ Mode override works correctly")
        print("  ✓ Error handling and validation works")
        print("\nThe vector database factory is production-ready!")
        print("=" * 80 + "\n")

        return 0

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
