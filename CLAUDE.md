# Claude Code

本项目是飞书内容助手。先读 [AGENTS.md](AGENTS.md)。

用户说「安装环境 / 初始化 / 帮我装」时：按 AGENTS.md 向用户要飞书 App ID 和 Secret，然后在仓库根目录执行 `./install.sh --app-id … --app-secret …`。不要自己发明安装步骤，不要让用户去终端敲命令。

内容任务的 Skill 在 [skills/](skills/)（每目录一份 `SKILL.md`）。用 `uv run python skills/<name>/scripts/run.py` 执行确定性步骤。不要自己实现 Agent 循环，不要读取其它目录的生产密钥。
