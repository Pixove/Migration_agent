# 候选规则与档案生成示例

本示例用于测试从知识文档生成候选 API 规则和候选迁移档案的完整命令。
示例不会自动修改正式规则，因为候选文件默认写入已被 gitignore 的目录。

## 文件

- `knowledge/samplelib_upgrade.md`：包含三个明确的 API 迁移说明；
- `legacy_app.py`：包含对应旧 API 的最小项目，用于候选规则覆盖验证。

## 生成候选规则和档案

```powershell
.venv\Scripts\python.exe -m migration.rule_author `
  --docs examples\rule_author_demo\knowledge\samplelib_upgrade.md `
  --profile-name samplelib_upgrade `
  --output migration\rule_candidates\samplelib_upgrade.yaml `
  --profile-output migration\profile_candidates\samplelib_upgrade.yaml `
  --description "samplelib 2.0 API 迁移" `
  --scope deprecated_api `
  --keyword samplelib `
  --verify-against examples\rule_author_demo\legacy_app.py
```

预期结果：

- 提取约 3 条候选规则；
- 生成 `migration/rule_candidates/samplelib_upgrade.yaml`；
- 生成 `migration/profile_candidates/samplelib_upgrade.yaml`；
- 生成 `migration/rule_candidates/samplelib_upgrade.review.md`；
- 覆盖验证应命中 `3/3` 个候选 API。

## 检查结果

```powershell
Get-Content migration\rule_candidates\samplelib_upgrade.yaml
Get-Content migration\profile_candidates\samplelib_upgrade.yaml
Get-Content migration\rule_candidates\samplelib_upgrade.review.md
```

候选档案会引用正式路径：

```text
migration/rules/profiles/samplelib_upgrade.yaml
```

只有确认候选内容正确后，才通过 `--approve` 安装到正式规则和档案目录。
正式安装会写入项目文件，普通命令测试不需要执行这一步。
