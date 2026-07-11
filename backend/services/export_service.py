from io import BytesIO
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from services.text_utils import text_to_canvas_format


_TITLE_LEVEL_MAP = {
    "first": 1,
    "second": 2,
    "third": 3,
}


def _extract_node_text(node):
    if isinstance(node, str):
        return node.strip()
    if not isinstance(node, dict):
        return ""

    value = node.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()

    parts = []
    for child in node.get("children", []) or []:
        child_text = _extract_node_text(child)
        if child_text:
            parts.append(child_text)
    return "".join(parts).strip()


def _canvas_blocks(content):
    if not content:
        return []

    if isinstance(content, str):
        content = text_to_canvas_format(content)

    blocks = content if isinstance(content, list) else [content]
    normalized = []
    for block in blocks:
        if isinstance(block, str):
            text = block.strip()
            if text:
                normalized.append({"kind": "paragraph", "text": text})
            continue

        if not isinstance(block, dict):
            continue

        block_type = (block.get("type") or "").strip()
        text = _extract_node_text(block)
        if not text:
            continue

        if block_type == "title":
            normalized.append({
                "kind": "heading",
                "text": text,
                "level": _TITLE_LEVEL_MAP.get(block.get("level"), 2),
            })
        elif block_type == "list":
            normalized.append({
                "kind": "list",
                "text": text,
                "list_type": "number" if block.get("listType") == "number" else "bullet",
            })
        else:
            normalized.append({"kind": "paragraph", "text": text})

    return normalized


def extract_text_from_canvas_editor(content):
    return "\n".join(block["text"] for block in _canvas_blocks(content))


def generate_bid_document(bid, chapters):
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "宋体")

    title = doc.add_heading(bid.title, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def add_chapter(chapter, level=1):
        doc.add_heading(chapter.title, level=level)

        if chapter.content:
            blocks = _canvas_blocks(chapter.content)
            for block in blocks:
                if block["kind"] == "heading":
                    doc.add_heading(block["text"], level=min(max(level + block.get("level", 1) - 1, 1), 4))
                    continue
                if block["kind"] == "list":
                    style_name = "List Number" if block.get("list_type") == "number" else "List Bullet"
                    doc.add_paragraph(block["text"], style=style_name)
                    continue

                para = doc.add_paragraph(block["text"])
                para.paragraph_format.first_line_indent = Pt(24)
                para.paragraph_format.line_spacing = 1.5

        children = getattr(chapter, 'children_list', [])
        if children:
            for child in children:
                add_chapter(child, level=min(level + 1, 3))

    for chapter in chapters:
        add_chapter(chapter)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def generate_project_markdown(project):
    title = project.title or "Untitled report"
    lines = [f"# {title}", ""]
    if project.description:
        lines.extend([project.description.strip(), ""])

    outline = project.outline or _outline_from_text(project.final_content)
    if outline:
        lines.extend(["## 报告大纲", ""])
        lines.extend([f"{index + 1}. {item}" for index, item in enumerate(outline)])
        lines.append("")

    if project.final_content:
        lines.extend(["## 正文", "", project.final_content.strip(), ""])
    else:
        lines.extend(["## 正文", "", "当前项目还没有生成正文。", ""])

    return "\n".join(lines).encode("utf-8")


def generate_project_docx(project):
    doc = Document()
    title = doc.add_heading(project.title or "Untitled report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if project.description:
        doc.add_paragraph(project.description)

    outline = project.outline or _outline_from_text(project.final_content)
    if outline:
        doc.add_heading("报告大纲", level=1)
        for item in outline:
            doc.add_paragraph(str(item), style="List Number")

    doc.add_heading("正文", level=1)
    content = (project.final_content or "当前项目还没有生成正文。").strip()
    for block in content.splitlines():
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            level = min(stripped.count("#"), 3)
            doc.add_heading(stripped.strip("# "), level=level)
        elif stripped.startswith(("-", "*")):
            doc.add_paragraph(stripped.strip("-* "), style="List Bullet")
        else:
            doc.add_paragraph(stripped)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def _outline_from_text(text):
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith(("-", "*")):
            lines.append(stripped.strip("#-* "))
    return lines[:10]


def _split_markdown_sections(text):
    sections = []
    current = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if current:
                sections.append(current)
            current = {"title": stripped.strip("# "), "bullets": [], "notes": ""}
            continue
        if current is None:
            current = {"title": "Key points", "bullets": [], "notes": ""}
        current["notes"] += stripped + "\n"
        if stripped.startswith(("-", "*")) or len(current["bullets"]) < 5:
            current["bullets"].append(stripped.strip("-* "))
    if current:
        sections.append(current)
    return sections
