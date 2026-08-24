---
name: convert-wechat
description: 把已转换的官网 Markdown 换成公众号预览页：左侧文章预览（手机/电脑），右侧可调主题/字体/字号/主题色，一键复制当前样式。
---

# 转换为公众号文章

用户能听懂的名字：**转换为公众号文章**。

本目录是完整 Skill，拷到其他 Agent 的 skills 下即可用，**不要**依赖宿主项目的 CLI 包。

```
convert-wechat/
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

官网 Markdown 已写好之后。推荐先 `deploy-local`，这样预览页里的图片是可访问的绝对 URL。

```mermaid
flowchart LR
  dl[download-feishu-doc] --> cw[convert-website]
  cw --> cm[compress-media]
  cm --> loc[deploy-local]
  loc --> wx[convert-wechat]
```

## 命令

```bash
uv run python <本Skill目录>/scripts/run.py
uv run python <本Skill目录>/scripts/run.py --markdown path/to/article.md --root /path/to/workspace
```

默认读 last-job 的 `content_path`。

## 依赖

见 `scripts/requirements.txt`（`markdown`、`pydantic-settings`、`pygments`）。

## 行为

- **不改写原文**，只换皮，并把飞书 XML 里的颜色/下划线/高亮补回来。
- 仅当正文第一行一级标题与 front matter 的 `title` 相同，才当作文章标题去掉。正文里其它一级标题（如「# 一、…」）保留。公众号编辑器自己有标题栏。
- `figure` → 图+注；markdown 图片的 alt 也当 caption。
- grid 展平；video / 视频 callout 做成信息卡片，后面的封面图收进卡片。
- 代码块保留语言，带标题时显示标题栏，并用 Pygments 做语法高亮。
- 加粗、斜体、下划线、删除线、字体颜色、背景高亮、有序/无序列表、表格、引用都会进预览 HTML。
- 图片改成 `SITE_BASE_URL` 绝对地址。
- 写入 `preview/_wechat/{lang}/{slug}/index.html`。
- 预览页左侧是文章（可切手机 / 电脑宽度），右侧可调主题、字体、字号、主题色。预览用 CSS 变量；点「一键复制」时在浏览器里把当前计算样式写成 inline，并把图片嵌进剪贴板。不要单独复制图片（`127.0.0.1` 公众号后台拉不到）。
- 没有「发布」按钮，也不接主题市场。
- 成功时打印 `WECHAT_PREVIEW=...`

飞书里无法写入系统剪贴板，复制必须在浏览器预览页完成。
