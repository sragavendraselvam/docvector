"""Tests for Qdrant vector database implementation."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docvector.vectordb import QdrantVectorDB, VectorRecord, VectorSearchResult


# Module-level fixtures
@pytest.fixture
def mock_qdrant_client():
    """Create a mock AsyncQdrantClient."""
    client = AsyncMock()

    # Mock collection info
    collection_info = MagicMock()
    collection_info.points_count = 0
    collection_info.config.params.vectors = MagicMock()
    collection_info.config.params.vectors.size = 384
    collection_info.config.params.vectors.distance = "Distance.COSINE"

    client.get_collection.return_value = collection_info
    client.get_collections.return_value = MagicMock(collections=[])

    # Mock count
    count_result = MagicMock()
    count_result.count = 0
    client.count.return_value = count_result

    # Mock upsert
    upsert_result = MagicMock()
    from qdrant_client import models
    upsert_result.status = models.UpdateStatus.COMPLETED
    client.upsert.return_value = upsert_result

    # Mock search/query
    query_result = MagicMock()
    query_result.points = []
    client.query_points.return_value = query_result

    return client


@pytest.fixture
async def vectordb(mock_qdrant_client):
    """Create QdrantVectorDB instance with mocked client."""
    db = QdrantVectorDB(host="localhost", port=6333)

    # Patch the AsyncQdrantClient
    with patch("docvector.vectordb.qdrant_client.AsyncQdrantClient", return_value=mock_qdrant_client):
        await db.initialize()

    # Replace with our mock
    db.client = mock_qdrant_client

    yield db

    await db.close()


class TestQdrantVectorDB:
    """Test Qdrant vector database implementation."""

    @pytest.mark.asyncio
    async def test_initialize_local(self, mock_qdrant_client):
        """Test Qdrant initialization for local deployment."""
        db = QdrantVectorDB(host="localhost", port=6333)

        with patch("docvector.vectordb.qdrant_client.AsyncQdrantClient", return_value=mock_qdrant_client) as mock_class:
            await db.initialize()

            # Verify AsyncQdrantClient was called with correct args
            mock_class.assert_called_once_with(host="localhost", port=6333)
            assert db.client is not None

    @pytest.mark.asyncio
    async def test_initialize_grpc(self, mock_qdrant_client):
        """Test Qdrant initialization with gRPC."""
        db = QdrantVectorDB(host="localhost", grpc_port=6334, use_grpc=True)

        with patch("docvector.vectordb.qdrant_client.AsyncQdrantClient", return_value=mock_qdrant_client) as mock_class:
            await db.initialize()

            mock_class.assert_called_once_with(host="localhost", grpc_port=6334, prefer_grpc=True)

    @pytest.mark.asyncio
    async def test_initialize_cloud(self, mock_qdrant_client):
        """Test Qdrant initialization for cloud deployment."""
        db = QdrantVectorDB(url="https://example.qdrant.cloud", api_key="test-key")

        with patch("docvector.vectordb.qdrant_client.AsyncQdrantClient", return_value=mock_qdrant_client) as mock_class:
            await db.initialize()

            mock_class.assert_called_once_with(url="https://example.qdrant.cloud", api_key="test-key")

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, vectordb):
        """Test that initialize is idempotent."""
        client_ref = vectordb.client
        await vectordb.initialize()
        await vectordb.initialize()
        assert vectordb.client is client_ref

    @pytest.mark.asyncio
    async def test_close(self, vectordb):
        """Test closing connection."""
        await vectordb.close()
        assert vectordb.client is None

    @pytest.mark.asyncio
    async def test_create_collection_cosine(self, vectordb, mock_qdrant_client):
        """Test creating collection with cosine metric."""
        from qdrant_client import models

        await vectordb.create_collection(
            name="test_cosine",
            dimension=384,
            distance_metric="cosine"
        )

        # Verify create_collection was called
        mock_qdrant_client.create_collection.assert_called_once()
        call_args = mock_qdrant_client.create_collection.call_args

        assert call_args.kwargs["collection_name"] == "test_cosine"
        assert call_args.kwargs["vectors_config"].size == 384
        assert call_args.kwargs["vectors_config"].distance == models.Distance.COSINE

    @pytest.mark.asyncio
    async def test_create_collection_euclidean(self, vectordb, mock_qdrant_client):
        """Test creating collection with euclidean metric."""
        from qdrant_client import models

        await vectordb.create_collection(
            name="test_euclidean",
            dimension=128,
            distance_metric="euclidean"
        )

        call_args = mock_qdrant_client.create_collection.call_args
        assert call_args.kwargs["vectors_config"].distance == models.Distance.EUCLID

    @pytest.mark.asyncio
    async def test_create_collection_dot(self, vectordb, mock_qdrant_client):
        """Test creating collection with dot product metric."""
        from qdrant_client import models

        await vectordb.create_collection(
            name="test_dot",
            dimension=256,
            distance_metric="dot"
        )

        call_args = mock_qdrant_client.create_collection.call_args
        assert call_args.kwargs["vectors_config"].distance == models.Distance.DOT

    @pytest.mark.asyncio
    async def test_create_collection_already_exists(self, vectordb, mock_qdrant_client):
        """Test creating collection that already exists."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        # Mock 409 Conflict response
        error = UnexpectedResponse(
            status_code=409,
            reason_phrase="already exists",
            content=b"already exists",
            headers={}
        )
        mock_qdrant_client.create_collection.side_effect = error

        with pytest.raises(ValueError, match="already exists"):
            await vectordb.create_collection("test_dup", dimension=384)

    @pytest.mark.asyncio
    async def test_delete_collection(self, vectordb, mock_qdrant_client):
        """Test deleting a collection."""
        await vectordb.delete_collection("test_delete")

        mock_qdrant_client.delete_collection.assert_called_once_with(collection_name="test_delete")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_collection(self, vectordb, mock_qdrant_client):
        """Test deleting collection that doesn't exist."""
        mock_qdrant_client.delete_collection.side_effect = Exception("Not found")

        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.delete_collection("nonexistent")

    @pytest.mark.asyncio
    async def test_collection_exists_true(self, vectordb, mock_qdrant_client):
        """Test checking if collection exists (true case)."""
        mock_qdrant_client.get_collection.return_value = MagicMock()

        exists = await vectordb.collection_exists("test_exists")
        assert exists is True

    @pytest.mark.asyncio
    async def test_collection_exists_false(self, vectordb, mock_qdrant_client):
        """Test checking if collection exists (false case)."""
        mock_qdrant_client.get_collection.side_effect = Exception("Not found")

        exists = await vectordb.collection_exists("does_not_exist")
        assert exists is False

    @pytest.mark.asyncio
    async def test_get_collection_info(self, vectordb, mock_qdrant_client):
        """Test getting collection info."""
        from qdrant_client import models

        # Setup mock response
        info = MagicMock()
        info.points_count = 100
        info.config.params.vectors = models.VectorParams(size=384, distance=models.Distance.COSINE)
        mock_qdrant_client.get_collection.return_value = info

        result = await vectordb.get_collection_info("test")

        assert result is not None
        assert result["name"] == "test"
        assert result["dimension"] == 384
        assert result["vector_count"] == 100
        assert "distance_metric" in result

    @pytest.mark.asyncio
    async def test_get_collection_info_nonexistent(self, vectordb, mock_qdrant_client):
        """Test getting info for nonexistent collection."""
        mock_qdrant_client.get_collection.side_effect = Exception("Not found")

        info = await vectordb.get_collection_info("nonexistent")
        assert info is None

    @pytest.mark.asyncio
    async def test_upsert_single_record(self, vectordb, mock_qdrant_client):
        """Test upserting a single record."""
        records = [
            VectorRecord(
                id="vec1",
                vector=[0.1, 0.2, 0.3],
                payload={"text": "test document"}
            )
        ]

        count = await vectordb.upsert("test_collection", records)
        assert count == 1

        # Verify upsert was called
        mock_qdrant_client.upsert.assert_called_once()
        call_args = mock_qdrant_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == "test_collection"
        assert len(call_args.kwargs["points"]) == 1

    @pytest.mark.asyncio
    async def test_upsert_multiple_records(self, vectordb, mock_qdrant_client):
        """Test upserting multiple records."""
        records = [
            VectorRecord(id=f"vec{i}", vector=[i*0.1] * 3, payload={"index": i})
            for i in range(10)
        ]

        count = await vectordb.upsert("test_batch", records)
        assert count == 10

        call_args = mock_qdrant_client.upsert.call_args
        assert len(call_args.kwargs["points"]) == 10

    @pytest.mark.asyncio
    async def test_upsert_empty(self, vectordb, mock_qdrant_client):
        """Test upserting empty list."""
        count = await vectordb.upsert("test", [])
        assert count == 0

        # Should not call upsert for empty records
        mock_qdrant_client.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_nonexistent_collection(self, vectordb, mock_qdrant_client):
        """Test upserting to nonexistent collection."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        error = UnexpectedResponse(
            status_code=404,
            reason_phrase="not found",
            content=b"not found",
            headers={}
        )
        mock_qdrant_client.upsert.side_effect = error

        records = [VectorRecord(id="vec1", vector=[0.1, 0.2, 0.3], payload={})]

        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.upsert("nonexistent", records)

    @pytest.mark.asyncio
    async def test_search_basic(self, vectordb, mock_qdrant_client):
        """Test basic vector search."""
        # Setup mock response
        result1 = MagicMock()
        result1.id = "vec1"
        result1.score = 0.95
        result1.payload = {"name": "test1"}

        result2 = MagicMock()
        result2.id = "vec2"
        result2.score = 0.85
        result2.payload = {"name": "test2"}

        query_result = MagicMock()
        query_result.points = [result1, result2]
        mock_qdrant_client.query_points.return_value = query_result

        results = await vectordb.search(
            collection="test_search",
            query_vector=[0.1, 0.2, 0.3],
            limit=10
        )

        assert len(results) == 2
        assert isinstance(results[0], VectorSearchResult)
        assert results[0].id == "vec1"
        assert results[0].score == 0.95
        assert results[0].payload == {"name": "test1"}

    @pytest.mark.asyncio
    async def test_search_with_limit(self, vectordb, mock_qdrant_client):
        """Test search respects limit parameter."""
        query_result = MagicMock()
        query_result.points = []
        mock_qdrant_client.query_points.return_value = query_result

        await vectordb.search(
            collection="test_limit",
            query_vector=[0.1, 0.2, 0.3],
            limit=5
        )

        call_args = mock_qdrant_client.query_points.call_args
        assert call_args.kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_search_with_score_threshold(self, vectordb, mock_qdrant_client):
        """Test search with score threshold filtering."""
        query_result = MagicMock()
        query_result.points = []
        mock_qdrant_client.query_points.return_value = query_result

        await vectordb.search(
            collection="test_threshold",
            query_vector=[0.1, 0.2, 0.3],
            limit=10,
            score_threshold=0.8
        )

        call_args = mock_qdrant_client.query_points.call_args
        assert call_args.kwargs["score_threshold"] == 0.8

    @pytest.mark.asyncio
    async def test_search_with_filters(self, vectordb, mock_qdrant_client):
        """Test search with metadata filters."""
        query_result = MagicMock()
        query_result.points = []
        mock_qdrant_client.query_points.return_value = query_result

        await vectordb.search(
            collection="test_filter",
            query_vector=[0.1, 0.2, 0.3],
            limit=10,
            filters={"category": "A"}
        )

        # Verify filter was built and passed
        call_args = mock_qdrant_client.query_points.call_args
        assert call_args.kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_search_empty_collection(self, vectordb, mock_qdrant_client):
        """Test searching in empty collection."""
        query_result = MagicMock()
        query_result.points = []
        mock_qdrant_client.query_points.return_value = query_result

        results = await vectordb.search(
            collection="test_empty",
            query_vector=[0.1, 0.2, 0.3],
            limit=10
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_search_nonexistent_collection(self, vectordb, mock_qdrant_client):
        """Test searching in nonexistent collection."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        error = UnexpectedResponse(
            status_code=404,
            reason_phrase="not found",
            content=b"not found",
            headers={}
        )
        mock_qdrant_client.query_points.side_effect = error

        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.search(
                collection="nonexistent",
                query_vector=[0.1, 0.2, 0.3],
                limit=10
            )

    @pytest.mark.asyncio
    async def test_delete_by_ids(self, vectordb, mock_qdrant_client):
        """Test deleting vectors by IDs."""
        # Setup pre and post counts
        pre_info = MagicMock()
        pre_info.points_count = 5

        post_info = MagicMock()
        post_info.points_count = 3

        mock_qdrant_client.get_collection.side_effect = [pre_info, post_info]

        deleted = await vectordb.delete("test_delete", ids=["vec1", "vec2"])
        assert deleted == 2

    @pytest.mark.asyncio
    async def test_delete_by_filter(self, vectordb, mock_qdrant_client):
        """Test deleting vectors by metadata filter."""
        pre_info = MagicMock()
        pre_info.points_count = 5

        post_info = MagicMock()
        post_info.points_count = 3

        mock_qdrant_client.get_collection.side_effect = [pre_info, post_info]

        deleted = await vectordb.delete("test_delete", filters={"category": "A"})
        assert deleted == 2

    @pytest.mark.asyncio
    async def test_delete_no_params(self, vectordb):
        """Test delete raises error when no params provided."""
        with pytest.raises(ValueError, match="Either ids or filters must be provided"):
            await vectordb.delete("test_delete")

    @pytest.mark.asyncio
    async def test_count(self, vectordb, mock_qdrant_client):
        """Test counting vectors in collection."""
        count_result = MagicMock()
        count_result.count = 100
        mock_qdrant_client.count.return_value = count_result

        count = await vectordb.count("test_count")
        assert count == 100

    @pytest.mark.asyncio
    async def test_count_nonexistent_collection(self, vectordb, mock_qdrant_client):
        """Test counting nonexistent collection."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        error = UnexpectedResponse(
            status_code=404,
            reason_phrase="not found",
            content=b"not found",
            headers={}
        )
        mock_qdrant_client.count.side_effect = error

        with pytest.raises(ValueError, match="does not exist"):
            await vectordb.count("nonexistent")


class TestQdrantFilterBuilder:
    """Test Qdrant filter building functionality."""

    @pytest.mark.asyncio
    async def test_build_filter_exact_match(self, vectordb):
        """Test building filter for exact match."""
        filter_dict = {"category": "test"}
        qdrant_filter = vectordb._build_filter(filter_dict)

        assert qdrant_filter is not None
        assert qdrant_filter.must is not None
        assert len(qdrant_filter.must) == 1

    @pytest.mark.asyncio
    async def test_build_filter_in_operator(self, vectordb):
        """Test building filter with $in operator."""
        filter_dict = {"category": {"$in": ["A", "B", "C"]}}
        qdrant_filter = vectordb._build_filter(filter_dict)

        assert qdrant_filter.must is not None
        assert len(qdrant_filter.must) == 1

    @pytest.mark.asyncio
    async def test_build_filter_range(self, vectordb):
        """Test building filter with range operators."""
        filter_dict = {"age": {"$gt": 18, "$lt": 65}}
        qdrant_filter = vectordb._build_filter(filter_dict)

        assert qdrant_filter.must is not None
        # Two conditions: gt and lt
        assert len(qdrant_filter.must) == 2

    @pytest.mark.asyncio
    async def test_build_filter_multiple_conditions(self, vectordb):
        """Test building filter with multiple conditions."""
        filter_dict = {
            "category": "A",
            "status": "active",
            "score": {"$gt": 0.5}
        }
        qdrant_filter = vectordb._build_filter(filter_dict)

        assert qdrant_filter.must is not None
        assert len(qdrant_filter.must) == 3


class TestQdrantConfiguration:
    """Test Qdrant configuration and settings."""

    @pytest.mark.asyncio
    async def test_default_settings(self, mock_qdrant_client):
        """Test that default settings are used when not provided."""
        db = QdrantVectorDB()

        # Should use settings from core.settings
        assert db.host is not None
        assert db.port is not None

    @pytest.mark.asyncio
    async def test_custom_settings(self, mock_qdrant_client):
        """Test custom settings override defaults."""
        db = QdrantVectorDB(
            host="custom-host",
            port=9999,
            grpc_port=8888,
            use_grpc=True
        )

        assert db.host == "custom-host"
        assert db.port == 9999
        assert db.grpc_port == 8888
        assert db.use_grpc is True

    @pytest.mark.asyncio
    async def test_cloud_configuration(self, mock_qdrant_client):
        """Test cloud configuration takes precedence."""
        db = QdrantVectorDB(
            url="https://cloud.qdrant.io",
            api_key="test-key",
            host="localhost",  # Should be ignored
            port=6333  # Should be ignored
        )

        assert db.url == "https://cloud.qdrant.io"
        assert db.api_key == "test-key"
