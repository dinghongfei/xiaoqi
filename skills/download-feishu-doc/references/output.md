# 输出

标准输出类似：

```
文档已下载，媒体已落到 static/。 识别到 slug=demo lang=zh-cn。
slug=demo
```

同一 token 再次下载会覆盖本地稿，标准输出类似：

```
文档已重新下载并覆盖本地稿，媒体已落到 static/。 识别到 slug=demo lang=zh-cn。
slug=demo
```

产物：

- `data/jobs/<token>/raw.md`（下载原文）、`processed.md`（`<title>` 已转成一级标题，媒体已本地化）
- `data/last-job.json`
- 媒体写入 `site/static/image/`、`site/static/video/`

不写 Hugo `content/`。
