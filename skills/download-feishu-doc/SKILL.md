---
name: download-feishu-doc
description: 下载飞书云文档（wiki→docx），拉取 markdown 与 xml，把图片/视频/画板落到 static/ 并改成本地路径。不写 Hugo、不部署。
---

# 下载飞书云文档

用户能听懂的名字：**下载飞书云文档**。

本目录是完整 Skill，拷到其他 Agent 的 skills 下即可用，**不要**依赖宿主项目的 CLI 包。

```
download-feishu-doc/
├── SKILL.md
├── scripts/
│   ├── run.py
│   └── requirements.txt
├── references/
│   ├── input.md
│   └── output.md
└── assets/                  # 资源文件（本 Skill 暂无）
```

## 何时调用

- 用户给了飞书 docx / wiki 链接，后续要做官网或公众号。
- 官网预览、公众号预览、只丢链接：都先跑本 Skill。
- 同一链接再次发送也必须再跑：云文档可能已修改。不要因为 `data/last-job.json` 已有同一 token 而跳过。
- 仅当用户**没有**给新链接、只要把上次已下载的 `processed.md` 再出公众号时，才读 `data/last-job.json`。

```mermaid
flowchart LR
  dl[download-feishu-doc] --> cw[convert-website]
  cw --> cm[compress-media]
  cm --> loc[deploy-local]
  loc --> wx[convert-wechat]
```

## 命令

```bash
uv run python <本Skill目录>/scripts/run.py --url 'https://xxx.feishu.cn/docx/TOKEN'
uv run python <本Skill目录>/scripts/run.py --url 'https://xxx.feishu.cn/wiki/TOKEN' --section blog --root /path/to/workspace
```

栏目固定 `blog`。

## 依赖

- 本机 `lark-cli`（已登录 bot 身份）
- Python 包见 `scripts/requirements.txt`（`httpx`、`pydantic-settings`）
- 工作区 `.env` 中的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `LARK_CLI_PROFILE`
- 禁止从其它目录拷贝生产密钥填入本项目

## 行为

1. wiki 先解析成 docx。
2. `docs +fetch` 拉 markdown + xml。
3. 下载图片、视频、画板缩略图，SHA256 命名写入 `site/static/image|video`。
4. 正文媒体改成本地路径。
5. 产物写入 `data/jobs/<token>/`（同一 token 会覆盖上次的 `raw.md` / `processed.md` / `raw.xml`），并更新 `data/last-job.json`。`raw.md` 是下载原文（含 `<title>`）。`processed.md` 由原文加工：开头 `<title>` 转成 markdown 一级标题，媒体改成本地路径。
6. **不**写 `content/`，**不**跑 Hugo。
7. 未更换的媒体 token 会复用 `site/static/` 里已有文件；正文和 XML 每次都从云端重新拉取。

元数据表格不完整时下载仍可成功，但 `convert-website` 会失败。可先 `enrich-doc` 写回云文档；没有编辑权限时请先下载，再 `enrich-doc`（只会写入本地已下载文档）。
