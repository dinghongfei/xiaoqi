# 输出

`inspect` 成功：标准输出 JSON，含 `article_text`、`doc_title`、`need_cover_prompt`、`default_date`、`can_edit` 等。失败：中文原因，退出码 1。

`apply` 成功：中文说明补全完成。有编辑权限会写回云文档；没有则说明已写入本地已下载文档路径。

若云文档或本地已下载文档顶部已有可解析属性表：拒绝补全（无需再写）。

无编辑权限且本地没有已下载文档：失败，提示先 `download-feishu-doc`。

不写 Hugo、不部署。
