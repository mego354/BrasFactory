"""
PDF Report Generator Utility for Garment Factory Management System.
Features:
- Full Arabic language support with bidirectional shaping (arabic_reshaper + bidi).
- Dynamic cross-platform font loading (Windows, Linux, PythonAnywhere).
- Professional factory header with mock company details, exact print date/time, and embedded verification QR Code.
- Numbered canvas with dynamic "Page X of Y" footers.
- Reusable report builder functions for models, production, workers, and clients.
"""
import io
import os
import re
import qrcode
from django.utils import timezone
from django.http import HttpResponse

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable, Image
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import arabic_reshaper
from bidi.algorithm import get_display

# ─────────────────────────────────────────────────────────────
# Factory Information (Mock / Configurable)
# ─────────────────────────────────────────────────────────────
FACTORY_INFO = {
    'name': 'مصنع النور للملابس الجاهزة والمنسوجات',
    'name_en': 'AL-NOOR APPAREL & TEXTILE FACTORY',
    'subtitle': 'نظام إدارة ومتابعة الإنتاج والعمليات الصناعية',
    'tax_id': '320-845-119',
    'cr_no': '489201',
    'phone': '01002345678 - 01234567890',
    'address': 'المنطقة الصناعية - المحلة الكبرى / القاهرة',
}

# ─────────────────────────────────────────────────────────────
# Font Registration (Arabic TrueType)
# ─────────────────────────────────────────────────────────────
_FONTS_REGISTERED = False
_ARABIC_FONT = 'Helvetica'
_ARABIC_FONT_BOLD = 'Helvetica-Bold'


def _register_fonts():
    global _FONTS_REGISTERED, _ARABIC_FONT, _ARABIC_FONT_BOLD
    if _FONTS_REGISTERED:
        return

    candidate_fonts = [
        # Windows
        ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
        ('C:/Windows/Fonts/tahoma.ttf', 'C:/Windows/Fonts/tahomabd.ttf'),
        ('C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/segoeuib.ttf'),
        # Linux / PythonAnywhere / Debian / Ubuntu
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('/usr/share/fonts/truetype/freefont/FreeSans.ttf', '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'),
        ('/usr/share/fonts/truetype/msttcorefonts/Arial.ttf', '/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf'),
    ]

    for reg_path, bold_path in candidate_fonts:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont('FactoryArabic', reg_path))
                if bold_path and os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont('FactoryArabicBold', bold_path))
                else:
                    pdfmetrics.registerFont(TTFont('FactoryArabicBold', reg_path))
                _ARABIC_FONT = 'FactoryArabic'
                _ARABIC_FONT_BOLD = 'FactoryArabicBold'
                _FONTS_REGISTERED = True
                return
            except Exception:
                continue

    _FONTS_REGISTERED = True


_register_fonts()


def _reshape_plain(text):
    if not text:
        return ''
    try:
        has_arabic = any('\u0600' <= char <= '\u06FF' or '\u0750' <= char <= '\u077F' or '\u08A0' <= char <= '\u08FF' or '\uFB50' <= char <= '\uFDFF' or '\uFE70' <= char <= '\uFEFF' for char in text)
        if not has_arabic:
            return text
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def ar(text):
    """Reshapes and applies bidirectional algorithm for Arabic strings in PDF while preserving line breaks."""
    if text is None:
        return ''
    text_str = str(text)
    if not text_str:
        return ''
    
    lines = re.split(r'<br\s*/?>|\n', text_str)
    reshaped_lines = [_reshape_plain(l.strip()) for l in lines]
    return '<br/>'.join(reshaped_lines)


