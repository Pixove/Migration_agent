# LangChain 知识库

本目录存放 LangChain 生态迁移的最佳实践文档，供
`migration.profile: langchain_community` 自动加载，也可以通过
`--docs knowledge_base/langchain` 手动传入。

## 文件索引

| 文件 | 内容 |
| --- | --- |
| `01_langchain_community_拆分迁移.md` | Community 集成拆分为独立包、导入迁移、LCEL 注意事项与验证方法 |

## 使用方式

```powershell
.venv\Scripts\python.exe main.py --chat --agentic
```

回答迁移目标时说明“升级 LangChain Community 的废弃 API”，会使用
`langchain_community` 档案。

也可以显式指定：

```powershell
.venv\Scripts\python.exe main.py --source D:\legacy --output D:\migrated --docs knowledge_base/langchain --agentic
```
