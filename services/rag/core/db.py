import os
import pickle
from pathlib import Path
from loguru import logger
import chromadb
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

class DBManager:
    """Manages Vector DB (Chroma) and Keyword Index (BM25)."""
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.chroma_dir = self.data_dir / "chroma"
        self.bm25_path = self.data_dir / "bm25_index.pkl"
        
        self.chroma_collection_name = "kids_knowledge"
        
        # Initialize Embedding Model
        # Using local CPU embedding to save GPU memory for the main LLM.
        logger.info("Initializing Embedding Model: BAAI/bge-small-zh-v1.5")
        self.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-zh-v1.5", device="cpu")
        
        # Initialize ChromaDB
        logger.info(f"Initializing ChromaDB connection at {self.chroma_dir}")
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.chroma_collection = self.chroma_client.get_or_create_collection(self.chroma_collection_name)
        
        self.vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        
        # Initialize Vector Index
        try:
            self.vector_index = VectorStoreIndex.from_vector_store(
                self.vector_store,
                embed_model=self.embed_model
            )
            logger.info("Loaded Vector Index successfully.")
        except Exception as e:
            logger.error(f"Failed to load Vector Index. It might be empty. Error: {e}")
            # Empty index will be created during ingestion.
            self.vector_index = None

        # Initialize BM25 Retriever
        self.bm25_retriever = None
        self._load_bm25()

    def _load_bm25(self):
        """Loads BM25 index from disk if it exists."""
        if self.bm25_path.exists():
            try:
                with open(self.bm25_path, "rb") as f:
                    self.bm25_retriever = pickle.load(f)
                logger.info(f"Loaded BM25 index from {self.bm25_path}")
            except Exception as e:
                logger.error(f"Failed to load BM25 index: {e}")
        else:
            logger.info("No existing BM25 index found. Needs to be built during ingestion.")

    def save_bm25(self, retriever: BM25Retriever):
        """Persists the BM25 index manually since BM25 is purely in-memory."""
        try:
            with open(self.bm25_path, "wb") as f:
                pickle.dump(retriever, f)
            self.bm25_retriever = retriever
            logger.info(f"Saved BM25 index to {self.bm25_path}")
        except Exception as e:
            logger.error(f"Failed to save BM25 index: {e}")

    def update_vector_index(self, index: VectorStoreIndex):
        """Update the running vector index after ingestion."""
        self.vector_index = index

db_manager = DBManager()
