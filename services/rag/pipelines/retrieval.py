from typing import List, Dict
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

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict]:
        """Hybrid Search: Performs Vector + BM25 search and returns formatted citations."""
        logger.info(f"Starting retrieval for query: '{query}'")
        
        if self.db.vector_index is None:
            logger.warning("Vector Index is missing or empty. Returning empty context.")
            return []

        # 1. Setup Vector Retriever
        vector_retriever = self.db.vector_index.as_retriever(similarity_top_k=5)
        
        # 2. Setup BM25 Retriever
        if self.db.bm25_retriever is None:
            logger.warning("BM25 Retriever is missing. Falling back to Vector-only search.")
            retrievers = [vector_retriever]
        else:
            self.db.bm25_retriever.similarity_top_k = 5
            retrievers = [vector_retriever, self.db.bm25_retriever]
            
        # 3. Setup Reciprocal Rank Fusion (RRF)
        # Using QueryFusionRetriever to combine results from multiple retrievers
        hybrid_retriever = QueryFusionRetriever(
            retrievers=retrievers,
            similarity_top_k=top_k,
            num_queries=1, # No query generation, just execute the exact query on both
            mode="reciprocal_rerank",
            llm=self.mock_llm
        )
        
        try:
            results: List[NodeWithScore] = hybrid_retriever.retrieve(query)
            logger.info(f"Hybrid retrieval found {len(results)} pertinent nodes.")
            
            # Format results for the Brain service
            formatted_results = []
            for item in results:
                source_file = item.node.metadata.get("file_name", "Unknown Source")
                formatted_results.append({
                    "content": item.node.text,
                    "source": source_file,
                    "score": item.score
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error during retrieval: {e}")
            return []
