# Skills

本分支专供**豆包工作 Agent**：直接使用仓库 `skills/` 与内置已登录的 lark-cli。不要为其它 IDE/Agent 软链或拷贝本目录。

每个子目录都是完整 Skill：脚本只依赖本目录，不要调用宿主项目的 `bot` 包。

```
skill-name/                  # 技能根目录
├── SKILL.md                 # 核心指令（必须）
├── scripts/                 # 可执行脚本（可选）
├── references/              # 参考资料（可选）
└── assets/                  # 资源文件（可选）
```

入口是 `scripts/run.py`。没有素材时不要建空的 `assets/`。

**在本仓库**（已 `uv sync`）一律走项目环境：

```bash
uv run python <本Skill目录>/scripts/run.py
```

`uv run` 用的是仓库根目录 `.venv`，**不会**根据 `scripts/requirements.txt` 另装一套。Skill 依赖须写在仓库 `pyproject.toml` 里。`uv run bot` 只用于 `preview-http`。

飞书读写由豆包工作 Agent 调用环境已登录的 `lark-cli`（不要 `--profile` / `--as`），脚本只处理本地文件。另需 Hugo / ffmpeg，以及工作区 `.env`。请把工作目录设为项目根目录。

执行时以**站点工作区**为数据根（`site/`、`data/`、`.env`），用 `--root` 或环境变量 `BOT_ROOT` 指定。
