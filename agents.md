# Chat Insight 项目记忆与行为规范

## 1. 项目使命、范围与禁止事项

Chat Insight 是自托管的 QQ / Telegram 群聊采集、统计、AI 分析与飞书报告系统。v0.1.0 以 Linux amd64 Docker Compose 为运行目标，发布前必须在本机 Docker Desktop Linux Engine 完成真实 QQ、Telegram、LLM、飞书与报告闭环。2C4G VPS 验证延期到发布后，未验证前不得宣称已具备对应性能结论。

必须遵守：

- 只采集用户本人账号已经加入且有权查看的 QQ 群、Telegram 群/超级群/频道。
- 所有消息源默认关闭；用户明确启用后才保存消息。
- Telegram 使用个人账号 TDLib；QQ 使用 NapCat + OneBot v11 + AstrBot。
- Core 平台无关；平台差异只能进入 Collector/Adapter。
- 聊天内容永远是不可信数据，不能成为 Agent 指令，LLM 不获得工具。
- 私聊、媒体自动下载、Telemetry、公共凭据、绕过权限、破解协议均禁止。
- 不得在日志、异常、API 响应中泄露验证码、密码、Session、API Hash、API Key、Webhook、Secret、内部 Token。
- 不引入 Redis、Kafka、Elasticsearch、PostgreSQL、多 Worker 或尚无第二实现的工厂/插件框架。

v0.1.0 包含 QQ/TG 实时采集、来源选择、小时/日报、跨平台报告、OpenAI-compatible AI、飞书、认证、WebUI、SQLite 与 Docker。周报、自定义 Cron、AstrBot LLM Bridge、ARM64、多账号 UI、报告重生成/导出均延期到 v0.2。

## 2. 代码风格、命名与架构决策

- Python 3.12，完整类型标注，ruff；公开边界使用 Pydantic，持久化使用 SQLAlchemy 2 async。
- React + TypeScript + Vite；中文 UI，语义化 HTML、键盘可达、移动端可用。
- Python 源码采用 `src/chat_insight` 单包，两条进程入口：Server 与 Telegram Collector。
- Core 是 SQLite 唯一写入者；Collector 使用带 Token 的 HTTP batch API，至少一次传递，数据库唯一索引去重。
- 外部平台 ID 一律字符串；内部主键使用整数；时间使用 UTC epoch milliseconds，展示/窗口使用 `zoneinfo`。
- SQLite 启用 WAL、foreign keys、busy timeout；Server 单 Worker。
- APScheduler 3.11.2 仅作内存触发器，`report_tasks` 与 `report_runs` 才是持久真相。
- 只实现真实的 `OpenAICompatibleClient`，不创建单实现的抽象工厂。
- API 路径：公开 `/api/v1`，采集 `/internal/v1`；Collector Token 使用 Bearer。
- 敏感配置用 Docker secret 提供的主密钥加密；密码 Argon2id；会话为服务端可撤销 Session + CSRF。

## 3. 技术栈与第三方基线

- FastAPI、Pydantic、SQLAlchemy、aiosqlite、Alembic、httpx、cryptography、pwdlib[argon2]、APScheduler 3.11.2。
- React、TypeScript、Vite；构建产物由 FastAPI 同源托管，生产镜像无 Node runtime。
- AstrBot v4.27.3；NapCat 源码基线 v4.18.19，Compose 暂固定官方已发布镜像
  v4.18.13；TDLib commit `022d60202e446ad1287b9fb68e687c8a0760788b`。
- Core/Web/Telegram 使用 MIT；AstrBot 插件单独 AGPL-3.0；NapCat 只引用官方镜像并声明其有限、非商业许可。

## 4. 长期记忆与历史教训

- TDLib Chat 列表必须由 `loadChats` + update 流维护，`getChats` 只作信息展示。
- NapCat 新版推荐 message/user/group ID 全部使用字符串，禁止数值化。
- QQ 无可靠历史补采，AstrBot 插件必须持久化 SQLite Outbox；TG 依赖 TDLib history gap 补采。
- Scheduled report 的唯一性由 `(task_id, window_start, window_end)` 保证，不能只依赖 Scheduler 内存状态。
- AI 引用只能返回 message ID，最终原文从数据库回填，不能信任模型生成的 quote。
- 飞书自定义机器人完整请求体必须小于 20KB；正文按 18KB 安全预算分片。
  429/5xx/timeout 才重试，其他 4xx 直接失败并记录。
- NapCat v4.18.13/v4.18.19 对部分 QQ 账号无法恢复快速登录，即使 Session、账号与
  密码回退均正确也会被 QQ 登录接口拒绝。用户已于 2026-08-17 确认将“部分账号
  重启后需重新扫码”作为 v0.1.0 已知限制，不阻断发布，但必须在 README、安装与
  Release Notes 明示，不能宣称所有 QQ 账号均可免登录重启。

## 5. 工作流程与质量标准

- 每次工作前读取本文件。若要修改本文件中的规范，先说明理由并获得用户确认。
- `progress.md` 记录进度，`findings.md` 记录可验证事实/踩坑，`task_plan.md` 记录大型任务分解，`structure.md` 保持目录说明。
- 每阶段必须运行对应测试、lint/build，记录变更、架构影响和已知限制。
- 外部服务 CI 全部 Mock；发布前必须使用专用真实账号完成 QQ、TG、频道、LLM、飞书、重启与故障验收。QQ 登录态重启按上述已确认的上游限制验收，其余数据、Session 与 Outbox 持久化仍必须通过。
- 任何未真实验证的能力必须明确标注，不得用 TODO、Mock 或文档声称完成。
