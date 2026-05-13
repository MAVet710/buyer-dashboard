from __future__ import annotations

from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _build_competitor_intelligence_report_pdf(payload: dict) -> bytes:
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    w, h = letter

    def header(title: str, dark: bool = False) -> None:
        c.setFillColor(colors.HexColor("#121212") if dark else colors.white)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#ff8c42"))
        c.rect(24, h - 90, w - 48, 4, fill=1, stroke=0)
        c.setFillColor(colors.white if dark else colors.HexColor("#111111"))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(24, h - 70, title)
        c.setFont("Helvetica", 10)
        c.drawRightString(w - 24, 24, f"Page {c.getPageNumber()}")

    header("Competitor Intelligence Report", dark=True)
    summary = payload.get("executive_summary", "No summary available.")
    c.setFont("Helvetica", 11)
    text = c.beginText(24, h - 120)
    text.setFillColor(colors.white)
    for line in str(summary)[:1200].split("\n"):
        text.textLine(line[:110])
    c.drawText(text)

    for section in ["competitors", "pricing", "assortment_gaps", "promo_pressure", "recommendations", "data_quality"]:
        c.showPage()
        header(section.replace("_", " ").title(), dark=False)
        c.setFillColor(colors.HexColor("#222222"))
        c.setFont("Helvetica", 10)
        body = payload.get(section, "No data available.")
        text = c.beginText(24, h - 110)
        if isinstance(body, list):
            lines = [f"• {item}" for item in body]
        else:
            lines = str(body).split("\n")
        for line in lines[:42]:
            text.textLine(str(line)[:112])
        c.drawText(text)

    c.save()
    out.seek(0)
    return out.read()
