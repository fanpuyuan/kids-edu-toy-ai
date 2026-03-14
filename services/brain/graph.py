from typing import Annotated, TypedDict, List, Dict
import os
import httpx
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from loguru import logger

# 环境变量
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
RAG_URL = os.getenv("RAG_URL", "http://rag-service:8003")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")

class GraphState(TypedDict):
    """LangGraph 状态定义"""
    input: str
    chat_history: List[BaseMessage]
    intent: str
    context: str
    response: str
    session_id: str
    config: Dict # 存储模型和参数

# 获取 LLM 实例的辅助函数
def get_llm(state: GraphState):
    model = state.get("config", {}).get("model") or LLM_MODEL
    temp = state.get("config", {}).get("temperature", 0.7)
    return ChatOllama(model=model, base_url=OLLAMA_HOST, temperature=temp)

async def classify_intent(state: GraphState):
    """节点 1: 意图分类"""
    prompt = ChatPromptTemplate.from_template(
        "分析以下儿童输入的意图，只返回标签: story, qa, chat。\n输入: {input}\n意图:"
    )
    llm = get_llm(state)
    chain = prompt | llm | StrOutputParser()
    intent_raw = await chain.ainvoke({"input": state["input"]})
    intent = intent_raw.lower().strip()
    
    # 归一化意图
    if "story" in intent: intent = "story"
    elif "qa" in intent: intent = "qa"
    else: intent = "chat"
    
    logger.info(f"Session {state['session_id']} Intent: {intent}")
    return {"intent": intent}

async def retrieve(state: GraphState):
    """节点 2: RAG 检索 (通过 HTTP 调用 RAG Service)"""
    if state["intent"] not in ["story", "qa"]:
        return {"context": ""}
    
    logger.info(f"正在检索 RAG 知识: {state['input']}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(
                f"{RAG_URL}/retrieve", 
                json={"query": state["input"], "k": 3, "category": state["intent"]}
            )
            docs = res.json()
            context = "\n".join([d["page_content"] for d in docs])
            return {"context": context}
        except Exception as e:
            logger.error(f"RAG Retrieval failed: {e}")
            return {"context": ""}

async def generate(state: GraphState):
    """节点 3: 生成回答"""
    intent = state["intent"]
    context = state["context"]
    
    if intent == "story":
        prompt = ChatPromptTemplate.from_template("你是讲故事专家。基于以下素材为孩子讲个故事：\n素材：{context}\n请求：{input}\n故事：")
    elif intent == "qa":
        prompt = ChatPromptTemplate.from_template("你是百科老师。基于以下知识回答孩子：\n知识：{context}\n问题：{input}\n回答：")
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是活泼的AI玩具伙伴。"),
            ("human", "{input}")
        ])
    
    
    llm = get_llm(state)
    chain = prompt | llm | StrOutputParser()
    response = await chain.ainvoke({
        "input": state["input"],
        "context": context
    })
    return {"response": response}

def build_graph():
    """构建状态机"""
    workflow = StateGraph(GraphState)
    
    # 添加节点
    workflow.add_node("classify", classify_intent)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)
    
    # 设置入口
    workflow.set_entry_point("classify")
    
    # 添加边
    workflow.add_edge("classify", "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)
    
    return workflow.compile()

# 导出编译好的 Graph
story_graph = build_graph()
