---
name: mac-proxy-env
description: >-
  Living map of the proxy, Clash, Headroom, agent routing, SSH, and Tailscale
  environment across the user's Mac machines. Use this skill before changing
  anything network-related — Clash config, proxy settings, Headroom ports or
  upstreams, agent BASE_URL, launchd proxy env, SSH config, Claude Switcher,
  Tailscale routing — so you act on facts instead of guessing. Also use it when
  the user mentions proxy, 7897, 8787, 8788, 8789, Clash Verge, Headroom,
  mihomo, TUN, clash-ssh-nc, proxy_on, or asks to audit or debug network
  connectivity on either Mac. After any change to this environment, update the
  skill's reference files per the self-iteration rule below.
---

# Mac Proxy Environment

## What this is

A self-updating knowledge base of the network/proxy stack on two Macs:
MacBook Air and Mac mini. It exists so that before you touch anything
network-related, you have the full picture without re-exploring.

## When to use

Read this skill before:
- Changing Clash Verge config, rules, proxy groups, or TUN
- Changing Headroom ports, upstreams, or profiles
- Changing agent `BASE_URL` in Claude, Codex, Hermes, Kimi, or Grok config
- Changing launchd proxy environment (`com.yunzhiwang.proxy.env`)
- Changing SSH config or `clash-ssh-nc`
- Changing Claude Switcher bodyguard or timezone watchdog
- Changing Tailscale or cross-machine connections
- Debugging "why can't X reach the internet" or "why is Claude using the wrong API"

If the user mentions 7897, 8787, 8788, 8789, Clash, Headroom, mihomo, TUN,
proxy, or asks to audit network state on either Mac, this skill applies.

## Shortest path to current state

Run the audit script. It prints the full proxy environment in one shot:

```sh
sh /Users/yunzhiwang/.agents/skills/mac-proxy-env/scripts/audit-proxy-env.sh
```

The script is read-only: it queries Clash via its unix socket, reads config
files, checks launchd state, and lists Headroom processes. It does not send
any traffic through the proxies or call any paid API. It sanitizes secrets —
no API keys, tokens, or subscription URLs appear in its output.

After running it, compare the output against `references/topology.md` and the
machine-specific file (`references/air.md` or `references/mini.md`). If
anything differs, the reference file is stale — update it per the
self-iteration rule below before acting on it.

## How to identify which machine you're on

| Hostname | Machine | Tailscale IP |
|---|---|---|
| `YunzhideMacBook-Air.local` | MacBook Air | 100.91.254.69 |
| `YunzhiWang.local` | Mac mini | 100.96.164.38 |

The audit script detects the machine by hostname and prints it in the first
section.

## Reference files

Read `references/topology.md` for the full network topology: machines,
Tailscale links, Clash, Headroom, agent routing, Claude Switcher, SSH, and
Paseo. This is the single document that should make re-exploring unnecessary.

Read the machine-specific file for details that differ:
- `references/air.md` — MacBook Air
- `references/mini.md` — Mac mini

Read `references/changelog.md` to see what has changed and when. This is an
append-only trail of environment modifications.

## Self-iteration rule

This skill stays accurate by being updated after every change. The rule is
simple: if you change the network/proxy environment, or discover that a
reference file's claim is wrong, update the relevant reference file and
append an entry to `references/changelog.md`.

What counts as a change:
- Clash config, rules, proxy groups, TUN settings, port assignments
- Headroom ports, upstreams, profiles, LaunchAgents, manifest content
- Agent `BASE_URL` in `~/.claude/settings.json`, `~/.codex/config.toml`,
  `~/.hermes/.env`, `~/.hermes/config.yaml`, `~/.kimi-code/config.toml`,
  `~/.grok/config.toml`
- launchd proxy env (`com.yunzhiwang.proxy.env.plist`)
- SSH config or `clash-ssh-nc`
- Claude Switcher scripts or LaunchDaemons
- Tailscale connection between machines
- Paseo or Hermes gateway configuration

Changelog entry format:

```markdown
## 2026-11-06 — <one-line summary>
- Changed: <what>
- Files updated: <which reference files>
- Verified by: <audit script / manual check / command output>
- Backed up to: <backup path if any>
```

The reason for this rule: the next agent that reads this skill will trust what
the reference files say. If they are stale, it will act on wrong information
and potentially break the environment. Keeping them current is not optional
cleanup — it is what makes the skill work.

## Safety constraints

Before changing anything in this environment:
1. Run the audit script and read the relevant reference file.
2. Back up the files you will change (`cp -p` to a timestamped directory).
3. Validate syntax after writing (`zsh -n`, `bash -n`, `python3 -m json.tool`,
   `python3 -c "import tomllib; tomllib.load(...)"` or equivalent).
4. If a change requires restarting a Headroom instance, only restart the one
   you changed — do not restart all three.
5. Verify after the change: re-run the audit script, check `/readyz` on
   affected Headroom ports, and confirm Clash state unchanged unless you
   meant to change it.

Do not change Clash rules, PROXY group node order, UDP policy, or TUN config
without explicit user approval — these affect all traffic on the machine.

## Future: Windows and Linux

This skill is Mac-specific. The audit script uses macOS tools (`scutil`,
`networksetup`, `launchctl`, `lsof`). When adapting for Windows or Linux, the
reference file structure and self-iteration rule stay the same; only the
script and the specific config paths change. Add a `references/windows.md` or
`references/linux.md` and a platform-specific audit script when needed.
