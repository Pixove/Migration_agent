# Migration Agent

企业级代码库现代化迁移 Agent。用户通过命令行指定两条路径：待迁移的
遗留项目路径（只读）与迁移后输出路径（唯一可写区域）。迁移方案由
大模型生成，harness 负责校验、执行、验证与审计。

## 功能特性

- 双路径 CLI，输入项目只读，输出目录唯一可写；
- 大模型生成迁移计划，支持 OpenAI 兼容服务与 Ollama；
- RAG 混合检索：BM25 精确匹配 + 向量语义检索 + Cross-Encoder 重排；
- 按档案与主题组织的内置知识库；
- 工具白名单、路径沙箱、预算限制、影响面审批；
- 30% 大规模重构阈值，超限必须用户同意；
- 计划证据强制关联检索命中，禁止无依据修改；
- 迁移档案与转换规则（py2to3 正则 / py3_upgrade AST）；
- 语义编辑模式：LLM 生成 diff，自动评审 + 人工审批；
- 评估系统：检索、迁移、Agentic 编排、语义编辑四类指标；
- Agentic 按需读取 rules/skills，节省上下文；
- 验证失败自动回滚，完整审计与中文报告。

## 快速开始

### 1. 准备环境

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

### 2. 配置大模型

编辑 `config.yaml` 中的 `llm` 段：

- `provider: openai`：任意 OpenAI 兼容服务；
- `provider: ollama`：本地 Ollama；
- DeepSeek：取消 `openai` 段内注释的三行预设，并设置环境变量。

API Key 通过环境变量提供，不写入配置文件：

```powershell
$env:OPENAI_API_KEY = "你的密钥"
```

### 3. 运行迁移

交互模式：

```powershell
.venv\Scripts\python.exe main.py
```

完整模式（内置知识库 + 大模型）：

```powershell
.venv\Scripts\python.exe main.py --source D:\legacy --output D:\migrated --docs knowledge_base/py2to3
```

不使用大模型（回退为原样复制）：

```powershell
.venv\Scripts\python.exe main.py --source D:\legacy --output D:\migrated --no-llm
```

## 示例项目

仓库内置一个多模块 Python 2 遗留示例项目，用于测试迁移效果：

```text
examples/legacy_demo/
├─ main.py               # 订单系统入口
├─ models/               # 商品与订单模型
├─ services/             # 折扣计算与报表
├─ utils/                # 数据加载与工具函数
└─ data/products.txt     # 商品数据
```

迁移示例项目：

```powershell
.venv\Scripts\python.exe main.py --source examples\legacy_demo --output D:\demo_migrated --docs knowledge_base/py2to3
```

迁移完成后在输出目录运行：

```powershell
cd D:\demo_migrated
D:\IDE\VSCode\Migration_agent\.venv\Scripts\python.exe main.py
```

另有 Python 3.8 风格升级示例 `examples/py38_demo/`：

```powershell
.venv\Scripts\python.exe main.py --source examples\py38_demo --output D:\py38_migrated --docs knowledge_base/py3_upgrade
```

迁移完成后在输出目录运行 `main.py` 验证。

大型语义编辑示例 `examples/semantic_big_demo/`（300+ 行，15 个文件，
20 个 `__del__` / `utcnow` / `utcfromtimestamp` 信号）：

```powershell
.venv\Scripts\python.exe main.py --source examples\semantic_big_demo --output D:\big_migrated --agentic
```

## CLI 参数

| 参数 | 说明 |
| --- | --- |
| `--source` | 待迁移项目路径，必须是目录 |
| `--output` | 迁移输出路径 |
| `--config` | 配置文件路径，默认 `config.yaml` |
| `--docs` | 最佳实践文档路径，文件或目录，可多次指定 |
| `--no-llm` | 不使用大模型，使用回退复制计划 |
| `--auto-approve` | 跳过 `medium/high` 计划审批 |
| `--chat` | 使用对话引导模式确认迁移目标与路径 |
| `--agentic` | 使用 LLM 工具决策循环，让模型自主调用工具 |

## 工作流程

```text
初始化护栏 → 扫描输入项目 → 导入知识库并检索
→ LLM 生成计划 → 校验与审批 → 应用补丁 → 验证 → 报告
```

关键约束：

