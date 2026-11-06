# Network Topology

This file is the single source of truth for the proxy/network environment
across both Mac machines. An agent that reads this should not need to
re-explore the environment before making changes — unless the audit script
shows a mismatch, in which case update this file first.

Last verified: 2026-11-06 17:00 JST.

## Machines

| Machine | Hostname | macOS | Tailscale IP |
|---|---|---|---|
| MacBook Air | `YunzhideMacBook-Air.local` | 27.2 | 100.91.254.69 |
| Mac mini | `YunzhiWang.local` | 27.2 | 100.96.164.38 |

Both on the same Tailnet (`tail0a6daa.ts.net`).

## Cross-machine links

### Tailscale

- Air ↔ mini are on the same Tailnet.
- SSH from Air to mini: `ssh yunzhiwang@100.96.164.38`.
- Tailscale traffic (`100.64.0.0/10`, `*.ts.net`, `*.tailscale.com`) is in
  the system proxy bypass list and in `NO_PROXY`, so it does not go through
  Clash.

### SSH config

`~/.ssh/config` on Air:

```
Host 10.* 100.* 127.* 169.254.* 192.168.* 172.16.* ... 172.31.* localhost *.local *.lan *.cn
  ProxyCommand none

Host *
  ProxyCommand /Users/yunzhiwang/.local/bin/clash-ssh-nc %h %p
```

`clash-ssh-nc` is a one-line wrapper:
```sh
exec /usr/bin/nc -X 5 -x 127.0.0.1:7897 "$@"
```

So: SSH to Tailscale/local/CN hosts goes direct; SSH to everything else goes
through Clash's SOCKS proxy on 7897.

Air maintains persistent SSH master sockets to mini under
`~/.hermes/desktop-ssh/` (two `ssh -M -N -f` processes with
`ControlPersist=300`).

### Paseo (remote control)

- Paseo CLI connects Air to mini via a relay (`relay.paseo.sh:443`).
- Host file: `~/.paseo/mac-mini.host`
- Hosts registry: `~/.paseo/hosts.json`
- Air `.zshrc` has a `paseo-mini()` function that reads the host file.
- Paseo on mini spawns Claude CLI processes (observed PID 81607 on mini
  spawning multiple `claude` child processes).

### Hermes gateway

- LaunchAgent: `ai.hermes.gateway.plist` (WorkingDirectory `~/.hermes`)
- Unix socket: `~/.hermes/gateway.sock`
- PID file: `~/.hermes/gateway.pid`
- Logs: `~/.hermes/logs/gateway.log`, `~/.hermes/logs/gateway.error.log`
- KeepAlive on crash (exit 75), not on clean exit (exit 0).
- ThrottleInterval 30s.
- The gateway is a separate process from the Headroom hermes instance on
  port 8789; do not confuse them.

## Clash Verge (both machines, same structure)

### Processes

| Component | Path |
|---|---|
| App | `/Applications/Clash Verge.app` |
| Service | `/Library/PrivilegedHelperTools/io.github.clash-verge-rev.clash-verge-rev.service.bundle` |
| Core | `verge-mihomo` |
| Runtime config | `/Library/Application Support/clash-verge-service/users/501/runtime/config.yaml` |
| Unix socket | `/var/run/clash-verge-service/users/501/verge-mihomo.sock` |
| User config | `~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml` |
| LaunchAgent | `io.github.clash-verge-rev.clash-verge-rev.plist` |

Query live state via the unix socket (read-only):
```sh
curl -s --unix-socket /var/run/clash-verge-service/users/501/verge-mihomo.sock http://localhost/configs
curl -s --unix-socket /var/run/clash-verge-service/users/501/verge-mihomo.sock http://localhost/proxies
curl -s --unix-socket /var/run/clash-verge-service/users/501/verge-mihomo.sock http://localhost/rules
curl -s --unix-socket /var/run/clash-verge-service/users/501/verge-mihomo.sock http://localhost/connections
```

