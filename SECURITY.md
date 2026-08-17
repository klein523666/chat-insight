# Security Policy / 安全策略

## 部署基线

- 不要直接向公网映射 Core、Telegram Collector、AstrBot、NapCat 或 OneBot。
- 通过 HTTPS 反向代理或 VPN/SSH Tunnel 使用 Chat Insight；反向代理拒绝
  `/internal/*`。
- 保护 `deploy/secrets/`、Telegram Session Volume、QQ 数据、SQLite 和备份。
- NapCat 密码回退只允许写入 `deploy/secrets/napcat_quick_password.txt`；保持文件
  权限为仅部署用户可读，禁止改为 Compose 环境变量或输出到日志。
- 首次创建管理员后仍应保留 Setup Token 文件，但应用会因管理员已存在而拒绝复用；
  可在完成备份后离线归档该文件。
- 定期轮换 LLM/飞书密钥；Collector Token 和主密钥轮换需要协调全部服务，不能
  直接替换主密钥，否则已有加密配置无法解密。

## 日志红线

Telegram code/2FA/API Hash/database key、QQ 凭据、Session、飞书 Webhook/Secret、
LLM API Key、Collector Token 不得出现在日志、Issue、截图或测试 fixture 中。
Compose 禁用 NapCat 容器的 Docker 日志，避免上游输出的临时登录二维码链接被
持久化；扫码和 QQ 诊断只使用绑定本机回环地址的临时管理页面。

## 漏洞报告

请使用 GitHub Security Advisory 私下报告。不要在公开 Issue 中附带真实凭据、
消息、数据库或 Session。报告应包含受影响版本、复现步骤、影响和建议修复。

## Security checklist

- [ ] Telegram session 未泄漏
- [ ] Telegram API Hash 未泄漏
- [ ] QQ 数据与登录态未泄漏
- [ ] Webhook/Secret 未泄漏
- [ ] LLM API Key 未泄漏
- [ ] 所有 Source 默认关闭
- [ ] WebUI 有管理员认证与 CSRF
- [ ] Internal API 未映射公网且启用 Bearer Token
