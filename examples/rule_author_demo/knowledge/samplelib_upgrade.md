# samplelib 2.0 API 迁移指南

本示例用于验证 `migration.rule_author` 从知识文档生成候选规则和候选档案
的能力。以下三个 API 已明确给出旧用法、新用法和迁移原因。

## OldModel 迁移

旧代码：

```python
from samplelib.old import OldModel
```

新代码：

```python
from samplelib.models import Model
```

`samplelib.old.OldModel` 已迁移到 `samplelib.models.Model`，后续调用点需要
同步重命名。

## LegacyClient 迁移

旧代码：

```python
client = samplelib.client.LegacyClient(endpoint)
```

新代码：

```python
client = samplelib.client.Client(endpoint)
```

`samplelib.client.LegacyClient` 已改名为 `samplelib.client.Client`，构造参数
保持不变。

## load_config 迁移

旧代码：

```python
config = samplelib.utils.load_config(path)
```

新代码：

```python
config = samplelib.config.load_config(path)
```

配置加载函数已从 `samplelib.utils` 迁移到 `samplelib.config`，函数签名
保持不变。
