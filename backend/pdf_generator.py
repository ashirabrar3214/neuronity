import os
import re
import io
import tempfile
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Frame, PageTemplate, Table, TableStyle, Image
from reportlab.platypus.flowables import ImageAndFlowables
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Matplotlib for proper chart rendering
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Use standard Times-Roman which is built-in to ReportLab
FONT_NAME = 'Times-Roman'
FONT_SIZE = 11

def convert_citations_to_superscript(text, url_map=None):
    """
    Convert [http...] citations to superscript format, strip hallucinated numbers,
    and build a deterministic bibliography map.
    """
    if url_map is None:
        url_map = {}
        
    # 1. Strip out any hallucinated number citations the LLM stubbornly generates (e.g., [1], [41])
    text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text)
    
    # 2. Handle the [http://...] style by converting them to deterministic sequential numbers
    def url_replacer(match):
        url = match.group(1).strip()
        if url not in url_map:
            url_map[url] = len(url_map) + 1 # Assign the next available number
        num = url_map[url]
        return f'<super>[{num}]</super>'
        
    text = re.sub(r'\[(https?://[^\]]+)\]', url_replacer, text)
    
    return text, url_map

# ─── Chart color palette ───
_PALETTE = [
    '#2c3e50', '#e74c3c', '#3498db', '#2ecc71', '#f39c12',
    '#9b59b6', '#1abc9c', '#e67e22', '#34495e', '#16a085',
]

def _render_chart(chart_data: dict) -> str:
    """
    Render a chart with matplotlib → temp PNG.
    Title is NOT rendered on the chart — it goes in the PDF caption instead.

    Supported: bar, barh, line, pie, multi_bar
    """
    c_type = chart_data.get("type", "bar").lower()
    labels = chart_data.get("labels", [])
    values = chart_data.get("values", [])
    ylabel = chart_data.get("ylabel", "")
    xlabel = chart_data.get("xlabel", "")

    if not labels or not values:
        return None

    # Sizing — compact figures, high DPI for crispness when downscaled in PDF
    if c_type == "pie":
        fig, ax = plt.subplots(figsize=(5.0, 2.8), dpi=400)
    elif c_type == "barh":
        h = max(2.4, 0.32 * len(labels))
        fig, ax = plt.subplots(figsize=(5.0, min(h, 4.5)), dpi=400)
    else:
        fig, ax = plt.subplots(figsize=(5.5, 2.8), dpi=400)

    fig.patch.set_facecolor('white')

    if c_type == "bar":
        vals = [float(v) for v in values]
        bar_colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(vals))]
        bars = ax.bar(range(len(vals)), vals, color=bar_colors, edgecolor='white', linewidth=0.5)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=40, ha='right', fontsize=9)
        for bar, val in zip(bars, vals):
            fmt = f'{val:,.0f}' if val > 100 else f'{val:,.1f}'
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals)*0.01,
                    fmt, ha='center', va='bottom', fontsize=8, color='#444')

    elif c_type == "barh":
        vals = [float(v) for v in values]
        bar_colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(vals))]
        y_pos = list(range(len(vals)))
        bars = ax.barh(y_pos, vals, color=bar_colors, edgecolor='white', linewidth=0.5,
                       height=0.65)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.invert_yaxis()
        for bar, val in zip(bars, vals):
            fmt = f'{val:,.0f}' if val > 100 else f'{val:,.1f}'
            ax.text(bar.get_width() + max(vals)*0.015, bar.get_y() + bar.get_height()/2,
                    fmt, ha='left', va='center', fontsize=8, color='#444')
        ax.yaxis.set_major_locator(ticker.FixedLocator(y_pos))

    elif c_type == "line":
        vals = [float(v) for v in values]
        ax.plot(range(len(vals)), vals, color=_PALETTE[0], linewidth=1.5, marker='o',
                markersize=3, markerfacecolor=_PALETTE[1], markeredgecolor='white', markeredgewidth=0.5)
        ax.fill_between(range(len(vals)), vals, alpha=0.06, color=_PALETTE[0])
        n = len(labels)
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([labels[i] for i in ticks], rotation=35, ha='right', fontsize=8)

    elif c_type == "pie":
        vals = [float(v) for v in values]
        total = sum(vals)
        pie_colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(vals))]
        wedges, _, autotexts = ax.pie(
            vals, labels=None, autopct='%1.0f%%', colors=pie_colors,
            pctdistance=0.78, startangle=90, textprops={'fontsize': 8},
            wedgeprops={'edgecolor': 'white', 'linewidth': 1.2}
        )
        for i, t in enumerate(autotexts):
            pct = vals[i] / total * 100 if total else 0
            t.set_fontweight('bold')
            t.set_color('white' if pct >= 8 else '#333')
            if pct < 3:
                t.set_text('')  # hide tiny-slice labels
        centre = plt.Circle((0, 0), 0.45, fc='white')
        ax.add_artist(centre)
        ax.set_aspect('equal')
        ax.legend(wedges, labels, loc='center left', bbox_to_anchor=(1.0, 0.5),
                  fontsize=8, frameon=False)

    elif c_type == "multi_bar":
        import numpy as np
        series_labels = chart_data.get("series_labels", [])
        n_series = len(values)
        n_groups = len(labels)
        bar_width = 0.8 / n_series
        x = np.arange(n_groups)
        for i, series in enumerate(values):
            vals = [float(v) for v in series]
            ax.bar(x + i * bar_width, vals, bar_width,
                   label=series_labels[i] if i < len(series_labels) else f"Series {i+1}",
                   color=_PALETTE[i % len(_PALETTE)], edgecolor='white', linewidth=0.5)
        ax.set_xticks(x + bar_width * (n_series - 1) / 2)
        ax.set_xticklabels(labels, rotation=35, ha='right', fontsize=9)
        ax.legend(fontsize=8, framealpha=0.9, edgecolor='#ddd')

    else:
        vals = [float(v) for v in values]
        ax.bar(range(len(vals)), vals, color=_PALETTE[0])
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha='right', fontsize=9)

    # Axis labels (no chart title — that goes in PDF caption)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color='#555')
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color='#555')
    ax.tick_params(axis='both', labelsize=8, colors='#555')

    if c_type != "pie":
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#ddd')
        ax.spines['bottom'].set_color('#ddd')
        if c_type == "barh":
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(
                lambda x, p: f'{x:,.0f}' if x >= 1000 else f'{x:g}'
            ))
            ax.grid(axis='x', alpha=0.15, linestyle='--')
        else:
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(
                lambda x, p: f'{x:,.0f}' if x >= 1000 else f'{x:g}'
            ))
            ax.grid(axis='y', alpha=0.15, linestyle='--')

    plt.tight_layout(pad=0.8)

    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    fig.savefig(tmp.name, format='png', bbox_inches='tight', facecolor='white', pad_inches=0.1)
    plt.close(fig)
    return tmp.name

