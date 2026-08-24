# Python 2 到 3 语法迁移

## 背景

Python 2 与 Python 3 存在大量不兼容语法。迁移时应先处理编译期语法差异，
再处理运行时行为差异。

## print 语句

Before:

```python
print 'hello'
print >> sys.stderr, 'error'
```

After:

```python
print('hello')
print('error', file=sys.stderr)
```

风险：`print` 带重定向、多参数、尾随逗号时需要逐条检查语义。

## except 异常捕获

Before:

```python
except ValueError, e:
    print e
```

After:

```python
except ValueError as e:
    print(e)
```

风险：异常变量作用域在 Python 3 中于 `except` 块结束后被删除。

## xrange 与 range

Before: `for i in xrange(10):`

After: `for i in range(10):`

注意：Python 3 的 `range` 是惰性对象，内存占用低；对超大范围仍安全。

## long 与整数

Before: `value = long(3)`

After: `value = int(3)`

Python 3 中 `int` 为任意精度，`long` 已不存在。

## raw_input 与 input

Before: `name = raw_input('name: ')`

After: `name = input('name: ')`

风险：Python 2 的 `input` 会执行表达式，迁移时必须替换为 `raw_input`
对应语义的 `input`，不得保留旧 `input`。

## basestring 与 unicode

Before:

```python
if isinstance(s, basestring):
    s = unicode(s)
```

After:

```python
if isinstance(s, str):
    s = str(s)
```

## unicode 字面量

Before: `text = u'你好'`

After: `text = '你好'`

注意：`u'...'` 在 Python 3 中虽然保留，但建议统一移除前缀。

## 整数除法

Before: `half = count / 2`

After:

```python
half = count // 2       # 保留整除语义
half = count / 2.0      # 需要浮点除法时显式转换
```

风险：Python 2 中 `/` 对整数是整除，Python 3 中是浮点除法。

## dict 迭代方法

Before: `for key in d.iterkeys():`

After: `for key in d.keys():`

`iteritems`、`iterkeys`、`itervalues` 均已移除，使用
`items`、`keys`、`values`，必要时包 `list()`。

## exec 语句

Before: `exec code`

After: `exec(code)`

## 旧式类

Before: `class A: pass`

After: `class A(object): pass`

风险：旧式类属性查找与 `super` 行为不同，迁移后应运行完整测试。

## 注意事项

语法迁移优先使用 AST 级工具或规则集，避免纯字符串全局替换；
每次变更后必须执行语法验证与测试。
