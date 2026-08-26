# 输入

先由 Agent 用环境已登录的 `lark-cli` 拉文档（**不要**加 `--profile` / `--as`），再跑脚本：

```
lark-cli drive +inspect --url 'https://xxx.feishu.cn/wiki/TOKEN'   # 仅 wiki
lark-cli docs +fetch --api-version v2 --doc 'DOC' --doc-format markdown
lark-cli docs +fetch --api-version v2 --doc 'DOC' --doc-format xml --detail full
```

把正文写入 `data/jobs/<token>/raw.md` 与 `raw.xml` 后：

```
--url 'https://xxx.feishu.cn/docx/TOKEN'
--url 'https://xxx.feishu.cn/wiki/TOKEN' --section blog
```

正文里的图片/视频若已是完整 URL，脚本会直接下载到 `data/jobs/<token>/media/`，不必先 `media-download`。

可选：`--markdown`、`--xml`、`--media-dir`、`--document-id`。

不需要飞书 App ID / Secret。脚本不会 subprocess 调用 lark-cli。
