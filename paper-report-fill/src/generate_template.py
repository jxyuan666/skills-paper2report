#!/usr/bin/env python
"""
生成文献汇报 Word 模板（含 {{placeholder}} 占位符）。

运行：
  python src/generate_template.py templates/report_template.docx

模板结构完全按照 ICM-107 汇报格式：
  【文献汇报】
  标题
  分享人 / 研究方向 / 链接 / 单位
  ──
  研究背景 (3点)
  解决的科学问题 (3点)
  研究内容与创新点 (子章节 + 图)
  个人收获 (3点)
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


def _style_para(para, font_cn: str, font_en: str, size_pt: float,
                bold: bool = False, alignment=None, first_line_indent_cm: float = 0):
    """对段落中的 run 应用字体样式。"""
    if not para.runs:
        run = para.add_run("")
    else:
        run = para.runs[0]

    run.font.size = Pt(size_pt)
    run.bold = bold

    rPr = run._element.get_or_add_rPr()
    from lxml import etree
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = etree.SubElement(rPr, qn("w:rFonts"))
    rFonts.set(qn("w:eastAsia"), font_cn)
    rFonts.set(qn("w:ascii"), font_en)
    rFonts.set(qn("w:hAnsi"), font_en)

    if alignment is not None:
        para.alignment = alignment
    if first_line_indent_cm:
        para.paragraph_format.first_line_indent = Cm(first_line_indent_cm)


def generate_template(output_path: str):
    """生成文献汇报 Word 模板（含 {{placeholder}} 占位符）。

    模板结构（ICM-107 汇报格式）：
      分享人 / 研究方向
      （空行）
      【文献汇报】
      1、标题 / 2、链接 / 3、单位
      ──
      研究背景 (3点)
      解决的科学问题 (3点)
      研究内容与创新点 (子章节 + 图)
      个人收获 (3点)
    """
    doc = Document()

    # ── 默认样式 ──
    style = doc.styles["Normal"]
    style.font.size = Pt(11)

    # ═══════════════════════════════════════════
    # 开局：分享人信息（无标题，直接开始）
    # ═══════════════════════════════════════════
    p = doc.add_paragraph()
    p.add_run("分享人：{{reporter_name}}")
    _style_para(p, "等线", "Times New Roman", 11)

    p = doc.add_paragraph()
    p.add_run("研究方向：{{research_direction}}")
    _style_para(p, "等线", "Times New Roman", 11)

    doc.add_paragraph()  # 空行

    # ═══════════════════════════════════════════
    # 文献汇报
    # ═══════════════════════════════════════════
    p = doc.add_paragraph()
    p.add_run("【文献汇报】")
    _style_para(p, "等线", "Times New Roman", 11, bold=True)

    p = doc.add_paragraph()
    p.add_run("1、标题：{{paper_title}}")
    _style_para(p, "等线", "Times New Roman", 11)

    p = doc.add_paragraph()
    p.add_run("2、链接：{{paper_url}}")
    _style_para(p, "等线", "Times New Roman", 11)

    p = doc.add_paragraph()
    p.add_run("3、单位：{{institution}}")
    _style_para(p, "等线", "Times New Roman", 11)

    doc.add_paragraph()  # 空行

    # ═══════════════════════════════════════════
    # 研究背景（等线 11 加粗）
    # ═══════════════════════════════════════════
    p = doc.add_paragraph()
    p.add_run("研究背景：")
    _style_para(p, "等线", "Times New Roman", 11, bold=True)

    p = doc.add_paragraph()
    p.add_run("{{research_background}}")
    _style_para(p, "宋体", "Times New Roman", 11, first_line_indent_cm=0.78)

    doc.add_paragraph()  # 空行

    # ═══════════════════════════════════════════
    # 解决的科学问题（等线 11 加粗）
    # ═══════════════════════════════════════════
    p = doc.add_paragraph()
    p.add_run("解决的科学问题：")
    _style_para(p, "等线", "Times New Roman", 11, bold=True)

    p = doc.add_paragraph()
    p.add_run("{{scientific_problems}}")
    _style_para(p, "宋体", "Times New Roman", 11, first_line_indent_cm=0.78)

    doc.add_paragraph()  # 空行

    # ═══════════════════════════════════════════
    # 研究内容与创新点（等线 11 加粗）
    # ═══════════════════════════════════════════
    p = doc.add_paragraph()
    p.add_run("研究内容与创新点")
    _style_para(p, "等线", "Times New Roman", 11, bold=True)

    p = doc.add_paragraph()
    p.add_run("{{research_content_sections}}")
    _style_para(p, "宋体", "Times New Roman", 11, first_line_indent_cm=0.78)

    doc.add_paragraph()  # 空行

    # ═══════════════════════════════════════════
    # 个人收获（等线 11 加粗）
    # ═══════════════════════════════════════════
    p = doc.add_paragraph()
    p.add_run("【个人收获】")
    _style_para(p, "等线", "Times New Roman", 11, bold=True)

    p = doc.add_paragraph()
    p.add_run("{{personal_takeaways}}")
    _style_para(p, "宋体", "Times New Roman", 11, first_line_indent_cm=0.78)

    # ═══════════════════════════════════════════
    # 图表区（等线 小五 居中）
    # ═══════════════════════════════════════════
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("{{all_figures}}")
    _style_para(p, "等线", "Times New Roman", 9, alignment=WD_ALIGN_PARAGRAPH.CENTER)

    # ── 保存 ──
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    print(f"模板已生成: {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "templates/report_template.docx"
    generate_template(out)