from reportlab.platypus.flowables import Flowable

class ImageWithCaptionAndSource(Flowable):
    """A custom Flowable to combine an Image, a Caption, and potentially a Source,
    presenting a unified block to ImageAndFlowables."""
    def __init__(self, img, caption, source=None):
        Flowable.__init__(self)
        self.img = img
        self.caption = caption
        self.source = source
        self.width = img.drawWidth
        
        self.cap_w, self.cap_h = self.caption.wrap(self.width, 1000)
        self.height = img.drawHeight + self.cap_h + 5
        
        if self.source:
            self.src_w, self.src_h = self.source.wrap(self.width, 1000)
            self.height += self.src_h + 5
            
    def _restrictSize(self, aW, aH):
        return self.width, self.height
        
    def _unRestrictSize(self):
        return self.width, self.height
        
    def wrap(self, aW, aH):
        return self.width, self.height
        
    def draw(self):
        # Draw image at top
        self.img.drawOn(self.canv, 0, self.height - self.img.drawHeight)
        
        # Draw caption below it
        y = self.height - self.img.drawHeight - self.cap_h - 5
        self.caption.drawOn(self.canv, 0, y)
        
        # Draw source below that
        if self.source:
            y -= self.src_h + 5
            self.source.drawOn(self.canv, 0, y)

