# 知识库

本目录存放迁移 Agent 使用的内置知识文档，按“档案 + 主题”组织。
知识库只提供检索证据和迁移说明，不会自动产生 AST 扫描规则。

## 目录说明

| 目录 | 内容 | 加载方式 |
| --- | --- | --- |
| `py2to3/` | Python 2 到 Python 3 语法迁移 | `py2to3` 档案默认加载 |
| `py3_upgrade/` | Python 3.x 升级、废弃 API 与新语法 | `py3_upgrade` 档案默认加载 |
| `langchain/` | LangChain Community 包拆分与 API 迁移 | `langchain_community` 档案默认加载 |
| `topics/` | 并发、内存、风险、验证等通用实践 | 所有档案默认加载 |

## 加载规则

- 未传 `--docs` 时，自动加载当前档案的 `knowledge_base` 列表；
- 传入 `--docs` 时，在档案默认知识库之外追加文档，不会覆盖默认目录；
- `--docs` 可以指定文件或目录，也可以重复传入：

```powershell
.venv\Scripts\python.exe main.py `
  --source D:\legacy `
  --output D:\migrated `
  --docs D:\docs\company-standard `
  --docs D:\docs\langchain_upgrade.md `
  --agentic
```

## 支持格式

- Markdown：`.md`
- 纯文本：`.txt`
- PDF：`.pdf`，需要安装 `pypdf`

```powershell
.venv\Scripts\python.exe -m pip install pypdf
```

## 缓存

导入后的知识库缓存在 `config.yaml` 的 `retrieval.kb_dir` 下，默认：

```text
kb/
├─ kb.json      # 文档清单与内容
└─ chroma/      # 可选的向量索引
```

`kb/` 已被 `.gitignore` 忽略，不需要提交。

## 从文档生成规则

知识文档不会自动决定扫描哪些文件。需要生成 API 规则时使用：

```powershell
.venv\Scripts\python.exe -m migration.rule_author `
  --docs D:\docs\pandas_upgrade.md `
  --profile-name pandas_upgrade `
  --verify-against D:\samples\pandas_legacy
```

生成候选规则和候选档案后，人工确认，再使用 `--approve` 启用。
详细规则见 `migration/rules/README.md`。
