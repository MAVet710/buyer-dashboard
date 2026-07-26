from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
import re
from typing import Iterable, Sequence

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    KeepTogether,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PAGE_SIZE = landscape(letter)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE
CONTENT_WIDTH = PAGE_WIDTH - 0.9 * inch


@dataclass(frozen=True)
class ReportPalette:
    accent: str
    accent_soft: str
    accent_dark: str
    division: str


RETAIL_PALETTE = ReportPalette(
    accent="#E7984E",
    accent_soft="#FFF0E2",
    accent_dark="#7A3F11",
    division="RETAIL OPS",
)
PRODUCTION_PALETTE = ReportPalette(
    accent="#4CD388",
    accent_soft="#E6F8EE",
    accent_dark="#155B37",
    division="PRODUCTION OPS",
)


@dataclass(frozen=True)
class ReportMetric:
    label: str
    value: str
    context: str = ""


@dataclass
class ReportSection:
    title: str
    dataframe: pd.DataFrame | None = None
    description: str = ""
    columns: Sequence[str] | None = None
    max_rows: int = 60


@dataclass
class ExecutiveReportSpec:
    title: str
    subtitle: str
    palette: ReportPalette
    metrics: Sequence[ReportMetric] = field(default_factory=list)
    executive_brief: str = ""
    findings: Sequence[str] = field(default_factory=list)
    recommendations: Sequence[str] = field(default_factory=list)
    sections: Sequence[ReportSection] = field(default_factory=list)
    chart_title: str = ""
    chart_items: Sequence[tuple[str, float, str]] = field(default_factory=list)
    organization: str = "Current organization"
    facility: str = "Current facility"
    reporting_period: str = "Current session"
    generated_at: datetime | None = None
    confidentiality: str = "CONFIDENTIAL - INTERNAL OPERATIONS"


def _clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2022": "-",
        "\u00a0": " ",
        "\u00e2\u20ac\u00a2": "-",
        "\u00e2\u20ac\u201d": "-",
        "\u00e2\u20ac\u201c": "-",
        "â€¢": "-",
        "â€”": "-",
        "â€“": "-",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return " ".join(text.split())