### Core settings

- Mixed port: 7897 (HTTP + SOCKS in one port)
- TUN: `utun1024`, gVisor stack, auto-route, DNS hijack `any:53`, IPv6 off
- Mode: rule
- allow-lan: false
- find-process-mode: strict (Air)
- unified-delay: true

### PROXY group (the final exit for unmatched traffic)

- Type: `fallback` (not `url-test` — picks first available, not lowest latency)
- Health check URL: `https://www.gstatic.com/generate_204`
- Interval: 60 seconds
- Timeout: 5 seconds
- `lazy: false` (checks even when idle)
- Node order: Korea 03 → 01 → 02 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → REJECT
- If all nodes fail, traffic hits `REJECT` — it does not fall back to direct.

### Other groups (not the final exit, but exist in the subscription)

- `自动选择`: URLTest, interval 86400s (effectively dormant), picks lowest
  latency across all nodes.
- `故障转移`: Fallback, interval 7200s, all nodes in subscription order.
- `trumpyun - 特朗普云`: Selector, manual.

These groups exist in the proxy list but the final `MATCH` rule sends to
`PROXY`, not to them. AI-related rules also send to `PROXY`.

### Rules

- Air: 669 rules. Mini: 767 rules.
- AI domains (`claude.ai`, `claude.com`, `anthropic.com`,
  `claudeusercontent.com`, `x.ai`) → PROXY.
- AI process names (`Claude`, `Claude.exe`, `Claude Helper`, `claude`) → PROXY.
- AI keywords (`anthropic`, `claude`, `openai`, `openaimerge`) → PROXY.
- A complex AND rule sends traffic from agent CLIs (`claude`, `codex`,
  `grok`, `kimi-cli`, `curl`, `git`, `ssh`, `npm`, etc.) to PROXY when the
  destination is not a CN domain.
- Final rule: `MATCH → PROXY`.

### UDP policy

- `NETWORK,udp → REJECT` — all UDP is rejected by default.
- Specific STUN/TURN ports rejected first: 3478, 5349, 19302.
- Syncthing UDP 22000 → DIRECT (exempted before the blanket reject).
- Node `udp: true` in proxy metadata does not override this; the rule layer
  takes precedence.

### System proxy bypass list (both machines, identical)

Includes: `127.0.0.1`, private ranges (`192.168.0.0/16`, `10.0.0.0/8`,
`172.16.0.0/12`), `100.64.0.0/10` (Tailscale), `*.local`, `*.ts.net`,
`*.tailscale.com`, WPS/Kingsoft domains, WeChat/QQ/Tencent domains, Bilibili,
and several specific IPs.

### Node switching behavior

When the PROXY fallback group switches nodes, only **new** connections use the
new node. Existing long-lived connections (e.g. an active Anthropic API
stream) stay on the old node until they close. This is expected behavior, not
a bug.

## Headroom (both machines, three parallel instances)

Headroom is a local proxy that sits between AI clients and upstream API
providers. It does compression, caching, and protocol conversion. It is not a
system-wide proxy — only clients whose `BASE_URL` points to a Headroom port
go through it.

### Common config

- Install: `~/.local/share/uv/tools/headroom-ai/`
- Binary: `~/.local/bin/headroom`
- Deploy: `~/.headroom/deploy/{default,kimi,hermes}/`
- Each instance has: `run-headroom.sh`, `manifest.json`, `ensure-headroom.sh`
- Mode: cache
- Backend: anthropic
- Telemetry: off
- Rate limit: off
- HTTP/2: off
- Keepalive expiry: 20s (this is upstream connection idle timeout, not
  process restart)
- Health endpoint: `/readyz` on each port

### LaunchAgents

| Instance | Label | Port | RunAtLoad | KeepAlive |
|---|---|---|---|---|
| default | `com.headroom.default` | 8787 | true | true |
| kimi | `com.headroom.kimi` | 8788 | true | true |
| hermes | `com.headroom.hermes` | 8789 | true | true |

