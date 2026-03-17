import os
import sys
import io
import json
import pytest

# 将上一级目录 (即 /app 或 services/rag) 加入 Python 模块搜索路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

# Create a test client
client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    """Clear database before and after the test module."""
    client.post("/clear_docs")
    yield
    client.post("/clear_docs")

def test_api_upload_and_retrieve():
    """Test standard file upload and then retrieve from it."""
    # 1. Upload a UTF-8 text file
    test_text = "这是一个测试故事。有一天，小灰狼在森林里迷路了，遇到了一只会说话的兔子。"
    file_obj = io.BytesIO(test_text.encode('utf-8'))
    
    upload_res = client.post(
        "/upload_doc",
        files={"file": ("test_story_utf8.txt", file_obj, "text/plain")}
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["status"] == "success"
    assert data["chunks_added"] > 0
    doc_id = data["doc_id"]
    
    # 2. Upload a GBK text file
    test_text_gbk = "另一段文字：小明今天吃了一个很大的红苹果。"
    file_obj_gbk = io.BytesIO(test_text_gbk.encode('gbk'))
    
    upload_res_gbk = client.post(
        "/upload_doc",
        files={"file": ("test_apple_gbk.txt", file_obj_gbk, "text/plain")}
    )
    assert upload_res_gbk.status_code == 200
    data_gbk = upload_res_gbk.json()
    assert data_gbk["status"] == "success"
    assert data_gbk["chunks_added"] > 0
    doc_id_gbk = data_gbk["doc_id"]
    
    # 3. Retrieve across both files
    retrieve_res = client.post(
        "/retrieve",
        json={"query": "小明吃了什么？", "top_k": 2}
    )
    assert retrieve_res.status_code == 200
    ret_data = retrieve_res.json()
    assert "红苹果" in ret_data["results"][0]["content"]
    
    # 4. Delete the first document
    delete_res = client.post("/delete_doc", json={"doc_id": doc_id})
    assert delete_res.status_code == 200
    assert delete_res.json()["status"] == "success"
    
def test_api_clear_db():
    """Test clearing the entire database logic."""
    # 1. Upload something first
    file_obj = io.BytesIO(b"Something to chunk.")
    client.post("/upload_doc", files={"file": ("temp.txt", file_obj, "text/plain")})
    
    # 2. Clear Database
    clear_res = client.post("/clear_docs")
    assert clear_res.status_code == 200
    assert clear_res.json()["status"] == "success"
    
    # 3. Retrieve should be empty or handle gracefully
    ret_res = client.post("/retrieve", json={"query": "test", "top_k": 2})
    assert ret_res.status_code == 200
    assert len(ret_res.json()["results"]) == 0

def test_api_memory_lifecycle():
    """Test Memory updates and full retrieval."""
    # 1. Update Short-Term (SNAPSHOT) Memory
    mem_update = client.post(
        "/memory/update",
        json={
            "layer": "snapshot",
            "content": "孩子今天心情不错，刚才玩了玩具汽车。",
            "append": True
        }
    )
    assert mem_update.status_code == 200
    assert mem_update.json()["status"] == "success"
    
    # 2. Get All Memory
    mem_all = client.get("/memory/all")
    assert mem_all.status_code == 200
    
    data = mem_all.json()
    assert "孩子今天心情不错，刚才玩了玩具汽车。" in data["snapshot"]
    
    # Check that system files are still there
    assert data["system"] is not None

def test_api_multi_provider_md5():
    """Test identical file uploaded with different providers are not skipped."""
    file_content = b"This is a specific test for MD5 collisions across providers."
    file_obj1 = io.BytesIO(file_content)
    
    # Provider 1: local
    res1 = client.post(
        "/upload_doc",
        data={"embedding_provider": "local"},
        files={"file": ("md5_test.txt", file_obj1, "text/plain")}
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"
    doc_id1 = res1.json()["doc_id"]
    
    # Provider 2: cloud (Same File, Different Provider)
    file_obj2 = io.BytesIO(file_content) # rewind
    res2 = client.post(
        "/upload_doc",
        data={"embedding_provider": "cloud"},
        files={"file": ("md5_test.txt", file_obj2, "text/plain")}
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "success" # Should NOT be skipped!
    doc_id2 = res2.json()["doc_id"]
    
    # Provider 3: local again (Same File, Same Provider)
    file_obj3 = io.BytesIO(file_content)
    res3 = client.post(
        "/upload_doc",
        data={"embedding_provider": "local"},
        files={"file": ("md5_test.txt", file_obj3, "text/plain")}
    )
    assert res3.status_code == 200
    assert res3.json()["status"] == "skipped" # Should be skipped this time
    
    # Cleanup
    client.post("/delete_doc", json={"doc_id": doc_id1, "embedding_provider": "local"})
    client.post("/delete_doc", json={"doc_id": doc_id2, "embedding_provider": "cloud"})
