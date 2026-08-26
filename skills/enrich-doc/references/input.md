# 输入

先由 Agent 用 `lark-cli docs +fetch` 拉 markdown（不要 `--profile` / `--as`），写入 `data/jobs/<token>/raw.md` 或传 `--markdown`。然后：

```
inspect --url 'https://xxx.feishu.cn/docx/TOKEN'
apply --url 'https://xxx.feishu.cn/docx/TOKEN' --slug … --lang zh --title … --date YYYY-MM-DD --author … --categories … --summary … [--cover-prompt …]
```

不要配置 `LLM_*`：字段由编排该 Skill 的 Agent 生成。脚本不调用 lark-cli。

apply 只写本地 `processed.md` 与 `enrich.xml`。写回飞书由 Agent 执行 `docs +update append` → fetch xml `--detail with-ids` → `enrichment-ids` → `block_move_after`。失败则只保留本地稿。
