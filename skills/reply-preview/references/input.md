# 输入

必填：飞书 `message_id`（回复哪一条用户消息）。

可选：

```
--site-preview     官网预览 URL
--wechat-preview   公众号预览 URL
--summary          失败或补充说明（中文）
```

未传 URL 时读工作区 `data/last-job.json` 的 `site_preview` / `wechat_preview`。

凭证：工作区 `.env` 的 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`（机器人身份）。
