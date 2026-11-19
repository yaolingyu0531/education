# -*- coding: utf-8 -*-
"""把技术方案 Markdown 渲染为 docx。

用途：读取 技术方案-实习反馈整理系统.md，生成同名 .docx。
支持：# / ## / ### 标题、表格、``` 代码块、- 与 1. 列表、> 引用、**粗体**、`行内代码`。
局限：不解析图片、脚注、HTML；表格不支持合并单元格。
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# 版式常量：集中在这里，改样式不用翻整篇代码
BODY_FONT_EA = "宋体"
HEAD_FONT_EA = "微软雅黑"
CODE_FONT = "Consolas"
BODY_SIZE = Pt(10.5)
TABLE_SIZE = Pt(9)
CODE_SIZE = Pt(8.5)
ACCENT = RGBColor(0x1F, 0x38, 0x64)
SUB_ACCENT = RGBColor(0x2E, 0x5A, 0x88)
GRAY = RGBColor(0x59, 0x59, 0x59)


# ---------------------------------------------------------------- 字体工具

def set_run_font(run, size=None, bold=None, color=None,
                 latin=BODY_FONT_EA, eastasia=BODY_FONT_EA, italic=None):
    """设置一个 run 的字体（中英文分别指定），失败时静默跳过不支持的属性。

    python-docx 的 font.name 只管西文，中文字形必须写 w:eastAsia，否则 Word 里会回退成默认字体。
    """
    if size is not None:
        run.font.size = size
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    run.font.name = latin
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:eastAsia"), eastasia)


def shade(element, fill):
    """给段落或单元格加底色；fill 为 6 位十六进制，如 F2F2F2。"""
    pr = element.get_or_add_pPr() if hasattr(element, "get_or_add_pPr") else element
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def shade_cell(cell, fill):
    """单元格底色，走 tcPr。"""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def add_field(paragraph, instr, placeholder=""):
    """插入 Word 域（目录、页码）。域需要用户在 Word 里更新一次才会填充内容。"""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = instr
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    text_el = OxmlElement("w:t")
    text_el.text = placeholder
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, instr_el, sep, text_el, end):
        run._r.append(node)
    return run


# ---------------------------------------------------------------- 行内标记

INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def add_inline(paragraph, text, size=BODY_SIZE, base_bold=False, color=None):
    """把一行文本按 **粗体** 和 `代码` 切成多个 run，保持其余格式一致。"""
    for token in INLINE.split(text):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**") and len(token) > 4:
            run = paragraph.add_run(token[2:-2])
            set_run_font(run, size=size, bold=True, color=color)
        elif token.startswith("`") and token.endswith("`") and len(token) > 2:
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, size=Pt(size.pt - 0.5), bold=base_bold,
                         color=RGBColor(0xA6, 0x1B, 0x29),
                         latin=CODE_FONT, eastasia=CODE_FONT)
        else:
            run = paragraph.add_run(token)
            set_run_font(run, size=size, bold=base_bold, color=color)


# ---------------------------------------------------------------- 样式

def build_styles(doc):
    """配置正文、标题、列表、代码四类样式的默认字体与间距。"""
    normal = doc.styles["Normal"]
    normal.font.size = BODY_SIZE
    normal.font.name = BODY_FONT_EA
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_EA)
    pf = normal.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = 1.35
    pf.space_after = Pt(4)

    for name, size, color, before, after in (
        ("Heading 1", 16, ACCENT, 14, 6),
        ("Heading 2", 13, SUB_ACCENT, 10, 4),
        ("Heading 3", 11.5, SUB_ACCENT, 8, 3),
    ):
        style = doc.styles[name]
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.font.name = HEAD_FONT_EA
        style.element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT_EA)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True


def page_setup(doc):
    """A4、页边距、页眉页脚。"""
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.4)
    sec.right_margin = Cm(2.2)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)

    header = sec.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run("实习反馈受限整理与教学改进辅助系统 · 技术方案 v1.0")
    set_run_font(run, size=Pt(8.5), color=GRAY, eastasia=HEAD_FONT_EA)

    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run("— ")
    set_run_font(run, size=Pt(8.5), color=GRAY)
    add_field(footer, "PAGE", "1")
    run = footer.add_run(" / ")
    set_run_font(run, size=Pt(8.5), color=GRAY)
    add_field(footer, "NUMPAGES", "1")
    run = footer.add_run(" —")
    set_run_font(run, size=Pt(8.5), color=GRAY)


def cover(doc, title):
    """封面：标题、副标题、版本行、密级提示。"""
    for _ in range(4):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    set_run_font(run, size=Pt(24), bold=True, color=ACCENT, eastasia=HEAD_FONT_EA)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("技术方案 · 受控辅助工作流 + 本地知识库与知识图谱")
    set_run_font(run, size=Pt(13), color=SUB_ACCENT, eastasia=HEAD_FONT_EA)

    for _ in range(2):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("知行职业学院 · 机电专业 + 5 家企业 · 4 周最小验证")
    set_run_font(run, size=Pt(10.5), color=GRAY)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("v1.0 草案 · 2026-11-12 · 内部评审用")
    set_run_font(run, size=Pt(10.5), color=GRAY)

    for _ in range(6):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("本方案基于合成场景访谈整理，结论为待验证假设，不代表真实客户授权、生产上线或实际收益。")
    set_run_font(run, size=Pt(9), color=GRAY)

    doc.add_page_break()


def toc(doc):
    """目录页：插入 TOC 域，提示在 Word 中更新。"""
    p = doc.add_paragraph()
    run = p.add_run("目录")
    set_run_font(run, size=Pt(16), bold=True, color=ACCENT, eastasia=HEAD_FONT_EA)
    p.paragraph_format.space_after = Pt(8)

    p = doc.add_paragraph()
    add_field(p, 'TOC \\o "1-2" \\h \\z \\u', "（在 Word 中右键此处 → 更新域，生成目录）")

    hint = doc.add_paragraph()
    run = hint.add_run("提示：目录为自动域，首次打开时按 Ctrl+A 再按 F9 即可生成/更新。")
    set_run_font(run, size=Pt(8.5), color=GRAY, italic=True)
    doc.add_page_break()


# ---------------------------------------------------------------- 块级渲染

def add_table(doc, rows):
    """渲染表格：表头深底白字、首行跨页重复、单元格 9pt。"""
    header, body = rows[0], rows[1:]
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    hdr = table.rows[0]
    tr_pr = hdr._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    tr_pr.append(repeat)

    for i, text in enumerate(header):
        cell = hdr.cells[i]
        cell.text = ""
        para = cell.paragraphs[0]
        para.paragraph_format.space_after = Pt(0)
        add_inline(para, text, size=TABLE_SIZE, base_bold=True,
                   color=RGBColor(0xFF, 0xFF, 0xFF))
        shade_cell(cell, "1F3864")

    for row in body:
        cells = table.add_row().cells
        for i, text in enumerate(row[: len(header)]):
            cell = cells[i]
            cell.text = ""
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.line_spacing = 1.15
            add_inline(para, text, size=TABLE_SIZE)

    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_code(doc, lines):
    """代码块：等宽字体 + 浅灰底 + 单倍行距，整体作为一段以保持底色连续。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.4)
    pf.space_before = Pt(4)
    pf.space_after = Pt(6)
    pf.line_spacing = 1.0
    shade(p._p, "F4F5F7")
    for idx, line in enumerate(lines):
        run = p.add_run(line)
        set_run_font(run, size=CODE_SIZE, latin=CODE_FONT, eastasia=CODE_FONT)
        if idx < len(lines) - 1:
            run.add_break()
    return p


