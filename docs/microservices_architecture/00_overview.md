# 玩具微服务架构概览 (Overall Microservices Architecture)

本项目目前已经从早期紧凑的单体应用，全面重构为基于 Docker Compose 的微服务架构。主要目的是**降低服务耦合**、**支持组件独立扩展**，以及隔离复杂环境依赖。

## 系统拓扑图 (Topology)

```mermaid
graph TD
    User([终端用户/实体玩具]) -->|WebSocket/HTTP| Frontend[Web前端: 8501]
    User -->|WebSocket| Gateway[Gateway API 网关: 8000]
    
    Frontend -->|HTTP| Gateway
    
    subgraph Kids-AI-Net [Docker 内部网络 (kids-ai-net)]
        Gateway -->|HTTP POST| ASR[ASR 语音转文字服务: 8001]
        Gateway -->|HTTP POST| TTS[TTS 文字转语音服务: 8002]
        Gateway -->|HTTP POST| Brain[Brain 大脑思维调度服务: 8004]
        Gateway -->|HTTP| RAG[RAG 知识库与记忆服务: 8003]
        
        Brain -->|HTTP POST /retrieve| RAG
        Brain -->|HTTP POST /generate| Ollama[Ollama 本地大模型基座: 11434]
    end
```

## 服务端口与功能清单
| 服务名称 | 暴露端口 | 核心技术栈 | 主节点职责描述 |
|---|---|---|---|
| **Gateway** | `8000` | FastAPI, WebSockets | 唯一的对外收发枢纽，维持全双工心跳，异步分发音频流与前端 HTTP 请求。 |
| **Frontend** | `8501` | Streamlit | Web 控制台 UI。管理模型参数、上传私有本地知识库，与家长人设大纲交互。 |
| **ASR Service** | `8001` (内网) | FastAPI, SenseVoiceSmall | 接收二进制音频流，离线精准识别为中文字符串，自动断词断句。 |
| **TTS Service** | `8002` (内网) | FastAPI, edge-tts | 接收大模型字符流，调用线上接口返回合成波形。 |
| **RAG Service** | `8003` (内网) | FastAPI, LlamaIndex, ChromaDB | 提供长短文本混合检索倒排，管理三层系统记忆 (SYSTEM/FAMILY/SNAPSHOT)。 |
| **Brain Service** | `8004` (内网) | FastAPI, LangGraph | 使用状态机路由 LLM 思考逻辑（闲聊 vs 查资料），决定是否触发知识库工具。 |
| **Ollama** | `11434` (内网) | Ollama (C++) | 提供开箱即用的本地大语言模型高速推理引擎 (Qwen 等模型)。 |
