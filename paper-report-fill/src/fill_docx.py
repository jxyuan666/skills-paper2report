"""
DOCX 填充模块 —— 将 FillSchema JSON 填入 Word 模板。

模板中的占位符格式: {{field_name}}
  - 简单字段: {{paper_title}}, {{reporter_name}}, ...
  - 编号要点: {{research_background}} → 自动渲染为编号列表
  - 子章节: {{research_content_sections}} → 自动渲染为带标题的章节
  - 图表: {{all_figures}} → 插入图片 + 图题

字体与样式通过 FONT_STYLE 常量集中控制。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from .schema import FillSchema

# ─────────────────────────────────────────────
# 字体与样式配置（集中控制，修改这里即可）
# ─────────────────────────────────────────────

FONT_STYLE = {
    "title": {
        "font_name_cn": "等线",
        "font_name_en": "Times New Roman",
        "size_pt": 11,
        "bold": True,
        "color": None,
        "alignment": WD_ALIGN_PARAGRAPH.LEFT,
    },
    "section_heading": {
        "font_name_cn": "等线",
        "font_name_en": "Times New Roman",
        "size_pt": 11,
        "bold": True,
        "color": None,
        "alignment": WD_ALIGN_PARAGRAPH.LEFT,
    },
    "subsection_heading": {
        "font_name_cn": "等线",
        "font_name_en": "Times New Roman",
        "size_pt": 11,
        "bold": True,
        "color": None,
        "alignment": WD_ALIGN_PARAGRAPH.LEFT,
    },
    "body": {
        "font_name_cn": "宋体",
        "font_name_en": "Times New Roman",
        "size_pt": 11,
        "bold": False,
        "color": None,
        "first_line_indent_cm": 0.78,  # 两字符缩进（11pt）
        "line_spacing": 1.25,
        "alignment": WD_ALIGN_PARAGRAPH.JUSTIFY,
    },
    "figure_caption": {
        "font_name_cn": "等线",
        "font_name_en": "Times New Roman",
        "size_pt": 9,  # 小五
        "bold": False,
        "color": None,
        "alignment": WD_ALIGN_PARAGRAPH.CENTER,
    },
    "meta_info": {
        "font_name_cn": "等线",
        "font_name_en": "Times New Roman",
        "size_pt": 11,
        "bold": False,
        "color": None,
        "alignment": WD_ALIGN_PARAGRAPH.LEFT,
    },
}

# 默认图片宽度
FIGURE_WIDTH_CM = 14.0


# ─────────────────────────────────────────────
# 底层 helper
# ─────────────────────────────────────────────

def _apply_font(run, style_key: str):
    """对 docx Run 应用 FONT_STYLE 中的字体设置。"""
    cfg = FONT_STYLE[style_key]
    run.font.size = Pt(cfg["size_pt"])
    run.bold = cfg["bold"]
    if cfg.get("color"):
        run.font.color.rgb = RGBColor(*cfg["color"])

    # 设置中英文字体
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = __import__("lxml.etree", fromlist=["etree"]).SubElement(
            rPr, qn("w:rFonts")
        )
    rFonts.set(qn("w:eastAsia"), cfg["font_name_cn"])
    rFonts.set(qn("w:ascii"), cfg["font_name_en"])
    rFonts.set(qn("w:hAnsi"), cfg["font_name_en"])


def _add_paragraph(doc, text: str, style_key: str) -> "Paragraph":
    """添加一个带样式的段落。"""
    p = doc.add_paragraph()
    p.alignment = FONT_STYLE[style_key].get("alignment", WD_ALIGN_PARAGRAPH.LEFT)

    # 段落间距
    pf = p.paragraph_format
    if "line_spacing" in FONT_STYLE[style_key]:
        pf.line_spacing = FONT_STYLE[style_key]["line_spacing"]
    if "first_line_indent_cm" in FONT_STYLE[style_key]:
        pf.first_line_indent = Cm(FONT_STYLE[style_key]["first_line_indent_cm"])

    if text:
        run = p.add_run(text)
        _apply_font(run, style_key)

    return p


def _set_cn_font(doc: Document):
    """为文档设置默认中文字体（仅对新建文档有效，模板文档由样式控制）。"""
    style = doc.styles["Normal"]
    style.font.name = FONT_STYLE["body"]["font_name_en"]
    style.font.size = Pt(FONT_STYLE["body"]["size_pt"])
    rPr = style.element.get_or_add_rPr()
    rFonts = __import__("lxml.etree", fromlist=["etree"]).SubElement(
        rPr, qn("w:rFonts")
    )
    rFonts.set(qn("w:eastAsia"), FONT_STYLE["body"]["font_name_cn"])


def _find_placeholder_paragraphs(doc: Document) -> dict:
    """扫描文档中所有段落，找到包含 {{placeholder}} 的段落，返回 {placeholder: paragraph_index}。"""
    placeholders = {}
    for i, para in enumerate(doc.paragraphs):
        matches = re.findall(r"\{\{(\w+)\}\}", para.text)
        for m in matches:
            placeholders[m] = i
    return placeholders


# ─────────────────────────────────────────────
# 各模块渲染
# ─────────────────────────────────────────────

def _render_numbered_points(
    doc: Document,
    points: list,
    heading_text: str,
):
    """渲染编号要点列表（研究背景/科学问题/个人收获）。"""
    if not points:
        return

    _add_paragraph(doc, heading_text, "section_heading")
    for pt in points:
        idx = getattr(pt, "index", 0) if hasattr(pt, "index") else pt.get("index", 0)
        content = getattr(pt, "content", "") if hasattr(pt, "content") else pt.get("content", "")
        text = f"{idx}. {content}"
        _add_paragraph(doc, text, "body")


def _render_research_content(
    doc: Document,
    sections: list,
    figures_base_dir: Path | None = None,
):
    """渲染研究内容子章节。figures_base_dir 用于解析图片相对路径。"""
    if not sections:
        return

    _add_paragraph(doc, "研究内容与创新点", "section_heading")

    for sec in sections:
        order = getattr(sec, "order", 0) if hasattr(sec, "order") else sec.get("order", 0)
        title = getattr(sec, "title", "") if hasattr(sec, "title") else sec.get("title", "")
        body = getattr(sec, "body", "") if hasattr(sec, "body") else sec.get("body", "")
        figures = getattr(sec, "figures", []) if hasattr(sec, "figures") else sec.get("figures", [])

        # 子章节标题： (一) xxx
        _add_paragraph(doc, f"（{_num_to_cn(order)}）{title}", "subsection_heading")

        # 正文
        for para_text in body.split("\n"):
            para_text = para_text.strip()
            if para_text:
                _add_paragraph(doc, para_text, "body")

        # 图表
        for fig in figures:
            fig_id = getattr(fig, "figure_id", "") if hasattr(fig, "figure_id") else fig.get("figure_id", "")
            caption = getattr(fig, "caption", "") if hasattr(fig, "caption") else fig.get("caption", "")
            image_path = getattr(fig, "image_path", "") if hasattr(fig, "image_path") else fig.get("image_path", "")

            # 尝试插入图片
            inserted = False
            if image_path:
                img_full = Path(image_path)
                if figures_base_dir and not img_full.is_absolute():
                    img_full = figures_base_dir / img_full
                if img_full.exists():
                    try:
                        p_img = doc.add_paragraph()
                        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run_img = p_img.add_run()
                        run_img.add_picture(
                            str(img_full),
                            width=Cm(FIGURE_WIDTH_CM),
                        )
                        inserted = True
                    except Exception as e:
                        print(f"[fill_docx] 图片插入失败 {image_path}: {e}")

            if not inserted:
                # 占位提示
                _add_paragraph(
                    doc,
                    f"[{fig_id} 插入位置: {image_path or '未提供路径'}]",
                    "figure_caption",
                )

            # 图题
            if caption:
                _add_paragraph(doc, caption, "figure_caption")
            elif fig_id:
                _add_paragraph(doc, f"{fig_id}：{caption or '(图题缺失)'}", "figure_caption")


def _render_figure_index(doc: Document, figures: list):
    """在文末渲染图表索引（可选）。"""
    if not figures:
        return


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def fill_docx(
    schema: FillSchema,
    template_path: str | Path,
    output_path: str | Path,
    *,
    figures_base_dir: str | Path | None = None,
) -> Path:
    """
    将 FillSchema 填入 Word 模板，生成最终 DOCX。

    Parameters
    ----------
    schema : FillSchema
        结构化填充数据。
    template_path : str | Path
        Word 模板路径（含 {{placeholder}}）。
    output_path : str | Path
        输出 DOCX 路径。
    figures_base_dir : str | Path | None
        图片根目录，用于解析 schema 中的相对路径。

    Returns
    -------
    Path
        生成的 DOCX 文件路径。
    """
    template_path = Path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if figures_base_dir:
        figures_base_dir = Path(figures_base_dir)

    doc = Document(str(template_path))

    # 渲染策略：一律从零构建（保证复杂字段渲染一致性）
    #    模板仅作为样式参考，不依赖占位符逐段替换
    #    清空模板内容后，按固定结构重新生成

    for para in doc.paragraphs:
        p_element = para._element
        p_element.getparent().remove(p_element)

    # ── 开局：分享人信息（无标题，直接开始）──
    _add_paragraph(doc, f"分享人：{schema.reporter_name}", "meta_info")
    _add_paragraph(doc, f"研究方向：{schema.research_direction}", "meta_info")

    # ── 空行 ──
    doc.add_paragraph()

    # ── 文献汇报 ──
    _add_paragraph(doc, "【文献汇报】", "section_heading")
    _add_paragraph(doc, f"1、标题：{schema.paper_title}", "meta_info")
    if schema.paper_url:
        _add_paragraph(doc, f"2、链接：{schema.paper_url}", "meta_info")
    if schema.institution:
        label = f"3、单位：{schema.institution}" if schema.paper_url else f"2、单位：{schema.institution}"
        _add_paragraph(doc, label, "meta_info")

    # ── 研究背景 ──
    _render_numbered_points(doc, schema.research_background, "研究背景：")

    # ── 解决的科学问题 ──
    _render_numbered_points(doc, schema.scientific_problems, "解决的科学问题：")

    # ── 研究内容与创新点 ──
    _render_research_content(doc, schema.research_content_sections, figures_base_dir)

    # ── 个人收获 ──
    _render_numbered_points(doc, schema.personal_takeaways, "【个人收获】")

    # 4. 保存
    doc.save(str(output_path))
    print(f"[fill_docx] 已生成 DOCX → {output_path}")

    return output_path


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

_CN_NUM = " 一二三四五六七八九十"

def _num_to_cn(n: int) -> str:
    """1→一, 2→二, ..., 10→十。"""
    if 1 <= n <= 10:
        return _CN_NUM[n]
    return str(n)


# ─────────────────────────────────────────────
# 独立运行
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("用法: python fill_docx.py <fill.json> <output.docx> [template.docx]")
        sys.exit(1)

    from .build_fill_json import load_fill_json

    schema = load_fill_json(sys.argv[1])
    template = sys.argv[3] if len(sys.argv) > 3 else "templates/report_template.docx"
    fill_docx(schema, template, sys.argv[2])
