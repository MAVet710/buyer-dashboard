from io import BytesIO
from reportlab.pdfgen import canvas


def _build_white_label_repack_report_pdf(payload: dict) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 760, "White Label Repack Report")
    c.save()
    return buffer.getvalue()
