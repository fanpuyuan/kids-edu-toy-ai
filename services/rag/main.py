import os
import shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List, Dict, Optional
import uvicorn
from pydantic import BaseModel

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

class MemoryUpdateRequest(BaseModel):
    layer: str
    content: str
    
# --- RAG Retrieval Endpoints ---
@app.post("/retrieve")
async def retrieve(request: QueryRequest):
    """Executes a Hybrid Search (BM25 + Vector) and returns cited contexts."""
    results = retrieval_pipeline.retrieve(query=request.query, top_k=request.top_k)
    return {"status": "success", "results": results}

# --- Document Management (Ingestion) Endpoints ---
@app.post("/upload_doc")
async def upload_doc(file: UploadFile = File(...)):
    """Uploads a diverse document format and processes it into the Knowledge Base."""
    tmp_path = Path(f"/tmp/{file.filename}")
    
    # 1. Register document in SQLite
    doc_id = sqlite_manager.add_document(file.filename)
    if not doc_id:
        raise HTTPException(status_code=500, detail="Failed to register document in SQLite.")
        
    try:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        # Read raw bytes
        raw_content = await file.read()
        
        # 1.5 Auto-Detect Encoding & Convert to UTF-8 for text files
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
            # For PDF, DOCX, etc., write binary directly
            with open(tmp_path, "wb") as buffer:
                buffer.write(raw_content)
        
        # 2. Process file via Unstructured/LlamaIndex and inject doc_id
        num_chunks = ingestion_pipeline.ingest_file(str(tmp_path), doc_id=doc_id)
        
        # 3. Mark as success
        sqlite_manager.update_document_status(doc_id, "success")
        return {"status": "success", "doc_id": doc_id, "filename": file.filename, "chunks_added": num_chunks}
    except Exception as e:
        # Mark as failed
        sqlite_manager.update_document_status(doc_id, "failed")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        if tmp_path.exists():
            os.remove(tmp_path)

@app.post("/clear_docs")
async def clear_docs():
    """Wipes the Vector and BM25 databases from the Knowledge Base."""
    success = ingestion_pipeline.clear_database()
    if success:
         return {"status": "success", "message": "Databases cleared."}
    raise HTTPException(status_code=500, detail="Failed to clear databases.")

@app.get("/list_docs")
async def list_docs():
    """Returns the list of uploaded documents and their status from SQLite."""
    docs = sqlite_manager.get_all_documents()
    return {"status": "success", "documents": docs}

class DeleteRequest(BaseModel):
    doc_id: str

@app.post("/delete_doc")
async def delete_doc(request: DeleteRequest):
    """Deletes a document from ChromaDB and SQLite."""
    # 1. Delete from ChromaDB
    chroma_deleted = ingestion_pipeline.delete_doc(request.doc_id)
    
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
