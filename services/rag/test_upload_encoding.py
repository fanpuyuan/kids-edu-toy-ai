import os
import io
import httpx
import pytest
from fastapi.testclient import TestClient

# Create a dummy client hitting the FastAPI app directly for unit testing
from main import app

client = TestClient(app)

def test_upload_gbk_encoded_text():
    """Test if a GBK encoded text file is correctly processed and chunked."""
    # Create a string with Chinese characters
    test_text = "这是一个测试文档，包含一些中文字符：罗密欧与朱丽叶是一部伟大的悲剧。"
    
    # Encode it as GBK (simulating a Windows Notepad save)
    gbk_bytes = test_text.encode('gbk')
    
    # Create an in-memory file-like object
    file_obj = io.BytesIO(gbk_bytes)
    
    # We spoof the upload process
    response = client.post(
        "/upload_doc",
        files={"file": ("test_gbk.txt", file_obj, "text/plain")}
    )
    
    # Assertions
    assert response.status_code == 200, f"Upload failed with {response.status_code}: {response.text}"
    data = response.json()
    assert data["status"] == "success"
    assert "doc_id" in data
    
    # This proves that SimpleDirectoryReader didn't crash because we intercepted it and fixed it to UTF-8
    assert data["chunks_added"] > 0, "No chunks were generated, suggesting parsing failed or text was lost."

    print(f"✅ Test Passed! Successfully chunked GBK encoded file into {data['chunks_added']} nodes.")
    
    # Cleanup via API to prevent polluting the test DB too much, assuming delete works
    doc_id = data["doc_id"]
    delete_res = client.post("/delete_doc", json={"doc_id": doc_id})
    assert delete_res.status_code == 200

def test_upload_utf8_encoded_text():
    """Ensure standard UTF-8 files still work perfectly."""
    test_text = "这是标准 UTF-8 测试文档。"
    utf8_bytes = test_text.encode('utf-8')
    file_obj = io.BytesIO(utf8_bytes)
    
    response = client.post(
        "/upload_doc",
        files={"file": ("test_utf8.txt", file_obj, "text/plain")}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["chunks_added"] > 0

    print(f"✅ Test Passed! Successfully chunked UTF-8 encoded file into {data['chunks_added']} nodes.")
    
    # Cleanup
    client.post("/delete_doc", json={"doc_id": data["doc_id"]})

if __name__ == "__main__":
    # Can be run directly without Pytest if needed for quick check
    print("Running GBK Test...")
    test_upload_gbk_encoded_text()
    print("Running UTF-8 Test...")
    test_upload_utf8_encoded_text()
    print("All encoding unit tests passed successfully.")
