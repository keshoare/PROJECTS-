!pip install reportlab gradio
"""
ScribeWritta ✍️
================
Turn your typed assignment into handwritten-style PDF pages using your own
TTF/OTF handwriting font.
"""

import io
import os
import tempfile
import traceback
import re

import gradio as gr
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, Color
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_SIZES = {"A4": A4, "Letter": letter}

def hex_to_color(hex_str: str) -> Color:
    hex_str = hex_str.strip()
    if not hex_str.startswith("#"):
        hex_str = "#" + hex_str
    try:
        return HexColor(hex_str)
    except Exception:
        return black

def safe_register_font(path: str) -> str:
    if not path or not os.path.isfile(path):
        return "Helvetica"
    name = "UserHandwriting"
    try:
        pdfmetrics.registerFont(TTFont(name, path))
        return name
    except Exception as e:
        print(f"[ScribeWritta] Font load warning: {e} — falling back to Helvetica")
        return "Helvetica"

def is_heading(line: str, all_lines: list, current_index: int) -> bool:
    line = line.strip()
    if not line:
        return False

    word_count = len(line.split())
    is_short = word_count <= 8 and len(line) < 60

    words = line.split()
    if words:
        capitalized_words = sum(1 for w in words if w and w[0].isupper())
        is_title_case = capitalized_words >= len(words) * 0.6
        is_all_caps = line.isupper() and len(line) > 3
    else:
        is_title_case = False
        is_all_caps = False

    is_followed_by_blank = False
    if current_index + 1 < len(all_lines):
        next_line = all_lines[current_index + 1].strip()
        is_followed_by_blank = (not next_line) or (next_line and len(next_line) < 20)

    is_after_blank = False
    if current_index > 0:
        prev_line = all_lines[current_index - 1].strip()
        is_after_blank = not prev_line

    has_heading_pattern = (
        is_title_case or
        is_all_caps or
        (line and line[0].isupper() and is_short)
    )

    if is_short and has_heading_pattern:
        if is_after_blank or current_index == 0 or is_followed_by_blank:
            return True

    return False

def word_wrap(text: str, font_name: str, font_size: float,
              max_width: float) -> list:
    lines = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = (current + " " + word) if current else word
            if stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines

def draw_two_line_margin(cv, page_w, page_h, ml, mr, mt, mb, color,
                         lw=0.7):
    cv.setStrokeColor(color)
    cv.setLineWidth(lw)
    cv.line(0,  page_h - mt, page_w, page_h - mt)
    cv.line(ml, 0, ml, page_h)

def draw_four_line_margin(cv, page_w, page_h, ml, mr, mt, mb, color,
                          lw=0.7):
    cv.setStrokeColor(color)
    cv.setLineWidth(lw)
    cv.rect(ml, mb, page_w - ml - mr, page_h - mt - mb, stroke=1, fill=0)

def generate_pdf(
    text: str,
    ttf_path,
    page_size_name: str,
    margin_left_mm: float,
    margin_right_mm: float,
    margin_top_mm: float,
    margin_bottom_mm: float,
    font_size: float,
    line_spacing: float,
    text_color_hex: str,
    background_color_hex: str,
    margin_style: str,
    margin_line_color_hex: str,
    char_spacing: float,
    heading_font_size: float,
) -> bytes:

    text = text or ""
    if not text.strip():
        raise ValueError("⚠️ Please type some text before generating the PDF.")

    font_name = safe_register_font(ttf_path)

    page_w, page_h = PAGE_SIZES.get(page_size_name, A4)
    ml = float(margin_left_mm)  * mm
    mr = float(margin_right_mm) * mm
    mt = float(margin_top_mm)   * mm
    mb = float(margin_bottom_mm)* mm
    usable_w    = page_w - ml - mr
    line_height = float(font_size) * float(line_spacing)

    text_color  = hex_to_color(text_color_hex  or "#0000FF")
    bg_color    = hex_to_color(background_color_hex or "#FFFFFF")
    mline_color = hex_to_color(margin_line_color_hex or "#555555")
    heading_color = black

    all_lines = text.splitlines()
    heading_indices = set()

    for i, line in enumerate(all_lines):
        if is_heading(line, all_lines, i):
            heading_indices.add(i)

    processed_lines = []
    for i, line in enumerate(all_lines):
        if i in heading_indices or not line.strip():
            processed_lines.append((line, i in heading_indices))
        else:
            wrapped = word_wrap(line, font_name, float(font_size), usable_w)
            for wrapped_line in wrapped:
                processed_lines.append((wrapped_line, False))

    buf = io.BytesIO()
    cv  = canvas.Canvas(buf, pagesize=(page_w, page_h))

    def new_page():
        cv.setFillColor(bg_color)
        cv.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        if margin_style == "Two-line":
            draw_two_line_margin(cv, page_w, page_h, ml, mr, mt, mb, mline_color)
        elif margin_style == "Four-line":
            draw_four_line_margin(cv, page_w, page_h, ml, mr, mt, mb, mline_color)

    def set_text_style(is_heading_line: bool):
        if is_heading_line:
            cv.setFont(font_name, float(heading_font_size))
            cv.setFillColor(heading_color)
            cv.setStrokeColor(heading_color)
        else:
            cv.setFont(font_name, float(font_size))
            cv.setFillColor(text_color)
            cv.setStrokeColor(text_color)

        try:
            if is_heading_line:
                cv.setCharSpace(float(char_spacing))
            else:
                cv.setCharSpace(float(char_spacing))
        except:
            pass

    new_page()
    set_text_style(False)
    y = page_h - mt - float(font_size)

    for line_text, is_heading_line in processed_lines:
        if not line_text.strip():
            y -= line_height * 0.5
            continue

        current_line_height = float(heading_font_size) * float(line_spacing) if is_heading_line else line_height

        if y < mb + current_line_height:
            cv.showPage()
            new_page()
            set_text_style(False)
            y = page_h - mt - float(font_size)

        set_text_style(is_heading_line)
        cv.drawString(ml, y, line_text)
        y -= current_line_height

    cv.save()
    return buf.getvalue()

