# 调研与踩坑记录

## 2026-08-17

- 专用 Telegram 账号已真实登录并进入 `Ready`；UI 展示的会话总数包含不可采集
  会话，Core 最终发现 184 个群、超级群或频道来源。
- 登录后数据库中 Telegram 来源启用数为 0、Telegram 消息数为 0，证明来源发现
  不会绕过默认关闭策略；TDLib 独立 Volume 已产生持久化 Session 数据。
- 本次登录后的 Docker Desktop 瞬时观测约为 Core 92MiB、Telegram Collector
  100MiB RSS；该数值仅作本机功能预检，不能替代 2C4G VPS 性能验收。
- Telegram Collector 真实重启后直接恢复 `Ready`，无需重新扫码，TDLib Session
  持久化验收通过。
- 两次测试标记未入库的根因是同名的升级前普通群被误启用，而消息实际发送到升级
  后的超级群。对齐 Source 后实时 outgoing 文本成功入库；重启补采找回此前消息，
  再次重启后仍保持 5 条消息、5 个不同外部消息 ID，关闭来源消息数为 0。
- TDLib 会通过 `updateBasicGroup.upgraded_to_supergroup_id` 保留升级关系，但旧群可能
  不在当前 `loadChats` 缓存中。Collector 现使用 `createBasicGroupChat(force=true)`
  取回缺失的旧 chat，将其标记为 `migrated`；Core 自动关闭并拒绝再次启用，WebUI
  保留该行作为审计记录并显示“已迁移”。

## 2026-08-16

- TDLib 默认调试日志可能输出认证请求参数；创建客户端前必须将
  `td_set_log_verbosity_level` 设为 0，且认证失败只向 WebUI 返回固定的非敏感提示。
- Telegram API Hash 粘贴时混入首尾空白会导致 `API_ID_INVALID`；公开配置输入统一去除首尾空白。
- TDLib 的 `td_receive` 不能由共享线程池随机调度；必须通过每个客户端独占的单线程执行器调用，否则会被 TDLib 终止会话。
- 二维码请求失败后必须清空旧 `qr_link`；否则 WebUI 会继续展示过期码，手机端扫描将报错。
- Telegram 授权错误只能向 UI 暴露全大写错误码或固定中文提示，不能转发任意错误文本。
- 手机号、验证码等授权端点须显式转换 TDLib 错误；否则 Core 会将 Collector 的 500 误报为“不可用”。
- TDLib 新客户端不会可靠地主动推送首个授权状态；配置完成后应显式调用 `getAuthorizationState`，再处理返回状态。
- `setAuthenticationPhoneNumber` 仅可在 `authorizationStateWaitPhoneNumber` 等指定状态调用；处于 `authorizationStateWaitOtherDeviceConfirmation` 的二维码确认中不能直接切换手机号。
- 未登录且卡在二维码确认状态时，停止 Collector 并清除 `telegram_tdlib_data` 卷中的 `database` 与 `files` 后可安全回到 `WaitPhoneNumber`；执行前必须得到用户确认。
- TDLib update handler 不能在接收循环中同步等待新的 TDLib 请求；否则接收循环无法处理响应，`getMe` 和 `loadChats` 将超时。须异步分发更新处理。
- Telegram 已就绪时不显示 API 凭据表单，避免浏览器自动填充错误值后被误保存。
- TDLib 的 `updateChatFolders` 提供账号原有文件夹名称；聊天的 `chatListFolder` 位置可映射其所属文件夹，适合写入来源元数据而无需新增表。
- `updateChatFolders.name.text` 可能嵌套为 `formattedText`，展示前需解包至纯文本，不能直接转字符串。
- `loadChats` 仅加载指定的聊天列表；主列表不会覆盖文件夹专属聊天，必须为每个 `chatListFolder` 单独加载并维护已加载集合。

