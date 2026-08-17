# Chat Insight v0.1.0 技术设计

## 进程与边界

- `chat-insight-server`：公开 Web/API、认证、SQLite、消息批写、报告、Scheduler、AI、飞书。
- `chat-insight-telegram`：TDLib JSON client、授权、Chat discovery、update、history gap；不访问 SQLite。
- AstrBot 插件：QQ group event、OneBot group list、SQLite Outbox、HTTP batch；不包含业务分析。
- React WebUI：只调用同源公开 API；Core 代理 Telegram Collector 的授权接口。

Collectors 以至少一次语义向 `/internal/v1/messages:batch` 发送；只有 Core 提交事务后才返回 accepted/duplicate/rejected。所有 Source 首次发现均为 disabled，Collector 缓存并周期同步 enabled IDs。

## 数据与调度

SQLite 为单一真相，使用 WAL、foreign keys 和 5 秒 busy timeout。消息使用外部组合唯一索引；没有外部消息 ID 时使用 SHA-256 fallback hash。

时间存 UTC epoch milliseconds，所有报告区间为左闭右开。小时报覆盖上一完整自然小时；日报覆盖任务时区当日 00:00 到计划触发时刻。APScheduler 3.11.2 的任务从数据库重建；报告运行表的唯一约束负责幂等，启动最多补三个遗漏窗口。

## 安全与隐私

- 一次性 Setup Token 创建唯一管理员，成功后数据库记录 setup 完成并拒绝再次调用。
- Argon2id 密码；随机 Session Token 只在 Cookie 中出现，数据库存 SHA-256；写操作需要 CSRF Token。
- 主密钥、Collector Token、TDLib database key 由 Docker secrets 提供。
- Telegram API Hash、LLM API Key、飞书 Webhook/Secret 使用 Fernet 加密；读取 API 只返回 mask。
- 内部接口需要 Bearer Token；Compose 不映射 Collector、AstrBot、NapCat 端口，Web 仅绑定 127.0.0.1。
- 聊天消息作为 untrusted JSON data 提供给模型，模型没有工具；用户内部 ID 默认不进入 prompt。

## AI 与报告

确定性统计由 Python 计算。上下文按 Source 分组并按字符预算分块；小窗口直接分析，大窗口先生成 source summaries，再合并。结构化输出尝试 `json_schema`、`json_object`、纯 JSON；校验/修复失败时输出纯统计报告。

模型只能返回 evidence message IDs，引用文本由 Core 从本次窗口内数据库记录回填。飞书默认 interactive card，正文按 18KB 安全预算分片并保证完整请求体低于自定义机器人的 20KB 限制，重试 429、5xx 与网络超时。

## Docker 与许可

Core 与 Telegram 使用项目自建 amd64 镜像；AstrBot 固定官方 v4.27.3 镜像。
NapCat 源码技术基线为 v4.18.19，但 Compose 暂时固定官方 Docker Hub 已发布的
v4.18.13 镜像。持久卷分别保存 Core、TDLib、AstrBot、NapCat。Core/Web/Telegram
为 MIT，AstrBot 插件为 AGPL-3.0；NapCat 不复制、不改包，并在 README 明示
非商业限制。
