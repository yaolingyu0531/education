# -*- coding: utf-8 -*-
"""校验技术方案 docx 的结构完整性。

检查项：标题层级与数量、表格数量与空表、关键字符串是否落地、是否有未解析的 Markdown 残留。
退出码非 0 表示存在结构问题。
"""

import sys
from pathlib import Path

from docx import Document

DOCX = Path(__file__).resolve().parent.parent / "技术方案-实习反馈整理系统.docx"

# 必须出现在正文里的关键字符串：覆盖各章节与两条硬绑定
KEY_STRINGS = [
    "执行摘要",
    "qwen3:8b",
    "Ollama",
    "bge-m3",
    "think: false",
    "知识图谱",
    "Q1",
    "Harness",
    "R13",
    "E_GATE_STOPPED",
    "24/30",
    "G0",
    "M4",
]

# Markdown 残留标记：出现即说明解析漏了某类语法
LEFTOVERS = ["| ---", "```", "**", "## ", "- ["]


def main() -> int:
    """读取 docx 并逐项校验，打印 PASS/FAIL 表；有问题时返回 1。"""
    if not DOCX.exists():
        print(f"FAIL 文件不存在：{DOCX}")
        return 1

    doc = Document(str(DOCX))
    paragraphs = doc.paragraphs
    texts = [p.text for p in paragraphs]
    full = "\n".join(texts)

    checks = []

    # 1 标题结构
    h1 = [p.text for p in paragraphs if p.style.name == "Heading 1"]
    h2 = [p.text for p in paragraphs if p.style.name == "Heading 2"]
    checks.append(("一级标题数量 = 19", len(h1) == 19, f"实际 {len(h1)}"))
    checks.append(("二级标题数量 ≥ 40", len(h2) >= 40, f"实际 {len(h2)}"))

    # 2 表格
    tables = doc.tables
    checks.append(("表格数量 ≥ 30", len(tables) >= 30, f"实际 {len(tables)}"))
    empty = [i for i, t in enumerate(tables) if len(t.rows) < 2]
    checks.append(("无空表（行数 <2）", not empty, f"疑似空表：{empty}"))

    # 3 关键内容
    for key in KEY_STRINGS:
        checks.append((f"包含「{key}」", key in full or any(key in c.text for t in tables for r in t.rows for c in r.cells), ""))

    # 4 Markdown 残留
    leftovers = [m for m in LEFTOVERS if m in full]
    checks.append(("无 Markdown 残留", not leftovers, f"残留：{leftovers}"))

    # 5 代码块（等宽字体段落）
    code_paras = [
        p for p in paragraphs
        if p.runs and p.runs[0].font.name == "Consolas"
    ]
    checks.append(("代码块段落 ≥ 3", len(code_paras) >= 3, f"实际 {len(code_paras)}"))

    failed = 0
    print(f"{'结果':<6}{'检查项':<34}说明")
    print("-" * 70)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL':<6}{name:<34}{detail if not ok else ''}")
        failed += 0 if ok else 1

    print("-" * 70)
    print(f"段落 {len(paragraphs)} · 表格 {len(tables)} · H1 {len(h1)} · H2 {len(h2)} · 失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
