# LangChain Community 拆分迁移

## 背景

LangChain 已将 `langchain_community` 中的部分集成迁移到独立包，以降低
依赖耦合并独立发布版本。迁移通常涉及两层变化：

1. 导入路径从 `langchain_community.*` 改为独立包；
2. 类名或调用方式可能变化，需要结合业务代码验证行为。

规则表 `migration/rules/langchain_community.yaml` 负责定位需要检查的
文件，本文档提供迁移依据和示例。

## 导入迁移

向量存储：

```python
# Before
from langchain_community.vectorstores import Chroma

# After
from langchain_chroma import Chroma
```

```python
# Before
from langchain_community.vectorstores import PGVector

# After
from langchain_postgres import PGVector
```

```python
# Before
from langchain_community.vectorstores import Qdrant

# After
from langchain_qdrant import QdrantVectorStore
```

Embedding：

```python
# Before
from langchain_community.embeddings import HuggingFaceEmbeddings

# After
from langchain_huggingface import HuggingFaceEmbeddings
```

```python
# Before
from langchain_community.embeddings import OllamaEmbeddings

# After
from langchain_ollama import OllamaEmbeddings
```

模型：

```python
# Before
from langchain_community.chat_models import ChatOpenAI

# After
from langchain_openai import ChatOpenAI
```

```python
# Before
from langchain_community.chat_models import ChatOllama

# After
from langchain_ollama import ChatOllama
```

```python
# Before
from langchain_community.llms import Ollama

# After
from langchain_ollama import OllamaLLM
```

## 依赖包对照

| 迁移目标 | 安装包 |
| --- | --- |
| `langchain_chroma` | `langchain-chroma` |
| `langchain_postgres` | `langchain-postgres` |
| `langchain_qdrant` | `langchain-qdrant` |
| `langchain_pinecone` | `langchain-pinecone` |
| `langchain_huggingface` | `langchain-huggingface` |
| `langchain_ollama` | `langchain-ollama` |
| `langchain_openai` | `langchain-openai` |
| `langchain_anthropic` | `langchain-anthropic` |
| `langchain_google_genai` | `langchain-google-genai` |

迁移导入后，必须同步更新 `requirements.txt` 或 `pyproject.toml`，并确认
依赖版本与当前 LangChain 核心包兼容。

## 不是简单改导入的情况

以下场景需要人工确认，不能只按导入路径替换：

- 类名变化，例如 `Qdrant` 到 `QdrantVectorStore`；
- 构造函数或方法签名变化；
- `LLMChain`、旧 Agent 接口迁移到 LCEL；
- callback、streaming、structured output 行为变化。

LCEL 示例：

```python
# Before（示意）
chain = LLMChain(llm=llm, prompt=prompt)
result = chain.run(question)

# After（示意）
chain = prompt | llm
result = chain.invoke({"question": question})
```

这类改动应标记为 `high` 影响面并人工审批。

## 验证方法

1. 对每个修改过的文件执行 AST 语法验证；
2. 在隔离环境执行导入验证，例如
   `python -c "from langchain_chroma import Chroma"`；
3. 运行项目现有测试，重点覆盖向量存储、Embedding、模型调用；
4. 如果缺少测试，至少执行一次最小链路的加载、索引和查询；
5. 检查依赖锁文件，避免同一集成同时存在新旧两个包。

## 相关规则

- `migration/rules/langchain_community.yaml`：Community 导入迁移规则；
- `migration/rules/api_rules.yaml`：通用 Python 废弃 API 规则；
- `rules/README.md`：Agent 行为规则入口。
