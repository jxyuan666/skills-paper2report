#!/usr/bin/env python
"""
文献汇报生成管线 —— 总调度脚本。

三种运行模式：
  --extract-only    仅解析 PDF → Markdown + 图片
  --prompts-only    解析 PDF 后输出分阶段 prompt（供 Claude Code Skill 调用 LLM）
  --fill-only       从 fill.json + 模板 → 生成 DOCX（不调 LLM）
  --full            完整管线（需要设置 ANTHROPIC_API_KEY）

典型用法（通过 Claude Code Skill）：
  python src/run_pipeline.py --pdf paper.pdf --out outputs/report.docx

工作流：
  PDF → extract_pdf → markdown
       → build prompts (5 stages)
       → [Claude Code 逐阶段调用 LLM，收集 JSON]
       → assemble fill.json
       → fill_docx → report.docx
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

# 确保 src/ 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract_pdf import extract_pdf_hybrid, extract_pdf_local
from src.build_fill_json import (
    STAGE_META,
    build_stage_prompt,
    assemble_fill_schema,
    save_fill_json,
    load_fill_json,
)
from src.fill_docx import fill_docx
from src.schema import FillSchema


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="文献汇报生成管线 —— PDF → Markdown → (LLM) → fill.json → DOCX"
    )
    p.add_argument("--pdf", type=str, help="输入 PDF 路径")
    p.add_argument("--out", type=str, default="outputs/report.docx",
                   help="输出 DOCX 路径 (默认 outputs/report.docx)")
    p.add_argument("--work-dir", type=str, default="outputs",
                   help="中间文件工作目录 (默认 outputs/)")
    p.add_argument("--template", type=str, default="templates/report_template.docx",
                   help="Word 模板路径")
    p.add_argument("--fill-json", type=str, default=None,
                   help="已有 fill.json 路径（跳过 LLM 阶段）")

    # 模式
    p.add_argument("--extract-only", action="store_true",
                   help="仅解析 PDF，输出 markdown 和图片")
    p.add_argument("--prompts-only", action="store_true",
                   help="解析 PDF 后输出分阶段 prompt JSON，不调 LLM")
    p.add_argument("--fill-only", action="store_true",
                   help="仅从 fill.json 生成 DOCX")

    # Hybrid 选项
    p.add_argument("--local", action="store_true",
                   help="使用本地模式（无 hybrid 后端）")
    p.add_argument("--hybrid-backend", type=str, default="docling-fast")
    p.add_argument("--hybrid-url", type=str, default="http://127.0.0.1:5002")

    # 汇报人信息
    p.add_argument("--reporter-name", type=str, default="",
                   help="汇报人姓名")
    p.add_argument("--reporter-grade", type=str, default="研一",
                   help="年级")
    p.add_argument("--research-direction", type=str, default="",
                   help="研究方向")

    return p.parse_args()


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def _fixup_image_paths(stage_outputs: dict, cache_dir_name: str) -> None:
    """将 stage_4 中所有 image_path 前面补上缓存目录前缀，确保 fill_docx 能解析。"""
    s4 = stage_outputs.get("stage_4_content", {})
    for section in s4.get("research_content_sections", []):
        for fig in section.get("figures", []):
            img = fig.get("image_path", "")
            if img and not img.startswith(cache_dir_name):
                fig["image_path"] = f"{cache_dir_name}/{img}"
    for fig in s4.get("all_figures", []):
        img = fig.get("image_path", "")
        if img and not img.startswith(cache_dir_name):
            fig["image_path"] = f"{cache_dir_name}/{img}"


def _cleanup_cache(work_dir: Path) -> None:
    """删除 OpenDataLoader-PDF 的解析缓存（markdown + 图片），保留 JSON 中间产物。"""
    cache_dir = work_dir / ".cache"
    prompts_file = work_dir / "stage_prompts.json"

    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        print(f"[pipeline] 已清理缓存: {cache_dir}")

    if prompts_file.exists():
        prompts_file.unlink()
        print(f"[pipeline] 已清理 prompts: {prompts_file}")


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def main():
    args = parse_args()
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()

    # ── 模式: fill-only ──
    if args.fill_only:
        fill_json_path = args.fill_json or str(work_dir / "fill.json")
        template = args.template
        out = args.out
        print(f"[pipeline] fill-only 模式: {fill_json_path} + {template} → {out}")
        schema = load_fill_json(fill_json_path)
        schema.report_date = schema.report_date or today
        fill_docx(schema, template, out, figures_base_dir=work_dir)
        print(f"[pipeline] 完成: {out}")
        return

    # ── 需要 PDF ──
    if not args.pdf:
        print("错误: 需要 --pdf 参数")
        sys.exit(1)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"错误: PDF 不存在: {pdf_path}")
        sys.exit(1)

    cache_dir = work_dir / ".cache"

    # ── Step 1: 提取 PDF ──
    print(f"[pipeline] Step 1/4: 解析 PDF → {cache_dir}")
    if args.local:
        md_path = extract_pdf_local(pdf_path, cache_dir)
    else:
        md_path = extract_pdf_hybrid(
            pdf_path, cache_dir,
            hybrid_backend=args.hybrid_backend,
            hybrid_url=args.hybrid_url,
        )
    markdown_content = md_path.read_text(encoding="utf-8")
    print(f"[pipeline] Markdown 长度: {len(markdown_content)} 字符")

    # ── 模式: extract-only ──
    if args.extract_only:
        print(f"[pipeline] extract-only 完成: {md_path}")
        return

    # ── Step 2: 生成分阶段 prompt ──
    print(f"[pipeline] Step 2/4: 生成分阶段 prompt")

    paper_meta_hint = f"PDF: {pdf_path.name}"

    stage_prompts = {}
    for stage_key in STAGE_META:
        prompt = build_stage_prompt(
            stage_key,
            markdown_content,
            reporter_name=args.reporter_name,
            reporter_grade=args.reporter_grade,
            research_direction=args.research_direction,
            paper_meta_hint=paper_meta_hint,
        )
        stage_prompts[stage_key] = {
            "meta": STAGE_META[stage_key],
            "prompt": prompt,
        }

    prompts_path = work_dir / "stage_prompts.json"
    prompts_path.write_text(
        json.dumps(stage_prompts, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[pipeline] 已保存 {len(stage_prompts)} 个阶段 prompt → {prompts_path}")

    # ── 模式: prompts-only ──
    if args.prompts_only:
        print(f"[pipeline] prompts-only 完成。")
        print(f"[pipeline] 下一步: 将每个阶段的 prompt 发给 LLM，收集 JSON 输出。")
        print(f"[pipeline] 然后用 --fill-json 调用 --fill-only 生成 DOCX。")
        return

    # ── Step 3: 调用 LLM（需要 Skill 层完成，这里留接口）──
    print(f"[pipeline] Step 3/4: LLM 填充阶段")
    print(f"[pipeline] 注意: 在 Claude Code Skill 中，这一步由 Claude 逐阶段处理。")
    print(f"[pipeline] 如直接运行，请将 stage_prompts.json 中的 prompt 发给 LLM。")

    # 检查是否有预填充的 stage outputs
    stage_outputs_path = work_dir / "stage_outputs.json"
    if stage_outputs_path.exists():
        print(f"[pipeline] 发现已有 stage_outputs.json，跳过 LLM 阶段")
        stage_outputs = json.loads(stage_outputs_path.read_text(encoding="utf-8"))
    else:
        print(f"[pipeline] 未找到 {stage_outputs_path}，请先运行 LLM 阶段。")
        print(f"[pipeline] 提示: 在 Claude Code 中使用 Skill 可自动完成此步骤。")
        return

    # ── 修正图片路径: 确保相对于 work_dir 可解析 ──
    _fixup_image_paths(stage_outputs, ".cache")

    # ── Step 4: 组装 & 生成 DOCX ──
    print(f"[pipeline] Step 4/4: 组装 fill.json → 生成 DOCX")

    schema = assemble_fill_schema(
        stage_outputs,
        reporter_name=args.reporter_name,
        reporter_grade=args.reporter_grade,
        research_direction=args.research_direction,
        report_date=today,
    )

    fill_json_path = work_dir / "fill.json"
    save_fill_json(schema, fill_json_path)

    fill_docx(schema, args.template, args.out, figures_base_dir=work_dir)

    print(f"[pipeline] Done: {args.out}")

    # ── 清理缓存 ──
    _cleanup_cache(work_dir)


if __name__ == "__main__":
    main()
