# Agent 状态机

## 阶段定义

```text
init → scan → retrieve → plan → apply → verify → report → done
任意阶段可进入 failed
```

## 状态迁移表

| 当前阶段 | 允许迁移到 |
| --- | --- |
| `init` | `scan`、`failed` |
| `scan` | `retrieve`、`failed` |
| `retrieve` | `plan`、`failed` |
| `plan` | `apply`、`failed` |
| `apply` | `verify`、`failed` |
| `verify` | `apply`、`report`、`failed` |
| `report` | `done`、`failed` |
| `done`、`failed` | 终态 |

## 各阶段动作与产物

| 阶段 | 动作 | 产物 |
| --- | --- | --- |
| `init` | 创建审计工作区 | `.migration-agent/` |
| `scan` | 扫描输入项目 | 文件清单 |
| `retrieve` | 导入文档并检索 | 检索命中记录 |
| `plan` | 生成并校验计划 | `PlanItem` 列表 |
| `apply` | 应用补丁 | 输出文件与 diff |
| `verify` | 验证输出 | 验证结果 |
| `report` | 生成报告 | `report.md` |
| `done` | 任务完成 | 汇总状态 |
| `failed` | 记录错误 | 错误审计 |

## 状态持久化

状态写入输出目录下的 `.migration-agent/state.json`，包含：

- 输入与输出路径；
- 创建与更新时间；
- 当前阶段；
- 计划条目；
- 审计记录。
