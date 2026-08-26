# 语义编辑示例项目

用于体验语义编辑模式的小型项目，包含三个真实语义问题：

- `__del__` 清理资源：依赖析构不可靠，建议改为上下文管理器；
- `datetime.utcnow()`：已废弃且返回 naive 时间，建议改用 timezone-aware；
- 无锁计数器：多线程下会丢失更新，建议加锁或使用并发容器。

## 运行

建议使用 `--agentic`，让模型自主决定调用 `propose_edit`、评审和应用编辑：

```powershell
.venv\Scripts\python.exe main.py --source examples\semantic_demo --output D:\semantic_migrated --docs knowledge_base/py2to3 --agentic
```

说明：内存泄漏与并发安全文档位于 `knowledge_base/py2to3/`，可作为编辑证据。

## 预期链路

```text
模型调用 propose_edit → 自动评审 → 人工审批(medium/high) → apply_edit
```

如果模型只做了语法复制，说明它没有识别到语义问题；正常情况应能看到
`propose_edit` / `apply_edit` 被调用。
