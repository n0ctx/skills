# Mac mini

Hostname: `YunzhiWang.local`
Tailscale IP: 100.96.164.38
macOS: 27.2 (Build 26B123)

Last verified: 2026-11-06 17:00 JST.

## Clash current state

- Mixed port: 7897
- TUN: utun1024, gVisor, auto-route, DNS hijack any:53, IPv6 off
- TUN route-exclude-address includes private ranges, Tailscale
  (`100.64.0.0/10`), and specific IPs (`39.103.215.37/32`,
  `159.226.29.14/32`, `223.71.204.50/32`).
- Mode: rule
- PROXY group: Fallback, now = Korea 06, interval 60s, timeout 5s
- Rule count: 767
- Final MATCH → PROXY
- UDP: NETWORK,udp → REJECT

## System proxy

- Wi-Fi: HTTP/HTTPS/SOCKS all enabled, 127.0.0.1:7897
- Ethernet and Thunderbolt Bridge also configured.
- Tailscale network service present in list.

## launchd environment

`com.yunzhiwang.proxy.env` loaded and active (installed 2026-11-06). GUI
domain has:
- HTTP_PROXY / HTTPS_PROXY → http://127.0.0.1:7897
- ALL_PROXY → socks5://127.0.0.1:7897
- NO_PROXY → localhost,127.0.0.1,::1,100.64.0.0/10,*.ts.net,*.tailscale.com
- NODE_USE_ENV_PROXY → 1

Previously: no launchd proxy env. Used `~/.zshrc proxy_on` function (removed
during unification).

## Headroom instances

| Port | Profile | PID (snapshot) | OpenAI upstream | Anthropic upstream |
|---|---|---|---|---|
| 8787 | default | 72507 | https://inference-api.nousresearch.com | default (api.anthropic.com) |
| 8788 | kimi | 1567 | https://api.kimi.com/coding | https://api.kimi.com/coding |
| 8789 | hermes | 1557 | https://inference-api.nousresearch.com | default (api.anthropic.com) |

All three `/readyz` return 200.

8787 was changed from x.ai to Nous on 2026-11-06 to preserve Codex behavior
when port role was unified. Both `run-headroom.sh` and `manifest.json` were
updated.

8788 and 8789 do not set explicit proxy env in their run scripts; they rely
on launchd global env and TUN.

## Agent routing (after 2026-11-06 unification)

- Claude CLI: `~/.claude/settings.json` → `ANTHROPIC_BASE_URL` = 8787
  (was 8789 before unification)
- Codex CLI: `~/.codex/config.toml` → `model_provider = "headroom"`,
  `base_url = http://127.0.0.1:8787/v1` (was 8789 before unification),
  model `gpt-6.1-terra`
- Hermes default: `~/.hermes/config.yaml` → provider `openai-codex`,
  `base_url = http://127.0.0.1:8789/backend-api/codex`
- Hermes Nous: `.env` `NOUS_INFERENCE_BASE_URL` = 8789/v1
- Hermes Kimi: `.env` `KIMI_BASE_URL` = 8788
- Kimi CLI standalone: direct to `https://api.kimi.com/coding/v1`
- Grok CLI standalone: no Headroom base_url in config

## `.zshrc` notable entries

- `proxy_on` / `proxy_off` functions removed (2026-11-06).
- Headroom persistent env block: `HEADROOM_PORT=8789`,
  `OPENAI_TARGET_API_URL=https://inference-api.nousresearch.com`.
  No `ANTHROPIC_TARGET_API_URL` (unlike Air).
- `ANTHROPIC_BASE_URL=http://127.0.0.1:8787` and
  `OPENAI_BASE_URL=http://127.0.0.1:8787/v1` exported in `.zshrc`.

## Claude Switcher

- Bodyguard: loaded, runs=16395, interval 10s, last exit 0.
- TZ watchdog: interval 60s (more frequent than Air's 3600s).
- Bodyguard script installed at `/Library/Application Support/claude-switcher/`.

## Hermes gateway

- `ai.hermes.gateway.plist` loaded.
- Socket: `~/.hermes/gateway.sock`.
- `~/.hermes/desktop-ssh/` does not contain master sockets to Air (mini is
  the SSH server, not client, in this setup).

## Paseo

- Mini is the Paseo server (relay target). Air connects to it.
- Paseo process on mini (PID ~81607) spawns Claude CLI child processes.
- These child processes have `ANTHROPIC_BASE_URL=8789` in their environment
  (from the `.zshrc` at the time they were started), but were observed
  making direct connections to `api.anthropic.com` via Clash. This means
  not all Claude traffic necessarily goes through Headroom, even when the
  env says it should. The request types (model vs auxiliary) were not
  decrypted, so this remains an observation, not a fully explained behavior.

## Known quirks

- `python3` on mini is 3.9 (system). For Python 3.11+ features (tomllib),
  use `/opt/homebrew/bin/python3` (3.15).
- mini's TUN config includes `route-exclude-address` for specific IPs that
  Air's does not. These are likely custom direct routes for specific
  services.
- mini has 767 Clash rules vs Air's 669. The difference is in additional
  rules, not in the core proxy structure.
