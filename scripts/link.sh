#!/usr/bin/env bash
# 将本仓库 skills/ 下的技能安装进一个或多个 Agent 技能目录。
# 默认：全部技能软链到 ~/.agents/skills。
# 用 -h 查看完整用法。

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0
FORCE=0
COPY=0
TARGET_SET=0
SKILLS=()
TARGETS=("$HOME/.agents/skills")

usage() {
  cat <<'EOF'
用法: link.sh [选项]

  --skill NAME       只安装指定技能，可重复或用逗号分隔
  --agent NAME       安装到该 agent 的用户级 skills 目录，可重复或用逗号分隔
                     可选: agents, claude, workbuddy, codex, cursor, all
  --target DIR       追加自定义目标目录（可与 --agent 并用）
  --copy             复制目录而非建立软链（不再随 git pull 自动更新）
  --dry-run          只打印将要发生的改动
  --force            覆盖同名实体目录（先移入目标目录的 .trash）
  -h, --help         显示本说明

默认: 全部技能软链到 ~/.agents/skills
示例:
  ./scripts/link.sh --skill guard-ratchet --agent claude,workbuddy --dry-run
  ./scripts/link.sh --agent all
  ./scripts/link.sh --skill tavern-aesthetic --agent cursor --copy
EOF
}

agent_dir() {
  case "$1" in
    agents)             printf '%s\n' "$HOME/.agents/skills" ;;
    claude|claude-code) printf '%s\n' "$HOME/.claude/skills" ;;
    workbuddy)          printf '%s\n' "$HOME/.workbuddy/skills" ;;
    codex)              printf '%s\n' "$HOME/.codex/skills" ;;
    cursor)             printf '%s\n' "$HOME/.cursor/skills" ;;
    *) return 1 ;;
  esac
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
    --copy)    COPY=1 ;;
    -h|--help) usage; exit 0 ;;
    --skill)
      shift
      [ -n "${1:-}" ] || { echo "--skill 缺少参数" >&2; exit 2; }
      IFS=',' read -ra parts <<< "$1"
      for p in "${parts[@]}"; do
        p="$(printf '%s' "$p" | tr -d '[:space:]')"
        if [ -n "$p" ]; then SKILLS+=("$p"); fi
      done
      ;;
    --agent)
      shift
      [ -n "${1:-}" ] || { echo "--agent 缺少参数" >&2; exit 2; }
      IFS=',' read -ra parts <<< "$1"
      for p in "${parts[@]}"; do
        a="$(printf '%s' "$p" | tr -d '[:space:]')"
        if [ -z "$a" ]; then continue; fi
        if [ "$TARGET_SET" -eq 0 ]; then TARGETS=(); TARGET_SET=1; fi
        if [ "$a" = "all" ]; then
          for n in agents claude workbuddy codex cursor; do
            TARGETS+=("$(agent_dir "$n")")
          done
        else
          if ! d="$(agent_dir "$a")"; then
            echo "未知 agent: ${a}（可选: agents, claude, workbuddy, codex, cursor, all）" >&2
            exit 2
          fi
          TARGETS+=("$d")
        fi
      done
      ;;
    --target)
      shift
      [ -n "${1:-}" ] || { echo "--target 缺少参数" >&2; exit 2; }
      if [ "$TARGET_SET" -eq 0 ]; then TARGETS=(); TARGET_SET=1; fi
      TARGETS+=("$1")
      ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

available="$(find "$REPO/skills" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort | tr '\n' ' ')"

SKILL_SRCS=()
linked=0; kept=0; skipped=0; conflicts=0

if [ "${#SKILLS[@]}" -eq 0 ]; then
  for src in "$REPO"/skills/*/; do
    if [ -f "$src/SKILL.md" ]; then
      SKILL_SRCS+=("${src%/}")
    else
      echo "跳过 $(basename "$src")：缺少 SKILL.md"
      skipped=$((skipped+1))
    fi
  done
else
  for name in "${SKILLS[@]}"; do
    src="$REPO/skills/$name"
    if [ ! -f "$src/SKILL.md" ]; then
      echo "找不到 skill: $name" >&2
      echo "可用: $available" >&2
      exit 2
    fi
    SKILL_SRCS+=("$src")
  done
fi

install_one() {
  if [ "$COPY" -eq 1 ]; then
    if [ "$DRY_RUN" -eq 0 ]; then cp -R "$src" "$dest"; fi
  else
    if [ "$DRY_RUN" -eq 0 ]; then ln -s "$src" "$dest"; fi
  fi
}

for target in "${TARGETS[@]}"; do
  if [ ! -d "$target" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[dry] 创建目录 $target"
    else
      mkdir -p "$target"
      echo "创建目录 $target"
    fi
  fi
  if [ "$COPY" -eq 1 ]; then mode="复制"; else mode="软链"; fi
  echo "→ $target [$mode]"

  for src in "${SKILL_SRCS[@]}"; do
    name="$(basename "$src")"
    dest="$target/$name"

    if [ -L "$dest" ]; then
      current="$(readlink "$dest")"
      if [ "$COPY" -eq 0 ] && [ "$current" = "$src" ]; then
        echo "  已是最新 $name"
        kept=$((kept+1))
        continue
      fi
      if [ "$DRY_RUN" -eq 1 ]; then
        if [ "$COPY" -eq 1 ]; then
          echo "[dry] 移除软链并复制 $name"
        else
          echo "[dry] 重设软链 ${name}：$current → $src"
        fi
      else
        rm "$dest"
        install_one
        echo "  重设 $name"
      fi
      linked=$((linked+1))
      continue
    fi

    if [ -e "$dest" ]; then
      if [ "$FORCE" -ne 1 ]; then
        echo "  冲突 ${name}：目标已是实体目录，未改动（加 --force 覆盖）"
        conflicts=$((conflicts+1))
        continue
      fi
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry] 移走 $dest 并重新安装 $name"
      else
        mkdir -p "$target/.trash"
        mv "$dest" "$target/.trash/$name.$(date +%Y%m%d%H%M%S)"
        install_one
        echo "  已替换 $name"
      fi
      linked=$((linked+1))
      continue
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
      if [ "$COPY" -eq 1 ]; then
        echo "[dry] 复制 $name → $dest"
      else
        echo "[dry] 新建软链 $name → $src"
      fi
    else
      install_one
      echo "  安装 $name"
    fi
    linked=$((linked+1))
  done
done

echo "---"
echo "安装 $linked 个 / 已是最新 $kept 个 / 冲突 $conflicts 个 / 跳过 $skipped 个"
[ "$conflicts" -eq 0 ] || exit 1
