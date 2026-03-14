from fastapi import FastAPI
from typing import List, Optional
from rag_service import RAGModule
import uvicorn
from pydantic import BaseModel

class QueryRequest(BaseModel):
    query: str
    k: int = 5
    category: Optional[str] = None

app = FastAPI(title="RAG Service")
rag = RAGModule()

@app.post("/retrieve")
async def retrieve(request: QueryRequest):
    """检索接口"""
    docs = rag.retrieve(query=request.query, k=request.k, category=request.category)
    # 将模型对象转换为字典
    return [{"page_content": d.page_content, "metadata": d.metadata} for d in docs]

@app.post("/build")
async def build(docs_dir: str):
    """构建索引接口"""
    rag.build_index(docs_dir)
    return {"status": "success"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
