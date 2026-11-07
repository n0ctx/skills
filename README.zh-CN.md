# Skills

[English](README.md)

个人 Agent Skill 集合。每个技能是一个独立目录，`SKILL.md` 为该技能入口。

## 技能索引

| 技能 | 用途 |
|---|---|
| dag-engineering | 大规模多会话工程的规划与控制 |
| guard-ratchet | 落地棘轮式源码守卫（复杂度、死代码、重复、N+1、循环依赖、测试形状） |
| reader-first-writing | 任何给人读的文字的句子级可读性，不分文体和语言 |
| software-architecture | 软件架构任务（边界、权衡、迁移、架构决策） |
| software-engineering | 编码、调试、配置、测试、评审 |
| tavern-aesthetic | 角色扮演 / 互动小说 / 叙事型网页的沉浸式界面设计 |
| writing-for-agents | 撰写与改进 agent 要阅读执行的文本（prompt、SKILL.md、AGENTS.md、handoff） |

## 安装

每个技能都能单独安装到任意 agent。三种方式，选一种即可。

### 1. skills CLI —— 按技能、按 agent

```bash
npx skills add n0ctx/skills --list
npx skills add n0ctx/skills --skill guard-ratchet -a claude-code -g
npx skills add n0ctx/skills --skill tavern-aesthetic -a cursor -g --copy
```

| 参数 | 作用 |
|---|---|
| `-s, --skill <name>` | 只装指定技能；可重复、逗号分隔，或用 `*` 装全部 |
| `-a, --agent <name>` | 指定 agent，如 `claude-code`、`cursor`、`codex`；不填则交互选择 |
| `-g, --global` | 装到用户级目录，而非当前项目 |
| `--copy` | 复制文件而非软链 |
| `-l, --list` | 只列出可用技能，不安装 |

CLI 会自动发现 `skills/<name>/SKILL.md`，不需要额外清单。

### 2. Claude Code 插件市场

```bash
/plugin marketplace add n0ctx/skills
/plugin install guard-ratchet@n0ctx-skills
```

Claude Code 2.1.275+ 可一步完成：

```
/plugin install guard-ratchet --marketplace n0ctx/skills
```

市场名取自 `.claude-plugin/marketplace.json` 的 `name`（`n0ctx-skills`）；若客户端注册的名字不同，用 `/plugin marketplace list` 查。每个技能是一个独立插件，各自带 `.claude-plugin/plugin.json`。

### 3. link.sh —— 自建安装脚本，基于软链

```bash
git clone https://github.com/n0ctx/skills.git ~/Projects/skills
~/Projects/skills/scripts/link.sh --dry-run
~/Projects/skills/scripts/link.sh --skill guard-ratchet --agent claude,workbuddy
~/Projects/skills/scripts/link.sh --agent all
~/Projects/skills/scripts/link.sh --skill tavern-aesthetic --agent cursor --copy
```

| 参数 | 作用 |
|---|---|
| `--skill NAME` | 只装指定技能；可重复或逗号分隔，默认全部 |
| `--agent NAME` | `agents`、`claude`、`workbuddy`、`codex`、`cursor`、`all`，可重复 |
| `--target DIR` | 追加自定义目标目录 |
| `--copy` | 复制目录而非软链 |
| `--dry-run` | 只打印，不改动任何文件 |
| `--force` | 覆盖同名实体目录（先移入目标目录的 `.trash`） |

不带参数时：把全部技能软链到 `~/.agents/skills`。目标目录不存在会自动创建。

## 更新

| 安装方式 | 更新方法 |
|---|---|
| link.sh（软链） | `git pull` 后所有 agent 立即生效 |
| link.sh `--copy` | 重新执行同一条命令 |
| skills CLI | `npx skills update` |
| 插件市场 | `/plugin marketplace update n0ctx-skills` |

## 卸载

- CLI：`npx skills remove guard-ratchet -g`
- 插件市场：`/plugin uninstall guard-ratchet@n0ctx-skills`
- link.sh：在对应 agent 目录里 `unlink <软链路径>`，不要删除它指向的目标。

## 目录约定

```
skills/
└── <name>/
    ├── SKILL.md                     # 必需，YAML frontmatter 含 name/description
    ├── .claude-plugin/plugin.json  # Claude Code 插件清单
    ├── references/                 # 可选，按需加载的参考文档
    └── scripts/                    # 可选，可执行脚本
.claude-plugin/marketplace.json     # 市场清单，一个技能一个插件
scripts/link.sh                     # 本地安装脚本
```

## 兼容性说明

- 同一个 agent 目录不要混用多种安装方式。若已有工具在管理 `~/.claude/skills`、`~/.agents/skills`、`~/.workbuddy/skills` 里的软链，安装同名技能会替换掉原有链接。先跑 `--dry-run`；输出「重设软链」表示已有链接指向别处。
- skills CLI 与 `link.sh` 默认都用软链；不希望依赖 clone 路径时用 `--copy`。
- 保持 `SKILL.md` 位于 `skills/<name>/SKILL.md`。把它移到更深层（如 `plugins/<name>/skills/<name>/SKILL.md`）会让 `npx skills add` 找不到技能。`plugin.json` 用 `"skills": "./"` 就是为了避免这种移动。

## 许可

各技能目录下的 LICENSE 为准；未声明者版权归作者所有。
