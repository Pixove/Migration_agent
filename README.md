# Migration Agent

企业级代码库现代化迁移 Agent 的项目骨架。目标是让用户通过命令行指定两个路径：

1. 待迁移的遗留项目路径（只读）；
2. 迁移后输出路径（唯一可写区域）。

迁移方案由大模型生成，harness 负责校验、执行、验证与审计，约束 Agent 的行为边界，避免越权修改、无依据替换和不可追溯的变更。

## 快速开始

```bash
python -m pip install -r requirements.txt
python main.py
```

启动后会交互式询问输入项目路径与输出路径。也可以直接通过参数指定：

```bash
python main.py --source D:\legacy_project --output D:\migrated_project
```

## 两个入口文件

- `main.py`：程序运行入口，用户启动 CLI 时执行；
- `AGENTS.md`：Agent 行为入口，供 AI Agent 阅读，索引 `rules/`、`skills/`、`docs/` 的位置与红线，不包含可执行逻辑。

## 目录结构

```text
migration-agent/
├─ main.py                 # CLI 入口
├─ config.yaml             # 全局配置
├─ agent/                  # 状态机、护栏、LLM 适配
├─ tools/                  # 扫描、补丁、验证、报告
├─ retrieval/              # BM25、向量检索、重排
├─ rules/                  # 中文规则文档
├─ skills/                 # 中文技能文档
├─ docs/                   # 中文架构文档
└─ tests/                  # 单元测试
```

## 配置

所有配置集中在 `config.yaml`，其中：

- `llm.provider` 支持 `openai` 与 `ollama`；
- `llm.openai` 兼容所有 OpenAI 协议的服务；
- `llm.ollama` 指向本地 Ollama 服务；
- `guardrails` 控制路径边界、工具白名单、预算与审批分级。

详细说明见 `docs/03_配置说明.md`。
