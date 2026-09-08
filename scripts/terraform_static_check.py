#!/usr/bin/env python3
"""Offline syntax-shape checks for Arbiter Terraform.

This is intentionally not a replacement for `terraform validate`. It catches the
class of malformed compact HCL that previously slipped through the release gate,
so packages fail closed even where Terraform is not installed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TF_DIR = ROOT / "deploy" / "aws"
TF_FILES = (TF_DIR / "main.tf", TF_DIR / "variables.tf", TF_DIR / "outputs.tf")

BLOCK_HEADER = re.compile(
    r'^\s*(?:terraform|locals|provider\s+"[^"]+"|data\s+"[^"]+"\s+"[^"]+"|resource\s+"[^"]+"\s+"[^"]+"|variable\s+"[^"]+"|output\s+"[^"]+")\s*\{(.*)\}\s*$'
)


def strip_strings_and_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            out.append(" ")
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(" ")
            i += 1
            continue
        if ch == "#":
            while i < len(text) and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "/":
            out.extend([" ", " "])
            i += 2
            while i < len(text) and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def balanced(text: str) -> bool:
    clean = strip_strings_and_comments(text)
    pairs = {"}": "{", "]": "[", ")": "("}
    stack: list[str] = []
    for ch in clean:
        if ch in "{[(":
            stack.append(ch)
        elif ch in "}])":
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


def main() -> int:
    problems: list[str] = []
    for path in TF_FILES:
        if not path.exists() or not path.read_text().strip():
            problems.append(f"missing or empty: {path.relative_to(ROOT)}")
            continue
        text = path.read_text()
        if not balanced(text):
            problems.append(f"unbalanced delimiters: {path.relative_to(ROOT)}")
        for lineno, line in enumerate(text.splitlines(), 1):
            m = BLOCK_HEADER.match(line)
            if m and m.group(1).strip():
                problems.append(
                    f"non-empty top-level HCL block compressed to one line: "
                    f"{path.relative_to(ROOT)}:{lineno}"
                )
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}")
        return 1
    print("[PASS] Terraform files present and non-empty")
    print("[PASS] Terraform delimiters are balanced")
    print("[PASS] Terraform top-level blocks are not compressed into invalid single-line HCL")
    print("NOTE: run `terraform fmt -check && terraform validate` with Terraform installed for authoritative validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
