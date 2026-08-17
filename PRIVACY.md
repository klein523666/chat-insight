# Privacy / 隐私说明

Chat Insight 是完全自托管的软件：

- 消息、Session、报告和配置保存在用户自己的服务器。
- 项目没有作者运营的服务器，没有 Telemetry，也不会默认上传任何聊天内容。
- 只有用户明确启用的 Source 才会持久化；私人聊天不会采集。
- v0.1.0 不主动下载图片、视频、文件、语音或 GIF，只保存文本占位和最小元数据。
- 默认不向 AI 发送 QQ 号、Telegram 内部 user ID；引用通过内部 message ID 校验。
- 用户选择的 AI Provider 会收到报告窗口内的文本；用户配置的飞书机器人会收到
  最终报告。这两个外部处理方的隐私条款由用户自行评估。
- 消息默认保留 90 天，报告默认永久保留。删除 Volume/数据库前请先备份。

This project is self-hosted, has no telemetry, and sends data only to providers
and Feishu targets explicitly configured by the operator.
