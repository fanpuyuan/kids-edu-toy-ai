# RAG Service (知识检索与层次化记忆库)

**源码位置**: `services/rag/`
**框架**: `FastAPI`, `LlamaIndex`, `ChromaDB`, `HuggingFace Transformers`, `Unstructured`
**网络角色**: 被动数据仓库服务。负责存储长、短期以及个人状态数据，同时负责耗费资源的 NLP 切词入库运算。

## 核心机制架构设计
为了降低在 Windows 等宿主机环境中的复杂部署维护难度，所有的 C++ 底层解析依赖 (poppler, ocr 等) 都被封锁在了独立构建的 Linux 容器中运行。在框架底层选型上，摒弃了 LangChain RAG ，采用了被公认专用于检索的工业级重器：**LlamaIndex** 以及其背后的**双端混合索引技术**。

### 1. 三层文件化系统记忆池 (Hierarchical Markdown Memory)
完全不依赖于外部诸如 Neo4j 或者复杂的 RDBMS 图数据库，一切以最纯粹的 `.md` 文本形式托管，保证人类直观直接可调阅性。
- `data/SYSTEM.md`：核心最高指令池（存放着底层人设限制）。例如禁止任何暴力暗示，用儿童拟人化口吻强制回复。
- `data/FAMILY.md`：用户（家长在后台）维护的一个表。用于存储特定知识，如小主人叫做“糖糖”，六岁，对花生极度过敏等知识。
- `data/SNAPSHOT.md`：动态滑动窗口总结，存放历史对话产生的概要信息。
- 提供 `/memory/{layer}` API 作为读写对接口。

### 2. Pipeline 1: 多模态文档摄入管道 (Ingestion, 写入过程)
**入口请求方法**: `POST /upload_doc`
- **解析层 (Parser)**：采用重量级的 `unstructured` 框架。无论是用户上传的图片 PDF、繁体字 Docx 等不规范材料都能提取出平整的纯字符串流。
- **切割层 (Chunking)**：防止儿童故事中的情感在句子半截被打断丧失前置指代关系，配置为平缓切段策略 （每个文本块上限规定大约为 500-800 字，留余大约 50 字的安全重叠区）。
- **双模态入库引擎**：
    - **向量入库**：使用 HuggingFace `BAAI/bge-large-zh` 中文语义模型构建多维张量，压入 ChromaDB 轻量数据库中。
    - **字词入库**：启用倒排词树 BM25(Jieba 分词)。因为在“找孙悟空第十八页讲了什么”这类问题中，大语言模型生成的纯向量距离判断经常对于特殊名词敏感度欠缺，这里使用双备份保障命中。

### 3. Pipeline 2: 混合检索搜索管道 (Retrieval, 查询过程)
**入口请求方法**: `GET /retrieve?query=...`
- **混合重排 (RRF Fusion Algorithm)**: 
  由外部 Brain 层带进来用户的泛意图问题后。程序将在同一时间点：向 ChromaDB 询问在向量语义上最接近的点排前 5，向 BM25 词库系统询问关键名词词频最接近的文章片段也排前 5。
- **取消大模型查询改写依赖 (MockLLM 隔离)**: 
  LlamaIndex 的 `QueryFusionRetriever` 默认会尝试加载 OpenAI 进行 Query 重写。为了保持 RAG 服务的独立性并且避免由于缺少 API 密钥导致的 `500 Internal Server Error` 崩溃，在初始化该检索器时，显式配置了 `num_queries=1` (跳过问题改写步骤) 并注入了一个 `MockLLM` 作为占位符，完美隔离了检索层与生成层的 LLM 耦合。
- 将两套系统给出的合集文本块，使用倒数排名合并公式重新算出 Top-K 最具备价值的。
- 最终给原文添加出处 `Citation` 标记后返回到 JSON 給 Brain 节点消费。
