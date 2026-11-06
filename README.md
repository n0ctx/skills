# Skills

个人 Agent Skill 集合。每个技能是一个独立目录，`SKILL.md` 为该技能入口。

## 技能索引

| 技能 | 用途 |
|---|---|
| dag-engineering | 大规模多会话工程的规划与控制 |
| guard-ratchet | 落地棘轮式源码守卫（复杂度、死代码、重复、N+1、循环依赖、测试形状） |
| software-architecture | 软件架构任务（边界、权衡、迁移、架构决策） |
| software-engineering | 编码、调试、配置、测试、评审 |
| tavern-aesthetic | 角色扮演 / 互动小说 / 叙事型网页的沉浸式界面设计 |
| writing-for-agents | 撰写与改进 agent 要阅读执行的文本（prompt、SKILL.md、AGENTS.md、handoff） |
| agent-browser-edge | 复用本机 Edge 登录态的浏览器自动化封装 |
| macos-maintenance | macOS 周期性体检与优化（只读扫描 → 报告 → 确认 → 修复） |

## 安装

```bash
git clone https://github.com/n0ctx/skills.git ~/Projects/skills
~/Projects/skills/scripts/link.sh          # 链接到 ~/.agents/skills
~/Projects/skills/scripts/link.sh --dry-run # 只看会改什么
```

`link.sh` 把 `skills/<name>` 软链到 `~/.agents/skills/<name>`，已被识别为技能的目录（含 `SKILL.md`）才会链接，不覆盖实体目录。

## 更新

```bash
cd ~/Projects/skills && git pull
```

软链指向目录内部，pull 后所有 Agent 立即生效，无需重新安装。

## 目录约定

```
skills/
└── <name>/
    ├── SKILL.md          # 必需，YAML frontmatter 含 name/description
    ├── references/       # 可选，按需加载的参考文档
    └── scripts/          # 可选，可执行脚本
```

## 许可

各技能目录下的 LICENSE 为准；未声明者版权归作者所有。
