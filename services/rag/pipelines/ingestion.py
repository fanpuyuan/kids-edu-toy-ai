import os
import shutil
from pathlib import Path
from loguru import logger
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.retrievers.bm25 import BM25Retriever
from core.db import DBManager

class IngestionPipeline:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
        self.node_parser = SentenceSplitter(chunk_size=500, chunk_overlap=50)

    def ingest_file(self, file_path: str, doc_id: str = None):
        """Processes a single file and adds it to the ChromaDB and BM25 index."""
        logger.info(f"Starting ingestion for file: {file_path}")
        
        # Load document
        reader = SimpleDirectoryReader(
            input_files=[file_path],
            encoding="utf-8"
        )
        documents = reader.load_data()
        
        logger.info(f"Loaded {len(documents)} document objects. Extracting nodes...")
        
        # Parse into nodes (chunks)
        nodes = self.node_parser.get_nodes_from_documents(documents)
        logger.info(f"Generated {len(nodes)} nodes (chunks).")
        
        # Inject doc_id into Metadata to track lineage
        if doc_id:
            for node in nodes:
                node.metadata["doc_id"] = doc_id

        # 1. Insert into Vector Store
        if self.db.vector_index is None:
            # First time creating the index
            logger.info("Initializing new Vector Index...")
            self.db.vector_index = VectorStoreIndex(
                nodes,
                storage_context=self.db.storage_context,
                embed_model=self.db.embed_model
            )
        else:
            # Insert into existing index
            logger.info("Inserting nodes into existing Vector Index...")
            self.db.vector_index.insert_nodes(nodes)
        
        # 2. Rebuild BM25 Index
        # BM25Retriever in LlamaIndex currently needs to be re-initialized with all nodes
        # To do this correctly, we need to retrieve all nodes currently in the docstore.
        # For simplicity in this early version, we will fetch all docs from Chroma to rebuild BM25
        logger.info("Rebuilding BM25 Index...")
        self._rebuild_bm25()
        
        logger.info(f"Ingestion successful for {file_path}")
        return len(nodes)

    def _rebuild_bm25(self):
        """Fetches all documents from ChromaDB and rebuilds the BM25 index."""
        try:
            # Getting all documents currently in the vector store
            # LlamaIndex's Chroma store doesn't easily expose 'get_all_nodes', so we use the chroma client
            collection_data = self.db.chroma_collection.get()
            
            from llama_index.core.schema import TextNode
            all_nodes = []
            
            # Reconstruct nodes from Chroma dictionary format
            if collection_data and collection_data["documents"]:
                for i in range(len(collection_data["documents"])):
                    text = collection_data["documents"][i]
                    metadata = collection_data["metadatas"][i] if collection_data.get("metadatas") else {}
                    node_id = collection_data["ids"][i]
                    all_nodes.append(TextNode(text=text, id_=node_id, metadata=metadata))
            
            if all_nodes:
                import jieba
                # Standard BM25Retriever requires tokenizer for Chinese
                def chinese_tokenizer(text):
                    return list(jieba.cut(text))
                
                new_bm25 = BM25Retriever.from_defaults(
                    nodes=all_nodes, 
                    similarity_top_k=5, 
                    tokenizer=chinese_tokenizer
                )
                self.db.save_bm25(new_bm25)
                logger.info(f"BM25 rebuilt with {len(all_nodes)} nodes using jieba tokenizer.")
            else:
                logger.warning("No nodes found in ChromaDB to build BM25.")
        except Exception as e:
            logger.error(f"Failed to rebuild BM25: {e}")

    def clear_database(self):
        """Wipes the ChromaDB and deletes the BM25 pickle."""
        try:
            # Reset Chroma
            from llama_index.vector_stores.chroma import ChromaVectorStore
            from llama_index.core import StorageContext
            
            client = self.db.chroma_client
            client.delete_collection(self.db.chroma_collection_name)
            
            self.db.chroma_collection = client.get_or_create_collection(self.db.chroma_collection_name)
            self.db.vector_store = ChromaVectorStore(chroma_collection=self.db.chroma_collection)
            self.db.storage_context = StorageContext.from_defaults(vector_store=self.db.vector_store)
            
            self.db.vector_index = None # Reset in memory index
            
            
            # Reset BM25
            if self.db.bm25_path.exists():
                os.remove(self.db.bm25_path)
            self.db.bm25_retriever = None
            
            logger.info("Successfully cleared all Vector and BM25 databases.")
            return True
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            return False

    def delete_doc(self, doc_id: str) -> bool:
        """Deletes all chunks belonging to a specific doc_id from ChromaDB and rebuilds BM25."""
        try:
            # 1. Delete from Chroma vectors by metadata filter
            client = self.db.chroma_client
            collection = self.db.chroma_collection
            
            # LlamaIndex/ChromaDB typically allows deletion by where clause natively via chromadb
            collection.delete(where={"doc_id": doc_id})
            logger.info(f"Deleted vectors for doc_id: {doc_id} from ChromaDB")
            
            # 2. Rebuild BM25 to remove the deleted documents keywords 
            # (since BM25 is purely in-memory, we drop the whole index and rebuild it from the remaining chroma objects)
            logger.info("Rebuilding BM25 Index to purge deleted items...")
            self._rebuild_bm25()
            return True
        except Exception as e:
            logger.error(f"Failed to delete document vectors for doc_id {doc_id}: {e}")
            return False
