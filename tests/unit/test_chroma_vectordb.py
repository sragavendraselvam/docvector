"""Tests for ChromaDB vector database implementation."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docvector.vectordb import ChromaVectorDB, VectorRecord, VectorSearchResult


# Module-level fixtures
@pytest.fixture
async def temp_chroma_dir():
    """Create temporary directory for ChromaDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
async def vectordb(temp_chroma_dir):
    """Create ChromaDB instance with temporary storage."""
    db = ChromaVectorDB(persist_directory=temp_chroma_dir)
    await db.initialize()
    yield db
    await db.close()


class TestChromaVectorDB:
    """Test ChromaDB vector database implementation."""

    @pytest.mark.asyncio
    async def test_initialize(self, temp_chroma_dir):
        """Test ChromaDB initialization."""
        db = ChromaVectorDB(persist_directory=temp_chroma_dir)
        await db.initialize()

        assert db._client is not None
        assert os.path.exists(temp_chroma_dir)

        await db.close()

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, vectordb):
        """Test that initialize is idempotent."""
        # Initialize again should not raise error
        await vectordb.initialize()
        await vectordb.initialize()
        assert vectordb._client is not None

    @pytest.mark.asyncio
    async def test_create_collection_cosine(self, vectordb):
        """Test creating collection with cosine metric."""
        await vectordb.create_collection(
            name="test_cosine",
            dimension=384,
            distance_metric="cosine"
        )

        exists = await vectordb.collection_exists("test_cosine")
        assert exists is True

        info = await vectordb.get_collection_info("test_cosine")
        assert info is not None
        assert info["name"] == "test_cosine"
        assert info["dimension"] == 384
        assert info["distance_metric"] == "cosine"

    @pytest.mark.asyncio
    async def test_create_collection_euclidean(self, vectordb):
        """Test creating collection with euclidean metric."""
        await vectordb.create_collection(
            name="test_euclidean",
            dimension=128,
            distance_metric="euclidean"
        )

        info = await vectordb.get_collection_info("test_euclidean")
        assert info["distance_metric"] == "euclidean"

    @pytest.mark.asyncio
    async def test_create_collection_dot(self, vectordb):
        """Test creating collection with dot product metric."""
        await vectordb.create_collection(
            name="test_dot",
            dimension=256,
            distance_metric="dot"
        )

        info = await vectordb.get_collection_info("test_dot")
        assert info["distance_metric"] == "dot"

    @pytest.mark.asyncio
    async def test_create_collection_already_exists(self, vectordb):
        """Test creating collection that already exists."""
        await vectordb.create_collection("test_dup", dimension=384)

        with pytest.raises(ValueError, match="already exists"):
            await vectordb.create_collection("test_dup", dimension=384)

    @pytest.mark.asyncio
    async def test_delete_collection(self, vectordb):
        """Test deleting a collection."""
        await vectordb.create_collection("test_delete", dimension=384)
        assert await vectordb.collection_exists("test_delete") is True

        await vectordb.delete_collection("test_delete")
        assert await vectordb.collection_exists("test_delete") is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_collection(self, vectordb):
        """Test deleting collection that doesn't exist."""
        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.delete_collection("nonexistent")

    @pytest.mark.asyncio
    async def test_collection_exists_true(self, vectordb):
        """Test checking if collection exists (true case)."""
        await vectordb.create_collection("test_exists", dimension=384)
        exists = await vectordb.collection_exists("test_exists")
        assert exists is True

    @pytest.mark.asyncio
    async def test_collection_exists_false(self, vectordb):
        """Test checking if collection exists (false case)."""
        exists = await vectordb.collection_exists("does_not_exist")
        assert exists is False

    @pytest.mark.asyncio
    async def test_get_collection_info_nonexistent(self, vectordb):
        """Test getting info for nonexistent collection."""
        info = await vectordb.get_collection_info("nonexistent")
        assert info is None

    @pytest.mark.asyncio
    async def test_upsert_single_record(self, vectordb):
        """Test upserting a single record."""
        await vectordb.create_collection("test_upsert", dimension=3)

        records = [
            VectorRecord(
                id="vec1",
                vector=[0.1, 0.2, 0.3],
                payload={"text": "test document", "source": "test"}
            )
        ]

        count = await vectordb.upsert("test_upsert", records)
        assert count == 1

        total = await vectordb.count("test_upsert")
        assert total == 1

    @pytest.mark.asyncio
    async def test_upsert_multiple_records(self, vectordb):
        """Test upserting multiple records."""
        await vectordb.create_collection("test_batch", dimension=3)

        records = [
            VectorRecord(id=f"vec{i}", vector=[i*0.1, i*0.2, i*0.3], payload={"index": i})
            for i in range(10)
        ]

        count = await vectordb.upsert("test_batch", records)
        assert count == 10

        total = await vectordb.count("test_batch")
        assert total == 10

    @pytest.mark.asyncio
    async def test_upsert_update_existing(self, vectordb):
        """Test that upsert updates existing records."""
        await vectordb.create_collection("test_update", dimension=3)

        # Insert initial record
        records = [VectorRecord(id="vec1", vector=[0.1, 0.2, 0.3], payload={"version": 1})]
        await vectordb.upsert("test_update", records)

        # Update the same record
        records = [VectorRecord(id="vec1", vector=[0.4, 0.5, 0.6], payload={"version": 2})]
        await vectordb.upsert("test_update", records)

        # Should still have only 1 record
        total = await vectordb.count("test_update")
        assert total == 1

    @pytest.mark.asyncio
    async def test_upsert_nonexistent_collection(self, vectordb):
        """Test upserting to nonexistent collection."""
        records = [VectorRecord(id="vec1", vector=[0.1, 0.2, 0.3], payload={})]

        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.upsert("nonexistent", records)

    @pytest.mark.asyncio
    async def test_search_basic(self, vectordb):
        """Test basic vector search."""
        await vectordb.create_collection("test_search", dimension=3)

        # Insert test vectors
        records = [
            VectorRecord(id="vec1", vector=[1.0, 0.0, 0.0], payload={"name": "x-axis"}),
            VectorRecord(id="vec2", vector=[0.0, 1.0, 0.0], payload={"name": "y-axis"}),
            VectorRecord(id="vec3", vector=[0.0, 0.0, 1.0], payload={"name": "z-axis"}),
        ]
        await vectordb.upsert("test_search", records)

        # Search for vector close to x-axis
        results = await vectordb.search(
            collection="test_search",
            query_vector=[0.9, 0.1, 0.0],
            limit=2
        )

        assert len(results) == 2
        assert isinstance(results[0], VectorSearchResult)
        assert results[0].id == "vec1"  # Closest to x-axis
        assert results[0].score > results[1].score  # Best match first

    @pytest.mark.asyncio
    async def test_search_with_limit(self, vectordb):
        """Test search respects limit parameter."""
        await vectordb.create_collection("test_limit", dimension=3)

        # Insert 10 vectors
        records = [
            VectorRecord(id=f"vec{i}", vector=[i*0.1, 0.0, 0.0], payload={"index": i})
            for i in range(10)
        ]
        await vectordb.upsert("test_limit", records)

        # Search with limit=3
        results = await vectordb.search(
            collection="test_limit",
            query_vector=[0.5, 0.0, 0.0],
            limit=3
        )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_with_score_threshold(self, vectordb):
        """Test search with score threshold filtering."""
        await vectordb.create_collection("test_threshold", dimension=3)

        records = [
            VectorRecord(id="vec1", vector=[1.0, 0.0, 0.0], payload={"text": "test1"}),
            VectorRecord(id="vec2", vector=[0.0, 1.0, 0.0], payload={"text": "test2"}),
        ]
        await vectordb.upsert("test_threshold", records)

        # Search with high threshold - should filter out dissimilar results
        results = await vectordb.search(
            collection="test_threshold",
            query_vector=[1.0, 0.0, 0.0],
            limit=10,
            score_threshold=0.8
        )

        # Should only return the very similar vector
        assert len(results) >= 1
        assert all(r.score >= 0.8 for r in results)

    @pytest.mark.asyncio
    async def test_search_with_filters(self, vectordb):
        """Test search with metadata filters."""
        await vectordb.create_collection("test_filter", dimension=3)

        records = [
            VectorRecord(id="vec1", vector=[0.1, 0.2, 0.3], payload={"category": "A", "value": 10}),
            VectorRecord(id="vec2", vector=[0.2, 0.3, 0.4], payload={"category": "B", "value": 20}),
            VectorRecord(id="vec3", vector=[0.3, 0.4, 0.5], payload={"category": "A", "value": 30}),
        ]
        await vectordb.upsert("test_filter", records)

        # Search with category filter
        results = await vectordb.search(
            collection="test_filter",
            query_vector=[0.2, 0.3, 0.4],
            limit=10,
            filters={"category": "A"}
        )

        # Should only return category A results
        assert all(r.payload["category"] == "A" for r in results)

    @pytest.mark.asyncio
    async def test_search_empty_collection(self, vectordb):
        """Test searching in empty collection."""
        await vectordb.create_collection("test_empty", dimension=3)

        results = await vectordb.search(
            collection="test_empty",
            query_vector=[0.1, 0.2, 0.3],
            limit=10
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_search_nonexistent_collection(self, vectordb):
        """Test searching in nonexistent collection."""
        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.search(
                collection="nonexistent",
                query_vector=[0.1, 0.2, 0.3],
                limit=10
            )

    @pytest.mark.asyncio
    async def test_delete_by_ids(self, vectordb):
        """Test deleting vectors by IDs."""
        await vectordb.create_collection("test_delete_ids", dimension=3)

        # Insert test vectors
        records = [
            VectorRecord(id=f"vec{i}", vector=[i*0.1, 0.0, 0.0], payload={"index": i})
            for i in range(5)
        ]
        await vectordb.upsert("test_delete_ids", records)

        # Delete 2 vectors
        deleted = await vectordb.delete("test_delete_ids", ids=["vec0", "vec1"])
        assert deleted == 2

        # Should have 3 remaining
        total = await vectordb.count("test_delete_ids")
        assert total == 3

    @pytest.mark.asyncio
    async def test_delete_by_filter(self, vectordb):
        """Test deleting vectors by metadata filter."""
        await vectordb.create_collection("test_delete_filter", dimension=3)

        records = [
            VectorRecord(id="vec1", vector=[0.1, 0.2, 0.3], payload={"category": "A"}),
            VectorRecord(id="vec2", vector=[0.2, 0.3, 0.4], payload={"category": "B"}),
            VectorRecord(id="vec3", vector=[0.3, 0.4, 0.5], payload={"category": "A"}),
        ]
        await vectordb.upsert("test_delete_filter", records)

        # Delete all category A
        deleted = await vectordb.delete("test_delete_filter", filters={"category": "A"})
        assert deleted == 2

        total = await vectordb.count("test_delete_filter")
        assert total == 1

    @pytest.mark.asyncio
    async def test_delete_no_params(self, vectordb):
        """Test delete raises error when no params provided."""
        await vectordb.create_collection("test_delete_error", dimension=3)

        with pytest.raises(ValueError, match="Either ids or filters must be provided"):
            await vectordb.delete("test_delete_error")

    @pytest.mark.asyncio
    async def test_count_empty_collection(self, vectordb):
        """Test counting empty collection."""
        await vectordb.create_collection("test_count_empty", dimension=3)

        count = await vectordb.count("test_count_empty")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_nonexistent_collection(self, vectordb):
        """Test counting nonexistent collection."""
        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.count("nonexistent")

    @pytest.mark.asyncio
    async def test_distance_to_score_cosine(self, vectordb):
        """Test distance to score conversion for cosine metric."""
        # Distance 0 should give score 1.0
        score = vectordb._distance_to_score(0.0, "cosine")
        assert score == pytest.approx(1.0)

        # Distance 2 should give score 0.0
        score = vectordb._distance_to_score(2.0, "cosine")
        assert score == pytest.approx(0.0)

        # Distance 1 should give score 0.5
        score = vectordb._distance_to_score(1.0, "cosine")
        assert score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_distance_to_score_l2(self, vectordb):
        """Test distance to score conversion for L2 metric."""
        # Distance 0 should give score 1.0
        score = vectordb._distance_to_score(0.0, "l2")
        assert score == pytest.approx(1.0)

        # Distance 1 should give score 0.5
        score = vectordb._distance_to_score(1.0, "l2")
        assert score == pytest.approx(0.5)

        # Higher distance should give lower score
        score = vectordb._distance_to_score(10.0, "l2")
        assert 0.0 < score < 0.1

    @pytest.mark.asyncio
    async def test_persistence(self, temp_chroma_dir):
        """Test that data persists across sessions."""
        collection_name = "test_persist"

        # Create DB, add data, close
        db1 = ChromaVectorDB(persist_directory=temp_chroma_dir)
        await db1.initialize()
        await db1.create_collection(collection_name, dimension=3)

        records = [
            VectorRecord(id="vec1", vector=[0.1, 0.2, 0.3], payload={"text": "test"})
        ]
        await db1.upsert(collection_name, records)
        await db1.close()

        # Create new DB instance with same directory
        db2 = ChromaVectorDB(persist_directory=temp_chroma_dir)
        await db2.initialize()

        # Data should still exist
        exists = await db2.collection_exists(collection_name)
        assert exists is True

        count = await db2.count(collection_name)
        assert count == 1

        await db2.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, vectordb):
        """Test that close is idempotent."""
        await vectordb.close()
        await vectordb.close()  # Should not raise error


