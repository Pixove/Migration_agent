# 迁移档案定义

本目录用 YAML 定义迁移档案，`migration/registry.py` 会在启动时自动加载
并注册，不再需要在 Python 代码中新增档案字典。

## 文件索引

| 文件 | 档案 | 说明 |
| --- | --- | --- |
| `py2to3.yaml` | `py2to3` | Python 2 到 Python 3 语法迁移 |
| `py3_upgrade.yaml` | `py3_upgrade` | Python 3.x 升级与废弃 API |
| `langchain_community.yaml` | `langchain_community` | LangChain Community 包拆分 |

## 字段说明

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 档案唯一名称，供 `--profile` 和配置引用 |
| `description` | 是 | 档案说明，供 `--chat` 和文档展示 |
| `transform` | 否 | 确定性转换器名称：`py2to3`、`py3_upgrade` 或留空 |
| `scopes` | 是 | 支持的迁移范围，如 `syntax`、`deprecated_api` |
| `default_scope` | 否 | 未明确范围时使用的默认值 |
| `knowledge_base` | 是 | 默认加载的知识库目录列表 |
| `rules` | 否 | 档案专属 API 规则文件，运行时叠加到全局规则 |
| `keywords` | 否 | `--chat` 无模型时用于识别目标的关键词 |
| `priority` | 否 | 关键词匹配优先级，数值越大越优先 |

## 新增档案

只需要新增一个 YAML 文件，例如：

```yaml
name: pandas_upgrade
description: pandas 2.x API 迁移
transform:
scopes:
  - deprecated_api
default_scope: deprecated_api
knowledge_base:
  - knowledge_base/pandas
  - knowledge_base/topics
rules:
  - migration/rules/profiles/pandas_upgrade.yaml
keywords:
  - pandas
priority: 20
```

如果不需要确定性转换器，`transform` 留空即可，迁移由 Agentic 语义编辑
完成。只有需要 AST/正则自动改写的档案，才需要额外实现 Python transform
函数，并在 `migration/registry.py` 的转换器注册表中登记名称。

也可以从知识文档生成候选档案：

```powershell
.venv\Scripts\python.exe -m migration.rule_author `
  --docs D:\docs\pandas_upgrade.md `
  --profile-name pandas_upgrade
```

生成器会在 `migration/profile_candidates/` 下输出候选 YAML，并生成
`.review.md` 评审报告。确认后再移动到本目录，不会自动注册。

## 与知识库、规则表的关系

- `knowledge_base`：档案默认加载哪些知识文档；
- `migration/rules/*.yaml`：全局 API 扫描规则，所有档案共用；
- `rules`：档案专属规则文件，只在当前档案下叠加加载；
- `--docs`：在档案默认知识库之外追加文档；
- `--profile` / `--scope`：命令行覆盖配置中的档案与范围。

## 校验

启动时会检查：

- `name`、`description`、`scopes`、`knowledge_base` 不能为空；
- `default_scope` 必须属于 `scopes`；
- `transform` 必须是已登记的转换器名称或留空；
- 不同档案的 `name` 不能重复。
