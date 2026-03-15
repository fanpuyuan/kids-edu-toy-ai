from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.llms.mock import MockLLM
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.base.base_retriever import BaseRetriever

class DummyRetriever(BaseRetriever):
    def _retrieve(self, q): return [NodeWithScore(node=TextNode(text='dummy'), score=1.0)]

retriever = QueryFusionRetriever(retrievers=[DummyRetriever()], llm=MockLLM(), num_queries=1)
print('Success! Retriever initialized.')
results = retriever.retrieve('test query')
print('Success! Retrieval executed. Result length:', len(results))
