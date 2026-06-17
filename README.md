# 📄 paper-report-fill

> 从学术论文 PDF 自动生成符合 templates 规范 Word 文档。
> 包括图

---

## 一、📁 项目结构

```
skills/                                          ← Claude Code 工作区根目录
│
├── .claude/skills/paper-report-fill/
│   └── SKILL.md                                 ← 🧭 Skill 调度入口
│
├── .gitignore                                   ← 工作区忽略规则
│
└── paper-report-fill/                           ← 🏠 项目主目录
    │
    ├── .gitignore                               ← 项目忽略规则
    ├── requirements.txt                         ← 📦 Python 依赖清单
    │
    ├── src/                                     ← 🐍 核心源码
    │   ├── __init__.py                          ← 包初始化
    │   ├── schema.py                            ← 📐 Pydantic 数据模型
    │   ├── extract_pdf.py                       ← 📥 PDF 解析模块
    │   ├── build_fill_json.py                   ← 🧩 分阶段 Prompt 构建
    │   ├── fill_docx.py                         ← 📝 DOCX 填充与排版
    │   ├── generate_template.py                 ← 🏗️ Word 模板生成
    │   ├── validate_output.py                   ← ✅ 输出质量校验
    │   └── run_pipeline.py                      ← 🎯 总调度脚本
    │
    └── templates/
        └── report_template.docx                 ← 📋 ICM-107 占位符模板
```

### 二、各文件职责

| 文件 | 职责 | 调用关系 |
|------|------|----------|
| `SKILL.md` | Claude Code Skill 定义——告知 Claude 何时调用、按何顺序执行管线。不含具体逻辑 | 用户输入 `/paper-report-fill` 时触发 |
| `run_pipeline.py` | 总调度脚本。串联 PDF 解析 → Prompt 生成 → LLM 填充 → DOCX 输出四步，并提供 `--extract-only`、`--prompts-only`、`--fill-only` 三种独立运行模式 | 调用 `extract_pdf` → `build_fill_json` → `fill_docx` |
| `schema.py` | 全项目数据结构的**单一事实来源**。定义 `FillSchema`、`SubSection`、`FigureItem`、`NumberedPoint` 四个 Pydantic 模型 | 被 `build_fill_json`、`fill_docx`、`validate_output` 引用 |
| `extract_pdf.py` | 封装 OpenDataLoader-PDF，提供 `extract_pdf_hybrid()` 和 `extract_pdf_local()` 两个函数。Hybrid 模式启用 AI 后端优化表格/公式识别；Local 模式纯 Java 解析 | 被 `run_pipeline.py` 的 Step 1 调用 |
| `build_fill_json.py` | 按 5 个阶段构建结构化 Prompt，将论文 Markdown 注入各阶段模板。提供 `assemble_fill_schema()` 将 LLM 返回的 JSON 合并为完整 FillSchema | 被 `run_pipeline.py` 的 Step 2/4 调用 |
| `fill_docx.py` | 将 FillSchema 填入 Word 模板。`FONT_STYLE` 常量集中控制字体/字号/段落格式。支持自动编号列表、子章节渲染、图片插入与图题居中 | 被 `run_pipeline.py` 的 Step 4 调用 |
| `generate_template.py` | 独立运行，生成含 `{{placeholder}}` 占位符的空白 Word 模板 | 首次部署或模板丢失时手动运行 |
| `validate_output.py` | 独立运行，检查 fill.json 字段完整性、DOCX 可打开性、内嵌图片数量、占位符/Markdown 残留 | 生成 DOCX 后手动或 CI 调用 |
| `requirements.txt` | 声明 `opendataloader-pdf`、`python-docx`、`pydantic` 三个依赖 | `pip install -r requirements.txt` |
| `report_template.docx` | ICM-107 格式的 Word 占位符模板，由 `generate_template.py` 生成，`fill_docx.py` 填充 | Step 4 读取并注入数据 |

---

## 三、🚀 Quickstart

### 环境

```bash
pip install -r requirements.txt
```

> Python 3.10+ 必需。如需增强解析质量，安装 hybrid 扩展并启动后端：
> ```bash
> pip install "opendataloader-pdf[hybrid]"
> opendataloader-pdf-hybrid --port 5002
> ```

### 一行命令

在 Claude Code 中：

```
/paper-report-fill ./paper.pdf ./report.docx
```

> 汇报人信息可在命令后直接补充：`汇报人：张三，研二，钙钛矿太阳能电池方向`

### 分步执行（CLI）

```bash
cd paper-report-fill

# Step 1+2：解析 PDF + 生成 Prompt
python src/run_pipeline.py --pdf paper.pdf --prompts-only --work-dir outputs --local

# Step 3：将 outputs/stage_prompts.json 中各阶段的 prompt 发送给 LLM，
#         收集返回的 JSON，合并为 outputs/stage_outputs.json

# Step 4：生成 DOCX（自动清理缓存）
python src/run_pipeline.py --pdf paper.pdf --out report.docx --work-dir outputs --local
```

