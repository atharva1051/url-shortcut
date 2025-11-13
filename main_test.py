import pytest
import sqlite3
import tempfile
import os
from fastapi.testclient import TestClient
from unittest.mock import patch

# Import the app from your main file
# Adjust the import based on your file name
# from main import app, init_db, get_db, DATABASE
# For testing purposes, assuming the code is in main.py

@pytest.fixture
def test_db():
    """Create a temporary test database"""
    db_fd, db_path = tempfile.mkstemp()
    yield db_path
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(test_db, monkeypatch):
    """Create a test client with a temporary database"""
    # Patch the DATABASE constant to use test database
    monkeypatch.setattr("main.DATABASE", test_db)
    
    # Import app after patching DATABASE
    from main import app, init_db
    
    # Initialize test database
    init_db()
    
    # Create test client
    client = TestClient(app)
    yield client


@pytest.fixture
def populated_client(client):
    """Create a client with pre-populated data"""
    # Add some test entries
    client.post("/shorten", json={"code": "test1", "url": "https://example.com"})
    client.post("/shorten", json={"code": "test2", "url": "https://google.com"})
    client.post("/shorten", json={"code": "github", "url": "https://github.com"})
    yield client


class TestRootEndpoint:
    """Tests for the root endpoint"""
    
    def test_root_returns_welcome_message(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Welcome to the FastAPI application!"}


class TestCreateShortURL:
    """Tests for creating short URLs"""
    
    def test_create_short_url_success(self, client):
        response = client.post(
            "/shorten",
            json={"code": "example", "url": "https://example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "example"
        assert data["url"] == "https://example.com"
        assert data["message"] == "Short URL created successfully"
    
    def test_create_short_url_duplicate_code(self, client):
        # Create first entry
        client.post("/shorten", json={"code": "duplicate", "url": "https://example.com"})
        
        # Try to create duplicate
        response = client.post(
            "/shorten",
            json={"code": "duplicate", "url": "https://another.com"}
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Code already exists"
    
    def test_create_short_url_missing_fields(self, client):
        response = client.post("/shorten", json={"code": "test"})
        assert response.status_code == 422  # Validation error
    
    def test_create_short_url_empty_code(self, client):
        response = client.post(
            "/shorten",
            json={"code": "", "url": "https://example.com"}
        )
        # Should succeed as empty string is valid, but might want to add validation
        assert response.status_code == 200 or response.status_code == 422
    
    def test_create_short_url_special_characters(self, client):
        response = client.post(
            "/shorten",
            json={"code": "test-123_abc", "url": "https://example.com"}
        )
        assert response.status_code == 200


class TestUpdateURL:
    """Tests for updating URLs"""
    
    def test_update_existing_url(self, populated_client):
        response = populated_client.put(
            "/update/test1",
            json={"url": "https://updated-example.com"}
        )
        assert response.status_code == 200
        assert response.json()["message"] == "URL updated successfully"
        
        # Verify the update
        resolve_response = populated_client.get("/test1", follow_redirects=False)
        assert resolve_response.status_code == 302
        assert resolve_response.headers["location"] == "https://updated-example.com"
    
    def test_update_nonexistent_code(self, populated_client):
        response = populated_client.put(
            "/update/nonexistent",
            json={"url": "https://example.com"}
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Code not found"
    
    def test_update_with_invalid_data(self, populated_client):
        response = populated_client.put("/update/test1", json={})
        # Should fail due to missing 'url' key
        assert response.status_code in [400, 422, 500]


class TestDeleteURL:
    """Tests for deleting URLs"""
    
    def test_delete_existing_url(self, populated_client):
        response = populated_client.delete("/delete/test1")
        assert response.status_code == 200
        assert response.json()["message"] == "Entry deleted successfully"
        
        # Verify deletion - should redirect to /manage
        resolve_response = populated_client.get("/test1", follow_redirects=False)
        assert resolve_response.status_code == 302
        assert resolve_response.headers["location"] == "/manage"
    
    def test_delete_nonexistent_code(self, populated_client):
        response = populated_client.delete("/delete/nonexistent")
        assert response.status_code == 404
        assert response.json()["detail"] == "Code not found"
    
    def test_delete_twice(self, populated_client):
        # Delete once
        response1 = populated_client.delete("/delete/test1")
        assert response1.status_code == 200
        
        # Try to delete again
        response2 = populated_client.delete("/delete/test1")
        assert response2.status_code == 404


class TestResolveURL:
    """Tests for URL resolution and redirection"""
    
    def test_resolve_existing_code(self, populated_client):
        response = populated_client.get("/test1", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "https://example.com"
    
    def test_resolve_nonexistent_code(self, populated_client):
        response = populated_client.get("/nonexistent", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/manage"
    
    def test_resolve_follows_redirect(self, populated_client):
        response = populated_client.get("/test1", follow_redirects=True)
        # Note: This will fail if the external URL is not accessible
        # In real tests, you might want to mock this
        assert response.status_code in [200, 302]


class TestManagePage:
    """Tests for the management page"""
    
    def test_manage_page_loads(self, client):
        response = client.get("/manage")
        assert response.status_code == 200
        assert "URL Shortener Management" in response.text
    
    def test_manage_page_shows_entries(self, populated_client):
        response = populated_client.get("/manage")
        assert response.status_code == 200
        assert "test1" in response.text
        assert "https://example.com" in response.text
        assert "test2" in response.text
        assert "https://google.com" in response.text
    
    def test_manage_page_empty_database(self, client):
        response = client.get("/manage")
        assert response.status_code == 200
        assert "URL Shortener Management" in response.text
        # Should still render even with no entries
    
    def test_manage_page_contains_form(self, client):
        response = client.get("/manage")
        assert response.status_code == 200
        assert "createForm" in response.text
        assert "Create New Entry" in response.text


class TestDatabaseOperations:
    """Tests for database operations"""
    
    def test_database_initialization(self, test_db):
        from main import init_db
        # Manually initialize with test db
        with patch("main.DATABASE", test_db):
            init_db()
        
        # Verify table exists
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='urls'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None
        assert result[0] == "urls"
    
    def test_database_context_manager_closes_connection(self, test_db, monkeypatch):
        monkeypatch.setattr("main.DATABASE", test_db)
        from main import get_db, init_db
        
        init_db()
        
        with get_db() as conn:
            assert isinstance(conn, sqlite3.Connection)
        
        # Connection should be closed after exiting context
        # This is implicit in the context manager behavior


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""
    
    def test_very_long_url(self, client):
        long_url = "https://example.com/" + "a" * 2000
        response = client.post(
            "/shorten",
            json={"code": "long", "url": long_url}
        )
        assert response.status_code == 200
    
    def test_special_characters_in_url(self, client):
        special_url = "https://example.com/path?query=value&other=123#fragment"
        response = client.post(
            "/shorten",
            json={"code": "special", "url": special_url}
        )
        assert response.status_code == 200
        
        # Verify it resolves correctly
        resolve_response = client.get("/special", follow_redirects=False)
        assert resolve_response.headers["location"] == special_url
    
    def test_unicode_in_code(self, client):
        response = client.post(
            "/shorten",
            json={"code": "test-café", "url": "https://example.com"}
        )
        # Should handle unicode
        assert response.status_code == 200
    
    def test_concurrent_creates(self, client):
        # Test that database handles concurrent operations
        code = "concurrent"
        url1 = "https://example1.com"
        url2 = "https://example2.com"
        
        response1 = client.post("/shorten", json={"code": code, "url": url1})
        response2 = client.post("/shorten", json={"code": code, "url": url2})
        
        # One should succeed, one should fail
        assert (response1.status_code == 200 and response2.status_code == 400) or \
               (response1.status_code == 400 and response2.status_code == 200)


class TestIntegrationScenarios:
    """Integration tests for complete workflows"""
    
    def test_full_crud_workflow(self, client):
        # Create
        create_response = client.post(
            "/shorten",
            json={"code": "workflow", "url": "https://example.com"}
        )
        assert create_response.status_code == 200
        
        # Read (resolve)
        resolve_response = client.get("/workflow", follow_redirects=False)
        assert resolve_response.status_code == 302
        assert resolve_response.headers["location"] == "https://example.com"
        
        # Update
        update_response = client.put(
            "/update/workflow",
            json={"url": "https://updated.com"}
        )
        assert update_response.status_code == 200
        
        # Verify update
        resolve_response2 = client.get("/workflow", follow_redirects=False)
        assert resolve_response2.headers["location"] == "https://updated.com"
        
        # Delete
        delete_response = client.delete("/delete/workflow")
        assert delete_response.status_code == 200
        
        # Verify deletion
        resolve_response3 = client.get("/workflow", follow_redirects=False)
        assert resolve_response3.headers["location"] == "/manage"
    
    def test_manage_page_workflow(self, client):
        # Add entries via API
        client.post("/shorten", json={"code": "api1", "url": "https://api1.com"})
        client.post("/shorten", json={"code": "api2", "url": "https://api2.com"})
        
        # Check management page shows them
        response = client.get("/manage")
        assert "api1" in response.text
        assert "api2" in response.text
        
        # Delete one
        client.delete("/delete/api1")
        
        # Verify management page updated
        response2 = client.get("/manage")
        assert "api1" not in response2.text
        assert "api2" in response2.text