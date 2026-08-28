# 遗留示例项目

用于测试 Migration Agent 迁移效果的小型 Python 2 遗留项目。

## 文件说明

```text
legacy_demo/
├─ main.py              # 程序入口：加载商品、计算折扣、打印报表
├─ app.py               # 已是 Python 3 语法
├─ python2_demo.py      # 含 Python 2 语法，需要 transform
├─ models/
│  ├─ product.py        # 商品模型，含 basestring/unicode/long
│  ├─ order.py          # 订单模型，含 xrange
│  └─ customer.py       # 客户模型，含 basestring/unicode
├─ services/
│  ├─ pricing.py        # 阶梯折扣与积分，含 xrange
│  └─ report.py         # 报表打印，含 print 语句与 unicode 字面量
├─ utils/
│  ├─ helper.py         # 工具函数
│  ├─ storage.py        # 商品与客户加载，含 except 逗号语法
│  └─ cli.py            # 交互函数，含 raw_input（默认不调用）
└─ data/
   ├─ products.txt      # 商品数据
   ├─ customers.txt     # 客户数据
   └─ notes.txt         # 普通文本
```

## 项目功能

一个小型订单系统：加载商品与客户，生成订单，按金额计算阶梯折扣，
会员额外享受 9 折，输出订单明细、金额与积分。

## 完整迁移（大模型 + 内置知识库）

```powershell
.venv\Scripts\python.exe main.py --source examples\legacy_demo --output D:\demo_migrated --docs knowledge_base/py2to3
```

预期结果：

- `python2_demo.py` 与各业务模块中的 `print`、`except`、`xrange`、
  `long`、`basestring`、`unicode` 等语法被改写；
- 因重构比例超过 30%，CLI 会询问是否继续，输入 `y`；
- 其余文件按 `copy` 落到输出目录；
- 输出目录下 `.migration-agent/` 生成报告与审计。

## 迁移后运行验证

迁移完成后，在输出目录运行：

```powershell
cd D:\demo_migrated
D:\IDE\VSCode\Migration_agent\.venv\Scripts\python.exe main.py
```

预期输出类似：

```text
=== 订单明细 ===
客户: 张三 会员: V
苹果 x 1 = 100
香蕉 x 1 = 50
橙子 x 1 = 120
--- 金额 ---
小计: 270
会员价: 218
积分: 0
```

## 不使用大模型

```powershell
.venv\Scripts\python.exe main.py --source examples\legacy_demo --output D:\demo_migrated --no-llm
```

注意：`--no-llm` 是原样复制，`python2_demo.py` 复制后无法通过
Python 3 AST 验证，会被正确回滚并标记 `failed`，这是预期行为，
说明 harness 拒绝未完成迁移的输出。

## 快速查看转换效果

不启动完整流程，直接看规则集效果：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_transform -v
```

该测试会对 `python2_demo.py` 等样例运行转换并断言结果。
