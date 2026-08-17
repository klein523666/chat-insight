# Contributing

1. 先阅读 `agents.md`、`docs/technical-design.md` 和 `SECURITY.md`。
2. 不得扩大采集权限、默认开启 Source、记录密钥或给分析模型提供工具。
3. 平台差异放在 Collector/Adapter；Core、报告和数据库不得出现散落的平台分支。
4. 提交前运行 `ruff check src tests integrations`、`pytest` 和前端 `pnpm run build`。
5. 新行为必须有最小可运行测试；外部服务使用 Mock，禁止 CI 使用真实账号。
6. 变更数据库必须新增 Alembic migration，不得修改已发布 migration 或删表重建。

重大架构或规范变更先在 Issue 中说明动机、替代方案和迁移影响。
