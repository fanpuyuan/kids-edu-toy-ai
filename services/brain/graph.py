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
    context: str # The RAG context
    hardware_context: dict # The hardware-provided context (e.g., child's age)
    response: str
    session_id: str
    config: Dict # 存储模型和参数

from langchain_openai import ChatOpenAI

# 获取 LLM 实例的辅助函数
def get_llm(state: GraphState):
    config = state.get("config", {})
    model = config.get("model") or LLM_MODEL
    temp = config.get("temperature", 0.7)
    env = config.get("llm_env", "local")
    api_key = config.get("llm_api_key", "")
    
    if env == "cloud":
        base_url = None
        if "deepseek" in model.lower():
            base_url = "https://api.deepseek.com/v1"
        elif "glm" in model.lower():
            base_url = "https://open.bigmodel.cn/api/paas/v4"
            
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temp,
            max_tokens=1024,
            streaming=True
        )
    else:
        # Default Local Ollama
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(model=model, base_url=OLLAMA_HOST, temperature=temp, streaming=True)

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
    elif "qa" in intent or "knowledge" in intent or "info" in intent: intent = "qa"
    elif any(kw in state["input"] for kw in ["文件", "时间表", "知识库", "有没有", "是什么"]): intent = "qa" # 强制触发
    else: intent = "chat"
    
    logger.info(f"Session {state['session_id']} Intent: {intent}")
    return {"intent": intent}

async def retrieve(state: GraphState):
    """节点 2: RAG 检索 (通过 HTTP 调用 RAG Service)"""
    if state["intent"] not in ["story", "qa"]:
        return {"context": ""}
    
    logger.info(f"正在检索 RAG 知识: {state['input']} (Provider: {state['config'].get('embedding_provider', 'local')})")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(
                f"{RAG_URL}/retrieve", 
                json={
                    "query": state["input"], 
                    "top_k": 3,
                    "embedding_provider": state["config"].get("embedding_provider", "local"),
                    "embedding_api_key": state["config"].get("embedding_api_key", "")
                }
            )
            data = res.json()
            results = data.get("results", [])
            
            # 格式化带引用的上下文
            context_parts = []
            for i, item in enumerate(results):
                context_parts.append(f"[引用{i+1}] {item['content']} (来源: {item['source']})")
                
            context = "\n\n".join(context_parts)
            return {"context": context}
        except Exception as e:
            logger.error(f"RAG Retrieval failed: {e}")
            return {"context": ""}

async def fetch_memory() -> dict:
    """获取三层 Markdown 记忆"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{RAG_URL}/memory/all")
            if res.status_code == 200:
                return res.json()
    except Exception as e:
        logger.error(f"Failed to fetch memory from RAG service: {e}")
    return {"system": "你是活泼的AI早教伙伴。", "family": "", "snapshot": ""}

from langchain_core.runnables import RunnableConfig

async def generate(state: GraphState, config: RunnableConfig):
    """节点 3: 生成回答"""
    intent = state["intent"]
    context = state["context"]
    
    # 动态拉取记忆
    memory = await fetch_memory()
    sys_base = memory.get("system", "你是活泼的AI早教伙伴。")
    fam_base = memory.get("family", "")
    snap_base = memory.get("snapshot", "")
    
    # 注入记忆拦截提示词
    instructions = (
        "\n\n[隐藏任务：自我记忆]\n"
        "如果在对话中发现了关于用户的新特征、新偏好或重要事件，"
        "你必须在回答的最末尾加上特定标签来记录它。\n"
        "【警告】为了防止玩具读出这段代码，你必须在你所有对小孩的对话之后，输入分隔符 `|||`，然后再输出标签。\n"
        "格式：对小孩的话 ||| <UPDATE_MEMORY>简短总结新特征</UPDATE_MEMORY>\n"
        "例如：好的，我陪你玩！ ||| <UPDATE_MEMORY>我不喜欢吃胡萝卜</UPDATE_MEMORY>\n"
        "如果没有需要记忆的新信息，绝对不要输出 ||| 和这个标签！"
    )
    
    # 组装超级 System Prompt
    hw_ctx_str = f"\n\n[玩具环境变量]\n{state.get('hardware_context', {})}" if state.get("hardware_context") else ""
    full_system = f"{sys_base}\n\n[家庭档案]\n{fam_base}\n\n[近期记忆快照]\n{snap_base}{hw_ctx_str}{instructions}"
    
    if intent == "story" and context:
        prompt = ChatPromptTemplate.from_messages([
            ("system", full_system),
            ("human", "基于以下素材为我讲个故事。\n素材：\n{context}\n\n我的请求：{input}")
        ])
    elif intent == "qa" and context:
        prompt = ChatPromptTemplate.from_messages([
            ("system", full_system),
            ("human", "基于以下知识精准回答我的问题，不要编造。\n知识：\n{context}\n\n我的问题：{input}")
        ])
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", full_system),
            ("human", "{input}")
        ])
    
    llm = get_llm(state)
    # 打上唯一的 Tag，让 main.py 中的 astream_events 知道这是允许发给前端发音的文本
    chain = prompt | llm.with_config({"tags": ["generate_output"]}) | StrOutputParser()
    response = await chain.ainvoke({
        "input": state["input"],
        "context": context
    }, config=config)
    
    # ---------------- 核心：记忆拦截器 ----------------
    import re
    memory_match = re.search(r'<UPDATE_MEMORY>(.*?)</UPDATE_MEMORY>', response, re.DOTALL)
    if memory_match:
        new_memory = memory_match.group(1).strip()
        # 将标签从返回结果中剥离，避免 TTS 读出来
        response = re.sub(r'<UPDATE_MEMORY>.*?</UPDATE_MEMORY>', '', response, flags=re.DOTALL).strip()
        
        # 将截获的记忆发送到 RAG Service 追加进入快照
        logger.info(f"拦截到 AI 自助记忆: {new_memory}")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{RAG_URL}/memory/snapshot/append", 
                    data={"content": f"- {new_memory}"} # Form 字段，附带 Markdown 列表格式
                )
        except Exception as e:
            logger.error(f"AI Auto-Memory updating failed: {e}")
    # ---------------------------------------------------
            
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

