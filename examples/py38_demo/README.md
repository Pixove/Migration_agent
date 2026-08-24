# Python 3.8 风格升级示例

用于测试 `py3_upgrade` 档案的小型项目，包含 Python 3.8 时代常见写法：

- `typing.Dict` / `List` / `Tuple` 类型别名；
- `datetime.utcnow()` 废弃调用；
- 多模块互相调用。

## 迁移

配置 `migration.profile: py3_upgrade` 后运行：

```powershell
.venv\Scripts\python.exe main.py --source examples\py38_demo --output D:\py38_migrated
```

或显式指定知识库：

```powershell
.venv\Scripts\python.exe main.py --source examples\py38_demo --output D:\py38_migrated --docs knowledge_base/py3_upgrade
```

## 迁移后验证

```powershell
cd D:\py38_migrated
D:\IDE\VSCode\Migration_agent\.venv\Scripts\python.exe main.py
```

预期输出类似：

```text
用户: 张三
平均分: 91.5
最低分: 88.0
最高分: 95.0
时间: 2026-...
扁平化: [1, 2, 3]
```

检查迁移结果：

- `typing.Dict` 应改写为 `dict`；
- `datetime.utcnow()` 应保留调用并附带 `TODO(migration)` 标注。