def add_bullet(doc, text, level=0):
    """无序列表：用 List Bullet 样式，缩进按层级累加。"""
    style = "List Bullet" if level == 0 else "List Bullet 2"
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(2)
    add_inline(p, text)
    return p


def add_numbered(doc, text):
    """有序列表：手写序号，避免 Word 自动编号跨列表连续导致 1,2,3,4,5…"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.75)
    p.paragraph_format.first_line_indent = Cm(-0.4)
    p.paragraph_format.space_after = Pt(2)
    add_inline(p, text)
    return p


def add_quote(doc, text):
    """引用块：灰底 + 左缩进。"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.space_after = Pt(4)
    shade(p._p, "F7F7F2")
    run = p.add_run(text)
    set_run_font(run, size=Pt(9.5), color=GRAY, italic=True)
    return p


# ---------------------------------------------------------------- 解析

def split_row(line):
    """拆表格行：先保护转义竖线，再按 | 切，去掉首尾空段。"""
    line = line.strip()
    line = line.replace("\\|", "\u0000")
    parts = [seg.strip().replace("\u0000", "|") for seg in line.split("|")]
    if parts and parts[0] == "":
        parts.pop(0)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def is_separator(parts):
    """判断是否表格分隔行：全部由 - 与 : 组成。"""
    return bool(parts) and all(re.fullmatch(r":?-{2,}:?", c or "") for c in parts)


