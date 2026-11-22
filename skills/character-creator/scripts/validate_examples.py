#!/usr/bin/env python3
"""Validate SillyTavern-style dialogue examples or Character Card V2 JSON.

Structural check only; not a measure of character quality or canon accuracy.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SPEAKER = re.compile(r"^\s*\{\{(user|char)\}\}:\s*", re.IGNORECASE)
FULLWIDTH = re.compile(r"^\s*\{\{(?:user|char)\}\}：", re.IGNORECASE)
REQUIRED_V2 = ("name", "description", "personality", "scenario", "first_mes", "mes_example")


def validate_examples(text: str) -> list[str]:
    errors = []
    blocks = [part.strip() for part in re.split(r"(?m)^<START>\s*$", text) if part.strip()]
    if not re.search(r"(?m)^<START>\s*$", text):
        return ["Missing standalone <START> marker before examples."]
    preface = text.split("<START>", 1)[0].strip()
    if preface:
        errors.append("Unexpected content before first <START> marker.")
    for i, block in enumerate(blocks, 1):
        speakers = []
        for line in block.splitlines():
            if FULLWIDTH.match(line):
                errors.append(f"Block {i}: use ASCII ':' after speaker macro.")
            m = SPEAKER.match(line)
            if m:
                speakers.append(m.group(1).lower())
        if not speakers or "user" not in speakers or "char" not in speakers:
            errors.append(f"Block {i}: needs {{user}} and {{char}} role labels.")
        if speakers and speakers[0] != "user":
            errors.append(f"Block {i}: start with {{user}} for portable examples.")
        if any(a == b for a, b in zip(speakers, speakers[1:])):
            errors.append(f"Block {i}: repeated speaker label in sequence.")
    return errors


def validate_v2(card: dict) -> list[str]:
    errors = []
    if card.get("spec") != "chara_card_v2" or card.get("spec_version") != "2.0":
        errors.append("Expected spec=chara_card_v2 and spec_version=2.0.")
    data = card.get("data")
    if not isinstance(data, dict):
        return errors + ["data must be an object."]
    for key in REQUIRED_V2:
        if not isinstance(data.get(key), str) or not data[key].strip():
            errors.append(f"Missing or empty data.{key}.")
    if isinstance(data.get("mes_example"), str) and data["mes_example"].strip():
        errors.extend(validate_examples(data["mes_example"]))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", type=Path, help="mes_example .txt or Character Card V2 .json")
    args = ap.parse_args()
    try:
        txt = args.file.read_text(encoding="utf-8")
        issues = validate_v2(json.loads(txt)) if args.file.suffix.lower() == ".json" else validate_examples(txt)
    except (OSError, ValueError, TypeError) as ex:
        print(f"FAIL: cannot read or parse file: {ex}")
        return 2
    if issues:
        for issue in issues:
            print(f"FAIL: {issue}")
        return 1
    print("PASS: structural format check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
