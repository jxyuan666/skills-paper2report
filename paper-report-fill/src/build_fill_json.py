"""
分阶段提示词框架 —— 将 PDF 提取的 Markdown 转为结构化 FillSchema JSON。

本模块不直接调用 LLM，而是生成分阶段的提示词（prompt），
由上层（Claude Code Skill / run_pipeline.py）按顺序喂给 LLM 并收集结果。

设计原则：
  - 每个阶段只做一件事，降低出错概率
  - 每个阶段输出可校验的 JSON 片段
  - 最终由 assemble() 合并为完整 FillSchema
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .schema import FillSchema


# ─────────────────────────────────────────────
# 阶段定义
# ─────────────────────────────────────────────

STAGE_META = {
    "stage_1_meta": {
        "name": "论文元信息",
        "description": "提取论文标题、作者、期刊、链接、单位等元信息",
        "output_fields": [
            "paper_title", "paper_title_zh", "paper_url",
            "institution", "keywords",
        ],
    },
    "stage_2_background": {
        "name": "研究背景",
        "description": "概括论文的研究背景，输出 3 条编号要点",
        "output_fields": ["research_background"],
    },
    "stage_3_problems": {
        "name": "科学问题",
        "description": "提取论文解决的核心科学问题，输出 3 条编号要点",
        "output_fields": ["scientific_problems"],
    },
    "stage_4_content": {
        "name": "研究内容与创新点",
        "description": "按子章节拆分研究内容，提取每节的正文和图表的标题/位置",
        "output_fields": ["research_content_sections", "all_figures"],
    },
    "stage_5_takeaways": {
        "name": "个人收获",
        "description": "从论文中提炼 3 条个人收获",
        "output_fields": ["personal_takeaways"],
    },
}


# ─────────────────────────────────────────────
# Prompt 模板
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """你是一个学术文献分析助手。你的任务是从论文全文 Markdown 中提取结构化信息，
用于填写一份中文文献汇报模板。

要求：
1. 所有输出必须是合法 JSON，字段不得缺失。
2. 中文输出，专业术语保留英文原文。
3. 正文段落保持学术风格，不添加"本段介绍了…"之类的元描述。
4. 图表标题完整保留原文措辞。
5. 编号要点每条控制在 1-3 句话。
6. 只输出 JSON，不要输出其他解释文字。
7. 严禁使用"XXX（yyy）"式的括号补充说明句式。专业术语、缩写、人名、年份等
   信息必须融入句子自然表达，不得用括号追补。例如：
   - ✗ 错误：Wu等人（2020）引入pentaerythritol tetrakis (3-mercaptopropionate)（ML），
     该分子可同时抑制Pb2+（铅离子）……
   - ✓ 正确：Wu等人在2020年引入了多位点配体ML，其全称为pentaerythritol
     tetrakis (3-mercaptopropionate)。该分子可同时抑制铅离子Pb²⁺……
   一句话说完就结束，括号只在引用图表编号（如图1、表2）和图题中使用。"""


def build_stage_prompt(
    stage_key: str,
    markdown_content: str,
    *,
    reporter_name: str = "",
    reporter_grade: str = "研一",
    research_direction: str = "",
    paper_meta_hint: str = "",
) -> str:
    """
    为指定阶段构建 prompt。

    Parameters
    ----------
    stage_key : str
        阶段 key，如 "stage_1_meta"。
    markdown_content : str
        PDF 提取的全文 Markdown（各阶段共享）。
    reporter_name : str
        汇报人姓名。
    reporter_grade : str
        年级。
    research_direction : str
        研究方向。
    paper_meta_hint : str
        来自前一阶段的元信息（如标题），用于后续阶段上下文。

    Returns
    -------
    str
        完整的 user prompt 字符串。
    """
    meta = STAGE_META[stage_key]
    header = f"## 阶段：{meta['name']}\n{meta['description']}"

    # 各阶段专用指令
    stage_instructions = {
        "stage_1_meta": """
请输出以下 JSON（字段不可省略）：
{
  "paper_title": "完整标题原文",
  "paper_title_zh": "中文译名",
  "paper_url": "DOI或URL",
  "institution": "作者单位全称",
  "keywords": "关键词（分号分隔）"
}""",
        "stage_2_background": f"""
论文元信息（供参考）：
{paper_meta_hint}

请输出以下 JSON：
{{
  "research_background": [
    {{"index": 1, "content": "…"}},
    {{"index": 2, "content": "…"}},
    {{"index": 3, "content": "…"}}
  ]
}}
每条 content 为 1-3 句话，概括一个独立的研究背景要点。
	严禁括号追补句式，专业术语和缩写融入句子自然表达。""",
        "stage_3_problems": f"""
论文元信息（供参考）：
{paper_meta_hint}

请输出以下 JSON：
{{
  "scientific_problems": [
    {{"index": 1, "content": "…"}},
    {{"index": 2, "content": "…"}},
    {{"index": 3, "content": "…"}}
  ]
}}
每条 content 描述一个论文解决的核心科学问题，说明问题是什么、怎么解决的。
	严禁括号追补句式，专业术语和缩写融入句子自然表达。""",
        "stage_4_content": f"""
