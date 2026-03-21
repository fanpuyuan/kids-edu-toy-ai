import os
import shutil
import hashlib
from typing import List, Optional
from pathlib import Path
from loguru import logger
import jieba
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.retrievers.bm25 import BM25Retriever
from core.db import DBManager

class IngestionPipeline:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
        self.node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=[1024, 256])

    def calculate_md5(self, file_path: str) -> str:
        """Calculates MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def ingest_file(self, file_path: str, doc_id: str, provider: str = "local", api_key: Optional[str] = None) -> int:
        """Processes a file and stores its nodes in Chroma and BM25."""
        logger.info(f"Starting ingestion for file: {file_path} with doc_id: {doc_id} using provider: {provider}")
        
        engine = self.db.get_engine(provider, api_key=api_key)
        
        # Load and split
        documents = SimpleDirectoryReader(input_files=[file_path]).load_data()
        nodes = self.node_parser.get_nodes_from_documents(documents)
        leaf_nodes = get_leaf_nodes(nodes)
        
        # Add metadata
        for node in nodes:
            node.metadata["doc_id"] = doc_id
            
        # Add all nodes (parents and leaves) to docstore
        engine.storage_context.docstore.add_documents(nodes)
        
        # 1. Vector Store (only index leaf nodes)
        if engine.vector_index:
            engine.vector_index.insert_nodes(leaf_nodes)
        else:
            engine.vector_index = VectorStoreIndex(
                leaf_nodes, 
                storage_context=engine.storage_context,
                embed_model=engine.embed_model
            )
            
        # Persist the docstore
        engine.storage_context.persist(persist_dir=str(engine.storage_dir))
        
        # 2. Keyword Store (BM25) - only index leaf nodes
        # 优化: 不是每次都从 Chroma 全量拉取重建，而是将新增节点追加到现有的 BM25 中
        self._add_to_bm25(leaf_nodes, provider, api_key=api_key)
        
        return len(leaf_nodes)

    def _add_to_bm25(self, new_nodes: list, provider: str = "local", api_key: Optional[str] = None):
        """Incrementally adds new nodes to the existing BM25 index."""
        engine = self.db.get_engine(provider, api_key=api_key)
        
        def chinese_tokenizer(text):
            return list(jieba.cut(text))
            
        try:
            if engine.bm25_retriever is None:
                # If it doesn't exist, we fallback to rebuild (or init with these nodes)
                # In most cases of a fresh start, these are the only nodes anyway.
                logger.info(f"Initializing new BM25 index for {provider}")
                new_bm25 = BM25Retriever.from_defaults(
                    nodes=new_nodes, 
                    similarity_top_k=5, 
                    tokenizer=chinese_tokenizer
                )
                self.db.save_bm25(provider, new_bm25)
            else:
                # BM25 doesn't have a direct 'add_nodes' method in LlamaIndex out of the box.
                # Since LlamaIndex BM25 is just a wrapper around rank_bm25, 
                # appending is still safer than extracting everything from chromadb,
                # but we need to combine the nodes from the existing retriever 
                logger.info(f"Appending {len(new_nodes)} nodes to existing BM25 for {provider}")
                existing_nodes = engine.bm25_retriever.corpus_nodes
                # combine old and new
                all_nodes = list(existing_nodes) + new_nodes
                
                updated_bm25 = BM25Retriever.from_defaults(
                    nodes=all_nodes, 
                    similarity_top_k=5, 
                    tokenizer=chinese_tokenizer
                )
                self.db.save_bm25(provider, updated_bm25)
                
        except Exception as e:
            logger.error(f"Failed to add to BM25 for {provider}: {e}")
            # Fallback to full rebuild if incremental fails
            self._rebuild_bm25(provider, api_key=api_key)

    def _rebuild_bm25(self, provider: str = "local", api_key: Optional[str] = None):
        """Rebuilds the BM25 index for all documents of a specific provider. 
        Only used on document deletion."""
        engine = self.db.get_engine(provider, api_key=api_key)
        
        # Fetch all nodes from Chroma for this collection
        # Note: This is an expensive operation but ensures consistency for BM25
        try:
            collection_data = engine.chroma_collection.get()
            from llama_index.core.schema import TextNode
            all_nodes = []
            
            if collection_data and collection_data["documents"]:
                for i in range(len(collection_data["documents"])):
                    text = collection_data["documents"][i]
                    metadata = collection_data["metadatas"][i] if collection_data.get("metadatas") else {}
                    node_id = collection_data["ids"][i]
                    all_nodes.append(TextNode(text=text, id_=node_id, metadata=metadata))
            
            if all_nodes:
                def chinese_tokenizer(text):
                    return list(jieba.cut(text))
                
                new_bm25 = BM25Retriever.from_defaults(
                    nodes=all_nodes, 
                    similarity_top_k=5, 
                    tokenizer=chinese_tokenizer
                )
                self.db.save_bm25(provider, new_bm25)
                logger.info(f"BM25 index rebuilt for {provider} with {len(all_nodes)} nodes.")
        except Exception as e:
            logger.error(f"Failed to rebuild BM25 for {provider}: {e}")

    def delete_doc(self, doc_id: str, provider: str = "local", api_key: Optional[str] = None) -> bool:
        """Deletes all nodes associated with a doc_id from Chroma and rebuilds BM25."""
        engine = self.db.get_engine(provider, api_key=api_key)
        try:
            engine.chroma_collection.delete(where={"doc_id": doc_id})
            self._rebuild_bm25(provider, api_key=api_key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete {doc_id} from Chroma ({provider}): {e}")
            return False

    def clear_database(self, provider: str = "local", api_key: Optional[str] = None) -> bool:
        """Clears all vectors and BM25 for a specific provider."""
        engine = self.db.get_engine(provider, api_key=api_key)
        try:
            # Delete nodes from Chroma
            engine.chroma_collection.delete(where={})
            # Remove BM25 files
            if engine.bm25_dir.exists():
                shutil.rmtree(engine.bm25_dir)
            # Remove StorageContext files
            if engine.storage_dir.exists():
                shutil.rmtree(engine.storage_dir)
            # Reset engine state
            engine.vector_index = None
            engine.bm25_retriever = None
            return True
        except Exception as e:
            logger.error(f"Failed to clear database for {provider}: {e}")
            return False
