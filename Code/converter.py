"""
converter.py — File conversion logic for the DFS.

Supported conversions:
  Images  (Pillow):        jpg/jpeg/png/bmp/gif/webp/tiff  ↔ any of the same
  Text    (stdlib):        txt / csv / json / xml           ↔ any of the same
  Docs    (pypdf/docx):    pdf → txt/docx,  docx → txt/pdf

Returns the MD5 hex-digest of the output file.
"""

import os
import csv
import json
import hashlib
import logging
import xml.etree.ElementTree as ET
from io import StringIO

logger = logging.getLogger("converter")

IMAGE_FORMATS = {"jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff"}
TEXT_FORMATS  = {"txt", "csv", "json", "xml"}
DOC_FORMATS   = {"pdf", "docx"}

PIL_FORMAT_MAP = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
    "bmp": "BMP",  "gif": "GIF",  "webp": "WEBP", "tiff": "TIFF",
}


def convert_file(in_path, out_path, src_fmt, dst_fmt):
    src_fmt = src_fmt.lower()
    dst_fmt = dst_fmt.lower()

    if src_fmt in IMAGE_FORMATS and dst_fmt in IMAGE_FORMATS:
        _convert_image(in_path, out_path, dst_fmt)
    elif src_fmt in TEXT_FORMATS and dst_fmt in TEXT_FORMATS:
        _convert_text(in_path, out_path, src_fmt, dst_fmt)
    elif src_fmt in DOC_FORMATS or dst_fmt in DOC_FORMATS:
        _convert_document(in_path, out_path, src_fmt, dst_fmt)
    else:
        raise ValueError(
            f"Unsupported conversion: {src_fmt} → {dst_fmt}. "
            f"Images: {sorted(IMAGE_FORMATS)}, "
            f"Text: {sorted(TEXT_FORMATS)}, "
            f"Docs: {sorted(DOC_FORMATS)}"
        )
    return _md5_file(out_path)


# ── Image ─────────────────────────────────────────────────────────────────────

def _convert_image(in_path, out_path, dst_fmt):
    from PIL import Image
    pil_fmt = PIL_FORMAT_MAP[dst_fmt]
    with Image.open(in_path) as img:
        if pil_fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(out_path, format=pil_fmt, quality=95)


# ── Text / Data ───────────────────────────────────────────────────────────────

def _convert_text(in_path, out_path, src_fmt, dst_fmt):
    with open(in_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Parse
    if src_fmt == "json":
        data = json.loads(raw)
    elif src_fmt == "csv":
        data = list(csv.DictReader(StringIO(raw)))
    elif src_fmt == "xml":
        data = _xml_to_dict(raw)
    else:  # txt
        data = raw.splitlines()

    # Serialize
    if dst_fmt == "json":
        out = json.dumps(data, indent=2, ensure_ascii=False)
    elif dst_fmt == "csv":
        out = _to_csv_string(data)
    elif dst_fmt == "xml":
        out = _to_xml_string(data)
    else:  # txt
        out = _to_txt_string(data)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)


def _xml_to_dict(raw):
    """Parse XML into a list of dicts (one per child of root)."""
    root = ET.fromstring(raw)
    result = []
    for child in root:
        row = {"_tag": child.tag}
        row.update(child.attrib)
        for sub in child:
            row[sub.tag] = sub.text or ""
        if not list(child):
            row["_text"] = child.text or ""
        result.append(row)
    return result if result else [{"_tag": root.tag, "_text": root.text or ""}]


