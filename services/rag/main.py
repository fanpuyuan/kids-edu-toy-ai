import os
import shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List, Dict, Optional
import uvicorn
from pydantic import BaseModel
from loguru import logger

from core.db import db_manager
from core.db_sqlite import sqlite_manager
from core.memory import MemoryManager
from pipelines.ingestion import IngestionPipeline
from pipelines.retrieval import RetrievalPipeline

app = FastAPI(title="RAG Service (Hybrid + Markdown Memory)")

memory_manager = MemoryManager("/app/data")
ingestion_pipeline = IngestionPipeline(db_manager)
retrieval_pipeline = RetrievalPipeline(db_manager)

class QueryRequest(BaseModel):
    query: str
    top_k: int = 3
    embedding_provider: str = "local"
    embedding_api_key: Optional[str] = None

class MemoryUpdateRequest(BaseModel):
    layer: str
    content: str
    
# --- RAG Retrieval Endpoints ---
@app.post("/retrieve")
async def retrieve(request: QueryRequest):
    """Executes a Hybrid Search (BM25 + Vector) and returns cited contexts."""
    results = retrieval_pipeline.retrieve(
        query=request.query, 
        top_k=request.top_k,
        provider=request.embedding_provider,
        api_key=request.embedding_api_key
    )
    return {"status": "success", "results": results}

# --- Configuration Endpoints ---
@app.get("/config")
async def get_config():
    """Retrieves all global configuration settings."""
    configs = sqlite_manager.get_all_configs()
    return {"status": "success", "configs": configs}

@app.post("/config")
async def set_config(configs: dict):
    """Saves global configuration settings."""
    success = sqlite_manager.save_configs(configs)
    if success:
        return {"status": "success", "message": "Configs saved successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save configs")

# --- Document Management (Ingestion) Endpoints ---
@app.post("/upload_doc")
async def upload_doc(
    file: UploadFile = File(...),
    embedding_provider: str = Form("local"),
    embedding_api_key: Optional[str] = Form(None)
):
    """Uploads a document with MD5 deduplication and Upsert support."""
    # We need to save to a temp file first to calculate MD5 and RAG ingestion
    tmp_path = Path(f"/tmp/{file.filename}")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Read raw bytes to calculate MD5
        raw_content = await file.read()
        
        # 1. Calculate MD5 Hash
        import hashlib
        md5_hash = hashlib.md5(raw_content).hexdigest()
        
        # 2. Check for Identical Content (MD5) within the SAME provider
        existing_doc = sqlite_manager.get_doc_by_hash(md5_hash, provider=embedding_provider)
        if existing_doc:
            logger.info(f"File content already exists (MD5: {md5_hash}) for provider {embedding_provider}. Skipping ingestion.")
            return {
                "status": "skipped", 
                "message": "Content already exists in knowledge base.",
                "doc_id": existing_doc["doc_id"],
                "filename": existing_doc["filename"]
            }
            
        # 3. Check for Filename Collision (Upsert Logic - Scoped to Provider)
        old_file_doc = sqlite_manager.get_doc_by_filename(file.filename)
        # Only treat as collision if it's the SAME provider
        if old_file_doc and old_file_doc.get("embedding_provider") == embedding_provider:
            logger.info(f"Filename '{file.filename}' already exists for {embedding_provider} but content changed. Replacing.")
            ingestion_pipeline.delete_doc(old_file_doc["doc_id"], provider=embedding_provider)
            sqlite_manager.delete_document(old_file_doc["doc_id"])
            old_file_doc_id = old_file_doc["doc_id"]
        else:
            old_file_doc_id = None
            
        # 4. Prepare for Ingestion (Write to temp file)
        if file.filename.lower().endswith(('.txt', '.md', '.csv')):
            try:
                text = raw_content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text = raw_content.decode('gbk')
                except UnicodeDecodeError:
                    text = raw_content.decode('utf-8', errors='ignore')
            
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            with open(tmp_path, "wb") as buffer:
                buffer.write(raw_content)
        
        # 5. Register in SQLite and Ingest
        doc_id = sqlite_manager.add_document(file.filename, md5_hash=md5_hash, provider=embedding_provider)
        if not doc_id:
            raise HTTPException(status_code=500, detail="Failed to register document in SQLite.")
            
        num_chunks = ingestion_pipeline.ingest_file(
            str(tmp_path), 
            doc_id=doc_id, 
            provider=embedding_provider,
            api_key=embedding_api_key
        )
        
        # 6. Success
        sqlite_manager.update_document_status(doc_id, "success")
        return {
            "status": "success", 
            "doc_id": doc_id, 
            "filename": file.filename, 
            "chunks_added": num_chunks,
            "action": "updated" if old_file_doc_id else "created"
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path.exists():
            os.remove(tmp_path)

@app.post("/clear_docs")
async def clear_docs(embedding_provider: str = "local"):
    """Wipes the Vector and BM25 databases for a specific provider."""
    success = ingestion_pipeline.clear_database(provider=embedding_provider)
    if success:
         return {"status": "success", "message": f"Databases for {embedding_provider} cleared."}
    raise HTTPException(status_code=500, detail="Failed to clear databases.")

@app.get("/list_docs")
async def list_docs(embedding_provider: Optional[str] = None):
    """Returns the list of uploaded documents, optionally filtered by provider."""
    docs = sqlite_manager.get_all_documents(provider=embedding_provider)
    return {"status": "success", "documents": docs}

class DeleteRequest(BaseModel):
    doc_id: str
    embedding_provider: str = "local"
    embedding_api_key: Optional[str] = None

@app.post("/delete_doc")
async def delete_doc(request: DeleteRequest):
    """Deletes a document from ChromaDB and SQLite."""
    # 1. Delete from ChromaDB
    chroma_deleted = ingestion_pipeline.delete_doc(
        request.doc_id, 
        provider=request.embedding_provider,
        api_key=request.embedding_api_key
    )
    
    # 2. Delete from SQLite
    if chroma_deleted:
        sqlite_manager.delete_document(request.doc_id)
        return {"status": "success", "message": f"Document {request.doc_id} deleted."}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete vectors from ChromaDB.")

# --- Memory Management Endpoints ---
@app.get("/memory/all")
async def get_all_context():
    """Returns the full 3-layer Markdown memory for LLM context injection."""
    return memory_manager.get_all_context()

@app.get("/memory/{layer}")
async def get_memory_layer(layer: str):
    """Retrieve specific memory layer content (SYSTEM, FAMILY, SNAPSHOT)."""
    layer = layer.upper()
    try:
        content = memory_manager.read_memory(layer)
        return {"layer": layer, "content": content}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/memory/update")
async def update_memory_layer(request: MemoryUpdateRequest):
    """Overwrites the content of a specific memory layer."""
    layer = request.layer.upper()
    try:
        success = memory_manager.update_memory(layer, request.content)
        if success:
             return {"status": "success", "layer": layer}
        raise HTTPException(status_code=500, detail="Update failed internally.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/memory/snapshot/append")
async def append_snapshot(content: str = Form(...)):
    """Appends a new summary to the SNAPSHOT.md memory block."""
    success = memory_manager.append_to_snapshot(content)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to append snapshot.")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