- TDLib 固定 commit：`022d60202e446ad1287b9fb68e687c8a0760788b`。
- TDLib `getChats` 官方明确为信息用途；一致列表应使用 `loadChats` 与 updates。
- TDLib 授权状态除手机号/QR/验证码/2FA 外还可能要求邮箱地址与邮箱验证码。
- AstrBot v4.27.3 可通过公开平台实例/OneBot client 调用 action；模型调用桥延期到 v0.2。
- NapCat v4.18.19；新版外部 ID 必须视为字符串。
- APScheduler 4 仍是预发布且缺少平滑迁移，生产固定 3.11.2。
- OpenAI 官方当前仍支持 Chat Completions 与 Structured Outputs；为第三方兼容性使用 Chat Completions，并对结构化输出逐级降级。
- AstrBot 为 AGPL-3.0；NapCat 为有限再分发且禁止商业使用；TDLib 为 Boost-1.0。
- NapCat 源码已到 v4.18.19，但官方 Docker Hub 当前最新可固定发布镜像为
  v4.18.13；Compose 使用真实存在的 v4.18.13，`agents.md` 已按用户确认区分
  源码基线和发布镜像。
- TDLib `getChatHistory` 可能重复返回相同最旧消息游标；必须在处理重复页前停止，
  避免重复消息占满 Collector 内存队列（Core 唯一索引仍作为最终去重保障）。
- Python 依赖由 `uv.lock` 统一解析，并导出带哈希的生产/开发 requirements；
  运行镜像先按哈希锁安装，再以 `--no-deps` 安装项目包。
- Docker Desktop linux/amd64 已成功构建 Core 与 Telegram 镜像；Telegram 固定
  commit 编译约 28 分钟，`/build/td/build/libtdjson.so` 复制路径正确且运行镜像中
  可通过 `ctypes.CDLL` 加载。
- Core/TG 空闲实测约 68/45MiB RSS；该数据来自 8GiB Docker Desktop，不能替代
  2C4G VPS 性能验收。
- AstrBot v4.27.3 与 NapCat v4.18.13 官方镜像均为 linux/amd64，实际镜像大小约
  1.83GB 与 1.45GB，VPS 部署必须预留镜像、TDLib Session 和消息数据库空间。
- 本机 MSYS2 环境缺少 `dirname`/`mkdir`，Linux 目标脚本 `deploy/init.sh` 无法直接
  在该环境运行；本次用相同 OpenSSL 参数生成本地 secrets，脚本本身未作变更。
- 首次 Docker 设置实测发现管理员用户名规则未允许邮箱中的 `@`，FastAPI 422 的
  detail 数组又被前端显示为 `[object Object]`。现已允许常见邮箱式用户名字符，
  前端只提取结构化错误的 `msg` 字段，并加入 2 项原生 Node 回归测试；修复镜像
  无损重建后 Setup 仍保持未完成状态，日志 secret 扫描通过。
- Edge 密码管理器会把同页的 AI 与飞书配置误判成登录表单，向模型、Webhook 和
  密钥字段填入保存的登录凭据。现已使用独立字段名、关闭普通字段自动填充，并将
  两类密钥隔离为不同 `new-password` 分区；模型输入通过原生 `datalist` 提供
  `gpt-5.4-mini`、`gpt-5.4`、`gpt-5.4-nano` 预设且保留自由输入。这三项均经
  OpenAI 官方模型页确认支持本项目使用的 Chat Completions 接口。
# 已验证问题

- 2026-08-16：Telegram QR 登录依赖已保存的 API ID 与 API Hash；未配置时 TDLib 不会初始化。Collector 现以 409 返回明确提示，WebUI 会展示该提示，避免无提示的 500/不可用状态。
- 2026-08-16：TDLib 默认调试日志可能输出认证请求参数；创建客户端前必须将 `td_set_log_verbosity_level` 设为 0，且认证失败只向 WebUI 返回固定的非敏感提示。
