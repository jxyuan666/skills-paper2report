"""
Pydantic 数据模型 —— 文献汇报结构化填充 JSON 的单一事实来源。

模板骨架来自 ICM-107 汇报，覆盖：
  分享人 → 研究背景 → 科学问题 → 研究内容(含子章节+图表) → 个人收获
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# 细粒度组件
# ─────────────────────────────────────────────

class FigureItem(BaseModel):
    """一张图表：图片文件 + 标题 + 插入位置标记。"""

    figure_id: str = Field(
        default="",
        description="图表编号，如 '图1'、'图2'",
    )
    image_path: str = Field(
        default="",
        description="图片文件在 outputs/ 下的相对路径，如 'figures/figure_1.png'",
    )
    caption: str = Field(
        default="",
        description="完整图题，如 '图1. 本工作与先前代表性稠环含能材料...在密度、爆速...方面的对比'",
    )
    insert_after_paragraph: str = Field(
        default="",
        description="在哪个段落之后插入此图，用段落前几个字标记位置，如 '如图1所示，整个研究流程分为四个步骤'",
    )


class SubSection(BaseModel):
    """研究内容下的一个子章节，如 '(一) 分子库构建与ML-HTVS高通量虚拟筛选'。"""

    order: int = Field(default=0, description="序号，1/2/3/4...")
    title: str = Field(
        default="",
        description="子章节标题，如 '分子库构建与ML-HTVS高通量虚拟筛选'",
    )
    body: str = Field(
        default="",
        description="子章节正文，可包含多段。图引用保留原文如'如图X所示'",
    )
    figures: List[FigureItem] = Field(
        default_factory=list,
        description="本子章节内出现的图表",
    )


class NumberedPoint(BaseModel):
    """一条编号要点，用于研究背景/科学问题/个人收获。"""

    index: int = Field(default=0, description="序号 1/2/3...")
    content: str = Field(default="", description="要点正文，一段中文")


# ─────────────────────────────────────────────
# 顶层 Schema
# ─────────────────────────────────────────────

class FillSchema(BaseModel):
    """文献汇报完整填充数据 —— 与 ICM-107 模板结构一一对应。"""

    # ── 汇报人 ──
    reporter_name: str = Field(
        default="",
        description="汇报人姓名",
    )
    reporter_grade: str = Field(
        default="研一",
        description="年级，如 '研一'、'研二'、'博一'",
    )
    research_direction: str = Field(
        default="",
        description="研究方向，如 '文本挖掘与机器学习辅助钙钛矿添加剂分子解析、设计、验证'",
    )

    # ── 论文元信息 ──
    paper_title: str = Field(
        default="",
        description="论文完整标题（原文）",
    )
    paper_title_zh: str = Field(
        default="",
        description="论文中文译名",
    )
    paper_url: str = Field(
        default="",
        description="论文链接/DOI",
    )
    institution: str = Field(
        default="",
        description="作者单位，如 '中国工程物理研究院化学材料研究所，西安交通大学...'",
    )

    # ── 研究背景 ──
    research_background: List[NumberedPoint] = Field(
        default_factory=list,
        description="研究背景，3点左右，编号",
    )

    # ── 解决的科学问题 ──
    scientific_problems: List[NumberedPoint] = Field(
        default_factory=list,
        description="论文解决的核心科学问题，3点左右，编号",
    )

    # ── 研究内容与创新点 (核心主体) ──
    research_content_sections: List[SubSection] = Field(
        default_factory=list,
        description="研究内容的子章节，通常3-5个，含正文和图表",
    )
    innovation_summary: List[str] = Field(
        default_factory=list,
        description="创新点总结，3-5条，每条一句话",
    )

    # ── 个人收获 ──
    personal_takeaways: List[NumberedPoint] = Field(
        default_factory=list,
        description="个人收获，3点左右，编号",
    )

    # ── 全局图表索引 (从各 SubSection 汇总，便于 Word 排版) ──
    all_figures: List[FigureItem] = Field(
        default_factory=list,
        description="全文所有图表的汇总列表，由管线自动从 research_content_sections 汇总",
    )

    # ── 元数据 ──
    report_date: str = Field(
        default="",
        description="汇报日期，如 '2026-06-17'",
    )
