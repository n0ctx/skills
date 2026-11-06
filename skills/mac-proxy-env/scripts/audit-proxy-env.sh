#!/bin/sh
# Read-only audit of the local proxy/network environment.
# Run on either Mac. Prints structured state for comparison with reference files.
# Does not modify anything, does not send traffic through proxies, does not call paid APIs.
# Sanitizes secrets: no API keys, tokens, or subscription URLs in output.

set -eu

PY="/opt/homebrew/bin/python3"
[ -x "$PY" ] || PY="python3"
SOCK="/var/run/clash-verge-service/users/501/verge-mihomo.sock"
HOME_DIR="$HOME"

echo "=== MACHINE ==="
hostname
sw_vers 2>/dev/null || true
echo "tailscale_ip=$(ipconfig getifaddr utun1024 2>/dev/null || echo unknown)"

echo
echo "=== SYSTEM_PROXY ==="
scutil --proxy 2>/dev/null || true

echo
echo "=== LAUNCHD_ENV ==="
launchctl print gui/$(id -u) 2>/dev/null | grep -E "HTTP_PROXY =>|HTTPS_PROXY =>|ALL_PROXY =>|NO_PROXY =>|NODE_USE_ENV_PROXY =>" || echo "(could not read gui domain)"

echo
echo "=== PROXY_ENV_SERVICE ==="
launchctl print gui/$(id -u)/com.yunzhiwang.proxy.env 2>/dev/null | grep -E "state =|run interval =|runs =|last exit code =" || echo "(service not loaded)"

echo
echo "=== CLASH ==="
if [ -S "$SOCK" ]; then
  "$PY" -c "
import json, subprocess, sys
sock = '$SOCK'
def get(path):
    return json.loads(subprocess.check_output(['curl','-s','--unix-socket',sock,'http://localhost'+path], text=True))
c = get('/configs')
print('mixed_port', c.get('mixed-port'))
print('mode', c.get('mode'))
print('ipv6', c.get('ipv6'))
tun = c.get('tun', {})
print('tun_enable', tun.get('enable'))
print('tun_device', tun.get('device'))
print('tun_stack', tun.get('stack'))
p = get('/proxies')['proxies']
for name in ['PROXY','自动选择','故障转移']:
    if name in p:
        v = p[name]
        print(f'group {name} type={v.get(\"type\")} now={v.get(\"now\")} udp={v.get(\"udp\")}')
r = get('/rules').get('rules', [])
print('rule_count', len(r))
udp_reject = any(x.get('type')=='Network' and x.get('payload')=='udp' and x.get('proxy')=='REJECT' for x in r)
print('udp_reject', udp_reject)
match_rule = next((x for x in r if x.get('type')=='Match'), None)
if match_rule: print('match_target', match_rule.get('proxy'))
" 2>&1 || echo "(clash API query failed)"
else
  echo "(unix socket not found - Clash service may not be running)"
fi

echo
echo "=== HEADROOM ==="
ps -axo pid=,command= 2>/dev/null | grep "headroom.cli proxy --host 127.0.0.1 --port 878" | grep -v "grep" || echo "(no headroom processes found)"
echo "--- health ---"
for port in 8787 8788 8789; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$port/readyz" 2>/dev/null || echo "fail")
  echo "port $port readyz=$code"
done

echo
echo "=== HEADROOM_LAUNCHAGENTS ==="
for label in com.headroom.default com.headroom.kimi com.headroom.hermes com.headroom.default.daily-restart com.yunzhiwang.proxy.env; do
  state=$(launchctl print gui/$(id -u)/$label 2>/dev/null | grep -m1 "last exit code =" || echo "not_loaded")
  echo "$label $state"
done

echo
echo "=== AGENT_ROUTING ==="
"$PY" -c "
import pathlib, re, json
pat = re.compile(r'ANTHROPIC_BASE_URL|OPENAI_BASE_URL|base_url|model_provider|OPENAI_TARGET_API_URL|ANTHROPIC_TARGET_API_URL|HEADROOM_PORT')
skip = re.compile(r'api_key|token|secret|password|credential', re.I)
files = [
    '$HOME_DIR/.claude/settings.json',
    '$HOME_DIR/.codex/config.toml',
    '$HOME_DIR/.kimi-code/config.toml',
    '$HOME_DIR/.grok/config.toml',
    '$HOME_DIR/.zshrc',
]
for f in files:
    p = pathlib.Path(f)
    if not p.exists():
        print(f'FILE {f} MISSING')
        continue
    print(f'FILE {f}')
    for i, line in enumerate(p.read_text(errors='replace').splitlines(), 1):
        if pat.search(line) and not skip.search(line):
            print(f'  {i}:{line[:200]}')
" 2>&1 || echo "(could not read agent configs)"

echo
echo "=== HERMES_ENV ==="
"$PY" -c "
import pathlib, re
p = pathlib.Path('$HOME_DIR/.hermes/.env')
if not p.exists():
    print('(no .hermes/.env)')
else:
    pat = re.compile(r'PROXY|BASE_URL|HEADROOM|NO_PROXY')
    skip = re.compile(r'api_key|token|secret|password|credential', re.I)
    for i, line in enumerate(p.read_text(errors='replace').splitlines(), 1):
        if pat.search(line) and not skip.search(line):
            print(f'  {i}:{line[:200]}')
" 2>&1 || echo "(could not read hermes env)"

echo
echo "=== SSH_CONFIG ==="
if [ -f "$HOME_DIR/.ssh/config" ]; then
  cat "$HOME_DIR/.ssh/config"
else
  echo "(no ssh config)"
fi

echo
echo "=== CLAUDE_SWITCHER ==="
if [ -f "/Library/Application Support/claude-switcher/claude-bodyguard.sh" ]; then
  echo "bodyguard_script: installed"
  launchctl print system/local.claude-bodyguard 2>/dev/null | grep -E "state =|run interval =|runs =|last exit code =" || echo "bodyguard_service: not_loaded"
else
  echo "bodyguard_script: not_installed"
fi
if [ -f "/Library/Application Support/claude-switcher/tz-watchdog.sh" ]; then
  echo "tz_watchdog_script: installed"
  launchctl print system/local.tz-watchdog 2>/dev/null | grep -E "state =|run interval =|runs =|last exit code =" || echo "tz_watchdog_service: not_loaded"
else
  echo "tz_watchdog_script: not_installed"
fi

echo
echo "=== PASEO ==="
if [ -f "$HOME_DIR/.paseo/mac-mini.host" ]; then
  echo "mac-mini.host: present (content redacted)"
elif [ -f "$HOME_DIR/.paseo/hosts.json" ]; then
  echo "hosts.json: present (content redacted)"
else
  echo "(no paseo config found)"
fi

echo
echo "=== HERMES_GATEWAY ==="
if [ -S "$HOME_DIR/.hermes/gateway.sock" ]; then
  echo "gateway_socket: present"
else
  echo "gateway_socket: absent"
fi
launchctl print gui/$(id -u)/ai.hermes.gateway 2>/dev/null | grep -E "state =|last exit code =" || echo "gateway_service: not_loaded"

echo
echo "=== DONE ==="
