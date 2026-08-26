# 输出

标准输出类似：

```
文档已处理，媒体已落到 static/。 识别到 slug=demo lang=zh-cn。
slug=demo
```

同一 token 再次处理会覆盖本地稿，标准输出类似：

```
文档已重新处理并覆盖本地稿，媒体已落到 static/。 识别到 slug=demo lang=zh-cn。
slug=demo
```

还没有 `raw.md`、或缺少媒体文件时：失败，并打印应执行的 `lark-cli` 命令（不含 `--profile` / `--as`）。

产物：

- `data/jobs/<token>/raw.md`（下载原文）、`processed.md`（`<title>` 已转成一级标题，媒体已本地化）
- `data/jobs/<token>/media/`（按 URL 下载的原始媒体）
- `data/last-job.json`
- 供站点引用的副本：`site/static/image/`、`site/static/video/`

不写 Hugo `content/`。
