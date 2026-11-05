# writing-for-agents

An agent skill for writing or improving text that another AI agent reads and acts on: system prompts, subagent delegation briefs, SKILL.md files, MCP and tool descriptions, handoff documents, GitHub issues and plan files for coding agents, AGENTS.md / CLAUDE.md rules.

It is deliberately light. You give a rough request or an existing prompt, and the agent improves it in one pass, with no testing, A/B comparison, or eval loop.

The skill is built around a single idea: the reader has only the page. Before writing, it settles three things for that reader: where the work ends, what situation the reader is in, and what material it needs. It then writes in words the reader can use without the writer around. The specific rules were distilled from current Anthropic, OpenAI, and Google guidance (November 2026), keeping only advice that has a stated benefit, visibly changes what gets written, and that frontier models did not already list on their own when asked.

## Install

```bash
git clone git@github.com:n0ctx/writing-for-agents.git ~/.agents/skills/writing-for-agents

# Claude Code reads ~/.claude/skills/
ln -s ~/.agents/skills/writing-for-agents ~/.claude/skills/writing-for-agents
```

Agents without skill support can be told to read `SKILL.md` first and follow it.
