# 输入

必填：飞书 `message_id`（回复哪一条用户消息）。

可选：

```
--site-preview     官网预览 URL
--wechat-preview   公众号预览 URL
--summary          失败或补充说明（中文）
```

未传 URL 时读工作区 `data/last-job.json` 的 `site_preview` / `wechat_preview`。

无飞书应用凭证时跳过，不要编造密钥。豆包工作 Agent 不必调用本 Skill。
