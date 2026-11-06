# MacBook Air

Hostname: `YunzhideMacBook-Air.local`
Tailscale IP: 100.91.254.69
macOS: 27.2 (Build 26B123)

Last verified: 2026-11-06 16:30 JST.

## Clash current state

- Mixed port: 7897
- TUN: utun1024, gVisor, auto-route, DNS hijack any:53, IPv6 off
- Mode: rule
- PROXY group: Fallback, now = Korea 03, interval 60s, timeout 5s
- Rule count: 669
- Final MATCH → PROXY
- UDP: NETWORK,udp → REJECT (with STUN port exceptions 3478/5349/19302)
- Syncthing UDP 22000 → DIRECT

## System proxy

- Wi-Fi: HTTP/HTTPS/SOCKS all enabled, 127.0.0.1:7897
- Thunderbolt Bridge: same
- AX88179A (USB Ethernet): disabled
- Thunderbolt Bridge has PAC URL `http://127.0.0.1:33331/commands/pac` but
  ProxyAutoConfigEnable is 0 (not used).

## launchd environment

`com.yunzhiwang.proxy.env` loaded and active. GUI domain has:
- HTTP_PROXY / HTTPS_PROXY → http://127.0.0.1:7897
- ALL_PROXY → socks5://127.0.0.1:7897
- NO_PROXY → localhost,127.0.0.1,::1,100.64.0.0/10,*.ts.net,*.tailscale.com
- NODE_USE_ENV_PROXY → 1

## Headroom instances

| Port | Profile | PID (snapshot) | OpenAI upstream | Anthropic upstream |
|---|---|---|---|---|
| 8787 | default | 42230 | https://api.x.ai | default (api.anthropic.com) |
| 8788 | kimi | 2098 | https://api.kimi.com/coding | https://api.kimi.com/coding |
| 8789 | hermes | 14347 | https://inference-api.nousresearch.com | https://api.kimi.com/coding |

All three `/readyz` return 200.

8787 `run-headroom.sh` explicitly sets proxy env to 7897. 8788 and 8789
inherit the launchd global env.

## Agent routing

- Claude CLI: `~/.claude/settings.json` → `ANTHROPIC_BASE_URL` = 8787
- Codex CLI: `~/.codex/config.toml` → `model_provider = "headroom"`,
  `base_url = http://127.0.0.1:8787/v1`, model `gpt-6.1-terra`
- Hermes default: `~/.hermes/config.yaml` → provider `openai-codex`,
  `base_url = http://127.0.0.1:8789/backend-api/codex`
- Hermes Nous: `.env` `NOUS_INFERENCE_BASE_URL` = 8789/v1
- Hermes Kimi: `.env` `KIMI_BASE_URL` = 8788
- Kimi CLI standalone: direct to `https://api.kimi.com/coding/v1`
- Grok CLI standalone: no Headroom base_url in config

## `.zshrc` notable entries

- No `proxy_on` function (never had one; uses launchd instead).
- Headroom persistent env block: `HEADROOM_PORT=8789`,
  `ANTHROPIC_TARGET_API_URL=https://api.kimi.com/coding`,
  `OPENAI_TARGET_API_URL=https://inference-api.nousresearch.com`.
- `codex()` wrapper sets `HEADROOM_PROJECT=guoke-invest`.
- `paseo-mini()` reads `~/.paseo/mac-mini.host`.
- SSH sudo keepalive for SSH sessions.
- `no_proxy` includes `192.168.3.219` (additional to launchd NO_PROXY).

## Claude Switcher

- Bodyguard: loaded, runs=35389, interval 10s, last exit 0.
- TZ watchdog: interval 3600s.
- GUI app `/Applications/Claude切换器.app` was running during audit.

## Hermes gateway

- `ai.hermes.gateway.plist` loaded.
- Socket: `~/.hermes/gateway.sock`.
- Two persistent SSH master sockets to mini under
  `~/.hermes/desktop-ssh/`.

## Paseo

- Mini host file: `~/.paseo/mac-mini.host` (relay URL).
- `paseo-mini()` function in `.zshrc`.

## Known quirks

- `CODEBUDDY_SERVICE_PROXY_URL` in the environment points to
  `http://127.0.0.1:49371/internal/hooks/services/invoke` — this is
  WorkBuddy's internal hook service, not a network proxy. Do not confuse it
  with `HTTP_PROXY`.
- WorkBuddy itself does not go through Headroom; it uses Clash directly via
  the inherited proxy env.
