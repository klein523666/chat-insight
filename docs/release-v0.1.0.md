# Chat Insight v0.1.0

首个可用版本已完成本机真实 QQ、Telegram、OpenAI-compatible LLM、飞书与自动报告
闭环。所有消息源默认关闭，只有明确启用后才会保存消息。

## 主要功能

- Telegram 个人账号 TDLib 登录、Session 持久化、群/超级群/频道发现、实时采集与
  默认 3 小时补采。
- QQ 个人号 NapCat + OneBot v11 + AstrBot 采集，Core 离线期间由持久 Outbox 保留
  已启用群消息。
- 小时报、日报和 QQ + Telegram 混合报告，确定性统计、分块 Map-Reduce AI 分析与
  消息 ID 引用回填。
- 多飞书机器人目标、签名、低于 20KB 的卡片分片，以及 429/5xx/timeout 有界重试。
- 中文 WebUI、一次性管理员设置、服务端 Session、CSRF、Argon2id 与敏感配置加密。

## 安装

仅支持 Linux amd64。安装步骤见 README 与 `docs/installation.md`：

```bash
git clone https://github.com/klein523666/chat-insight.git
cd chat-insight
sh deploy/init.sh
cd deploy
docker compose up -d
```

QQ 为可选 `qq` Profile，并受 NapCat 上游有限、非商业许可约束。临时管理端口只能
绑定到 `127.0.0.1`，完成设置后应移除管理代理。

## 升级与备份

升级前备份 Core、TDLib、AstrBot 与 NapCat 四类 Docker Volume，以及
`deploy/secrets/`。不要执行 `docker compose down -v` 或删除 Volume；主密钥丢失后
已加密的 LLM 和飞书配置无法恢复。

## 已知限制

- 部分 QQ 账号在 NapCat/QQ 快速登录和密码回退时仍会被上游拒绝，NapCat 重启后
  需要重新扫码；已进入 AstrBot Outbox 和 Core 的消息不会因此丢失。
- NapCat 上游会把临时二维码链接写到 stdout，因此 Compose 默认禁用 NapCat 容器的
  Docker 日志；扫码和诊断使用回环管理页。
- 仅发布 linux/amd64；周报、自定义 Cron、导出、多账号 UI、ARM64 与 AstrBot LLM
  Bridge 延期到 v0.2。
- 尚未在真实 2C4G VPS 上验证性能；本机 Docker Desktop 结果不能作为 VPS 结论。

NapCat 不由本项目复制或重打包。启用 QQ 前请阅读仓库中的第三方许可说明。
