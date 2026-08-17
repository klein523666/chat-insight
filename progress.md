# 当前进度

更新日期：2026-08-18

- [x] WebUI 重构为克制的产品化 SaaS 仪表盘：12 列栅格、细边框、紧凑表单与响应式导航已完成，并通过浏览器桌面/移动静态渲染检查
- [x] Telegram 二维码登录未配置凭据时，后端返回可恢复的 409，WebUI 显示明确提示
- [x] 禁用 TDLib 认证调试日志，并对二维码凭据错误返回非敏感提示
- [x] Telegram API Hash 配置自动清除首尾空白，避免粘贴导致凭据校验失败
- [x] TDLib 接收循环固定到专用单线程，避免二维码授权时会话中断
- [x] 二维码请求失败后清除过期二维码，避免手机端误扫
- [x] Telegram 二维码登录失败按安全错误码给出可操作提示
- [x] 手机号和验证码登录失败返回明确的非敏感状态提示
- [x] Telegram Collector 初始化时主动获取授权状态，避免停留在 starting
- [x] 已获用户授权重置未完成 TDLib 登录状态，并验证恢复到 WaitPhoneNumber
- [x] TDLib 更新处理异步化，修复账号信息与群组发现阻塞；已登录状态隐藏凭据表单
- [x] Telegram 消息源按账号已有聊天文件夹同步并提供页面筛选
- [x] 已补齐 Telegram 文件夹专属聊天列表加载，避免来源分组缺失
- [x] Telegram 消息源分组支持确认后的全选开启与全部关闭，仅影响当前分组且跳过已迁移来源
- [x] 修复 AstrBot v4.27.3 插件配置注入与数据目录 API 兼容性，QQ Collector 心跳正常
- [x] QQ OneBot 真实连接、2 个群发现、来源默认关闭与启用同步验证
- [x] QQ 实时消息字符串 ID、唯一入库和 Core 离线 Outbox 14 条恢复验证
- [x] 临时管理端口改为独立代理，移除时不再重建 AstrBot/NapCat
- [x] NapCat 单账号自动选择与可选密码 Docker secret；当前账号重启需扫码已确认为发布已知限制
- [x] 飞书推送目标支持安全删除，并自动解除报告任务关联
- [x] AI 模型预设覆盖 OpenAI、DeepSeek、通义千问与腾讯混元，并提供官方开放平台入口
- [x] 报告任务支持完整编辑；每个任务可选择根据本次原始数据自适应分析，或保存最长 4,000 字的自定义报告控制提示词；迁移、新装兼容与任务级 AI 调用均已回归验证
- [x] 报告任务支持确认后删除，并立即移除未来调度；任务关联的运行记录、报告与投递日志按既有外键规则一并清理

- [x] 明确 v0.1.0 核心闭环范围
- [x] 固定 AstrBot、NapCat 与 TDLib 技术基线
- [x] 初始化项目规范与辅助记忆
- [x] Core、数据库、认证与内部采集 API（Mock/本地验证）
- [x] Telegram Collector（Mock 验证）
- [x] AstrBot QQ Adapter 与 Outbox（Mock/本地验证）
- [x] 报告、AI、飞书与 Scheduler（Mock/本地验证）
- [x] React WebUI 构建与首次设置页视觉检查
- [x] Compose、CI、文档与依赖锁
- [x] 两个 Linux amd64 镜像构建、非 root 用户与 TDLib 动态库加载验证
- [x] 专用 Telegram 账号真实登录、来源发现与默认关闭验证
- [x] Telegram Collector 重启免登录验证
- [x] Telegram 启用后新消息、3 小时历史补采与外部消息 ID 去重验证
- [x] Telegram 升级旧群识别、自动关闭与 WebUI“已迁移”状态验证
- [x] 专用 QQ/TG/LLM/飞书真实端到端验收
- [x] 有业务数据的完整 Docker restart 持久化与故障验收（QQ 登录按已确认上游限制验收）
- [x] GitHub Actions、公开 GHCR 镜像和 v0.1.0 Release 发布

本地质量门：ruff、mypy strict、36 项 pytest、2 项前端测试、前端 lint/build、Compose config
均通过。Docker Desktop linux/amd64 实测中，Core（约 211MB）与 Telegram
Collector（约 259MB）镜像成功构建，`libtdjson.so` 可加载；空库迁移、WAL、
健康检查、loopback 端口、内部鉴权、日志 secret 扫描和无数据 restart 均通过。
AI/飞书表单的 Edge 登录凭据误填已修复，模型预设已加入；Core 镜像无损重建后
健康、管理员初始化状态与数据 Volume 均保持正常。
Telegram 真实群消息已入库；两轮重启补采后数据库保持 5 个不同外部消息 ID，
关闭来源消息数为 0。TDLib 升级前旧群已自动标记为 `migrated`、关闭且禁止启用，
升级后的超级群保持唯一启用。
专用 Telegram 账号已进入 Ready，来源默认关闭、实时消息、补采、去重、重启免
登录和升级旧群迁移均已真实通过。真实 QQ 采集、默认关闭、Outbox、去重均已
通过；当前专用账号在 v4.18.13 与 v4.18.19 上均无法恢复快速登录，用户已确认把
重启后可能需扫码列为 v0.1.0 已知限制。真实小时报、日报、QQ+Telegram 混合报告、
LLM 与飞书均已通过；同分钟任务经服务层串行后不再锁库，1,244 条 Telegram 日报
和 569 条混合报告均 AI success、飞书 HTTP 200。完整 restart 后管理员 Session、
Telegram Ready、消息、任务与报告保留，验收时至少 3,190 条消息且三类重复均为 0；
Scheduler 还成功补偿先前遗漏的 22:00 日报（1,458 条、AI success、飞书 200）。
NapCat 上游会向 stdout 输出临时二维码，Compose 已禁用该容器 Docker 日志。
2C4G VPS 验证已按用户确认延期到发布后，文档
只能标注为未验证，不能宣称对应性能结论。

v0.1.0 已发布到公开仓库 `klein523666/chat-insight`。主分支和标签 CI 均成功，
Core/TG 的 `0.1.0`、`v0.1.0`、`latest` GHCR 标签已推送并通过全新匿名 Docker
配置拉取；公开标签干净克隆后的 Compose 校验与 Core `/health` 冒烟通过。
