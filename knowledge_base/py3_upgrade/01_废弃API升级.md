# 废弃 API 升级

## distutils

Python 3.12 起 `distutils` 被移除，应迁移到 `setuptools` 或
`packaging`。

Before:

```python
from distutils.core import setup
```

After:

```python
from setuptools import setup
```

## imp

Python 3.12 起 `imp` 模块被移除，应迁移到 `importlib`。

Before:

```python
import imp
module = imp.load_source('name', 'path.py')
```

After:

```python
import importlib.machinery
module = importlib.machinery.SourceFileLoader('name', 'path.py').load_module()
```

## datetime.utcnow

`datetime.utcnow()` 与 `utcfromtimestamp()` 已废弃，建议使用
timezone-aware 时间。

Before:

```python
now = datetime.utcnow()
```

After:

```python
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
```

## asyncio.get_event_loop

`asyncio.get_event_loop()` 已废弃，优先使用
`asyncio.get_running_loop()`；需要显式事件循环时创建并管理生命周期。

## typing 类型别名

`Dict`、`List`、`Tuple`、`Set`、`Type` 建议改为内置泛型
`dict`、`list`、`tuple`、`set`、`type`（Python 3.9+）。

Before: `x: Dict[str, int]`

After: `x: dict[str, int]`
