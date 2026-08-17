# 安装与运维

## 端口与网络

基础 Compose 只把 Chat Insight 映射到 `127.0.0.1:8080`。Telegram Collector
只在 Docker 网络监听 8090；AstrBot/NapCat 仅在临时 `compose.admin.yml` 中映射
本机管理端口。公网部署复制 `Caddyfile.example` 并启用 TLS。

## Telegram

1. 在 `my.telegram.org` 为自己的账号申请 API ID/API Hash。
2. WebUI → 账号保存凭据，选择 QR 或手机号流程。
3. QR 链接会自动刷新；部分账号还会要求 2FA 或邮箱验证码。
4. 登录成功后进入消息源，逐个启用群/超级群/频道。
5. TDLib 数据位于 `telegram_tdlib_data` Volume，升级时绝不能删除。

## QQ

1. 阅读并接受 NapCat 上游许可；本项目不提供 QQ 协议或凭据。
2. 使用 `qq` Profile 启动官方 NapCat/AstrBot 镜像。
3. 在 NapCat 扫码登录自己的 QQ，在 AstrBot 创建 OneBot v11 连接。
4. 仓库内 Adapter 通过只读 bind mount 安装，并从 Docker secret 读取 Token。
5. WebUI 消息源页面明确启用群。Core 离线时消息先进入 AstrBot Volume 内 Outbox。

## 备份与升级

```bash
docker compose stop
docker run --rm -v chat-insight_chat_insight_data:/data -v "$PWD":/backup \
  alpine tar czf /backup/chat-insight-data.tgz -C /data .
docker compose pull
docker compose up -d
```

Telegram、AstrBot、NapCat Volume 应分别备份。恢复前确保应用主密钥与 TDLib
数据库密钥和备份来自同一部署。

## 已知限制

- v0.1.0 仅发布 Linux amd64 镜像，Core 为单进程/SQLite 单写者。
- QQ 历史补采依赖上游能力，当前只保证插件 Outbox 中已经接收的消息。
- 不同步平台消息编辑/删除；不下载媒体。
- 周报、自定义 Cron、报告重生成/导出、AstrBot LLM Bridge 延期到 v0.2。
