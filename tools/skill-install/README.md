# 把 Skill 装到自己的 Agent

在本仓库里打开 Codex 或 Claude Code 时，不需要安装：Codex 读取 `.agents/skills/`，Claude Code 读取 `.claude/skills/`（指向同一份 Skill 的符号链接）和根目录的 `CLAUDE.md`。

想在**仓库以外**的资料目录里使用这个 Skill 时，从仓库根目录运行（Python 3.10+，标准库）：

```sh
python3 tools/skill-install/install.py --dry-run
python3 tools/skill-install/install.py
```

安装器只创建符号链接，指回本仓库的 `.agents/skills/hao-job-workspace`，所以 `git pull` 后所有 Agent 同时更新：

| 位置 | 读取它的 Agent | 何时创建 |
| --- | --- | --- |
| `~/.agents/skills/hao-job-workspace` | Codex 及其他遵循 Agent Skills 约定的工具 | 总是 |
| `~/.claude/skills/hao-job-workspace` | Claude Code | 已存在 `~/.claude/` 时 |

同名位置已有不是本安装器创建的文件或目录时，跳过并返回非零，不覆盖。安装后重启已打开的 Agent 会话。移除链接：

```sh
python3 tools/skill-install/install.py --uninstall
```

只装 Skill 不会带上仓库里的模板和 Python 工具；Skill 会沿用你已有的资料，不假定这些工具存在。浏览器填写与独立审查仍取决于宿主能力，安装 Skill 不会增加这些权限。
