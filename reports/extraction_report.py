from io import BytesIO
from reportlab.pdfgen import canvas


def _build_extraction_executive_report_pdf(payload: dict) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 760, "Extraction Executive Report")
    c.save()
    return buffer.getvalue()