def _escape(value: object) -> str:
    return (
        _clean_text(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _humanize_header(value: object) -> str:
    text = re.sub(r"[_\-]+", " ", _clean_text(value))
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return (
        text.title()
        .replace("Pct", "%")
        .replace("Sku", "SKU")
        .replace("Coa", "COA")
        .replace("Qa", "QA")
        .replace("Cogs", "COGS")
    )


def _format_value(value: object, column: str = "") -> str:
    if value is None or (not isinstance(value, (list, dict, tuple)) and pd.isna(value)):
        return "-"
    column_key = _clean_text(column).lower()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if any(token in column_key for token in ("margin", "yield", "attainment", "rate", "pct", "%")):
            return f"{numeric:,.1f}%"
        if any(token in column_key for token in ("revenue", "profit", "cost", "cogs", "price", "sales", "value", "$")):
            return f"${numeric:,.2f}"
        if column_key.endswith(" g") or "weight g" in column_key or "grams" in column_key:
            return f"{numeric:,.1f} g"
        if numeric.is_integer():
            return f"{int(numeric):,}"
        return f"{numeric:,.1f}"
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d %H:%M")
    return _clean_text(value)


class _Bar(Flowable):
    def __init__(self, ratio: float, accent: colors.Color, width: float = 190, height: float = 9):
        super().__init__()
        self.width = width
        self.height = height
        self.ratio = max(0.0, min(1.0, float(ratio)))
        self.accent = accent

    def draw(self):
        self.canv.setFillColor(colors.HexColor("#E7E9EC"))
        self.canv.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        if self.ratio:
            self.canv.setFillColor(self.accent)
            self.canv.roundRect(
                0,
                0,
                max(self.height, self.width * self.ratio),
                self.height,
                self.height / 2,
                stroke=0,
                fill=1,
            )


class _NumberedDocTemplate(BaseDocTemplate):
    def __init__(self, *args, report_spec: ExecutiveReportSpec, **kwargs):
        self.report_spec = report_spec
        super().__init__(*args, **kwargs)


def _styles(palette: ReportPalette) -> dict[str, ParagraphStyle]:
    accent = colors.HexColor(palette.accent)
    return {
        "cover_eyebrow": ParagraphStyle(
            "CoverEyebrow",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=accent,
            spaceAfter=10,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=31,
            textColor=colors.white,
            spaceAfter=7,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#BBC0C4"),
            spaceAfter=18,
        ),
        "meta": ParagraphStyle(
            "Meta",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#BBC0C4"),
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#93999E"),
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.white,
            spaceBefore=4,
        ),
        "metric_context": ParagraphStyle(
            "MetricContext",
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#93999E"),
            spaceBefore=2,
        ),
        "cover_section": ParagraphStyle(
            "CoverSection",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=accent,
            spaceAfter=5,
        ),
        "cover_body": ParagraphStyle(
            "CoverBody",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#F3F4F5"),
        ),
        "cover_bullet": ParagraphStyle(
            "CoverBullet",
            fontName="Helvetica",
            fontSize=8.2,
            leading=11,
            textColor=colors.HexColor("#E2E5E3"),
        ),
        "page_title": ParagraphStyle(
            "PageTitle",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#171A1C"),
            spaceAfter=4,
        ),
        "page_intro": ParagraphStyle(
            "PageIntro",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#666D72"),
            spaceAfter=13,
        ),
        "section": ParagraphStyle(
            "Section",
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#171A1C"),
            spaceBefore=5,
            spaceAfter=4,
        ),
        "section_description": ParagraphStyle(
            "SectionDescription",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#71777C"),
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#31363A"),
        ),
        "body_bold": ParagraphStyle(
            "BodyBold",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#31363A"),
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8.5,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            fontName="Helvetica",
            fontSize=6.7,
            leading=8.4,
            textColor=colors.HexColor("#25292C"),
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "Small",
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#666D72"),
        ),
    }


def _draw_cover_page(canvas, doc):
    spec = doc.report_spec
    palette = spec.palette
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#0B0E0C"))
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor(palette.accent))
    canvas.rect(0, PAGE_HEIGHT - 7, PAGE_WIDTH, 7, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#131714"))
    canvas.roundRect(PAGE_WIDTH - 165, PAGE_HEIGHT - 52, 123, 23, 11, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor(palette.accent))
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(PAGE_WIDTH - 103.5, PAGE_HEIGHT - 43, palette.division)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(32, PAGE_HEIGHT - 44, "DoobieLogic")
    canvas.setFillColor(colors.HexColor("#737A76"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(32, 18, spec.confidentiality)
    canvas.drawRightString(PAGE_WIDTH - 32, 18, f"Generated {(spec.generated_at or datetime.now()).strftime('%Y-%m-%d %H:%M')}")
    canvas.restoreState()


def _draw_content_page(canvas, doc):
    spec = doc.report_spec
    palette = spec.palette
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#F7F7F5"))
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#111512"))
    canvas.rect(0, PAGE_HEIGHT - 39, PAGE_WIDTH, 39, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor(palette.accent))
    canvas.rect(0, PAGE_HEIGHT - 42, PAGE_WIDTH, 3, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(32, PAGE_HEIGHT - 25, "DoobieLogic")
    canvas.setFillColor(colors.HexColor("#AFB5B1"))
    canvas.setFont("Helvetica", 8)
    report_label = _clean_text(spec.title).replace(" Executive Report", "")
    canvas.drawRightString(PAGE_WIDTH - 32, PAGE_HEIGHT - 25, f"{palette.division}  /  {report_label[:48]}")
    canvas.setStrokeColor(colors.HexColor("#DADDD9"))
    canvas.line(32, 25, PAGE_WIDTH - 32, 25)
    canvas.setFillColor(colors.HexColor("#777D79"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(32, 13, spec.confidentiality)
    canvas.drawRightString(PAGE_WIDTH - 32, 13, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _metric_grid(metrics: Sequence[ReportMetric], styles: dict[str, ParagraphStyle]) -> Table:
    padded = list(metrics[:8])
    while len(padded) % 4:
        padded.append(ReportMetric("", "", ""))
    rows = []
    for offset in range(0, len(padded), 4):
        row = []
        for metric in padded[offset : offset + 4]:
            if not metric.label:
                row.append("")
                continue
            parts = [
                Paragraph(_escape(metric.label).upper(), styles["metric_label"]),
                Paragraph(_escape(metric.value), styles["metric_value"]),
            ]
            if metric.context:
                parts.append(Paragraph(_escape(metric.context), styles["metric_context"]))
            row.append(parts)
        rows.append(row)
    table = Table(rows, colWidths=[CONTENT_WIDTH / 4] * 4, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#161B17")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#2B312D")),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#2B312D")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]
    table.setStyle(TableStyle(commands))
    return table


def _bullet_list(
    items: Iterable[str],
    styles: dict[str, ParagraphStyle],
    accent: str,
    *,
    style_name: str = "body",
) -> list[Flowable]:
    flowables: list[Flowable] = []
    for index, item in enumerate(items, 1):
        flowables.append(
            Paragraph(
                f'<font color="{accent}"><b>{index:02d}</b></font>&nbsp;&nbsp;{_escape(item)}',
                styles[style_name],
            )
        )
        flowables.append(Spacer(1, 4))
    return flowables


def _decision_table(spec: ExecutiveReportSpec, styles: dict[str, ParagraphStyle]) -> Table | None:
    findings = list(spec.findings)[:5]
    recommendations = list(spec.recommendations)[:5]
    if not findings and not recommendations:
        return None
    accent = spec.palette.accent
    left = [Paragraph("WHAT NEEDS ATTENTION", styles["cover_section"])]
    left.extend(
        _bullet_list(
            findings or ["No material exceptions detected."],
            styles,
            accent,
            style_name="cover_bullet",
        )
    )
    right = [Paragraph("RECOMMENDED NEXT MOVES", styles["cover_section"])]
    right.extend(
        _bullet_list(
            recommendations or ["Continue monitoring current operating signals."],
            styles,
            accent,
            style_name="cover_bullet",
        )
    )
    table = Table([[left, right]], colWidths=[CONTENT_WIDTH / 2] * 2)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#161B17")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#2B312D")),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#2B312D")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def _chart_table(spec: ExecutiveReportSpec, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    items = [(label, float(value), display) for label, value, display in spec.chart_items if value is not None]
    if not items:
        return []
    maximum = max(abs(value) for _, value, _ in items) or 1.0
    accent = colors.HexColor(spec.palette.accent)
    rows = []
    for label, value, display in items[:10]:
        rows.append(
            [
                Paragraph(_escape(label), styles["body_bold"]),
                Paragraph(_escape(display), styles["body"]),
                _Bar(abs(value) / maximum, accent),
            ]
        )
    table = Table(rows, colWidths=[2.25 * inch, 1.0 * inch, CONTENT_WIDTH - 3.25 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBELOW", (0, 0), (-1, -2), 0.35, colors.HexColor("#E2E4E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [
        CondPageBreak(150),
        Paragraph(_escape(spec.chart_title or "Performance Snapshot"), styles["section"]),
        table,
        Spacer(1, 10),
    ]


def _column_widths(df: pd.DataFrame, available: float) -> list[float]:
    if df.empty:
        return []
    raw_weights = []
    for column in df.columns:
        sample = [str(column)] + [_format_value(value, str(column)) for value in df[column].head(24)]
        longest = max((min(34, len(_clean_text(value))) for value in sample), default=8)
        raw_weights.append(max(7, longest))
    total = sum(raw_weights) or len(raw_weights)
    widths = [available * weight / total for weight in raw_weights]
    minimum = min(0.8 * inch, available / max(1, len(widths)))
    widths = [max(minimum, width) for width in widths]
    scale = available / sum(widths)
    return [width * scale for width in widths]


def _data_table(
    dataframe: pd.DataFrame,
    styles: dict[str, ParagraphStyle],
    palette: ReportPalette,
) -> LongTable:
    df = dataframe.copy()
    header = [Paragraph(_escape(_humanize_header(column)).upper(), styles["table_head"]) for column in df.columns]
    body = [
        [Paragraph(_escape(_format_value(value, str(column))), styles["table_cell"]) for column, value in row.items()]
        for _, row in df.iterrows()
    ]
    table = LongTable(
        [header] + body,
        colWidths=_column_widths(df, CONTENT_WIDTH),
        repeatRows=1,
        hAlign="LEFT",
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette.accent_dark)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8DBD7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row_index in range(1, len(body) + 1):
        background = colors.white if row_index % 2 else colors.HexColor("#F0F2EF")
        commands.append(("BACKGROUND", (0, row_index), (-1, row_index), background))
    table.setStyle(TableStyle(commands))
    return table


def _section_flowables(
    section: ReportSection,
    styles: dict[str, ParagraphStyle],
    palette: ReportPalette,
) -> list[Flowable]:
    df = section.dataframe if isinstance(section.dataframe, pd.DataFrame) else pd.DataFrame()
    if df.empty:
        return []
    if section.columns:
        available_columns = [column for column in section.columns if column in df.columns]
        if available_columns:
            df = df[available_columns]
    df = df.head(max(1, section.max_rows))
    heading = [Paragraph(_escape(section.title), styles["section"])]
    if section.description:
        heading.append(Paragraph(_escape(section.description), styles["section_description"]))
    return [CondPageBreak(150), KeepTogether(heading), _data_table(df, styles, palette), Spacer(1, 12)]


def build_executive_pdf(spec: ExecutiveReportSpec) -> bytes:
    generated_at = spec.generated_at or datetime.now()
    spec.generated_at = generated_at
    styles = _styles(spec.palette)
    buffer = BytesIO()
    document = _NumberedDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.68 * inch,
        bottomMargin=0.38 * inch,
        title=_clean_text(spec.title),
        author="DoobieLogic",
        subject=f"{spec.palette.division} executive operations report",
        report_spec=spec,
    )
    cover_frame = Frame(
        document.leftMargin,
        document.bottomMargin + 0.04 * inch,
        CONTENT_WIDTH,
        PAGE_HEIGHT - document.topMargin - document.bottomMargin - 0.1 * inch,
        id="cover_frame",
        showBoundary=0,
    )
    content_frame = Frame(
        document.leftMargin,
        document.bottomMargin + 0.08 * inch,
        CONTENT_WIDTH,
        PAGE_HEIGHT - document.topMargin - document.bottomMargin - 0.08 * inch,
        id="content_frame",
        showBoundary=0,
    )
    document.addPageTemplates(
        [
            PageTemplate(
                id="Cover",
                frames=[cover_frame],
                onPage=_draw_cover_page,
                autoNextPageTemplate="Content",
            ),
            PageTemplate(id="Content", frames=[content_frame], onPage=_draw_content_page),
        ]
    )

    metadata = (
        f"<b>Organization:</b> {_escape(spec.organization)}"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Facility:</b> {_escape(spec.facility)}"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Period:</b> {_escape(spec.reporting_period)}"
    )
    story: list[Flowable] = [
        Spacer(1, 0.08 * inch),
        Paragraph(f"{spec.palette.division} / EXECUTIVE BRIEF", styles["cover_eyebrow"]),
        Paragraph(_escape(spec.title), styles["cover_title"]),
        Paragraph(_escape(spec.subtitle), styles["cover_subtitle"]),
        Paragraph(metadata, styles["meta"]),
        Spacer(1, 0.18 * inch),
    ]
    if spec.metrics:
        story.extend([_metric_grid(spec.metrics, styles), Spacer(1, 0.16 * inch)])
    if spec.executive_brief:
        brief = Table(
            [
                [
                    [
                        Paragraph("EXECUTIVE READ", styles["cover_section"]),
                        Paragraph(_escape(spec.executive_brief), styles["cover_body"]),
                    ]
                ]
            ],
            colWidths=[CONTENT_WIDTH],
        )
        brief.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#161B17")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#2B312D")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.extend([brief, Spacer(1, 0.12 * inch)])
    decision_table = _decision_table(spec, styles)
    if decision_table is not None:
        story.append(decision_table)

    content_exists = bool(spec.chart_items) or any(
        isinstance(section.dataframe, pd.DataFrame) and not section.dataframe.empty for section in spec.sections
    )
    if content_exists:
        story.extend(
            [
                PageBreak(),
                Paragraph("Operational Detail", styles["page_title"]),
                Paragraph(
                    f"{_escape(spec.title)} - supporting analysis, exception detail, and action tables.",
                    styles["page_intro"],
                ),
            ]
        )
        story.extend(_chart_table(spec, styles))
        for section in spec.sections:
            story.extend(_section_flowables(section, styles, spec.palette))

    document.build(story)
    buffer.seek(0)
    return buffer.read()


def combine_report_pdfs(
    reports: Sequence[bytes],
    *,
    title: str,
    division: str,
) -> bytes:
    from PyPDF2 import PdfReader, PdfWriter

    writer = PdfWriter()
    for report in reports:
        if not report:
            continue
        reader = PdfReader(BytesIO(report))
        for page in reader.pages:
            writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": _clean_text(title),
            "/Author": "DoobieLogic",
            "/Subject": f"{_clean_text(division)} executive report pack",
        }
    )
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output.read()


__all__ = [
    "ExecutiveReportSpec",
    "PRODUCTION_PALETTE",
    "RETAIL_PALETTE",
    "ReportMetric",
    "ReportSection",
    "build_executive_pdf",
    "combine_report_pdfs",
]
