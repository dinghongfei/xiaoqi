# 输入

先由 Agent 用环境已登录的 `lark-cli` 拉文档（**不要**加 `--profile` / `--as`）。从用户链接取出 token，**只传 token**，不要传 `feishu.doubao.com` 等完整 URL：

```
lark-cli drive +inspect --url 'WIKI_TOKEN' --type wiki   # 仅 wiki
lark-cli docs +fetch --api-version v2 --doc 'DOCX_TOKEN' --doc-format markdown
lark-cli docs +fetch --api-version v2 --doc 'DOCX_TOKEN' --doc-format xml --detail full
```

把正文写入 `data/jobs/<token>/raw.md` 与 `raw.xml` 后：

```
--token 'DOCX_TOKEN'
--token 'WIKI_TOKEN' --kind wiki --section blog
```

正文里的图片/视频若已是完整媒体 URL，脚本会直接下载到 `data/jobs/<token>/media/`，不必先 `media-download`。

可选：`--markdown`、`--xml`、`--media-dir`、`--document-id`。

不需要飞书 App ID / Secret。脚本不会 subprocess 调用 lark-cli。