def run(
    text, font_file,
    page_size,
    margin_left, margin_right, margin_top, margin_bottom,
    font_size, line_spacing,
    text_color, bg_color,
    margin_style, margin_line_color,
    char_spacing,
    heading_font_size,
):
    ttf_path = font_file if isinstance(font_file, str) else None

    try:
        pdf_bytes = generate_pdf(
            text=text,
            ttf_path=ttf_path,
            page_size_name=page_size,
            margin_left_mm=margin_left,
            margin_right_mm=margin_right,
            margin_top_mm=margin_top,
            margin_bottom_mm=margin_bottom,
            font_size=font_size,
            line_spacing=line_spacing,
            text_color_hex=text_color,
            background_color_hex=bg_color,
            margin_style=margin_style,
            margin_line_color_hex=margin_line_color,
            char_spacing=char_spacing,
            heading_font_size=heading_font_size,
        )
    except ValueError as e:
        raise gr.Error(str(e))
    except Exception as e:
        traceback.print_exc()
        raise gr.Error(f"Unexpected error: {e}")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf",
                                      prefix="scribewritta_")
    tmp.write(pdf_bytes)
    tmp.close()
    return tmp.name

CSS = """
#title-banner { text-align: center; padding: 10px 0 4px 0; }
#title-banner h1 { font-size: 2.2rem; margin-bottom: 2px; }
#title-banner p  { opacity: 0.75; margin: 0; }
"""

with gr.Blocks(title="ScribeWritta", theme=gr.themes.Soft(), css=CSS) as demo:

    with gr.Column(elem_id="title-banner"):
        gr.HTML("""
            <h1>✍️ ScribeWritta</h1>
            <p>Type your assignment. Get it in your handwriting. Done.</p>
        """)

    with gr.Row():

        with gr.Column(scale=3):
            text_input = gr.Textbox(
                label="📝 Assignment Text",
                placeholder="Paste your assignment text here and let ScribeWritta do the rest…",
                lines=18,
                max_lines=200,
            )
            font_upload = gr.File(
                label="🖋️ Your Handwriting Font (.ttf or .otf)",
                file_types=[".ttf", ".otf"],
                type="filepath",
            )
            gr.Markdown(
                "_No font? Get free handwriting fonts from "
                "[Google Fonts](https://fonts.google.com/?category=Handwriting) "
                "or [DaFont](https://www.dafont.com/theme.php?cat=605). "
                "Download the `.ttf` file and upload it above._"
            )

        with gr.Column(scale=2):

            gr.Markdown("### 📄 Page")
            page_size    = gr.Radio(["A4", "Letter"], value="A4", label="Page Size")
            font_size    = gr.Slider(8, 36, value=15, step=1, label="Font Size (pt)")
            heading_font_size = gr.Slider(8, 36, value=18, step=1, label="Heading Font Size (pt)")
            line_spacing = gr.Slider(1.2, 3.0, value=1.9, step=0.1, label="Line Spacing")

            char_spacing = gr.Slider(-3, 3, value=0, step=0.1,
                                    label="Character Spacing (negative = connected)")
            gr.Markdown("*Tip: Use negative values (-1 to -3) for connected cursive letters*")

            gr.Markdown("### 📐 Margins (mm)")
            with gr.Row():
                margin_left  = gr.Number(value=25, label="Left",   minimum=5, maximum=80)
                margin_right = gr.Number(value=15, label="Right",  minimum=5, maximum=80)
            with gr.Row():
                margin_top   = gr.Number(value=20, label="Top",    minimum=5, maximum=80)
                margin_bottom= gr.Number(value=15, label="Bottom", minimum=5, maximum=80)

            gr.Markdown("### 📏 Margin Style")
            margin_style = gr.Radio(
                ["None", "Two-line", "Four-line"],
                value="Two-line",
                label="Margin Lines",
                info="Two-line = top + left  |  Four-line = full border",
            )
            margin_line_color = gr.ColorPicker(value="#444444", label="Margin Line Colour")

            gr.Markdown("### 🎨 Colours")
            with gr.Row():
                text_color = gr.ColorPicker(value="#0000FF", label="Body Text")
                bg_color   = gr.ColorPicker(value="#FFFFFF", label="Background")
            gr.Markdown("*Headings will automatically be in **black***")

    gr.Markdown("---")
    with gr.Row():
        generate_btn  = gr.Button("✨ Write My Assignment!", variant="primary",
                                  scale=2, size="lg")
        download_file = gr.File(label="⬇️ Download PDF", scale=3)

    generate_btn.click(
        fn=run,
        inputs=[
            text_input, font_upload,
            page_size,
            margin_left, margin_right, margin_top, margin_bottom,
            font_size, line_spacing,
            text_color, bg_color,
            margin_style, margin_line_color,
            char_spacing,
            heading_font_size,
        ],
        outputs=download_file,
    )

    gr.Markdown(
        "<center><sub>ScribeWritta — because life's too short to handwrite everything 😅</sub></center>"
    )

if __name__ == "__main__":
    demo.launch(share=True)
