# Migration Agent

企业级代码库现代化迁移 Agent。用户通过双路径 CLI 指定待迁移项目
（只读）和输出目录（唯一可写），由 LLM 生成迁移方案，harness 负责
校验、执行、验证、回滚与审计。

## 核心能力

- Python 2→3、Python 3.x 升级和 LangChain Community 包拆分迁移；
- RAG 混合检索：BM25 + 向量语义检索 + Cross-Encoder 重排；
- Agentic 与固定流水线两种运行模式；
- 证据校验、路径沙箱、工具白名单、预算和人工审批；
- 语义编辑、自动评审、AST 验证和失败回滚；
- 规则表与迁移档案数据驱动，可按生态扩展；
- 支持从知识文档生成候选规则和候选档案；
- 检索、迁移、Agentic、编辑、规则覆盖和端到端质量评估。

## 快速开始

### 1. 准备环境

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

向量检索和重排默认关闭；PDF 解析需要额外安装 `pypdf`。
依赖说明见 `docs/03_配置说明.md`。

### 2. 配置大模型

编辑 `config.yaml` 的 `llm` 段，支持 OpenAI 兼容服务与 Ollama。
API Key 通过环境变量提供：

```powershell
$env:OPENAI_API_KEY = "你的密钥"
```

DeepSeek 等 OpenAI 兼容服务可直接修改 `base_url`、`api_key_env` 和
`model`，具体示例见 `docs/03_配置说明.md`。

### 3. 运行迁移

对话引导模式，不需要在命令行传路径：

```powershell
.venv\Scripts\python.exe main.py --chat --agentic
```

也可以显式指定路径和档案：

```powershell
.venv\Scripts\python.exe main.py `
  --source D:\legacy `
  --output D:\migrated `
  --profile py3_upgrade `
  --scope deprecated_api `
  --agentic
```

输出目录必须为空，或只包含 `.venv`、`venv`、`.git` 和
`.migration-agent`；其他内容会在迁移启动前被拒绝。

不使用大模型时回退为原样复制：

```powershell
.venv\Scripts\python.exe main.py --source D:\legacy --output D:\migrated --no-llm
```

`--chat` 支持的迁移目标示例：

- Python 2 迁移到 Python 3；
- Python 3.x 升级；
- 修复废弃 API；
- 升级 LangChain Community 的导入与废弃 API。

## CLI 参数

| 参数 | 说明 |
| --- | --- |
| `--source` | 待迁移项目路径，必须是目录 |
| `--output` | 迁移输出路径 |
| `--config` | 配置文件路径，默认 `config.yaml` |
| `--docs` | 追加知识文档，文件或目录，可多次指定 |
| `--profile` | 指定迁移档案，覆盖配置文件 |
| `--scope` | 指定迁移范围，覆盖配置文件 |
| `--chat` | 对话引导模式，无需传入输入/输出路径 |
| `--agentic` | LLM 自主工具决策循环 |
| `--auto-approve` | 跳过 `medium/high` 人工审批 |
| `--no-llm` | 使用回退复制计划 |

## 工作流程

```text
扫描 → 检索 → 规划 → 审批 → 应用 → 验证 → 报告
```

固定流水线使用 `MigrationRunner`；`--agentic` 使用 `AgenticRunner`，
由模型按需调用白名单工具。架构和状态机见 `docs/01_总体架构.md`、
`docs/02_Agent状态机.md`。

## 示例项目

以下命令省略 `.venv\Scripts\python.exe` 前缀。

| 示例 | 用途 | 命令 |
| --- | --- | --- |
| `examples/legacy_demo` | Python 2→3 多模块项目 | `main.py --source examples\legacy_demo --output D:\demo_migrated --docs knowledge_base/py2to3` |
| `examples/py38_demo` | Python 3.8 风格升级 | `main.py --source examples\py38_demo --output D:\py38_migrated --docs knowledge_base/py3_upgrade` |
| `examples/semantic_big_demo` | 语义编辑与信号修复 | `main.py --source examples\semantic_big_demo --output D:\big_migrated --agentic` |
| `examples/langchain_legacy` | LangChain Community 包拆分 | 见 `examples/langchain_legacy/README.md` |

## 知识库与规则

- 知识库目录与 `--docs` 用法见 `knowledge_base/README.md`；
- API 规则字段、匹配类型和扩展示例见 `migration/rules/README.md`；
- 迁移档案定义与新增方式见 `migration/profile_defs/README.md`；
- Agent 行为规则和红线见 `rules/README.md`。

## 测试与评估

```powershell
# 单元测试
.venv\Scripts\python.exe -m unittest discover tests -v

# 默认评估
.venv\Scripts\python.exe -m evals.run

# 评估已有迁移输出
.venv\Scripts\python.exe -m evals.run --quality-output D:\migrated

# 真实 LLM 端到端评估（需要 LLM API）
.venv\Scripts\python.exe -m evals.run --e2e --e2e-source examples\semantic_big_demo
```

`--e2e` 未指定输出目录时，会自动使用
`evals/e2e_runs/时间戳/`，审计数据写入该目录下的
`.migration-agent/`；评估报告仍保存到 `evals/reports/`。也可显式指定：

```powershell
.venv\Scripts\python.exe -m evals.run `
  --e2e `
  --e2e-source examples\semantic_big_demo `
  --e2e-output D:\e2e_target
```

默认评估不依赖 LLM API；`--e2e` 需要 LLM API。结果保存到
`evals/reports/`。详细说明见 `docs/06_评估系统.md`。

## CI

GitHub Actions 在推送和 Pull Request 时运行单元测试与评估，覆盖
Python 3.11、3.12、3.13。配置见 `.github/workflows/ci.yml`，说明见
`docs/07_CI.md`。

## 文档入口

- `AGENTS.md`：Agent 行为入口与文件索引；
- `rules/README.md`：行为规则、优先级与红线；
- `migration/profile_defs/README.md`：迁移档案定义；
- `migration/rules/README.md`：API 迁移规则；
- `knowledge_base/README.md`：知识库导入与缓存；
- `docs/`：架构、状态机、配置、调试、评估和 CI；
- `skills/`：具体能力的操作说明。

## 已知限制

- `--source` 只支持项目目录，不支持单文件；
- 固定 transform 规则覆盖基础语法，复杂迁移依赖 Agentic 编辑；
- 语义迁移依赖大模型，无法离线生成；
- 向量检索和重排需要本地模型缓存；
- PDF 解析依赖 `pypdf`；
- 行为验证需要目标依赖已安装到运行环境。
