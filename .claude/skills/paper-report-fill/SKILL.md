---
name: paper-report-fill
description: 从学术 PDF 中提取内容，按 ICM-107 汇报模板生成规范 Word 文献汇报。输入 PDF 路径，输出完整 DOCX。
argument-hint: "<pdf_path> [output.docx]"
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit
---

# 任务

根据用户提供的学术论文 PDF，调用本项目本地 Python 管线，生成一份符合 ICM-107 文献汇报模板格式的 Word 文档 (.docx)。

项目代码位于 `paper-report-fill/` 目录下，所有脚本以该目录为工作目录执行。

模板结构：
  分享人 → 研究方向
  【文献汇报】
  → 1、标题 → 2、链接 → 3、单位
  → 研究背景（3点编号）
  → 解决的科学问题（3点编号）
  → 研究内容与创新点（3-5个子章节，含图和图题）
  → 个人收获（3点编号）

# 输入

- **必需参数**: PDF 文件路径
- **可选参数**: 输出 DOCX 路径（默认 `./output.docx`）
- 汇报人姓名、年级、研究方向可在 prompt 中指定，如不含则留空

# 执行流程

所有命令从项目目录 `paper-report-fill/` 执行。

## Step 1: 解析 PDF → Markdown + 图片

```bash
cd paper-report-fill && python src/run_pipeline.py --pdf "$PDF_PATH" --extract-only --work-dir outputs --local
```

若 hybrid 后端已启动（`opendataloader-pdf-hybrid --port 5002`），去掉 `--local` 以启用高质量解析。

## Step 2: 生成分阶段 Prompt

```bash
cd paper-report-fill && python src/run_pipeline.py --pdf "$PDF_PATH" --prompts-only --work-dir outputs --local
```

产物 `outputs/stage_prompts.json` 包含 5 个阶段：

| 阶段 | Key | 内容 |
|------|-----|------|
| 1 | `stage_1_meta` | 论文元信息（标题、作者、期刊、链接、单位） |
| 2 | `stage_2_background` | 研究背景（3条编号要点） |
| 3 | `stage_3_problems` | 科学问题（3条编号要点） |
| 4 | `stage_4_content` | 研究内容与创新点（子章节+图表） |
| 5 | `stage_5_takeaways` | 个人收获（3条编号要点） |

## Step 3: LLM 逐阶段填充（Claude 负责）

1. 读取 `paper-report-fill/outputs/md_output/*.md` 获取论文全文。
2. 读取 `paper-report-fill/outputs/stage_prompts.json`，对每个阶段的 `prompt` 字段生成对应 JSON 输出。
3. 将 5 个 JSON 片段合并写入 `paper-report-fill/outputs/stage_outputs.json`：

```json
{
  "stage_1_meta": { ... },
  "stage_2_background": { ... },
  "stage_3_problems": { ... },
  "stage_4_content": { ... },
  "stage_5_takeaways": { ... }
}
```

**约束**:
- 只输出合法 JSON，不得有解释文字
- 正文保留学术风格，专业术语保留英文
- 图题完整保留原文措辞
- 图表 `image_path` 指向 `outputs/.cache/` 下的文件路径（如 `.cache/figures/imageFile4.png`）。管线内置路径修正，LLM 可按 Markdown 中的原始路径填写

## Step 4: 生成 DOCX

```bash
cd paper-report-fill && python src/run_pipeline.py --pdf "$PDF_PATH" --out "$OUTPUT_PATH" --work-dir outputs --local
```

管线自动完成：读取 `stage_outputs.json` → 组装 `fill.json` → 填入模板 → 输出 `.docx`。

跳过 PDF 解析（已有 fill.json）：
```bash
cd paper-report-fill && python src/run_pipeline.py --fill-only --fill-json outputs/fill.json --out "$OUTPUT_PATH"
```

# 质量检查

生成后确认：
- [ ] Word 文档能正常打开
- [ ] 标题、分享人信息居左对齐
- [ ] 研究背景、科学问题、个人收获各有 3 条编号要点
- [ ] 研究内容有 3-5 个子章节（含正文和图表）
- [ ] 图表位置标注清晰，无乱码
- [ ] 无 Markdown 符号、JSON key、prompt 原文残留
- [ ] 字体：标题等线，正文宋体，英文 Times New Roman
- [ ] 正文字号 11pt，段落两端对齐，首行缩进两字符
- [ ] 图注等线小五，居中

运行自动校验：
```bash
cd paper-report-fill && python src/validate_output.py --docx "$OUTPUT_PATH" --fill-json outputs/fill.json
```

# 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `RuntimeError: OpenDataLoader-PDF 失败` | hybrid 后端未启动 | 加 `--local` 参数 |
| 图片无法插入 | 图片路径不对或文件缺失 | 检查 `paper-report-fill/outputs/md_output/figures/` |
| Word 模板缺失 | 未预先生成 | `cd paper-report-fill && python src/generate_template.py templates/report_template.docx` |
| LLM 输出非 JSON | prompt 约束不够 | 重新发送，强调「只输出 JSON」 |
