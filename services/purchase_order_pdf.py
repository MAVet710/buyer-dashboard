"""Render a saved purchase order without accepting browser-provided totals."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def money_value(value) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("A saved purchase-order amount is invalid.")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def saved_order_total(lines) -> Decimal:
    return sum((money_value(Decimal(str(line["quantity"])) * Decimal(str(line["unit_price"]))) for line in lines), Decimal("0.00"))


def render_saved_purchase_order(document: dict) -> bytes:
    order = document["order"]
    lines = document["lines"]
    if not lines:
        raise ValueError("The saved purchase order has no lines.")
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.6*inch, rightMargin=.6*inch, topMargin=.6*inch, bottomMargin=.6*inch)
    styles = getSampleStyleSheet()

    def text(value):
        return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), styles["BodyText"])

    story = [Paragraph("DoobieLogic | Purchase order", styles["Title"]), Spacer(1, 12)]
    story.extend([text(f"Order: {order['order_number']}  |  Status: {order['status']}"), text(f"Facility: {document.get('facility_name', '')}"), text(f"Vendor: {document.get('vendor_name', '')}"), text(f"Vendor license: {document.get('vendor_license', '')}"), text(f"Order date: {order.get('order_date', '')}  |  Due: {order.get('due_at') or 'Not specified'}"), Spacer(1, 14)])
    rows = [[text(value) for value in ("SKU", "Description", "Qty", "Unit", "Unit price", "Line total")]]
    for line in lines:
        quantity = Decimal(str(line["quantity"]))
        price = Decimal(str(line["unit_price"]))
        if not quantity.is_finite() or not price.is_finite() or quantity <= 0 or price < 0:
            raise ValueError("The saved purchase order contains an invalid quantity or price.")
        rows.append([text(line.get("sku_snapshot", "")), text(line.get("description", "")), text(f"{quantity:g}"), text(line.get("unit", "")), text(f"{money_value(price):,.2f}"), text(f"{money_value(quantity*price):,.2f}")])
    table = Table(rows, colWidths=[.85*inch, 2.55*inch, .65*inch, .65*inch, 1.05*inch, 1.55*inch], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#edf1f0")), ("LINEBELOW", (0,0), (-1,0), .75, colors.black), ("LINEBELOW", (0,1), (-1,-1), .25, colors.lightgrey), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7)]))
    story.extend([table, Spacer(1,14), text(f"Total ({order.get('currency') or 'USD'}): {saved_order_total(lines):,.2f}")])
    if order.get("notes"):
        story.extend([Spacer(1,12), Paragraph("Notes", styles["Heading2"]), text(order["notes"])])
    story.extend([Spacer(1,12), text("Generated from the saved DoobieLogic purchase-order record. This document does not submit a transaction to a state traceability system.")])
    pdf.build(story)
    return buffer.getvalue()
