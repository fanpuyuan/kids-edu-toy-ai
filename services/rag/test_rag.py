import os
import sys
# Add current directory to path so imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.db import db_manager
from pipelines.ingestion import IngestionPipeline
from pipelines.retrieval import RetrievalPipeline
from loguru import logger

def test_rag():
    logger.info("Initializing pipelines...")
    ingestion = IngestionPipeline(db_manager)
    retrieval = RetrievalPipeline(db_manager)

    logger.info("Clearing existing database for clean test...")
    ingestion.clear_database()

    sample_doc = "sample_docs/test_story.md"
    logger.info(f"Ingesting sample document: {sample_doc}")
    chunks = ingestion.ingest_file(sample_doc)
    logger.info(f"Ingested {chunks} chunks.")

    queries = [
        "小猪佩奇在干什么？", # Semantic specific
        "恐龙是怎么灭绝的？", # Semantic specific
        "星巴", # Keyword specific (BM25 should shine here)
    ]

    for q in queries:
        logger.info(f"\n--- Testing Query: '{q}' ---")
        results = retrieval.retrieve(q, top_k=2)
        for i, res in enumerate(results):
            logger.info(f"Rank {i+1} (Score: {res['score']:.4f}): {res['content'].strip()}")

if __name__ == "__main__":
    test_rag()
