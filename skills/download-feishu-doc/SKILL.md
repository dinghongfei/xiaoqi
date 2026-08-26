---
name: download-feishu-doc
description: 把 Agent 用 lark-cli 拉好的飞书文档加工成本地 raw/processed 稿；正文里的媒体 URL 直接下载到 data/jobs/<token>/media/，再复制到 static/。脚本不调用 lark-cli。不写 Hugo、不部署。
---

# 下载飞书云文档

用户能听懂的名字：**下载飞书云文档**。

本目录是完整 Skill，由豆包工作 Agent 直接使用仓库 `skills/`。脚本只依赖本目录，**不要**调用宿主项目的 CLI 包。

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
  cli[你执行 lark-cli] --> dl[download-feishu-doc 脚本]
  dl --> cw[convert-website]
```

## 你来执行 lark-cli（脚本不会调）

调用时**不要**加 `--profile` 或 `--as`。从用户链接里取出路径上的 token（`/docx/TOKEN` 或 `/wiki/TOKEN`），**只把 token 传给 lark-cli**。不要把 `https://feishu.doubao.com/...` 等完整 URL 传给 `--doc` / `--url`，否则可能报无法解析该域名。

知识库 wiki 先解析成 docx token：

```bash
lark-cli drive +inspect --url 'WIKI_TOKEN' --type wiki
```

用返回的 `data.token` 作为下面的 docx token：

```bash
lark-cli docs +fetch --api-version v2 --doc 'DOCX_TOKEN' --doc-format markdown
lark-cli docs +fetch --api-version v2 --doc 'DOCX_TOKEN' --doc-format xml --detail full
```

写入：

- `data/jobs/<token>/raw.md`
- `data/jobs/<token>/raw.xml`

图片 / 视频：正文和 XML 里如果已是完整 URL，**不要**逐个跑 `media-download`。跑本脚本即可，脚本会 HTTP 下载到 `data/jobs/<token>/media/`，再复制一份到 `site/static/image|video`（官网和公众号要读 static）。

只有没有 URL 的 token（常见是画板）才需要：

```bash
lark-cli docs +media-download --token 'MEDIA_TOKEN' --output 'data/jobs/<token>/media/MEDIA_TOKEN'
lark-cli docs +media-download --token 'MEDIA_TOKEN' --output 'data/jobs/<token>/media/MEDIA_TOKEN' --type whiteboard
```

缺哪个媒体，脚本会打印对应命令；下完再跑一次脚本。

## 命令

```bash
uv run python <本Skill目录>/scripts/run.py --token 'DOCX_TOKEN'
uv run python <本Skill目录>/scripts/run.py --token 'WIKI_TOKEN' --kind wiki --section blog --root /path/to/workspace
```

也可传 `--url`（脚本只从路径里取 token，不会去解析域名）。还可显式传入已保存的文件：`--markdown`、`--xml`、`--media-dir`、`--document-id`。栏目固定 `blog`。

## 依赖

- 环境已登录的 `lark-cli`（豆包工作 Agent 已内置）；由**你**在提示词流程里调用，不要让 Python 去 subprocess
- Python 包见 `scripts/requirements.txt`（`httpx`、`pydantic-settings`）
- 不需要飞书 App ID / Secret，不要安装或绑定 lark-cli

## 行为

1. 读取 Agent 写好的 markdown / xml。
2. 正文里的完整媒体 URL 由脚本直接下载到 `data/jobs/<token>/media/`，再 SHA256 命名复制到 `site/static/image|video`。没有 URL 的 token（画板等）才需要你先 `docs +media-download`。
3. 正文媒体改成本地 `/image/`、`/video/` 路径。
4. 产物写入 `data/jobs/<token>/`（同一 token 会覆盖上次的 `raw.md` / `processed.md` / `raw.xml`），并更新 `data/last-job.json`。`raw.md` 是下载原文（含 `<title>`）。`processed.md` 由原文加工：开头 `<title>` 转成 markdown 一级标题，媒体改成本地路径。
5. **不**写 `content/`，**不**跑 Hugo。
6. 未更换的媒体会复用 `data/jobs/<token>/media/` 与 `site/static/` 里已有文件。

还没有 `raw.md` 时脚本会失败并打印应执行的 lark-cli 命令。元数据表格不完整时加工仍可成功，但 `convert-website` 会失败。可先 `enrich-doc`；写回云文档也由你用 lark-cli 完成。
