"""Verification script for A5: Vector store factory pattern.

This script comprehensively tests the get_vector_db() factory function
to ensure it correctly selects implementations and validates configuration.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_factory_imports():
    """Test that factory components can be imported."""
    print("=" * 60)
    print("Test 1: Factory Imports")
    print("=" * 60)
    
    try:
        from docvector.vectordb import (
            get_vector_db,
            VectorDBConfigurationError,
            IVectorStore,
            ChromaVectorDB,
            QdrantVectorDB,
        )
        print("✓ get_vector_db imported successfully")
        print("✓ VectorDBConfigurationError imported successfully")
        print("✓ IVectorStore imported successfully")
        print("✓ ChromaVectorDB imported successfully")
        print("✓ QdrantVectorDB imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_local_mode_selection():
    """Test that local mode returns ChromaDB."""
    print("\n" + "=" * 60)
    print("Test 2: Local Mode Selection")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, ChromaVectorDB
        from docvector.core import settings
        
        # Save original mode
        original_mode = settings.mcp_mode
        original_dir = settings.chroma_persist_directory
        
        # Set local mode
        settings.mcp_mode = "local"
        settings.chroma_persist_directory = "./test_data/chroma"
        
        # Get instance
        db = get_vector_db()
        
        # Verify it's ChromaDB
        assert isinstance(db, ChromaVectorDB), f"Expected ChromaVectorDB, got {type(db).__name__}"
        print(f"✓ Local mode returns ChromaVectorDB")
        print(f"  - Type: {type(db).__name__}")
        print(f"  - Persist directory: {db.persist_directory}")
        
        # Restore original settings
        settings.mcp_mode = original_mode
        settings.chroma_persist_directory = original_dir
        
        return True
        
    except Exception as e:
        print(f"✗ Local mode test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cloud_mode_selection():
    """Test that cloud mode returns Qdrant."""
    print("\n" + "=" * 60)
    print("Test 3: Cloud Mode Selection")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, QdrantVectorDB
        from docvector.core import settings
        
        # Save original settings
        original_mode = settings.mcp_mode
        original_url = settings.qdrant_url
        original_key = settings.qdrant_api_key
        original_host = settings.qdrant_host
        
        # Set cloud mode with URL and API key
        settings.mcp_mode = "cloud"
        settings.qdrant_url = "https://test.cloud.qdrant.io:6333"
        settings.qdrant_api_key = "test-api-key-12345"
        
        # Get instance
        db = get_vector_db()
        
        # Verify it's Qdrant
        assert isinstance(db, QdrantVectorDB), f"Expected QdrantVectorDB, got {type(db).__name__}"
        print(f"✓ Cloud mode returns QdrantVectorDB")
        print(f"  - Type: {type(db).__name__}")
        print(f"  - URL: {db.url}")
        print(f"  - Has API key: {bool(db.api_key)}")
        
        # Restore original settings
        settings.mcp_mode = original_mode
        settings.qdrant_url = original_url
        settings.qdrant_api_key = original_key
        settings.qdrant_host = original_host
        
        return True
        
    except Exception as e:
        print(f"✗ Cloud mode test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hybrid_mode_selection():
    """Test that hybrid mode returns Qdrant."""
    print("\n" + "=" * 60)
    print("Test 4: Hybrid Mode Selection")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, QdrantVectorDB
        from docvector.core import settings
        
        # Save original settings
        original_mode = settings.mcp_mode
        original_host = settings.qdrant_host
        original_port = settings.qdrant_port
        original_url = settings.qdrant_url
        original_key = settings.qdrant_api_key
        
        # Set hybrid mode with self-hosted Qdrant
        settings.mcp_mode = "hybrid"
        settings.qdrant_url = None
        settings.qdrant_api_key = None
        settings.qdrant_host = "localhost"
        settings.qdrant_port = 6333
        
        # Get instance
        db = get_vector_db()
        
        # Verify it's Qdrant
        assert isinstance(db, QdrantVectorDB), f"Expected QdrantVectorDB, got {type(db).__name__}"
        print(f"✓ Hybrid mode returns QdrantVectorDB")
        print(f"  - Type: {type(db).__name__}")
        print(f"  - Host: {db.host}")
        print(f"  - Port: {db.port}")
        
        # Restore original settings
        settings.mcp_mode = original_mode
        settings.qdrant_host = original_host
        settings.qdrant_port = original_port
        settings.qdrant_url = original_url
        settings.qdrant_api_key = original_key
        
        return True
        
    except Exception as e:
        print(f"✗ Hybrid mode test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mode_override():
    """Test that mode parameter overrides settings."""
    print("\n" + "=" * 60)
    print("Test 5: Mode Override")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, ChromaVectorDB, QdrantVectorDB
        from docvector.core import settings
        
        # Save original settings
        original_mode = settings.mcp_mode
        original_chroma_dir = settings.chroma_persist_directory
        original_qdrant_host = settings.qdrant_host
        original_qdrant_port = settings.qdrant_port
        original_url = settings.qdrant_url
        original_key = settings.qdrant_api_key
        
        # Set cloud mode in settings
        settings.mcp_mode = "cloud"
        settings.qdrant_url = "https://test.cloud.qdrant.io"
        settings.qdrant_api_key = "test-key"
        settings.chroma_persist_directory = "./test_data/chroma"
        
        # Override to local
        db = get_vector_db(mode="local")
        assert isinstance(db, ChromaVectorDB), "Override to local should return ChromaDB"
        print("✓ Mode override to 'local' works")
        
        # Set local mode in settings
        settings.mcp_mode = "local"
        settings.qdrant_url = None
        settings.qdrant_api_key = None
        settings.qdrant_host = "localhost"
        settings.qdrant_port = 6333
        
        # Override to cloud
        settings.qdrant_url = "https://test.cloud.qdrant.io"
        settings.qdrant_api_key = "test-key"
        db = get_vector_db(mode="cloud")
        assert isinstance(db, QdrantVectorDB), "Override to cloud should return Qdrant"
        print("✓ Mode override to 'cloud' works")
        
        # Restore original settings
        settings.mcp_mode = original_mode
        settings.chroma_persist_directory = original_chroma_dir
        settings.qdrant_host = original_qdrant_host
        settings.qdrant_port = original_qdrant_port
        settings.qdrant_url = original_url
        settings.qdrant_api_key = original_key
        
        return True
        
    except Exception as e:
        print(f"✗ Mode override test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_invalid_mode():
    """Test that invalid mode raises ValueError."""
    print("\n" + "=" * 60)
    print("Test 6: Invalid Mode Validation")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db
        
        # Test invalid mode
        try:
            _db = get_vector_db(mode="invalid_mode")
            print("✗ Should have raised ValueError for invalid mode")
            return False
        except ValueError as e:
            assert "Invalid" in str(e) or "invalid" in str(e)
            print(f"✓ Invalid mode raises ValueError")
            print(f"  - Error message: {str(e)[:80]}...")

        # Test another invalid mode
        try:
            _db = get_vector_db(mode="production")
            print("✗ Should have raised ValueError for 'production' mode")
            return False
        except ValueError as e:
            print(f"✓ Invalid mode 'production' raises ValueError")
        
        return True
        
    except Exception as e:
        print(f"✗ Invalid mode test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_missing_chroma_config():
    """Test that missing ChromaDB config raises error."""
    print("\n" + "=" * 60)
    print("Test 7: Missing ChromaDB Configuration")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, VectorDBConfigurationError
        from docvector.core import settings
        
        # Save original
        original_dir = settings.chroma_persist_directory
        
        # Set empty directory
        settings.chroma_persist_directory = ""

        try:
            _db = get_vector_db(mode="local")
            print("✗ Should have raised VectorDBConfigurationError")
            settings.chroma_persist_directory = original_dir
            return False
        except VectorDBConfigurationError as e:
            assert "not configured" in str(e) or "ChromaDB" in str(e)
            print(f"✓ Missing ChromaDB config raises VectorDBConfigurationError")
            print(f"  - Error message: {str(e)[:80]}...")
        
        # Restore
        settings.chroma_persist_directory = original_dir
        
        return True
        
    except Exception as e:
        print(f"✗ Missing ChromaDB config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_missing_qdrant_config():
    """Test that missing Qdrant config raises error."""
    print("\n" + "=" * 60)
    print("Test 8: Missing Qdrant Configuration")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, VectorDBConfigurationError
        from docvector.core import settings
        
        # Save original
        original_url = settings.qdrant_url
        original_key = settings.qdrant_api_key
        original_host = settings.qdrant_host
        
        # Clear all Qdrant settings
        settings.qdrant_url = None
        settings.qdrant_api_key = None
        settings.qdrant_host = ""

        try:
            _db = get_vector_db(mode="cloud")
            print("✗ Should have raised VectorDBConfigurationError")
            return False
        except VectorDBConfigurationError as e:
            assert "not configured" in str(e) or "Qdrant" in str(e)
            print(f"✓ Missing Qdrant config raises VectorDBConfigurationError")
            print(f"  - Error message: {str(e)[:80]}...")
        
        # Restore
        settings.qdrant_url = original_url
        settings.qdrant_api_key = original_key
        settings.qdrant_host = original_host
        
        return True
        
    except Exception as e:
        print(f"✗ Missing Qdrant config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_partial_qdrant_config():
    """Test that partial Qdrant config (URL without key) raises error."""
    print("\n" + "=" * 60)
    print("Test 9: Partial Qdrant Configuration")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, VectorDBConfigurationError
        from docvector.core import settings
        
        # Save original
        original_url = settings.qdrant_url
        original_key = settings.qdrant_api_key
        
        # Set URL without API key
        settings.qdrant_url = "https://test.cloud.qdrant.io"
        settings.qdrant_api_key = None

        try:
            _db = get_vector_db(mode="cloud")
            print("✗ Should have raised VectorDBConfigurationError for URL without key")
            return False
        except VectorDBConfigurationError as e:
            assert "API key" in str(e) or "missing" in str(e)
            print(f"✓ URL without API key raises VectorDBConfigurationError")
            print(f"  - Error message: {str(e)[:80]}...")

        # Set API key without URL
        settings.qdrant_url = None
        settings.qdrant_api_key = "test-key"

        try:
            _db = get_vector_db(mode="cloud")
            print("✗ Should have raised VectorDBConfigurationError for key without URL")
            return False
        except VectorDBConfigurationError as e:
            assert "URL" in str(e) or "missing" in str(e)
            print(f"✓ API key without URL raises VectorDBConfigurationError")
        
        # Restore
        settings.qdrant_url = original_url
        settings.qdrant_api_key = original_key
        
        return True
        
    except Exception as e:
        print(f"✗ Partial Qdrant config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_interface_compliance():
    """Test that returned instances implement IVectorStore."""
    print("\n" + "=" * 60)
    print("Test 10: Interface Compliance")
    print("=" * 60)
    
    try:
        from docvector.vectordb import get_vector_db, IVectorStore
        from docvector.core import settings
        
        # Save original
        original_mode = settings.mcp_mode
        original_chroma_dir = settings.chroma_persist_directory
        original_qdrant_host = settings.qdrant_host
        original_qdrant_port = settings.qdrant_port
        original_url = settings.qdrant_url
        original_key = settings.qdrant_api_key
        
        # Test local mode
        settings.mcp_mode = "local"
        settings.chroma_persist_directory = "./test_data/chroma"
        db = get_vector_db()
        assert isinstance(db, IVectorStore), "ChromaDB should implement IVectorStore"
        print("✓ Local mode instance implements IVectorStore")
        
        # Test cloud mode
        settings.mcp_mode = "cloud"
        settings.qdrant_url = "https://test.cloud.qdrant.io"
        settings.qdrant_api_key = "test-key"
        db = get_vector_db()
        assert isinstance(db, IVectorStore), "Qdrant should implement IVectorStore"
        print("✓ Cloud mode instance implements IVectorStore")
        
        # Test hybrid mode
        settings.mcp_mode = "hybrid"
        settings.qdrant_url = None
        settings.qdrant_api_key = None
        settings.qdrant_host = "localhost"
        settings.qdrant_port = 6333
        db = get_vector_db()
        assert isinstance(db, IVectorStore), "Qdrant should implement IVectorStore"
        print("✓ Hybrid mode instance implements IVectorStore")
        
        # Restore
        settings.mcp_mode = original_mode
        settings.chroma_persist_directory = original_chroma_dir
        settings.qdrant_host = original_qdrant_host
        settings.qdrant_port = original_qdrant_port
        settings.qdrant_url = original_url
        settings.qdrant_api_key = original_key
        
        return True
        
    except Exception as e:
        print(f"✗ Interface compliance test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("A5: Vector Store Factory Verification")
    print("=" * 60 + "\n")
    
    tests = [
        ("Factory Imports", test_factory_imports),
        ("Local Mode Selection", test_local_mode_selection),
        ("Cloud Mode Selection", test_cloud_mode_selection),
        ("Hybrid Mode Selection", test_hybrid_mode_selection),
        ("Mode Override", test_mode_override),
        ("Invalid Mode Validation", test_invalid_mode),
        ("Missing ChromaDB Config", test_missing_chroma_config),
        ("Missing Qdrant Config", test_missing_qdrant_config),
        ("Partial Qdrant Config", test_partial_qdrant_config),
        ("Interface Compliance", test_interface_compliance),
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
        print("\n🎉 All tests passed! The factory pattern is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