def render(md_path: Path, docx_path: Path):
    """主流程：读 md → 建 docx → 保存。失败时抛出并带文件名，便于定位。"""
    doc = Document()
    build_styles(doc)
    page_setup(doc)

    lines = md_path.read_text(encoding="utf-8").splitlines()
    title = "实习反馈受限整理与教学改进辅助系统 · 技术方案"
    body_start = 0
    for idx, raw in enumerate(lines):
        if raw.startswith("# "):
            title = raw[2:].strip()
            body_start = idx + 1
            break

    cover(doc, title)
    toc(doc)

    i = body_start
    total = len(lines)
    while i < total:
        raw = lines[i]
        line = raw.rstrip()

        # 代码块
        if line.startswith("```"):
            i += 1
            buf = []
            while i < total and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            add_code(doc, buf or [""])
            continue

        if not line.strip():
            i += 1
            continue

        # 标题
        if line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=2)
            i += 1
            continue
        if line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=1)
            i += 1
            continue
        if line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=0)
            i += 1
            continue

        # 表格
        if line.lstrip().startswith("|"):
            rows = []
            while i < total and lines[i].lstrip().startswith("|"):
                parts = split_row(lines[i])
                if not is_separator(parts):
                    rows.append(parts)
                i += 1
            if rows:
                add_table(doc, rows)
            continue

        # 分隔线
        if re.fullmatch(r"-{3,}", line.strip()):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            pr = p._p.get_or_add_pPr()
            borders = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:color"), "D0D7E5")
            borders.append(bottom)
            pr.append(borders)
            i += 1
            continue

        # 引用
        if line.startswith("> "):
            add_quote(doc, line[2:].strip())
            i += 1
            continue

        # 列表
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- "):
            add_bullet(doc, stripped[2:].strip(), level=1 if indent >= 2 else 0)
            i += 1
            continue
        m = re.match(r"(\d+)\.\s+(.*)", stripped)
        if m:
            add_numbered(doc, f"{m.group(1)}. {m.group(2).strip()}")
            i += 1
            continue

        # 普通段落
        p = doc.add_paragraph()
        add_inline(p, line.strip())
        i += 1

    doc.save(docx_path)
    return docx_path


def main(argv):
    """命令行入口：允许显式传源与目标路径，默认按约定文件名。"""
    # 脚本放在 _tools/ 下，文档在其上级目录：默认路径按此约定推导
    base = Path(__file__).resolve().parent.parent
    md = Path(argv[1]) if len(argv) > 1 else base / "技术方案-实习反馈整理系统.md"
    out = Path(argv[2]) if len(argv) > 2 else md.with_suffix(".docx")
    if not md.exists():
        print(f"源文件不存在：{md}")
        return 1
    render(md, out)
    print(f"已生成：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
