#!/usr/bin/env bash
# 将本仓库 skills/ 下的技能链接进 Agent 技能目录。
# 用法：
#   ./scripts/link.sh                     # 链接到 ~/.agents/skills
#   ./scripts/link.sh --dry-run           # 只打印将要发生的改动
#   ./scripts/link.sh --force             # 覆盖同名实体目录（会先移入 .trash）
#   ./scripts/link.sh --target DIR        # 指定目标目录

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$HOME/.agents/skills"
DRY_RUN=0
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
    --target)  shift; TARGET="$1" ;;
    -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
  shift
done

[ -d "$TARGET" ] || { echo "目标目录不存在: $TARGET" >&2; exit 1; }

linked=0; kept=0; skipped=0; conflicts=0

for src in "$REPO"/skills/*/; do
  name="$(basename "$src")"
  [ -f "$src/SKILL.md" ] || { echo "跳过 ${name}：缺少 SKILL.md"; skipped=$((skipped+1)); continue; }
  dest="$TARGET/$name"

  if [ -L "$dest" ]; then
    current="$(readlink "$dest")"
    if [ "$current" = "${src%/}" ]; then
      kept=$((kept+1)); continue
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[dry] 重设软链 ${name}：${current} → ${src%/}"
    else
      ln -sfn "${src%/}" "$dest"; echo "重设软链 $name"
    fi
    linked=$((linked+1))
    continue
  fi

  if [ -e "$dest" ]; then
    if [ "$FORCE" -ne 1 ]; then
      echo "冲突 ${name}：目标已是实体目录，未改动（加 --force 覆盖）"
      conflicts=$((conflicts+1)); continue
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[dry] 移走实体目录 $dest 并建软链"
    else
      mkdir -p "$TARGET/.trash"
      mv "$dest" "$TARGET/.trash/$name.$(date +%Y%m%d%H%M%S)"
      ln -sfn "${src%/}" "$dest"; echo "已替换 $name"
    fi
    linked=$((linked+1))
    continue
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry] 新建软链 $name → ${src%/}"
  else
    ln -sfn "${src%/}" "$dest"; echo "新建软链 $name"
  fi
  linked=$((linked+1))
done

echo "---"
echo "链接 $linked 个 / 已是最新 $kept 个 / 冲突 $conflicts 个 / 跳过 $skipped 个"
[ "$conflicts" -eq 0 ] || exit 1