- 工具必须位于白名单，按名调用并计入调用次数；
- `low` 影响自动应用，`medium/high` 需要人工审批；
- 每条修改计划必须引用知识库检索命中；
- `transform` 涉及代码量超过 30% 时必须用户同意；
- 语义编辑必须 `propose_edit → 自动评审 → 人工审批 → apply_edit`；
- Python 输出文件必须通过 AST 验证，失败自动回滚。

## 运行模式

- 默认模式：固定流水线，扫描 → 检索 → 规划 → 应用 → 验证 → 报告；
- `--chat`：先对话确认迁移目标、路径与范围，再开始；
- `--agentic`：LLM 自主决策循环，模型按需调用白名单工具；
- `--chat --agentic`：对话确认后进入自主执行。

`--agentic` 依赖大模型，不能与 `--no-llm` 同时使用。

## 语义编辑与评审

固定规则只能处理语法与废弃 API；内存泄漏、并发、框架升级这类语义问题
由 LLM 生成结构化编辑，harness 负责把关。

```text
propose_edit（生成 diff 预览，不写文件）
→ 自动评审（检查范围/证据/无关改动，失败即拒绝）
→ 人工审批（medium/high）
→ apply_edit（写入输出目录）
→ 验证回滚
```

## 知识库

内置知识库位于 `knowledge_base/`，按“档案 + 主题”组织：

`py2to3/` 覆盖：

- Python 2 到 3 语法迁移；
- 字符串与字节处理；
- 异常处理迁移；
- 标准库变更；

`py3_upgrade/` 覆盖：

- 废弃 API 升级（distutils、imp、datetime.utcnow 等）；
- Python 3.11+ 性能与新语法。

`topics/` 覆盖通用最佳实践（所有档案自动加载）：

- 并发安全最佳实践；
- 内存泄漏修复指南；
- 迁移风险评估与控制；
- 验证与回滚最佳实践；
- 测试迁移正确性。

未传 `--docs` 时，主循环自动加载当前档案目录 + `topics/`。

可追加自定义文档：

```powershell
.venv\Scripts\python.exe main.py --source D:\legacy --output D:\migrated --docs knowledge_base/py2to3 --docs D:\docs\company-standard
```

知识库缓存目录由 `config.yaml` 的 `retrieval.kb_dir` 配置，默认 `kb/`，
已被 `.gitignore` 忽略。

## 输出与审计

迁移输出位于输出目录，审计数据位于：

```text
输出目录/
└─ .migration-agent/
   ├─ state.json    # 任务状态、计划条目、审计记录
   ├─ audit.log     # 运行日志
   └─ report.md     # 中文迁移报告
```

## 目录结构

```text
migration-agent/
├─ main.py                  # CLI 入口
├─ config.example.yaml      # 配置模板（入库）
├─ config.yaml              # 本地配置（不入库）
├─ agent/                   # 状态机、护栏、LLM 适配、调度、评审
├─ tools/                   # 扫描、补丁、验证、报告
├─ retrieval/               # 文档导入、BM25、向量、重排、知识库
├─ migration/               # 迁移档案（py2to3/py3_upgrade）与转换规则
├─ knowledge_base/          # 按档案与主题组织的内置迁移知识库
├─ examples/                # 示例遗留项目与转换演示
├─ evals/                   # 检索、迁移、Agentic、编辑评估
├─ rules/                   # 中文规则文档
├─ skills/                  # 中文技能文档
├─ docs/                    # 中文架构与调试文档
└─ tests/                   # 单元测试
```

## 测试

```bash
.venv\Scripts\python.exe -m unittest discover tests -v
```

运行评估系统（检索、迁移、Agentic 编排、语义编辑四类指标）：

```powershell
.venv\Scripts\python.exe -m evals.run
```

详细说明见 `docs/06_评估系统.md`。

## 文档入口

- `AGENTS.md`：Agent 行为入口与文件索引；
- `rules/`：运行时行为规则与红线；
- `skills/`：技能使用说明；
- `docs/`：架构、状态机、配置说明与调试排查。

## 已知限制

- `--source` 目前只接受项目目录，不支持单文件；
- `transform` 规则为基础集，复杂语法仍需扩展；
- 语义编辑依赖大模型生成与评审，无法离线生成；
- 向量检索与重排需要本地缓存模型，未缓存时对应功能关闭；
- PDF 解析依赖 `pypdf`，未安装时对应功能关闭；
- LLM 生成修改型计划需要知识库文档作为证据来源。
