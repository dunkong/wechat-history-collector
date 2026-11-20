#!/usr/bin/env python3
"""校验 SKILL.md 的基本规范（纯标准库，CI 友好）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

errors = []
if not text.startswith("---"):
    errors.append("缺少 YAML frontmatter 起始 '---'")

parts = text.split("---", 2)
front = parts[1] if len(parts) >= 3 else ""
name = ""
description = ""
for line in front.splitlines():
    line = line.strip()
    if line.startswith("name:"):
        name = line.split(":", 1)[1].strip()
    elif line.startswith("description:"):
        description = line.split(":", 1)[1].strip()

if not name:
    errors.append("frontmatter 缺少 name")
elif not all(c.islower() or c.isdigit() or c == "-" for c in name):
    errors.append(f"name 应为小写字母/数字/连字符: {name}")
if not description:
    errors.append("frontmatter 缺少 description")
if "agent_created: true" not in front:
    errors.append("frontmatter 缺少 agent_created: true")
if "<" in description or ">" in description:
    errors.append("description 不能包含尖括号 < >")

if errors:
    print("SKILL.md 校验失败:")
    for e in errors:
        print("  -", e)
    sys.exit(1)

print("SKILL.md OK:", name)
