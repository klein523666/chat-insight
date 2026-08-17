# 当前进度

更新日期：2026-08-17

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
- [ ] 专用 QQ/TG/LLM/飞书真实端到端验收
- [ ] 有业务数据的完整 Docker restart 持久化与故障验收
- [ ] GitHub Actions、公开 GHCR 镜像和 v0.1.0 Release 发布

本地质量门：ruff、mypy strict、33 项 pytest、2 项前端测试、前端 lint/build、Compose config
均通过。Docker Desktop linux/amd64 实测中，Core（约 211MB）与 Telegram
Collector（约 259MB）镜像成功构建，`libtdjson.so` 可加载；空库迁移、WAL、
健康检查、loopback 端口、内部鉴权、日志 secret 扫描和无数据 restart 均通过。
AI/飞书表单的 Edge 登录凭据误填已修复，模型预设已加入；Core 镜像无损重建后
健康、管理员初始化状态与数据 Volume 均保持正常。
Telegram 真实群消息已入库；两轮重启补采后数据库保持 5 个不同外部消息 ID，
关闭来源消息数为 0。TDLib 升级前旧群已自动标记为 `migrated`、关闭且禁止启用，
升级后的超级群保持唯一启用。
专用 Telegram 账号已进入 Ready，来源默认关闭、实时消息、补采、去重、重启免
登录和升级旧群迁移均已真实通过。真实 QQ、LLM、飞书、三类报告、有数据完整
restart 和故障验收仍是发布阻断。2C4G VPS 验证已按用户确认延期到发布后，文档
只能标注为未验证，不能宣称对应性能结论。