`com.headroom.default.daily-restart` runs `launchctl kickstart -k
gui/501/com.headroom.default` once daily (05:23 on Air; exact time on mini
not yet verified).

### Manifest is the source of truth

The `--openai-api-url` argument in the Headroom process command line comes
from `manifest.json` (`proxy_args` array and `base_env`), not from
environment variables in `run-headroom.sh`. If you change the OpenAI upstream
for a Headroom instance, you must update `manifest.json` — changing only
`run-headroom.sh` will not take effect after restart.

### Instance upstreams (current state after 2026-11-06 changes)

| Instance | Port | OpenAI-compatible upstream | Anthropic upstream |
|---|---|---|---|
| default | 8787 | Air: x.ai / Mini: Nous | default (api.anthropic.com) on both |
| kimi | 8788 | api.kimi.com/coding | api.kimi.com/coding |
| hermes | 8789 | inference-api.nousresearch.com | Air: api.kimi.com/coding / Mini: default |

The hermes instance's Anthropic upstream differs between machines because
Air's `run-headroom.sh` sets `ANTHROPIC_TARGET_API_URL` to Kimi, while mini's
does not set it (uses Headroom default).

## Agent routing

### Claude CLI

Config: `~/.claude/settings.json`, key `env.ANTHROPIC_BASE_URL`.

| Machine | Port | Upstream |
|---|---|---|
| Air | 8787 | Anthropic (via Headroom default) |
| Mini | 8787 | Anthropic (via Headroom default) |

Both machines also set `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`
in the same settings env block, pointing to 7897.

### Codex CLI

Config: `~/.codex/config.toml`, `model_provider = "headroom"`,
`[model_providers.headroom] base_url`.

| Machine | Port | Model | Upstream |
|---|---|---|---|
| Air | 8787/v1 | gpt-6.1-terra | x.ai |
| Mini | 8787/v1 | gpt-6.1-terra | Nous |

The Codex CLI function in `.zshrc` wraps `codex` to set
`HEADROOM_PROJECT=${HEADROOM_PROJECT:-guoke-invest}`.

### Hermes

Config: `~/.hermes/config.yaml` (model section) + `~/.hermes/.env`.

Default model: provider `openai-codex`, base_url
`http://127.0.0.1:8789/backend-api/codex`, model `gpt-6.1-terra`,
api_mode `codex_responses`.

Provider routing in `.env`:
- `NOUS_INFERENCE_BASE_URL` → `http://127.0.0.1:8789/v1`
- `HERMES_CODEX_BASE_URL` → `http://127.0.0.1:8789/backend-api/codex`
- `KIMI_BASE_URL` → `http://127.0.0.1:8788`

Hermes `.env` also sets `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` to 7897 and
`NO_PROXY` including localhost, Tailscale, and both machine IPs.

### Kimi CLI (standalone)

Config: `~/.kimi-code/config.toml`, `base_url` points directly to
`https://api.kimi.com/coding/v1`. This is NOT through Headroom. Traffic goes
through Clash only.

### Grok CLI (standalone)

Config: `~/.grok/config.toml`. No Headroom `base_url` found. The Headroom
default manifest has `tool_envs.grok` with `GROK_MODELS_BASE_URL` pointing to
8787/v1, but this only applies if launched through Headroom's wrap mechanism.
The standalone `grok` binary (`~/.grok/bin/grok`) does not use it.

## Terminal proxy environment

Both machines now use the same mechanism: a launchd LaunchAgent that runs at
login and sets proxy variables in the GUI domain.

### LaunchAgent

File: `~/Library/LaunchAgents/com.yunzhiwang.proxy.env.plist`
Label: `com.yunzhiwang.proxy.env`
RunAtLoad: true
KeepAlive: none (one-shot script, runs and exits)