def generate_qr_image_flowable(data_str: str, size: float = 48) -> Image:
    """Generates a high-contrast QR code flowable for PDF reports."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#1e1033', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Image(buf, width=size, height=size)


# ─────────────────────────────────────────────────────────────
# Numbered Canvas for "Page X of Y" Footer & Running Header
# ─────────────────────────────────────────────────────────────
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont(_ARABIC_FONT, 8)
        self.setFillColor(colors.HexColor('#6b5ea8'))

        # Bottom divider line
        self.setStrokeColor(colors.HexColor('#e2d9f3'))
        self.setLineWidth(0.75)
        self.line(30, 36, 565, 36)

        # Footer Left: Page number
        page_str = ar(f'صفحة {self._pageNumber} من {page_count}')
        self.drawString(30, 24, page_str)

        # Footer Center: Confidentiality / Factory Note
        note_str = ar(f"{FACTORY_INFO['name']} — وثيقة إلكترونية معتمدة")
        self.drawCentredString(297.5, 24, note_str)

        # Footer Right: System Tag
        sys_str = ar('نظام إدارة المصنع')
        self.drawRightString(565, 24, sys_str)

        self.restoreState()


# ─────────────────────────────────────────────────────────────
# Core PDF Builder
# ─────────────────────────────────────────────────────────────
class FactoryPDFReport:
    """Helper class to build styled PDF reports."""

    def __init__(self, title, subtitle=''):
        _register_fonts()
        self.title = title
        self.subtitle = subtitle
        self.buffer = io.BytesIO()
        self.doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            leftMargin=30,
            rightMargin=30,
            topMargin=30,
            bottomMargin=45
        )
        self.story = []
        self.styles = getSampleStyleSheet()
        self._init_styles()

    def _init_styles(self):
        self.title_style = ParagraphStyle(
            'ReportTitle',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT_BOLD,
            fontSize=14,
            leading=18,
            alignment=1, # Center
            textColor=colors.HexColor('#1e1033')
        )
        self.subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT,
            fontSize=9.5,
            leading=13,
            alignment=1,
            textColor=colors.HexColor('#6b5ea8')
        )
        self.meta_style = ParagraphStyle(
            'ReportMeta',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT,
            fontSize=8,
            leading=11,
            alignment=2, # Right
            textColor=colors.HexColor('#2d1a56')
        )
        self.th_style = ParagraphStyle(
            'TableHeader',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT_BOLD,
            fontSize=8.5,
            leading=11,
            alignment=1, # Center
            textColor=colors.white
        )
        self.td_style = ParagraphStyle(
            'TableCell',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT,
            fontSize=8,
            leading=11,
            alignment=1, # Center
            textColor=colors.HexColor('#1e1033')
        )
        self.td_right_style = ParagraphStyle(
            'TableCellRight',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT,
            fontSize=8,
            leading=11,
            alignment=2, # Right
            textColor=colors.HexColor('#1e1033')
        )
        self.kpi_title_style = ParagraphStyle(
            'KPITitle',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT,
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.HexColor('#6b5ea8')
        )
        self.kpi_value_style = ParagraphStyle(
            'KPIValue',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT_BOLD,
            fontSize=11.5,
            leading=14,
            alignment=1,
            textColor=colors.HexColor('#6e40c9')
        )
        self.qr_caption_style = ParagraphStyle(
            'QRCaption',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT,
            fontSize=6.5,
            leading=8,
            alignment=1,
            textColor=colors.HexColor('#6b5ea8')
        )

    def add_header(self, filters_dict=None, qr_data=None):
        """Adds factory letterhead, embedded verification QR Code, report title, date/time, and filter summary."""
        now_dt = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')

        if not qr_data:
            qr_data = f"DOC:{self.title} | DATE:{now_dt} | FACTORY:{FACTORY_INFO['name']} | AUTH_OK"

        qr_flowable = generate_qr_image_flowable(qr_data, size=46)
        qr_cell = [
            qr_flowable,
            Spacer(1, 1),
            Paragraph(ar('رمز التحقق'), self.qr_caption_style)
        ]

        left_meta = ar(f"تاريخ الطباعة: {now_dt}\nس.ت: {FACTORY_INFO['cr_no']} | ب.ض: {FACTORY_INFO['tax_id']}\nهاتف: {FACTORY_INFO['phone']}")
        right_meta = ar(f"{FACTORY_INFO['name']}\n{FACTORY_INFO['subtitle']}\n{FACTORY_INFO['address']}")

        header_data = [
            [
                Paragraph(left_meta, ParagraphStyle('LeftFac', parent=self.meta_style, alignment=0, leading=11)),
                qr_cell,
                Paragraph(right_meta, ParagraphStyle('RightFac', parent=self.meta_style, fontName=_ARABIC_FONT_BOLD, alignment=2, leading=11)),
            ]
        ]
        header_table = Table(header_data, colWidths=[195, 60, 280])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        self.story.append(header_table)
        self.story.append(Spacer(1, 4))
        self.story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#6e40c9'), spaceAfter=8, spaceBefore=2))

        # Report Title Box
        self.story.append(Paragraph(ar(self.title), self.title_style))
        if self.subtitle:
            self.story.append(Spacer(1, 2))
            self.story.append(Paragraph(ar(self.subtitle), self.subtitle_style))
        self.story.append(Spacer(1, 8))

        # Filter info box (if provided)
        if filters_dict:
            filter_items = []
            for k, v in filters_dict.items():
                if v:
                    filter_items.append(f"{k}: {v}")
            if filter_items:
                filter_text = "   |   ".join(filter_items)
                filter_table = Table(
                    [[Paragraph(ar(filter_text), ParagraphStyle('FiltP', parent=self.meta_style, fontName=_ARABIC_FONT_BOLD, alignment=1, fontSize=8, textColor=colors.HexColor('#4f2fa0')))]],
                    colWidths=[535]
                )
                filter_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f0ff')),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2d9f3')),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                self.story.append(filter_table)
                self.story.append(Spacer(1, 8))

    def add_kpis(self, kpi_list):
        """
        kpi_list is a list of tuples: [('إجمالي الكمية', '1,500 قطعة'), ('إجمالي القيمة', '45,000 ج.م'), ...]
        """
        if not kpi_list:
            return

        col_w = 535 / len(kpi_list)
        kpi_cells = []
        for label, val in kpi_list:
            cell_content = [
                Paragraph(ar(str(val)), self.kpi_value_style),
                Spacer(1, 2),
                Paragraph(ar(str(label)), self.kpi_title_style)
            ]
            kpi_cells.append(cell_content)

        kpi_table = Table([kpi_cells], colWidths=[col_w] * len(kpi_list))
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#e2d9f3')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2d9f3')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        self.story.append(kpi_table)
        self.story.append(Spacer(1, 10))

    def add_table(self, headers, rows, col_widths=None, right_align_cols=None):
        """
        headers: list of string headers
        rows: list of lists with row data (each item can be a string or a Flowable/Image)
        col_widths: list of width numbers (total 535pt for A4 with 30pt margins)
        right_align_cols: list of column indexes (0-based) that should be right-aligned
        """
        right_align_cols = right_align_cols or []

        # Prepare header cells
        header_cells = [Paragraph(ar(h), self.th_style) for h in headers]
        table_data = [header_cells]

        for r_idx, row in enumerate(rows):
            row_cells = []
            for c_idx, val in enumerate(row):
                if isinstance(val, (Image, Paragraph)):
                    row_cells.append(val)
                else:
                    style = self.td_right_style if c_idx in right_align_cols else self.td_style
                    row_cells.append(Paragraph(ar(str(val if val is not None else '—')), style))
            table_data.append(row_cells)

        if col_widths is None:
            col_widths = [535 / len(headers)] * len(headers)

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e1033')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2d9f3')),
        ]

        # Alternating row colors
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                t_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f8f7ff')))

        table.setStyle(TableStyle(t_style))
        self.story.append(table)
        self.story.append(Spacer(1, 10))

    def add_section_title(self, title_text):
        p = Paragraph(ar(title_text), ParagraphStyle(
            'SecTitle',
            parent=self.styles['Normal'],
            fontName=_ARABIC_FONT_BOLD,
            fontSize=10.5,
            leading=14,
            alignment=2,
            textColor=colors.HexColor('#1e1033')
        ))
        self.story.append(p)
        self.story.append(Spacer(1, 4))

    def build_response(self, filename='report.pdf'):
        """Builds the PDF and returns a Django HttpResponse with application/pdf content type."""
        self.doc.build(self.story, canvasmaker=NumberedCanvas)
        pdf_data = self.buffer.getvalue()
        self.buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(pdf_data)
        return response
