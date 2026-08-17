# Chat Insight QQ Adapter

AstrBot v4.27.3+ 的薄 QQ 适配器。它只负责群列表、群事件标准化、持久
Outbox 和发送 Core；所有消息源默认关闭，报告、AI 与飞书均在 Core 中运行。

配置 `core_url` 和部署时生成的同一 Collector Token。插件数据存放于 AstrBot
插件数据目录，更新插件不会覆盖 `outbox.db`。