The script runs `launchctl setenv` for:
- `HTTP_PROXY` / `http_proxy` → `http://127.0.0.1:7897`
- `HTTPS_PROXY` / `https_proxy` → `http://127.0.0.1:7897`
- `ALL_PROXY` / `all_proxy` → `socks5://127.0.0.1:7897`
- `NO_PROXY` / `no_proxy` → `localhost,127.0.0.1,::1,100.64.0.0/10,*.ts.net,*.tailscale.com`
- `NODE_USE_ENV_PROXY` → `1`

This affects GUI apps, LaunchAgent services (Headroom), and terminals opened
from Spotlight/Dock. It does not affect SSH sessions or already-running
processes.

### History

- Air: has had this LaunchAgent for a while.
- Mini: installed 2026-11-06. Previously used `~/.zshrc proxy_on` (a shell
  function that exported proxy vars on zsh startup). That function was
  removed during unification.

### `.zshrc` persistent env

Both machines have a Headroom persistent env block in `~/.zshrc`:
```
export HEADROOM_PORT="8789"
export HEADROOM_HOST="127.0.0.1"
export HEADROOM_MODE="cache"
export HEADROOM_BACKEND="anthropic"
...
```

On Air, `.zshrc` also has `ANTHROPIC_TARGET_API_URL` set to Kimi and
`OPENAI_TARGET_API_URL` set to Nous in this block. On mini, only
`OPENAI_TARGET_API_URL` is set to Nous.

## Claude Switcher (both machines)

Claude Switcher is not in the traffic path. It is a watchdog that kills
Claude when the proxy infrastructure is down.

### Bodyguard

- Script: `/Library/Application Support/claude-switcher/claude-bodyguard.sh`
- LaunchDaemon: `local.claude-bodyguard` (system domain)
- Interval: 10 seconds
- Checks: (1) fake-ip `198.18.x.x` exists in network interfaces, (2)
  `verge-mihomo` process is running.
- If either check fails: terminates Claude Desktop (`Claude.app`) and Claude
  Code CLI (native binary and `@anthropic-ai/claude-code` via node/bun).
- Logs: `~/Library/Logs/claude-bodyguard.log`
- Does not modify any config or restart Claude.

### Timezone watchdog

- Script: `/Library/Application Support/claude-switcher/tz-watchdog.sh`
- LaunchDaemon: `local.tz-watchdog` (system domain)
- Checks `/etc/localtime` symlink target. If not `Asia/Seoul`, runs
  `systemsetup -settimezone Asia/Seoul`.
- Air interval: 3600s. Mini interval: 60s.
- Logs: `~/Library/Logs/tz-watchdog.log`

### GUI app and CLI

- GUI: `/Applications/Claude切换器.app` (Chinese name, running on Air during
  audit)
- CLI: `~/.local/bin/claude-switch.sh` (audit/switch/fix commands)
- Auto-update: `local.claude-update.plist`, every 12 hours

### Version note

The installed bodyguard script differs from the template in
`~/Downloads/ClaudeSwitcher-1.7.1/` and from
`~/Desktop/Projects/claude-switcher/`. The installed version additionally
kills Claude Code CLI, not just Desktop. Always refer to
`/Library/Application Support/claude-switcher/` for current behavior.

## Three layers of proxy entry

The environment has three independent ways traffic enters Clash:

1. **System proxy** (`networksetup` / `scutil --proxy`): macOS system proxy
   settings, configured by Clash Verge to point at 7897. Affects most GUI
   apps and system services.
2. **Environment variables** (launchd + shell): `HTTP_PROXY` etc. in the
   process environment. Affects CLI tools, Headroom, Node, Python.
3. **TUN** (`utun1024`): virtual network interface that captures all traffic
   not bypassed by route rules. Catches anything that ignores system proxy
   and env vars.

All three point to the same Clash instance on 7897. They coexist; none is
redundant because different software honors different layers. TUN is the
catch-all fallback.
