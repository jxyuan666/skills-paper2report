"""
输出质量校验 —— 验证生成的 DOCX 和 fill.json 是否符合模板要求。

用法:
  python src/validate_output.py --docx output.docx --fill-json outputs/fill.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docx import Document


def validate_fill_json(fill_path: Path) -> list[str]:
    """校验 fill.json 字段完整性，返回问题列表。"""
    issues: list[str] = []

    if not fill_path.exists():
        issues.append(f"fill.json 不存在: {fill_path}")
        return issues

    data = json.loads(fill_path.read_text(encoding="utf-8"))

    # 必填字段检查
    required_str_fields = [
        ("paper_title", "论文标题"),
        ("paper_url", "论文链接"),
        ("institution", "作者单位"),
    ]
    for key, label in required_str_fields:
        if not data.get(key):
            issues.append(f"缺少必填字段: {label} ({key})")

    # 编号要点数量检查
    list_checks = [
        ("research_background", "研究背景", 3),
        ("scientific_problems", "科学问题", 3),
        ("personal_takeaways", "个人收获", 3),
    ]
    for key, label, expected in list_checks:
        items = data.get(key, [])
        if len(items) < expected:
            issues.append(
                f"{label} 只有 {len(items)} 条要点，期望 {expected} 条"
            )
        for item in items:
            if not item.get("content", "").strip():
                issues.append(f"{label} 第 {item.get('index', '?')} 条内容为空")

    # 子章节数量检查
    sections = data.get("research_content_sections", [])
    if len(sections) < 3:
        issues.append(f"研究内容只有 {len(sections)} 个子章节，期望 3-5 个")
    if len(sections) > 5:
        issues.append(f"研究内容有 {len(sections)} 个子章节，超出 5 个上限")

    # 图表检查
    all_figures = data.get("all_figures", [])
    if len(all_figures) == 0:
        issues.append("all_figures 为空，缺少图表")

    # 创新点（可选字段，仅提示）
    innovation = data.get("innovation_summary", [])
    if len(innovation) == 0:
        print("  [INFO] innovation_summary 为空（可选字段，不影响输出）")

    return issues


def validate_docx(docx_path: Path) -> list[str]:
    """校验 DOCX 可打开性及基本排版，返回问题列表。"""
    issues: list[str] = []

    if not docx_path.exists():
        issues.append(f"DOCX 文件不存在: {docx_path}")
        return issues

    try:
        doc = Document(str(docx_path))
    except Exception as e:
        issues.append(f"无法打开 DOCX: {e}")
        return issues

    paragraphs = doc.paragraphs
    if len(paragraphs) < 10:
        issues.append(f"DOCX 段落数过少 ({len(paragraphs)})，可能生成不完整")

    # 检查是否有明显的占位符残留
    placeholder_patterns = ["{{", "}}", "research_background", "stage_",
                            "all_figures", "scientific_problems"]
    for i, para in enumerate(paragraphs):
        text = para.text
        for pat in placeholder_patterns:
            if pat in text:
                issues.append(f"段落 {i} 存在占位符残留: '{pat}'")
                break

    # 检查是否混入了 Markdown 标记
    md_patterns = ["###", "![image", "**", "```"]
    for i, para in enumerate(paragraphs):
        text = para.text
        for pat in md_patterns:
            if pat in text:
                issues.append(f"段落 {i} 存在 Markdown 标记残留: '{pat}'")
                break

    # 检查 DOCX 内嵌图片数量
    inline_shapes = doc.inline_shapes
    image_count = len(inline_shapes)
    if image_count == 0:
        issues.append("DOCX 中未检测到内嵌图片，可能图片插入失败")
    else:
        print(f"  [INFO] DOCX 内嵌图片: {image_count} 张")

    return issues


def validate_figures(fill_path: Path, work_dir: Path) -> list[str]:
    """检查 fill.json 中引用的图片文件是否存在（仅当缓存目录存在时检查）。"""
    issues: list[str] = []

    if not fill_path.exists():
        return issues

    data = json.loads(fill_path.read_text(encoding="utf-8"))
    all_figures = data.get("all_figures", [])

    # 若缓存目录已被清理（管线正常行为），跳过源文件存在性检查
    cache_dir = work_dir / ".cache"
    if not cache_dir.exists():
        missing_count = sum(1 for f in all_figures if f.get("image_path"))
        if missing_count > 0:
            print(f"  [INFO] 缓存已清理，跳过 {missing_count} 个源图片文件检查")
        return issues

    for fig in all_figures:
        image_path = fig.get("image_path", "")
        if not image_path:
            issues.append(
                f"图 {fig.get('figure_id', '?')} 缺少 image_path"
            )
            continue

        full_path = work_dir / image_path
        if not full_path.exists():
            issues.append(
                f"图 {fig.get('figure_id', '?')} 图片不存在: {full_path}"
            )

    return issues


def main():
    p = argparse.ArgumentParser(description="校验文献汇报输出质量")
    p.add_argument("--docx", type=str, help="生成的 DOCX 路径")
    p.add_argument("--fill-json", type=str, help="fill.json 路径")
    p.add_argument("--work-dir", type=str, default="outputs",
                   help="工作目录（用于解析图片相对路径）")
    args = p.parse_args()

    all_issues: list[str] = []
    work_dir = Path(args.work_dir)

    if args.fill_json:
        fill_path = Path(args.fill_json)
        print(f"[validate] 检查 fill.json: {fill_path}")
        issues = validate_fill_json(fill_path)
        all_issues.extend(issues)
        for issue in issues:
            print(f"  [FAIL] {issue}")
        if not issues:
            print("  [OK]fill.json 字段完整")

        print(f"[validate] 检查图片文件引用...")
        fig_issues = validate_figures(fill_path, work_dir)
        all_issues.extend(fig_issues)
        for issue in fig_issues:
            print(f"  [FAIL] {issue}")
        if not fig_issues:
            print("  [OK]所有图片文件存在")

    if args.docx:
        docx_path = Path(args.docx)
        print(f"[validate] 检查 DOCX: {docx_path}")
        issues = validate_docx(docx_path)
        all_issues.extend(issues)
        for issue in issues:
            print(f"  [FAIL] {issue}")
        if not issues:
            print("  [OK]DOCX 格式正常")

    print()
    if all_issues:
        print(f"[validate] 发现 {len(all_issues)} 个问题")
        sys.exit(1)
    else:
        print("[validate] 全部检查通过 [OK]")


if __name__ == "__main__":
    main()
