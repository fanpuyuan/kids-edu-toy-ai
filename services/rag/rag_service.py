"""RAG检索模块"""

from typing import List, Optional
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader
from loguru import logger

class RAGModule:
    def __init__(
        self,
        persist_dir: str = "/app/data/chroma",
        embedding_model: str = "BAAI/bge-small-zh-v1.5",
    ):
        logger.info(f"加载Embedding模型: {embedding_model}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.persist_dir = persist_dir
        self.vectorstore: Optional[Chroma] = None
        logger.info("RAG模块初始化完成")

    def build_index(self, docs_dir: str):
        logger.info(f"从 {docs_dir} 构建向量索引")
        loader = DirectoryLoader(docs_dir, glob="**/*.txt")
        documents = loader.load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "！", "？"],
        )
        chunks = splitter.split_documents(documents)
        for chunk in chunks:
            source = chunk.metadata.get("source", "")
            if "story" in source:
                chunk.metadata["category"] = "story"
            elif "knowledge" in source:
                chunk.metadata["category"] = "knowledge"
            else:
                chunk.metadata["category"] = "general"
        self.vectorstore = Chroma.from_documents(
            chunks, self.embeddings, persist_directory=self.persist_dir
        )
        logger.info("向量索引构建完成")

    def load(self):
        try:
            self.vectorstore = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=self.embeddings,
            )
            logger.info("向量库加载完成")
        except Exception as e:
            logger.warning(f"向量库加载失败: {e}")

    def retrieve(
        self,
        query: str,
        k: int = 5,
        category: Optional[str] = None,
    ) -> List:
        if not self.vectorstore:
            self.load()
        if not self.vectorstore:
            return []
        where_filter = {"category": category} if category else None
        docs = self.vectorstore.similarity_search(query, k=k, filter=where_filter)
        return docs
