from io import BytesIO
from reportlab.pdfgen import canvas


def _build_buyer_executive_report_pdf(payload: dict) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 760, "Buyer Executive Report")
    c.save()
    return buffer.getvalue()


def _build_buyer_executive_report_bytes(payload: dict) -> bytes:
    return _build_buyer_executive_report_pdf(payload)
