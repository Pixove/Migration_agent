# API 迁移规则表

本目录存放机器可读的 API 迁移规则，供 `migration/scan_signals.py` 的
AST 扫描器加载。规则表负责决定**哪些文件需要进入迁移流程**，知识库
文档负责提供**为什么改、怎么改**的证据。

## 工作方式

```text
migration/rules/*.yaml
  -> scan_python_signals() 生成信号
  -> AgenticRunner 分批注入待修文件
  -> LLM 生成 apply_edit
  -> 评审、审批、应用、AST 验证、定向修复
```

扫描器会合并本目录下全部 `.yaml` / `.yml` 文件，因此可以按生态拆分
规则，例如：

```text
migration/rules/
├─ api_rules.yaml                  # 全局规则，所有档案加载
└─ profiles/
   └─ langchain_community.yaml     # 档案专属规则，按需加载
```

顶层 `*.yaml` 是所有档案共享的全局规则；`profiles/` 下的规则文件
不会自动加载，必须由档案 YAML 的 `rules` 字段引用。例如
`langchain_community.yaml` 档案只在自己的迁移任务中加载 LangChain
规则，不会污染 `py2to3` 或 `py3_upgrade` 的信号检测。

## 字段说明

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 规则唯一标识，用于去重、审计与追踪，不能重复 |
| `kind` | 是 | 信号类型，如 `deprecated_api`、`removed_module` |
| `type` | 是 | AST 匹配方式，见下方“匹配类型” |
| `name` | 是 | 匹配目标名称；`from_import` 时表示要导入的符号 |
| `module` | `from_import` 必填 | 来源模块 |
| `message` | 是 | 写入信号与报告的迁移提示 |
| `replacement` | 否 | 建议替换内容，供模型参考 |
| `docs` | 否 | 关联的知识文档 ID |
| `alias` | 否 | 是否允许按名称末段匹配别名 |
| `package` | 否 | 所属包或生态，如 `langchain_community` |
| `deprecated_in` | 否 | 开始废弃的版本 |
| `removed_in` | 否 | 开始移除的版本 |
| `severity` | 否 | 严重程度，如 `low`、`medium`、`high` |

`kind` 表示“这是什么问题”，`type` 表示“怎么找到它”，`severity` 表示
“问题有多严重”。目前 `severity` 会进入信号，但自动应用或人工审批仍
由编辑条目的 `impact` 和 `guardrails` 配置决定。

## 匹配类型

| type | 匹配对象 | 示例 |
| --- | --- | --- |
| `function_def` | 函数定义 | `def __del__` |
| `call` | 函数调用 | `datetime.utcnow()` |
| `attribute` | 属性访问或注解 | `typing.Dict`、`Dict[str, int]` |
| `module` | 模块导入 | `import distutils` |
| `from_import` | 指定模块下的符号 | `from langchain_community.vectorstores import Chroma` |

`alias: true` 时，`dt.utcnow()`、`t.Dict`、直接使用 `Dict` 也能匹配。

## 完整示例

```yaml
- id: langchain_community_chroma_import
  kind: deprecated_api
  type: from_import
  module: langchain_community.vectorstores
  name: Chroma
  replacement: from langchain_chroma import Chroma
  message: Chroma 已迁移到 langchain_chroma
  docs: langchain_community_upgrade
  package: langchain_community
  deprecated_in: "0.2.0"
  severity: medium
```

扫描：

```python
from langchain_community.vectorstores import Chroma
```

生成的信号大致为：

```json
{
  "file": "app.py",
  "line": 1,
  "kind": "deprecated_api",
  "api": "langchain_community.vectorstores.Chroma",
  "message": "Chroma 已迁移到 langchain_chroma",
  "replacement": "from langchain_chroma import Chroma",
  "docs": "langchain_community_upgrade",
  "package": "langchain_community",
  "severity": "medium"
}
```

## 校验规则

加载规则时会检查：

- `id`、`kind`、`type`、`name`、`message` 不能为空；
- `id` 不能重复；
- `type` 必须是已支持的类型；
- `from_import` 必须提供 `module`；
- `deprecated_api` 至少提供 `replacement` 或 `docs`；
- YAML 文件必须包含 `rules` 列表。

规则文件错误时任务会直接失败并给出具体文件和条目位置，避免静默漏扫。

## 新增规则流程

1. 在合适的规则文件中增加一条规则；
2. 补充对应的知识文档，并通过 `--docs` 或内置知识库提供；
3. 增加扫描器测试，确认目标 API 能生成预期信号；
4. 用示例项目运行一次迁移，检查信号是否进入批次并被正确修复；
5. 复杂或高风险的迁移规则设置 `severity: high`，保留人工审批。

## 当前限制

- 规则表目前手工维护，不会自动解析 PDF/TXT 文档生成规则；
- AST 只能识别语法结构和名称，无法判断运行时版本、参数签名或行为差异；
- 接口语义变化（如 LangChain `LLMChain` → LCEL）可能需要跨文件重构，
  需要人工审批和行为验证；
- 规则命中只说明“需要检查”，不保证模型给出的修改一定语义正确。
