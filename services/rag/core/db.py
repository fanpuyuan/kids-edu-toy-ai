import os
from typing import Optional
import pickle
from pathlib import Path
from loguru import logger
import chromadb
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
try:
    from llama_index.embeddings.dashscope import DashScopeEmbedding
except ImportError:
    from llama_index.embeddings.dashscope.base import DashScopeEmbedding

class EmbeddingEngine:
    """Holds all components for a specific embedding provider."""
    def __init__(self, provider: str, embed_model, chroma_client, chroma_dir: Path, bm25_dir: Path):
        self.provider = provider
        self.embed_model = embed_model
        self.chroma_collection_name = f"kids_knowledge_{provider}"
        self.chroma_collection = chroma_client.get_or_create_collection(self.chroma_collection_name)
        self.vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        self.bm25_dir = bm25_dir / provider
        
        # Initialize Vector Index
        try:
            self.vector_index = VectorStoreIndex.from_vector_store(
                self.vector_store,
                embed_model=self.embed_model
            )
            logger.info(f"Loaded Vector Index for {provider} successfully.")
        except Exception as e:
            logger.error(f"Failed to load Vector Index for {provider}. Error: {e}")
            self.vector_index = None

        # Initialize BM25 Retriever
        self.bm25_retriever = None
        self._load_bm25()

    def _load_bm25(self):
        if self.bm25_dir.exists() and any(self.bm25_dir.iterdir()):
            try:
                self.bm25_retriever = BM25Retriever.from_persist_dir(str(self.bm25_dir))
                logger.info(f"Loaded BM25 index for {self.provider} from {self.bm25_dir}")
            except Exception as e:
                logger.error(f"Failed to load BM25 index for {self.provider}: {e}")

class DBManager:
    """Manages Multiple Embedding Engines (Local, DashScope, etc.)."""
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.chroma_dir = self.data_dir / "chroma"
        self.bm25_base_dir = self.data_dir / "bm25_index"
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        
        # Shared configuration
        self.dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        
        # Cache for initialized engines
        self.engines = {}

    def get_engine(self, provider: str = "local", api_key: Optional[str] = None) -> EmbeddingEngine:
        """Lazy-loads and returns an EmbeddingEngine for the given provider."""
        provider = provider.lower()
        
        # Determine effective API key
        effective_key = api_key or self.dashscope_key
        
        # Check if engine exists and if the key matches for dashscope
        if provider in self.engines:
            engine = self.engines[provider]
            # If dashscope and key changed, we need to re-initialize
            if provider == "dashscope" and effective_key and getattr(engine, "api_key_used", None) != effective_key:
                logger.info(f"API Key changed for {provider}, re-initializing engine.")
            else:
                return engine
        
        logger.info(f"Initializing Embedding Engine for provider: {provider}")
        
        if provider == "dashscope":
            if not effective_key:
                logger.warning("DashScope API Key not provided. Falling back to local.")
                return self.get_engine("local")
            
            embed_model = DashScopeEmbedding(
                model_name="text-embedding-v3",
                api_key=effective_key
            )
        else:
            # Local BGE
            embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-zh-v1.5", device="cpu")
            
        engine = EmbeddingEngine(
            provider=provider,
            embed_model=embed_model,
            chroma_client=self.chroma_client,
            chroma_dir=self.chroma_dir,
            bm25_dir=self.bm25_base_dir
        )
        # Store the key used for future change detection
        if provider == "dashscope":
            engine.api_key_used = effective_key
            
        self.engines[provider] = engine
        return engine

    def save_bm25(self, provider: str, retriever: BM25Retriever):
        """Persists the BM25 index for a specific provider."""
        engine = self.get_engine(provider)
        try:
            engine.bm25_dir.mkdir(parents=True, exist_ok=True)
            retriever.persist(str(engine.bm25_dir))
            engine.bm25_retriever = retriever
            logger.info(f"Saved BM25 index for {provider} to {engine.bm25_dir}")
        except Exception as e:
            logger.error(f"Failed to save BM25 index for {provider}: {e}")

db_manager = DBManager()
