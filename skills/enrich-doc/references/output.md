# 输出

`inspect` 成功：标准输出 JSON，含 `article_text`、`doc_title`、`need_cover`、`default_date` 等。`can_edit` 恒为 `null`。失败：中文原因（可能含应执行的 lark-cli），退出码 1。

`apply` 成功：中文说明已写入本地路径，并打印写回云文档要用的 lark-cli 命令（含缺封面时的 `media-insert`）。产物包括 `processed.md`（不改 `raw.md`）和 `data/jobs/<token>/enrich.xml`。XML 里没有生图提示词。

若本地已下载文档顶部已有可解析属性表：拒绝补全（无需再写）。

没有本地正文稿：失败，提示先用 lark-cli fetch 或先 `download-feishu-doc`。

`enrichment-ids --xml after.xml`：打印属性区块 id，逗号分隔，供 `block_move_after` 使用。

不写 Hugo、不部署。
