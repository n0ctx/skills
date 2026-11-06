# Changelog

Append new entries at the bottom. Do not edit or delete past entries.

## 2026-11-06 — Initial audit and mini port unification
- Changed: mini Claude CLI and Codex CLI routing from 8789 to 8787
- Changed: mini Headroom default (8787) OpenAI upstream from x.ai to Nous
- Changed: mini `~/.zshrc` removed `proxy_on` function
- Added: mini `com.yunzhiwang.proxy.env.plist` (launchd proxy env)
- Updated: mini `~/.headroom/deploy/default/manifest.json` (base_env + proxy_args)
- Updated: mini `~/.headroom/deploy/default/run-headroom.sh` (OPENAI_TARGET_API_URL)
- Files updated: references/topology.md, references/air.md, references/mini.md
- Verified by: audit-proxy-env.sh equivalents, /readyz 200 on all ports,
  launchctl print gui/501 env, Clash API queries
- Backed up to: mini `~/.config/proxy-simplification-backups/20261106-164902/`
- Air: not modified