class TestChromaMetricMapping:
    """Test ChromaDB distance metric mapping."""

    @pytest.mark.asyncio
    async def test_metric_mapping(self, temp_chroma_dir):
        """Test that standard metrics map correctly to ChromaDB spaces."""
        db = ChromaVectorDB(persist_directory=temp_chroma_dir)
        await db.initialize()

        # Test each metric type
        metrics = {
            "cosine": "cosine",
            "euclidean": "euclidean",
            "dot": "dot"
        }

        for standard, expected in metrics.items():
            collection_name = f"test_{standard}"
            await db.create_collection(collection_name, dimension=128, distance_metric=standard)

            info = await db.get_collection_info(collection_name)
            assert info["distance_metric"] == expected

        await db.close()


class TestChromaEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_large_batch_upsert(self, temp_chroma_dir):
        """Test upserting large batch of vectors."""
        db = ChromaVectorDB(persist_directory=temp_chroma_dir)
        await db.initialize()
        await db.create_collection("test_large", dimension=384)

        # Insert 1000 vectors
        records = [
            VectorRecord(
                id=f"vec{i}",
                vector=[i * 0.001] * 384,
                payload={"index": i}
            )
            for i in range(1000)
        ]

        count = await db.upsert("test_large", records)
        assert count == 1000

        total = await db.count("test_large")
        assert total == 1000

        await db.close()

    @pytest.mark.asyncio
    async def test_high_dimensional_vectors(self, temp_chroma_dir):
        """Test with high-dimensional vectors (1536 like OpenAI)."""
        db = ChromaVectorDB(persist_directory=temp_chroma_dir)
        await db.initialize()
        await db.create_collection("test_high_dim", dimension=1536)

        records = [
            VectorRecord(
                id="vec1",
                vector=[0.001] * 1536,
                payload={"model": "openai"}
            )
        ]

        count = await db.upsert("test_high_dim", records)
        assert count == 1

        results = await db.search(
            collection="test_high_dim",
            query_vector=[0.001] * 1536,
            limit=1
        )

        assert len(results) == 1
        assert results[0].id == "vec1"

        await db.close()
