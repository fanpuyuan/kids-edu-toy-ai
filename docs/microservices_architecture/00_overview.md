# 玩具微服务架构概览 (Overall Microservices Architecture)

本项目经历重大重构后，不仅采用了 Docker Compose 隔离出标准的微服务层，还在中枢逻辑上进行了**能力增强与职责整合**，以提供更高质量的幼教陪聊体验。

## 系统拓扑图 (Topology)

```mermaid
graph TD
    User([终端用户/实体玩具端]) -->|WebSocket音频流| Gateway[Gateway 网关: 8000]
    User_Web([家长控制台]) -->|HTTP 网页| Frontend[Web前端 UI: 8501]
    
    %% 前端将配置和交互指令统一发往网关
    Frontend -->|HTTP /config 设置代理| Gateway
    Frontend -->|HTTP /upload 资料上传| Gateway
    Frontend -->|HTTP /clone_voice 上传录音| Gateway
    
    subgraph Kids-AI-Net [Docker 内部隔离网络 (kids-ai-net)]
        Gateway[\Gateway API 心跳网关 <br> + 全局配置 SQLite 库\] 
        
        Gateway -->|HTTP POST| ASR[ASR 语音转文本: 8001]
        Gateway -->|HTTP POST| TTS[TTS 双引擎合成: 8002]
        Gateway -->|HTTP POST| Brain[Brain 思维调度: 8004]
        Gateway -->|HTTP POST| RAG[RAG 知识库检索: 8003]
        
        Brain -->|HTTP 查询| RAG
        Brain -->|HTTP 推理| Ollama[Ollama 本地/云端大模型接口]
        
        %% TTS 内部双引擎
        TTS -.->|直连外网| Edge[Edge-TTS API]
        TTS -.->|直连外网| Cosy[阿里云 CosyVoice大模型]
    end
```

## 服务角色与功能演进
| 服务名称 | 暴露端口 | 核心职责描述 |
|---|---|---|
| **Gateway** | `8000` | **全区总管。** 维持与前端、玩具的异步 WebSocket 心跳。**新增：**内置 `gateway.db` 管理全局配置（大模型设置、Voice ID、API Key等），所有底层服务所需的配置都由网关在请求时动态注入。 |
| **Frontend** | `8501` | **无状态展示层。** 控制台 UI。不仅能传文档，**新增：**提供独立的 CosyVoice 声音克隆界面、长短记忆管理面板，以及云端/本地大模型的切换开关。 |
| **ASR Service** | `8001` (内网) | 接收音频二进制流，高精度离线翻译为中文字符串，支持 VAD 断句。 |
| **TTS Service** | `8002` (内网) | **发声器官。** 接收文本流，**新增：**支持动态路由。根据网关传来的参数，可选用免费的 Edge-TTS，或调用阿里云 DashScope CosyVoice 进行零样本(Zero-shot)私有声音克隆合成。 |
| **RAG Service** | `8003` (内网) | **专属记忆库。** 被剥离了系统配置职责，现在纯粹专注于 ChromaDB 向量存储与文档切割提取。 |
| **Brain Service** | `8004` (内网) | **思考中枢。** 使用 LangGraph 路由不同层级思考，决定调用本地 Ollama 还是云端 Qwen 接口。 |
