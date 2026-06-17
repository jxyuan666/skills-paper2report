"""
PDF 提取模块 —— 封装 OpenDataLoader-PDF hybrid 模式。

输入：PDF 路径
输出：output_dir 下的 *.md + figures/ 目录
返回：生成的 markdown 文件路径
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def extract_pdf_hybrid(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    hybrid_backend: str = "docling-fast",
    hybrid_mode: str = "full",
    hybrid_url: str = "http://127.0.0.1:5002",
    timeout: int = 600,
) -> Path:
    """
    使用 OpenDataLoader-PDF hybrid 模式解析 PDF。

    Parameters
    ----------
    pdf_path : str | Path
        输入 PDF 文件路径。
    output_dir : str | Path
        输出目录（markdown + 图片均写入此目录）。
    hybrid_backend : str
        hybrid 后端名，默认 "docling-fast"。
    hybrid_mode : str
        hybrid 模式，"full" 表示启用图片描述和公式提取。
    hybrid_url : str
        hybrid 后端地址，默认 http://127.0.0.1:5002。
    timeout : int
        超时秒数，默认 600。

    Returns
    -------
    Path
        生成的第一个 markdown 文件路径。
    """
    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    cmd = [
        sys.executable, "-m", "opendataloader_pdf",
        str(pdf_path),
        "--output-dir", str(output_dir),
        "--format", "markdown",
        "--image-output", "external",
        "--image-dir", str(output_dir / "figures"),
        "--image-format", "png",
        "--hybrid", hybrid_backend,
        "--hybrid-mode", hybrid_mode,
        "--hybrid-url", hybrid_url,
        "--hybrid-timeout", str(timeout),
    ]

    print(f"[extract_pdf] 运行: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout + 30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"OpenDataLoader-PDF 解析失败 (exit {result.returncode})\n"
            f"--- STDOUT ---\n{result.stdout}\n"
            f"--- STDERR ---\n{result.stderr}"
        )

    print(f"[extract_pdf] STDOUT:\n{result.stdout}")
    if result.stderr:
        print(f"[extract_pdf] STDERR:\n{result.stderr}")

    # 找到生成的 markdown 文件
    md_files = sorted(output_dir.rglob("*.md"))
    if not md_files:
        raise FileNotFoundError(
            f"未在 {output_dir} 下找到任何 .md 文件。"
            f"OpenDataLoader 输出内容:\n{result.stdout}"
        )

    print(f"[extract_pdf] 生成 markdown: {md_files[0]}")
    print(f"[extract_pdf] 图片目录: {output_dir / 'figures'}")

    return md_files[0]


def extract_pdf_local(
    pdf_path: str | Path,
    output_dir: str | Path,
) -> Path:
    """
    使用 OpenDataLoader-PDF 本地模式（无 hybrid 后端）解析 PDF。
    适用于无 GPU / 无 hybrid 后端的场景。
    """
    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    cmd = [
        sys.executable, "-m", "opendataloader_pdf",
        str(pdf_path),
        "--output-dir", str(output_dir),
        "--format", "markdown",
        "--image-output", "external",
        "--image-dir", str(output_dir / "figures"),
        "--image-format", "png",
    ]

    print(f"[extract_pdf] 本地模式运行: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        raise RuntimeError(
            f"OpenDataLoader-PDF 本地解析失败 (exit {result.returncode})\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    md_files = sorted(output_dir.rglob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"未在 {output_dir} 下找到任何 .md 文件。")

    return md_files[0]
