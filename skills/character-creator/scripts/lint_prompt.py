#!/usr/bin/env python3
"""Flag mechanical defects in a draft character card.

Every hit is a prompt to re-read a line, not a verdict. This checks shapes that
are almost always wrong (meta preface, USER: syntax, unrequested restriction
boilerplate, {{user}} railroading); it cannot judge voice or canon.
Structural validation of mes_example / V2 JSON lives in validate_examples.py.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"|「[^」]*」")

META_ANYWHERE = [
    (r"本卡|此卡|这张卡", "meta framing: the card describes itself instead of acting"),
    (r"虚构角色|不是真人|非真人", "fiction disclaimer inside the card"),
    (r"免责声明|使用说明|设计思路", "user-facing documentation inside the card"),
]
META_LINE_START = re.compile(r"^\s*(假设|说明|使用说明|设计思路|免责声明|备注)\s*[:：]?\s*$")

RAILROAD = [
    (r"你(?:不禁|不由|忍不住|下意识|无意间)", "decides what {{user}} feels or does"),
    (r"(?<![当若如使果])你感到", "asserts {{user}}'s inner state"),
    (r"你的(?:心跳|脸颊|脸|声音|手)(?![比是也很太还就])", "describes {{user}}'s body"),
    (r"你(?:点了点头|摇了摇头|笑出声|叹了口气|愣住)", "writes {{user}}'s action"),
]

RESTRICTION = [
    (r"拒绝(与用户|和用户)?(建立)?(恋爱|亲密|浪漫|身体接触)", "blanket refusal"),
    (r"不(涉及|包含|接受)(恋爱|浪漫|性|亲密)", "blanket exclusion"),
]

GENERIC = [
    (r"避免(僵硬|生硬|过于)", "generic prohibition — true of every card, so it steers none"),
    (r"保持自然|符合角色(性格|设定)", "generic instruction with no testable behaviour"),
]

BLUSH = re.compile(r"脸红|羞红|心跳|颤抖|咬(了)?咬?(下)?唇")
ACTION_SUBJECT = re.compile(r"\*(?:她|他|\{\{char\}\})[^\n*]{0,14}")
SPEAKER_BAD = re.compile(r"(?m)^\s*(USER|CHAR|BOT)\s*:")
FULLWIDTH = re.compile(r"\{\{(?:user|char)\}\}：")


def char_turn_lengths(text: str) -> list[int]:
    """Character-count of each {{char}}: turn, up to the next speaker or <START>."""
    chunks = re.split(r"(?m)^\{\{char\}\}:\s*", text)[1:]
    lengths = []
    for chunk in chunks:
        stop = re.search(r"(?m)^(?:\{\{user\}\}:|<START>)", chunk)
        segment = chunk[: stop.start()] if stop else chunk
        lengths.append(len(re.sub(r"\s", "", segment)))
    return lengths


def lint(text: str) -> list[tuple[str, str]]:
    """Return (level, message) pairs, level in ERROR / WARN / INFO."""
    issues: list[tuple[str, str]] = []
    body = "\n".join(text.splitlines())
    stripped = QUOTED.sub("", body)

    for pattern, why in META_ANYWHERE:
        if re.search(pattern, body):
            issues.append(("ERROR", f"{why} — remove it and open with `你是 {{{{char}}}}`"))

    head = [ln for ln in body.splitlines() if ln.strip()][:12]
    for line in head:
        if META_LINE_START.match(line):
            issues.append(("ERROR", f"meta heading at the top: {line.strip()[:24]}…"))

    for pattern, why in RAILROAD:
        for hit in sorted({m.group(0) for m in re.finditer(pattern, stripped)}):
            issues.append(("WARN", f"{{{{user}}}} railroading ({hit}): {why}"))

    for pattern, why in RESTRICTION:
        for hit in sorted({m.group(0) for m in re.finditer(pattern, body)}):
            issues.append(("WARN", f"unrequested restriction ({hit}): verify the user asked for it"))

    for pattern, why in GENERIC:
        for hit in sorted({m.group(0) for m in re.finditer(pattern, body)}):
            issues.append(("INFO", f"{hit}: {why}"))

    subjects = sorted({m.group(0) for m in ACTION_SUBJECT.finditer(body)})
    if subjects:
        sample = "、".join(s.strip("*") for s in subjects[:3])
        issues.append(("WARN", f"{len(subjects)} action beat(s) carry a subject ({sample}) — the character is the default speaker; drop the pronoun unless two actors share the beat"))

    if SPEAKER_BAD.search(body):
        issues.append(("ERROR", "USER:/CHAR: speaker labels — use {{user}}: / {{char}}:"))

    if FULLWIDTH.search(body):
        issues.append(("ERROR", "fullwidth colon after speaker macro — use ASCII ':'"))

    has_char, has_start = "{{char}}:" in body, "<START>" in body
    if has_char and not has_start:
        issues.append(("WARN", "{{char}}: blocks without <START> — SillyTavern import needs the marker"))
    if has_start and not has_char:
        issues.append(("ERROR", "<START> present but no {{char}}: turn"))

    blushes = len(BLUSH.findall(body))
    if blushes > 3:
        issues.append(("WARN", f"{blushes} stock reaction beats (脸红/心跳/颤抖/咬唇) — keep 1–2 total"))

    if "你是" not in body:
        issues.append(("WARN", "never addresses the model as the character — no `你是 …` anywhere"))

    if re.search(r"(?m)^(scene|current_goal|current_emotion|relationship|unresolved_events)\s*:", body):
        issues.append(("INFO", "runtime state block present — confirm it was wanted"))

    size = len(re.sub(r"\s", "", body))
    if size > 6000:
        issues.append(("WARN", f"{size} chars — permanent fields start displacing chat memory; move worldbuilding to a lorebook"))
    if size < 300 and "你是" in body:
        issues.append(("WARN", f"{size} chars — thin for a full card; behaviour may be underspecified"))

    turns = char_turn_lengths(body)
    if len(turns) >= 2 and max(turns) < 40:
        issues.append(("INFO", f"longest {{{{char}}}} turn is {max(turns)} chars — the model copies that ceiling; let one turn hold the floor"))

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", type=Path, help="draft card .md/.txt, or - for stdin")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = ap.parse_args()

    try:
        text = sys.stdin.read() if str(args.file) == "-" else args.file.read_text(encoding="utf-8")
    except OSError as ex:
        print(f"FAIL: cannot read file: {ex}")
        return 2

    issues = lint(text)
    for level, message in issues:
        print(f"{level}: {message}")

    errors = sum(1 for level, _ in issues if level == "ERROR")
    warns = sum(1 for level, _ in issues if level == "WARN")
    if not issues:
        print("PASS: no mechanical defects found")
        return 0
    print(f"\n{errors} error(s), {warns} warning(s), {len(issues) - errors - warns} note(s)")
    if errors or (args.strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
