# RAG 服务测试策略与诊断指南

本文档记录了 Kids Edu Toy AI 项目中 RAG (Retrieval-Augmented Generation) 服务的常见问题诊断结论以及系统性的测试方案。

## 1. 常见问题诊断

### 1.1 `BM25 Retriever is missing` 警告分析

**现象原因：**
在 `rag_service` 启动或接收检索请求时，如果日志中出现 `BM25 Retriever is missing. Falling back to Vector-only search.` 的警告，这属于**正常的预期行为，并非代码 Bug**。

**详细原委：**
1. 系统的混合检索依赖两个索引库：**ChromaDB 向量库**（持久化为本地文件夹）和 **BM25 关键词倒排索引库**（由 LlamaIndex 构建后序列化为本地 `data/bm25_index.pkl`）。
2. 当系统初次部署启动，且还未向知识库中上传任何文档时，`data` 目录下不存在 `bm25_index.pkl` 文件。
3. 因此在实例化混合 Retriever 时，系统检测到 BM25 对象缺失，为了保证检索功能不立刻抛错中断，会退化为纯 Vector（向量）检索模式，并打印上述警告。

**解决与消除方法：**
此告警无需修改代码修复。您只需要在系统中**成功上传至少一个知识库文档**。上传流水线 (`ingestion.py` 的 `_rebuild_bm25`) 会自动从当前的 ChromaDB 里全量提取文本，为您重建 BM25 索引并持久化。此后的检索将自动恢复为双路混合检索状态，该警告也会随之消失。

---

## 2. RAG 服务系统性测试方案 (Testing Strategy)

为了保障儿童玩具 RAG 问答系统的准确性、安全性和性能，测试方案必须包含以下几个维度：

### 2.1 纯检索能力测试 (Retrieval Evaluation)
此阶段无需大语言模型 (LLM) 参与生成，专注于评估“找得准不准”。

*   **推荐测试框架**: `Ragas` 或 `LlamaIndex Evaluation`
*   **核心测试指标**:
    *   **Context Precision (上下文精度)**: 检索返回的 top-k 知识片段中，有多少是实际回答问题所必需的（信噪比）。
    *   **Context Recall (上下文召回率)**: 回答该问题必需的所有知识点，是否被完全检索到了 top-k 中。
*   **执行方式**:
    构建测试集 (Ground Truth Dataset)，每条数据包含“测试问题”和“预期的答案文档ID”。通过脚本批量发起检索，统计预期文档在检索结果中的命中率和排位。

### 2.2 生成质量与安全测试 (Generation Evaluation)
评估 LLM 根据检索到的上下文生成最终答案的质量，防范 AI “胡说八道”。

*   **推荐测试框架**: `TruLens` 
*   **核心测试指标 (RAG 三元组)**:
    *   **Faithfulness (忠实度/幻觉检测)**: 验证 LLM 回答的每一句话是否都能在检索出的上下文中找到明确支撑。出现毫无依据的幻觉即扣分。
    *   **Answer Relevance (回答相关度)**: 评估生成的答案是否直接回答了用户的提问，有无答非所问。
    *   **Context Relevance (上下文相关度)**: 评估检索出的上下文对当前问题是否有用。

### 2.3 端到端功能逻辑单元测试 (Unit & Integration Tests)
属于传统的软件工程保障，确保代码流转不中断。

*   **推荐测试框架**: `pytest`
*   **核心测试用例清单**:
    1.  **上传编解码测试**: 上传包含特殊中文字符及标点的 `.txt`/`.md` 文件，断言 HTTP 返回状态，并调取 SQLite `list_docs` 检查是否成功落库且无 `UnicodeDecodeError` 崩溃。
    2.  **清理与同步测试**: 调用清空数据库接口 (`/clear_db`) 或单文档删除接口 (`/delete_doc`)。直接查询底层的 ChromaDB 和 SQLite，确保数据干净清除，且不会引发下一次上传的内存状态污染。
    3.  **多层记忆库流转 (Memory)**: 调用 `/memory/update` 并写入测试记忆字段，随后立刻调取 `/memory/all`，断言返回的完整 Prompt 结构正确包裹了该记忆字段。

### 2.4 性能与压力测试 (Stress Testing)
针对儿童玩具智能硬件并发场景。

*   **推荐测试框架**: `Locust` 或 `JMeter`
*   **核心测试用例清单**:
    *   **多端并发连接**: 模拟多台设备（如 50-100 台）同时建立 WebSocket 连接，触发群发消息，观察后端的句柄消耗、内存水位以及队列阻塞情况。
    *   **长程多轮对话挑战**: 自动化脚本持续发送 100+ 轮极短闲聊内容（如“然后呢？”、“为什么？”），测试系统的 `chat_history` 截断逻辑是否正确生效，防止最终 Prompt 过长被大模型服务拒绝 (Token Limits)。
