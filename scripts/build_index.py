"""构建向量索引"""

import sys
sys.path.insert(0, ".")

from src.config import config
from src.modules import RAGModule


def main():
    rag = RAGModule(
        persist_dir=config.chroma_persist_dir,
        embedding_model=config.embedding_model,
    )
    rag.build_index(config.knowledge_dir)
    print("向量索引构建完成!")


if __name__ == "__main__":
    main()