> 若持有完整的 `fill.json`，可直接注入：`python src/run_pipeline.py --fill-only --fill-json outputs/fill.json --out report.docx`

### 质量校验

```bash
python src/validate_output.py --docx report.docx --fill-json outputs/fill.json --work-dir outputs
```

---

## 四、⚙️ 管线流程

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  Step 1  │     │   Step 2     │     │   Step 3     │     │  Step 4  │
│ PDF 解析  │ ──→ │ 构建 Prompt │ ──→  │  LLM 填充    │ ──→  │ DOCX 输出│
│ → .cache  │     │ → prompts   │     │ → stage JSON │     │ → .docx  │
└──────────┘     └──────────────┘     └──────────────┘     └──────────┘
                                                               │
                                                          🧹 自动清理 .cache
```

| 步骤 | 输入 | 产物 | 执行者 |
|------|------|------|--------|
| Step 1 | PDF 文件 | `.cache/*.md` + `.cache/figures/*.png` | `extract_pdf.py` (OpenDataLoader-PDF) |
| Step 2 | Markdown 全文 | `stage_prompts.json`（5 个阶段 Prompt） | `build_fill_json.py` |
| Step 3 | 各阶段 Prompt | `stage_outputs.json`（5 组结构化 JSON） | Claude（大模型） |
| Step 4 | `stage_outputs.json` | `fill.json` + 最终 `.docx` | `build_fill_json.py` + `fill_docx.py` |

> Step 4 完成后自动删除 `.cache/` 和 `stage_prompts.json`，仅保留 `stage_outputs.json` 和 `fill.json`（小型文本文件，便于追溯复用）。

---

## 五、📐 数据模型

本项目以 `schema.py` 作为数据结构的单一事实来源，LLM 输出与 Word 填充均受其约束。

### `FillSchema` —— 顶层

| 字段 | 类型 | 说明 |
|------|------|------|
| `reporter_name` | `str` | 汇报人姓名 |
| `reporter_grade` | `str` | 年级（研一/研二/博一） |
| `research_direction` | `str` | 研究方向 |
| `paper_title` | `str` | 论文完整标题（英文原文） |
| `paper_title_zh` | `str` | 中文译名 |
| `paper_url` | `str` | DOI 或 URL |
| `institution` | `str` | 作者单位全称 |
| `research_background` | `List[NumberedPoint]` | 研究背景（3 条） |
| `scientific_problems` | `List[NumberedPoint]` | 科学问题（3 条） |
| `research_content_sections` | `List[SubSection]` | 研究内容子章节（3–5 个） |
| `personal_takeaways` | `List[NumberedPoint]` | 个人收获（3 条） |
| `all_figures` | `List[FigureItem]` | 全文图表索引 |
| `report_date` | `str` | 汇报日期 |

### `SubSection` —— 子章节

| 字段 | 类型 | 说明 |
|------|------|------|
| `order` | `int` | 序号 |
| `title` | `str` | 子章节标题 |
| `body` | `str` | 正文 |
| `figures` | `List[FigureItem]` | 本章节图表 |

### `FigureItem` —— 图表

| 字段 | 类型 | 说明 |
|------|------|------|
| `figure_id` | `str` | 编号（图 1/图 2） |
| `image_path` | `str` | 相对路径（以 `outputs/` 为基准） |
| `caption` | `str` | 完整图题（英文原文） |
| `insert_after_paragraph` | `str` | 插入位置锚点文本 |

---

## 六、🎨 排版规范

以下规范硬编码于 `fill_docx.py` 的 `FONT_STYLE` 常量中。

| 用途 | 中文字体 | 英文字体 | 字号 | 加粗 | 对齐 | 其他 |
|------|----------|----------|------|------|------|------|
| 论文标题 | 等线 | Times New Roman | 11 pt | ● | 左对齐 | — |
| 章节标题 | 等线 | Times New Roman | 11 pt | ● | 左对齐 | — |
| 元信息 | 等线 | Times New Roman | 11 pt | ○ | 左对齐 | — |
| 正文 | 宋体 | Times New Roman | 11 pt | ○ | 两端对齐 | 行距 1.25×，首行缩进 0.78 cm |
| 图注 | 等线 | Times New Roman | 9 pt | ○ | 居中 | — |

图片统一宽度 14.0 cm，居中插入。

---

## 七、🔧 故障排查

| 现象 | 原因 | 措施 |
|------|------|------|
| `RuntimeError: OpenDataLoader-PDF 解析失败` | Hybrid 后端未启动 | 添加 `--local` 参数 |
| DOCX 中图片缺失 | 图片路径未正确解析 | 确认 `figures_base_dir` 指向 `outputs/` |
| LLM 输出非 JSON | Prompt 约束失效 | 重新发送，强调「只输出 JSON」 |
| 模板占位符未被替换 | 模板文件缺失或路径错误 | `python src/generate_template.py templates/report_template.docx` |
| 中文字体显示异常 | 系统缺少等线/宋体 | 在 Word 中手动替换，或修改 `FONT_STYLE` 常量 |

---

## 📄 许可

MIT
