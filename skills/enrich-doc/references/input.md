# 输入

先由 Agent 用 `lark-cli docs +fetch --doc TOKEN` 拉 markdown（不要 `--profile` / `--as`，不要传 feishu.doubao.com URL），写入 `data/jobs/<token>/raw.md` 或传 `--markdown`。然后：

```
inspect --token 'DOCX_TOKEN'
apply --token 'DOCX_TOKEN' --slug … --lang zh --title … --date YYYY-MM-DD --author … --categories … --summary … [--cover-image data/jobs/<token>/cover.png]
```

不要配置 `LLM_*`：字段由编排该 Skill 的 Agent 生成。缺封面时由 Agent 生图存盘，不要写封面提示词。脚本不调用 lark-cli。

apply 只写本地属性表与 `enrich.xml`，**不**把封面图写进 `processed.md`。写回飞书由 Agent 执行 `docs +update append` → fetch xml `--detail with-ids` → `enrichment-ids` → `block_move_after`；缺封面再 `docs +media-insert --file cover.png` 并把图片移到「图片」标题后，然后重新 fetch 并跑 `download-feishu-doc`，用云文档覆盖本地稿。`--doc` 一律用 token。失败则只保留本地属性表，不要把封面写进 processed.md。
