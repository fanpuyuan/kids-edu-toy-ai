# KidsEduToy AI (儿童教育智能玩具 - AI应用层)

KidsEduToy AI 是一款面向儿童教育的智能玩具后端AI应用系统。项目采用**微服务架构**与**Docker容器化部署**，集成了语音识别(ASR)、大语言模型处理(LLM)、检索增强生成(RAG)与语音合成(TTS)，并通过 WebSocket 为硬件玩具或前端UI提供低延迟的流式交互体验。

## 🌟 核心特性

- **微服务架构设计**：全系统拆分为 7 个独立 Docker 容器（Gateway, Brain, RAG, ASR, TTS, Frontend, Ollama），高度解耦，易于扩展与维护。
- **全栈流式交互 (WebSocket)**：网关层提供全双工 WebSocket 接口，支持语音/文本输入，并流式传回文本分块与音频分块，实现近似真人的对话延迟。
- **智能大脑编排 (LangGraph)**：基于 LangGraph 构建的状态机，自动进行意图分类（故事、问答、日常聊天），按需调度 RAG 检索引擎，支持无缝切换本地大模型 (Ollama) 与云端 API (DeepSeek/GLM-4)。
- **混合检索与三层记忆 (RAG)**：
  - **文档库**：支持多格式解析上传，采用混合检索（ChromaDB 向量 + BM25 关键词）。
  - **记忆机制**：创新的三层 Markdown 记忆架构（SYSTEM 核心人设、FAMILY 家庭档案、SNAPSHOT 近期快照）。AI 可在对话中通过隐式标签自动更新孩子的偏好记录。
- **开箱即用的控制台**：内置基于 Streamlit 的可视化 Web 控制台，方便调试对话、管理知识库与编辑玩具记忆体系。

## 🏗️ 系统架构与微服务

| 服务名称 | 端口 | 说明 | 核心依赖技术 |
| - | - | - | - |
| **Gateway** | 8000 | 对外 WebSokcet 网关，转发请求，编排微服务调用 | FastAPI, WebSockets |
| **Frontend** | 8501 | Web 测试控制台 (模拟玩具终端交互与后台管理) | Streamlit |
| **Brain** | 8004 | AI 核心逻辑引擎，处理意图分类、记忆注入、LLM 调用 | LangGraph, LangChain |
| **RAG** | 8003 | 知识检索、文件入库解析、长期/短期记忆层管理 | ChromaDB, LlamaIndex, SQLite |
| **ASR** | 8001 | 独立语音识别服务 (音频转文本) | FunASR (Paraformer) |
| **TTS** | 8002 | 独立语音合成服务 (文本转语音流) | Edge-TTS |
| **Ollama** | 11434 | 本地的大语言模型推理引擎 | Ollama (兼容 Nvidia GPU) |

## 🚀 快速开始

### 1. 环境准备
- 确保系统已安装 **Docker** 和 **Docker Compose**。
- 如需使用本地 GPU 加速大模型推理，请确保系统已安装 NVIDIA 驱动以及 NVIDIA Container Toolkit。

### 2. 一键启动服务
在项目根目录下执行以下命令：
```bash
# 以后台模式构建并启动所有容器
docker-compose up -d --build
```
启动后，系统会自动创建 `kids-ai-net` 网络桥接各服务，并挂载对应的缓存卷到 `data/` 目录下，以持久化向量库、模型权重和用户记忆。

### 3. 访问交互界面
- **Web 控制台 (推荐)**：在浏览器中打开 `http://localhost:8501` 进入可视化页面，进行测试对话、知识库上传管理，或拉取 Ollama 模型。
- **WebSocket 接口**：供实际硬件终端连接，地址为 `ws://localhost:8000/ws`。

## 📡 WebSocket API 协议

提供给智能玩具硬件终端接入的交互接口。

**连接端点:** `ws://<宿主机IP>:8000/ws`

**1. 客户端发送 (文字/语音请求):**
```json
{
  "action": "chat", // "chat" 文本聊天 / "audio" 语音聊天
  "session_id": "kids_session_001",
  "data": {
    "text": "讲个关于大灰狼的故事", // 当 action 为 audio 时，此字段变为 "audio": "base64音频字符串"
    "context": {"child_age": 5}
  },
  "config": {
    "llm_env": "local",          // 环境：local (Ollama) 或 cloud (API)
    "llm_model": "qwen3.5:2b",   // 模型选择
    "tts_voice": "zh-CN-XiaoxiaoNeural"
  }
}
```

**2. 服务端下发 (流式响应):**
```json
// 返回语音识别结果（如果是 audio 语音输入）
{"type": "asr_result", "data": {"text": "讲个关于大灰狼的故事"}}

// 返回思考生成的文本流
{"type": "text_chunk", "data": {"text": "很久很久以"}}
{"type": "text_chunk", "data": {"text": "前，森林里..."}}

// 返回语音合成流（可直接播放的音频块）
{"type": "audio_chunk", "data": {"audio": "base64_encoded_audio_bytes..."}}

// 响应全部结束标识
{"type": "response_complete", "data": {"full_text": "很久很久以前，森林里..."}}
```

## 🛠️ 项目目录说明

```text
kids-edu-toy-ai/
├── data/                  # 持久化数据与缓存目录 (知识库、模型缓存、SQLite等)
├── docs/                  # 详细架构图与深入服务设计文档集
├── services/              # 核心分布式微服务代码集
│   ├── asr/               # 语音识别处理服务
│   ├── brain/             # LangGraph 问答引擎与意图路由中心
│   ├── frontend/          # Web 测试展现台 (Streamlit)
│   ├── gateway/           # API Ws 网关服务节点
│   ├── rag/               # 知识检索与记忆管理服务核心
│   └── tts/               # 语音流合成服务
├── docker-compose.yml     # 容器服务全栈编排配置文件
└── requirements.txt       # 项目核心组件参考表 (各服务内拥有独立的运行依赖清单)
```

## 📝 特色：AI 自动记忆捕获机制
本项目实现了一套“自主长期人像学习”算法，记录用户偏好与特征：
`Brain` 服务在其 LangGraph 执行最后节点，注入了自我记忆规则。当 AI 根据孩子对话，分辨出全新的兴趣特征或性格时，它会在不可见的底层返回附加大括号语义，如 `<UPDATE_MEMORY>我不喜欢吃青椒</UPDATE_MEMORY>`。拦截模块会自动将其摘除，以免被朗读，随后自动推送到 RAG-Memory 数据库的 SNAPSHOT 记忆层中永久记录，赋予玩具真正成长的特征。

## ⚠️ 部署配置建议
1. **纯本地化算力部署**：推荐主机环境内存 >= 16GB。因为同时运行 FunASR 识别、大语言模型 Ollama 和 RAG 数据解析会导致内存的高占用。
2. **轻量云服务器部署**：若部署在 2核2G 规格的低配云服务器上执行，可能会遇到 OOM (Out Of Memory) 崩溃。此时建议修改 Frontend 与 Backend 偏好配置，转用 `Cloud (API)` 模型，使用提供商的外部大模型 API 以节省运行资源。
