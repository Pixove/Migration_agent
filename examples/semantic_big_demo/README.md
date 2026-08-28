# 大型语义编辑示例

用于测试 Agentic 语义编辑模式的中型项目，代码量超过 100 行，
包含多个需要语义修复的问题：

- 多个 `__del__` 清理资源（`Connection`、`Cache`、`TaskQueue`、`RegistryEntry`）；
- 多处 `datetime.utcnow` / `utcfromtimestamp`（废弃且返回 naive 时间）；
- 无锁计数器 `self.value += 1`（并发安全）；
- 全局可变注册表只增不减（内存增长）；
- 队列/资源缺少显式生命周期管理。

## 运行

```powershell
.venv\Scripts\python.exe main.py --source examples\semantic_big_demo --output D:\big_migrated --agentic
```

建议配合 `--auto-approve` 减少人工交互：

```powershell
.venv\Scripts\python.exe main.py --source examples\semantic_big_demo --output D:\big_migrated --agentic --auto-approve
```

## 预期结果

- `__del__` 全部改为 `__enter__/__exit__` 或显式 `close()`；
- `utcnow` / `utcfromtimestamp` 改为 timezone-aware；
- 计数器使用 `threading.Lock` 保护；
- 全局注册表支持注销或使用 `weakref`；
- 报告 `UNRESOLVED` 应为空（或明确列出未修复项）。