论文元信息（供参考）：
{paper_meta_hint}

请仔细阅读全文，按子章节拆分研究内容。输出以下 JSON：

{{
  "research_content_sections": [
    {{
      "order": 1,
      "title": "子章节标题（如'分子库构建与ML-HTVS高通量虚拟筛选'）",
      "body": "该子章节的完整中文概述（可包含多段，保留图引用如'如图X所示'）",
      "figures": [
        {{
          "figure_id": "图1",
          "image_path": ".cache/figures/imageFile4.png",
          "caption": "完整图题",
          "insert_after_paragraph": "定位文字，如'如图1所示，整个研究流程'"
        }}
      ]
    }}
  ]
}}

要求：
- 子章节数量通常 3-5 个
- body 字段需要详细概述该子章节内容，不能只写标题
- 图题完整保留原文
- image_path 统一用 ".cache/figures/imageFileN.png" 格式
- insert_after_paragraph 取所在段落的前 10-20 个字，用于定位插入位置
	- body 正文严禁使用"XXX（yyy）"式括号补充说明，专业术语/缩写融入句子自然表达""",
        "stage_5_takeaways": f"""
论文元信息（供参考）：
{paper_meta_hint}

汇报人：{reporter_name}（{reporter_grade}）
研究方向：{research_direction}

请结合论文内容和汇报人的研究方向，输出 3 条个人收获：

{{
  "personal_takeaways": [
    {{"index": 1, "content": "…"}},
    {{"index": 2, "content": "…"}},
    {{"index": 3, "content": "…"}}
  ]
}}

每条 content 应：
- 结合论文的具体方法/结论
- 联系汇报人的研究方向
- 体现方法论层面的思考
- 严禁括号追补句式，专业术语和缩写融入句子自然表达""",
    }

    instruction = stage_instructions.get(stage_key, "")
    paper_section = f"\n\n---\n## 论文全文 Markdown\n\n{markdown_content}"

    return f"{header}\n{instruction}{paper_section}"


# ─────────────────────────────────────────────
# 合并与校验
# ─────────────────────────────────────────────

def assemble_fill_schema(
    stage_outputs: dict,
    *,
    reporter_name: str = "",
    reporter_grade: str = "研一",
    research_direction: str = "",
    report_date: str = "",
) -> FillSchema:
    """
    将各阶段 LLM 输出的 JSON 片段合并为完整 FillSchema，并做校验。

    Parameters
    ----------
    stage_outputs : dict
        {"stage_1_meta": {...}, "stage_2_background": {...}, ...}
    reporter_name / reporter_grade / research_direction / report_date : str
        汇报人/日期信息。

    Returns
    -------
    FillSchema
        校验通过的完整填充数据。
    """
    merged: dict = {
        "reporter_name": reporter_name,
        "reporter_grade": reporter_grade,
        "research_direction": research_direction,
        "report_date": report_date,
    }

    # Stage 1: 元信息
    if "stage_1_meta" in stage_outputs:
        s1 = stage_outputs["stage_1_meta"]
        merged.update({
            "paper_title": s1.get("paper_title", ""),
            "paper_title_zh": s1.get("paper_title_zh", ""),
            "paper_url": s1.get("paper_url", ""),
            "institution": s1.get("institution", ""),
        })

    # Stage 2: 研究背景
    if "stage_2_background" in stage_outputs:
        merged["research_background"] = stage_outputs["stage_2_background"].get(
            "research_background", []
        )

    # Stage 3: 科学问题
    if "stage_3_problems" in stage_outputs:
        merged["scientific_problems"] = stage_outputs["stage_3_problems"].get(
            "scientific_problems", []
        )

    # Stage 4: 研究内容
    if "stage_4_content" in stage_outputs:
        s4 = stage_outputs["stage_4_content"]
        merged["research_content_sections"] = s4.get("research_content_sections", [])
        # 汇总所有图表
        all_figs = []
        for sec in merged["research_content_sections"]:
            all_figs.extend(sec.get("figures", []))
        merged["all_figures"] = all_figs

    # Stage 5: 个人收获
    if "stage_5_takeaways" in stage_outputs:
        merged["personal_takeaways"] = stage_outputs["stage_5_takeaways"].get(
            "personal_takeaways", []
        )

    # Pydantic 校验 + 默认值填充
    schema = FillSchema(**merged)

    # ── 自动汇总 all_figures ──
    if not schema.all_figures:
        all_figs = []
        for sec in schema.research_content_sections:
            all_figs.extend(sec.figures)
        schema.all_figures = all_figs

    return schema


# ─────────────────────────────────────────────
# 便捷函数：保存 / 加载 fill.json
# ─────────────────────────────────────────────

def save_fill_json(schema: FillSchema, path: str | Path) -> Path:
    """将 FillSchema 序列化为 JSON 文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        schema.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[build_fill_json] 已保存 fill.json → {path}")
    return path


def load_fill_json(path: str | Path) -> FillSchema:
    """从 JSON 文件反序列化为 FillSchema。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"fill.json 不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return FillSchema(**data)
