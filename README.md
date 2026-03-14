# KidsEduToy AI

儿童教育智能玩具 - AI应用层

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备知识库 (将txt文件放入 data/knowledge/)
mkdir -p data/knowledge/story
mkdir -p data/knowledge/knowledge

# 3. 构建向量索引
python scripts/build_index.py

# 4. 启动服务
python src/api.py

# 5. 测试
python scripts/test_api.py
```

## 项目结构

```
kids-edu-toy-ai/
├── src/
│   ├── modules/        # 核心模块
│   │   ├── asr.py      # 语音识别
│   │   ├── llm.py      # 大语言模型
│   │   ├── rag.py      # 检索增强
│   │   ├── tts.py      # 语音合成
│   │   └── chains.py   # LangChain编排
│   ├── api.py          # WebSocket服务
│   └── config.py       # 配置
│
├── data/
│   ├── knowledge/      # 知识库源文件
│   └── chroma/         # 向量数据库
│
├── models/
│   └── lora/           # LoRA权重
│
└── scripts/
    ├── build_index.py  # 构建索引
    └── test_api.py     # 测试
```

## WebSocket API

**端点:** `ws://<ip>:8000/ws`

**请求:**
```json
{
  "action": "chat",
  "data": {
    "text": "讲个故事",
    "session_id": "xxx",
    "context": {"child_age": 5}
  }
}
```

**响应 (流式):**
```json
{"type": "text_chunk", "data": {"text": "..."}}
{"type": "audio_chunk", "data": {"audio": "base64..."}}
{"type": "response_complete", "data": {"latency_ms": 650}}
```

## 配置

编辑 `src/config.py` 修改:
- LLM模型路径
- LoRA权重路径
- 向量库路径
- API端口等
