---
name: compress-media
description: 扫描 site/static/image 与 video，用 ffmpeg 压缩。没装 ffmpeg 则跳过并说明。
---

# 压缩视频/图片

用户能听懂的名字：**压缩视频/图片**。

本目录是完整 Skill，由豆包工作 Agent 直接使用仓库 `skills/`。脚本只依赖本目录，**不要**调用宿主项目的 CLI 包。

```
compress-media/
├── SKILL.md                 # 核心指令（必须）
├── scripts/                 # 可执行脚本
│   ├── run.py
│   └── requirements.txt
├── references/              # 输入/输出说明
│   ├── input.md
│   └── output.md
└── assets/                  # 资源文件（本 Skill 暂无）
```

## 何时调用

`convert-website` 之后、`deploy-local` 之前。官网预览推荐链路包含本步。

```mermaid
flowchart LR
  cw[convert-website] --> cm[compress-media]
  cm --> loc[deploy-local]
```

## 命令

在**站点工作区**（含 `site/`）下执行，或传入 `--root`：

```bash
uv run python <本Skill目录>/scripts/run.py
uv run python <本Skill目录>/scripts/run.py --root /path/to/site-workspace
uv run python <本Skill目录>/scripts/run.py --image-dir ./site/static/image --video-dir ./site/static/video
```

外部依赖：本机 `ffmpeg`、Python 3.11+、`scripts/requirements.txt`。`ffmpeg` 未安装时脚本会跳过并中文说明，不要当成致命错误。

## 行为

- 扫描 `site/static/image` 与 `site/static/video`（可用参数覆盖）。
- 使用 ffmpeg；未安装则跳过并中文说明。
- 无额外必填参数。
