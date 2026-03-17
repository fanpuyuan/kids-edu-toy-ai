from typing import List, Dict, Optional
from loguru import logger
from llama_index.core.schema import NodeWithScore
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.llms.mock import MockLLM
from core.db import DBManager

class RetrievalPipeline:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
        # Initialize a mock LLM because QueryFusionRetriever insists on having an LLM initialized
        # even if num_queries=1 (which means it won't actually do any generation).
        self.mock_llm = MockLLM()

    def retrieve(self, query: str, top_k: int = 3, provider: str = "local", api_key: Optional[str] = None, llm_api_key: Optional[str] = "", embedding_provider: Optional[str] = "local", embedding_api_key: Optional[str] = "") -> List[Dict]:
        """Hybrid search using local or cloud engine."""
        logger.info(f"Starting retrieval for query: '{query}' with provider: '{provider}'")
        
        engine = self.db.get_engine(provider, api_key=api_key, embedding_api_key=embedding_api_key)

        if engine.vector_index is None:
            logger.warning(f"Vector Index is missing or empty for provider '{provider}'. Returning empty context.")
            return []

        # Calculate actual corpus size to bound top_k to prevent BM25 crashing on small datasets
        # This part might need adjustment if cloud engines don't expose chroma_collection directly
        try:
            # Assuming engine.chroma_collection exists for local, or a similar count for cloud
            doc_count = engine.chroma_collection.count() if hasattr(engine, 'chroma_collection') else 100 # Fallback for cloud
            actual_top_k = min(top_k, doc_count) if doc_count > 0 else top_k
        except Exception as e:
            logger.warning(f"Could not determine actual corpus size for provider '{provider}': {e}. Using top_k as is.")
            actual_top_k = top_k

        # 1. Setup Vector Retriever
        vector_retriever = engine.vector_index.as_retriever(similarity_top_k=actual_top_k)
        
        # 2. Setup BM25 Retriever
        if engine.bm25_retriever is None:
            logger.warning(f"BM25 Retriever is missing for provider '{provider}'. Falling back to Vector-only search.")
            retrievers = [vector_retriever]
        else:
            engine.bm25_retriever.similarity_top_k = actual_top_k
            retrievers = [vector_retriever, engine.bm25_retriever]
            
        # 3. Setup Reciprocal Rank Fusion (RRF)
        
        fusion_retriever = QueryFusionRetriever(
            retrievers,
            similarity_top_k=actual_top_k,
            num_queries=1,  # No query expansion for now
            mode="reciprocal_rerank",
            use_async=False,
        )
        
        try:
            results: List[NodeWithScore] = fusion_retriever.retrieve(query)
            logger.info(f"Hybrid retrieval found {len(results)} pertinent nodes.")
            
            # Format results for the Brain service
            formatted_results = []
            for item in results:
                source_file = item.node.metadata.get("file_name", "Unknown Source")
                formatted_results.append({
                    "content": item.node.text,
                    "source": source_file,
                    "score": item.score,
                    "llm_api_key": llm_api_key,
                    "embedding_provider": embedding_provider,
                    "embedding_api_key": embedding_api_key
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error during retrieval: {e}")
            return []
