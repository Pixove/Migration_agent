# LangChain Community 迁移示例

本示例模拟使用 LangChain Community 集成包的遗留项目，用于验证
`migration/rules/langchain_community.yaml` 能正确识别需要迁移的导入。

示例包含：

- 向量存储：`Chroma`、`PGVector`、`Pinecone`、`Qdrant`；
- Embedding：`HuggingFaceEmbeddings`、`HuggingFaceBgeEmbeddings`、
  `OllamaEmbeddings`、`OpenAIEmbeddings`；
- Chat 模型：`ChatOllama`、`ChatOpenAI`、`ChatAnthropic`、
  `ChatGoogleGenerativeAI`；
- LLM：`Ollama`、`OpenAI`、`Anthropic`。

## 扫描信号

```powershell
.venv\Scripts\python.exe -c "from pathlib import Path; from migration.registry import load_profile; from migration.scan_signals import rules_paths_for_profile, scan_python_signals; src=Path('examples/langchain_legacy/app.py'); rules=list(rules_paths_for_profile(load_profile('langchain_community').rules)); print(scan_python_signals(src.read_text(encoding='utf-8'), 'app.py', rules_path=rules))"
```

预期得到 15 个 `deprecated_api` 信号，每个信号包含原模块、符号名和
建议迁移到的独立包。这些规则只在 `langchain_community` 档案下加载。

## 迁移说明

迁移方法见 `knowledge_base/langchain/01_langchain_community_拆分迁移.md`。
本示例只用于扫描和规则验证，不要求在当前环境安装 LangChain 依赖。
