# 输入

先 inspect，再 apply：

```
inspect --url 'https://xxx.feishu.cn/docx/TOKEN'
apply --url 'https://xxx.feishu.cn/docx/TOKEN' --slug … --lang zh --title … --date YYYY-MM-DD --author … --categories … --summary … [--cover-prompt …]
```

工作区 `.env` 需要飞书应用凭证。不要配置 `LLM_*`：字段由编排该 Skill 的 Agent 生成。

有云文档编辑权限时 apply 会回写飞书；没有则只写入本地 `processed.md`，不改 `raw.md`。无权限且还没下载时，先跑 `download-feishu-doc` 再 apply。