def _to_xml_string(data):
    root = ET.Element("root")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                tag = item.get("_tag", "item")
                child = ET.SubElement(root, tag)
                for k, v in item.items():
                    if k not in ("_tag", "_text"):
                        sub = ET.SubElement(child, k)
                        sub.text = str(v)
                if "_text" in item:
                    child.text = item["_text"]
            else:
                child = ET.SubElement(root, "item")
                child.text = str(item)
    else:
        child = ET.SubElement(root, "data")
        child.text = str(data)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _to_csv_string(data):
    if not data:
        return ""
    buf = StringIO()
    if isinstance(data, list) and isinstance(data[0], dict):
        writer = csv.DictWriter(buf, fieldnames=data[0].keys(),
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    else:
        writer = csv.writer(buf)
        for item in data:
            writer.writerow([item])
    return buf.getvalue()


def _to_txt_string(data):
    if isinstance(data, list):
        return "\n".join(str(x) for x in data)
    return str(data)


# ── Documents ─────────────────────────────────────────────────────────────────

def _convert_document(in_path, out_path, src_fmt, dst_fmt):
    if src_fmt == "pdf" and dst_fmt == "txt":
        _pdf_to_txt(in_path, out_path)
    elif src_fmt == "pdf" and dst_fmt == "docx":
        _pdf_to_docx(in_path, out_path)
    elif src_fmt == "docx" and dst_fmt == "txt":
        _docx_to_txt(in_path, out_path)
    elif src_fmt == "docx" and dst_fmt == "pdf":
        _docx_to_pdf(in_path, out_path)
    else:
        raise ValueError(f"Unsupported document conversion: {src_fmt} → {dst_fmt}")


def _pdf_to_txt(in_path, out_path):
    import pypdf
    reader = pypdf.PdfReader(in_path)
    text = "\n\n".join(
        page.extract_text() or "" for page in reader.pages
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)


def _pdf_to_docx(in_path, out_path):
    """Extract PDF text and place it into a DOCX document."""
    import pypdf
    from docx import Document as DocxDocument
    reader = pypdf.PdfReader(in_path)
    doc = DocxDocument()
    doc.add_heading("Converted from PDF", level=1)
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        doc.add_heading(f"Page {i + 1}", level=2)
        for line in text.splitlines():
            if line.strip():
                doc.add_paragraph(line)
    doc.save(out_path)


def _docx_to_txt(in_path, out_path):
    from docx import Document as DocxDocument
    doc = DocxDocument(in_path)
    lines = [para.text for para in doc.paragraphs]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _docx_to_pdf(in_path, out_path):
    """Convert DOCX to PDF using reportlab (pure Python, no LibreOffice needed)."""
    from docx import Document as DocxDocument
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        doc = DocxDocument(in_path)
        pdf = SimpleDocTemplate(out_path, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []
        for para in doc.paragraphs:
            if para.text.strip():
                style = styles["Heading1"] if para.style.name.startswith("Heading") \
                        else styles["Normal"]
                story.append(Paragraph(para.text, style))
                story.append(Spacer(1, 6))
        pdf.build(story)
    except ImportError:
        # Fallback: save plain text as PDF using fpdf2
        try:
            from fpdf import FPDF
            text_lines = [p.text for p in DocxDocument(in_path).paragraphs]
            pdf_obj = FPDF()
            pdf_obj.add_page()
            pdf_obj.set_font("Helvetica", size=12)
            for line in text_lines:
                pdf_obj.multi_cell(0, 8, line or " ")
            pdf_obj.output(out_path)
        except ImportError:
            # Last resort: write text content into a minimal PDF manually
            _docx_to_txt(in_path, out_path.replace(".pdf", "_tmp.txt"))
            with open(out_path.replace(".pdf", "_tmp.txt"), "r",
                      encoding="utf-8") as f:
                text = f.read()
            _write_minimal_pdf(out_path, text)


def _write_minimal_pdf(out_path, text):
    """Write a very basic valid PDF containing plain text."""
    lines = text.splitlines()[:200]          # cap at 200 lines
    escaped = []
    for ln in lines:
        ln = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        escaped.append(ln)

    stream_lines = ["BT", "/F1 12 Tf", "50 750 Td", "14 TL"]
    for ln in escaped:
        stream_lines.append(f"({ln}) Tj T*")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines)

    pdf = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R "
        "/MediaBox [0 0 595 842] /Contents 4 0 R /Resources "
        "<< /Font << /F1 5 0 R >> >> >>\nendobj\n"
        f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        "xref\n0 6\n"
        "trailer\n<< /Size 6 /Root 1 0 R >>\n"
        "startxref\n0\n%%EOF\n"
    )
    with open(out_path, "w", encoding="latin-1") as f:
        f.write(pdf)


# ── Utility ───────────────────────────────────────────────────────────────────

def _md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