class ReportPDFGenerator:
    def __init__(self, filename, title):
        self.filename = filename
        self.title = title
        self.styles = getSampleStyleSheet()
        
        # Define specific styles based on requirements
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontName='Times-Roman',
            fontSize=16,
            alignment=1, # Center
            spaceAfter=20
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontName='Times-Roman',
            fontSize=13,
            fontWeight='bold',
            spaceBefore=12,
            spaceAfter=6
        ))
        
        self.styles.add(ParagraphStyle(
            name='NormalText',
            parent=self.styles['Normal'],
            fontName='Times-Roman',
            fontSize=11,
            leading=14, # Line spacing
            alignment=4 # Justified
        ))
        
        self.styles.add(ParagraphStyle(
            name='SourceItem',
            parent=self.styles['Normal'],
            fontName='Times-Roman',
            fontSize=10,
            leading=12,
            leftIndent=20,
            spaceBefore=4
        ))

        self.styles.add(ParagraphStyle(
            name='FigureCaption',
            parent=self.styles['Normal'],
            fontName='Times-Roman',
            fontSize=9,
            leading=11,
            alignment=1,  # Center
            spaceBefore=4,
            spaceAfter=2,
            textColor=colors.HexColor('#333333'),
        ))

        self.styles.add(ParagraphStyle(
            name='FigureSource',
            parent=self.styles['Normal'],
            fontName='Times-Roman',
            fontSize=7.5,
            leading=9,
            alignment=1,  # Center
            spaceBefore=0,
            spaceAfter=10,
            textColor=colors.HexColor('#888888'),
        ))

    @staticmethod
    def draw_fixed_elements(canvas, doc):
        """Draws page numbers and metadata on every page."""
        canvas.saveState()
        
        # Page number
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.setFont('Times-Roman', 9)
        canvas.drawCentredString(LETTER[0]/2, 0.35 * inch, text)
        
        # Agent ID in bottom-left
        agent_id = getattr(doc, 'agent_id', 'Unknown')
        canvas.setFont('Times-Roman', 8)
        canvas.drawString(0.5 * inch, 0.35 * inch, f"Agent ID: {agent_id}")
        
        canvas.restoreState()

    def generate(self, content_data, agent_name="Agent", agent_id="Unknown"):
        """
        content_data expected format:
        {
            "summary": "...",
            "sections": [
                {"title": "...", "content": "..."},
                ...
            ],
            "sources": [
                {"title": "...", "url": "..."},
                ...
            ]
        }
        """
        doc = SimpleDocTemplate(self.filename, pagesize=LETTER, topMargin=0.75*inch, bottomMargin=0.75*inch)
        
        # Attach agent_id to doc so draw_fixed_elements can access it
        doc.agent_id = agent_id
        
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        story = []
        
        # Header Metadata
        story.append(Paragraph(f"Report Generated by: {agent_name}", self.styles['NormalText']))
        story.append(Paragraph(f"Date: {now}", self.styles['NormalText']))
        story.append(Spacer(1, 0.2*inch))
        
        # Title
        story.append(Paragraph(self.title, self.styles['ReportTitle']))
        story.append(Spacer(1, 0.2*inch))
        
        # Track URLs so numbering matches across sections
        self.url_map = {}
        fig_counter = 0  # Running figure number
        
        # Summary/Introduction
        if content_data.get("summary"):
            story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
            # Fix spacing: Replace single newlines with spaces, keep double newlines
            clean_summary = re.sub(r'(?<!\n)\n(?!\n)', ' ', content_data["summary"])
            summary_text, self.url_map = convert_citations_to_superscript(clean_summary, self.url_map)
            story.append(Paragraph(summary_text, self.styles['NormalText']))
            story.append(Spacer(1, 0.2*inch))

        # Main Sections
        for section in content_data.get("sections", []):
            story.append(Paragraph(section["title"], self.styles['SectionHeader']))
            
            # --- NEW: Smart Block Parsing (Text vs Tables) ---
            # Split the section by double-newlines to process paragraph by paragraph
            blocks = re.split(r'\n\s*\n', section["content"].strip())
            
            section_flowables = []
            
            for block in blocks:
                block = block.strip()
                if not block:
                    continue
                    
                lines = block.split('\n')
                # Detect a Markdown table: At least 3 lines, has pipes, and has a '---' separator row
                is_table = len(lines) >= 3 and '|' in lines[0] and re.search(r'\|[\s\-:]+\|', lines[1])
                
                if is_table:
                    table_data = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        # Skip the markdown separator row (e.g., |---|---|)
                        if re.match(r'^\|?[\s\-:\|]+\|?$', line):
                            continue
                            
                        # Split by pipe, ignore empty outer strings
                        cells = [c.strip() for c in line.strip('|').split('|')]
                        
                        row_data = []
                        for cell in cells:
                            cell_text, self.url_map = convert_citations_to_superscript(cell, self.url_map)
                            # Make the header row bold
                            if len(table_data) == 0: 
                                cell_text = f"<b>{cell_text}</b>"
                            # Wrap text in Paragraph so it wraps nicely inside the cell
                            row_data.append(Paragraph(cell_text, self.styles['NormalText']))
                            
                        if row_data:
                            table_data.append(row_data)
                            
                    if table_data:
                        # Render the native PDF Table
                        t = Table(table_data)
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e0e0e0')), # Grey header
                            ('VALIGN', (0,0), (-1,-1), 'TOP'),
                            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                            ('PADDING', (0,0), (-1,-1), 6),
                        ]))
                        section_flowables.append(t)
                        section_flowables.append(Spacer(1, 0.15*inch))
                else:
                    # Normal Paragraph: Apply the spacing fix safely here!
                    clean_content = re.sub(r'(?<!\n)\n(?!\n)', ' ', block)
                    section_content, self.url_map = convert_citations_to_superscript(clean_content, self.url_map)
                    section_flowables.append(Paragraph(section_content, self.styles['NormalText']))
                    section_flowables.append(Spacer(1, 0.1*inch))
            # -------------------------------------------------
            
            # --- CHART RENDERING (matplotlib -> PNG -> PDF) ---
            if "chart" in section and section["chart"]:
                chart_data = section["chart"]
                try:
                    img_path = _render_chart(chart_data)
                    if img_path:
                        fig_counter += 1
                        # Embed at corner size to leave space for text wrapping
                        c_type = chart_data.get("type", "bar").lower()
                        img_w = 4.5 * inch
                        
                        # Use PIL to read actual exact dimensions from the saved PNG to avoid ANY stretching
                        from PIL import Image as PilImage
                        with PilImage.open(img_path) as p_img:
                            px_w, px_h = p_img.size
                            aspect_ratio = px_h / float(px_w)
                            
                        img_h = img_w * aspect_ratio
                            
                        # Preserve aspect ratio to prevent stretching
                        img = Image(img_path, width=img_w, height=img_h)
                        img.hAlign = 'CENTER'
                        
                        # Wrap text around image
                        
                        # Figure caption
                        fig_title = chart_data.get("title", "")
                        caption = Paragraph(
                            f"<b>Figure {fig_counter}.</b>  {fig_title}",
                            self.styles['FigureCaption'])
                            
                        # Source citation
                        fig_source = chart_data.get("source", "")
                        source_p = None
                        if fig_source:
                            source_p = Paragraph(
                                f"<i>Source: {fig_source}</i>",
                                self.styles['FigureSource'])
                                
                        combo = ImageWithCaptionAndSource(img, caption, source_p)
                        
                        if section_flowables:
                            story.append(ImageAndFlowables(combo, section_flowables, imageSide='right', imageLeftPadding=15, imageTopPadding=0, imageBottomPadding=5))
                        else:
                            story.append(combo)
                            story.append(Spacer(1, 0.08*inch))
                except Exception as e:
                    print(f"Warning: Failed to render chart: {e}")
                    story.extend(section_flowables)
            else:
                story.extend(section_flowables)
            # ----------------------------------
            
        # Sources Page
        story.append(PageBreak())
        story.append(Paragraph("Sources and References", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1*inch))
        
        # ONLY print sources that were actually cited in the text (stored in self.url_map)
        if hasattr(self, 'url_map') and self.url_map:
            # Reverse the map to order by citation number (1, 2, 3...)
            reverse_map = {v: k for k, v in self.url_map.items()}
            
            for i in range(1, len(self.url_map) + 1):
                url = reverse_map[i]
                # Look up the real title from the LLM's JSON array, fallback to "Reference" if not found
                title = next((s.get("title", "Reference") for s in content_data.get("sources", []) if s.get("url") == url), "Reference")
                
                prefix = f"<b>[{i}]</b> "
                link_html = f'<a href="{url}" color="blue">{title}</a>'
                story.append(Paragraph(f"{prefix}{link_html}<br/><i>{url}</i>", self.styles['SourceItem']))
                story.append(Spacer(1, 0.05*inch))
        else:
            story.append(Paragraph("No specific sources were cited in the text.", self.styles['NormalText']))
            
        # Build the PDF
        doc.build(story, onFirstPage=self.draw_fixed_elements, onLaterPages=self.draw_fixed_elements)
        return self.filename


if __name__ == "__main__":
    # Test generation
    test_data = {
        "summary": "This is a test summary for the report generation tool. It covers the basic functionality and layout requirements.",
        "sections": [
            {"title": "Implementation Progress", "content": "The PDF generator is currently being implemented using the reportlab library. It supports Times New Roman, borders, and page numbers as requested by the user."},
            {"title": "Future Steps", "content": "Next steps include integrating this with the LLM synthesis logic to process data from various sources like web searches and other agents."}
        ],
        "sources": [
            {"title": "ReportLab Documentation", "url": "https://www.reportlab.com/docs/reportlab-userguide.pdf"},
            {"title": "Google Gemini API", "url": "https://ai.google.dev/"}
        ]
    }
    gen = ReportPDFGenerator("test_report.pdf", "AI Integration Test Report")
    gen.generate(test_data)
    print("Test report generated: test_report.pdf")
