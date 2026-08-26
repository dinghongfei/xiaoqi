# 飞书内容助手

本分支专供**豆包工作 Agent**。先读 [AGENTS.md](AGENTS.md)。

用户说「安装环境 / 初始化 / 帮我装」时：按 AGENTS.md 在仓库根目录执行 `./install.sh`。不要向用户要飞书 App ID 和 Secret，不要创建飞书应用，不要下载 lark-cli。不要自己发明安装步骤，不要让用户去终端敲命令。

内容任务的 Skill 在 [skills/](skills/)（每目录一份 `SKILL.md`）。飞书云文档用环境已登录的 `lark-cli`（由你按 SKILL.md 执行，不要 `--profile` / `--as`）；本地加工用 `uv run python skills/<name>/scripts/run.py`。若报 `uv` 不在 PATH，改用 `$HOME/.local/bin/uv`（或 `$HOME/.cargo/bin/uv`）的绝对路径；`hugo` 同理，改用 `$HOME/.local/bin/hugo`。不要让用户改 PATH。不要自己实现 Agent 循环，不要用 Python 调 lark-cli，不要读取其它目录的生产密钥。
