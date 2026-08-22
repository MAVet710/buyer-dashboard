from __future__ import annotations

from difflib import SequenceMatcher
from io import BytesIO
import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import Engine

from services.web_buyer_parity import buyer_intelligence, forecast_view, records, sku_inventory_view
from ..auth import RequestContext, get_request_context, get_retail_context
from ..database import get_engine
from .buyer_parity import _model

router = APIRouter(prefix="/po-parity", tags=["po-parity"], dependencies=[Depends(get_retail_context)])


class POLine(BaseModel):
    sku: str = ""
    description: str = Field(min_length=1, max_length=500)
    strain: str = ""
    size: str = ""
    quantity: float = Field(gt=0)
    price: float = Field(default=0, ge=0)


class POReviewRequest(BaseModel):
    items: list[POLine] = Field(default_factory=list, max_length=500)


class POPdfRequest(BaseModel):
    store_name: str = "Cannabis Store"
    store_address: str = ""
    store_phone: str = ""
    store_contact: str = ""
    vendor_name: str = ""
    vendor_license: str = ""
    vendor_address: str = ""
    vendor_contact: str = ""
    po_number: str = ""
    po_date: str = ""
    terms: str = ""
    fulfillment_notes: str = ""
    tax_rate: float = Field(default=0, ge=0, le=100)
    discount: float = Field(default=0, ge=0)
    shipping: float = Field(default=0, ge=0)
    items: list[POLine] = Field(min_length=1, max_length=500)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _size_norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").casefold())


def _inventory_rows(context: RequestContext, engine: Engine, target_doh: int, velocity_adjustment: float, sales_days: int, sku_window: int):
    detail, product, _inv, _sales, _inventory_source, _sales_source = _model(context, engine, target_doh, velocity_adjustment, sales_days)
    _, sku_product, _inv2, _sales2, _, _ = _model(context, engine, target_doh, velocity_adjustment, sku_window)
    forecast = forecast_view(detail, product)
    reorder = forecast[forecast["reorderpriority"].astype(str).eq("1 – Reorder ASAP")] if not forecast.empty else forecast
    sku = sku_inventory_view(sku_product)
    return detail, product, reorder, sku


def _best_match(item: POLine, inventory: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float, str]:
    sku = _norm(item.sku)
    desc = _norm(item.description)
    size = _size_norm(item.size)
    if sku:
        for row in inventory:
            if _norm(row.get("sku")) == sku:
                return row, 1.0, "SKU exact match"
    best: dict[str, Any] | None = None
    best_score = 0.0
    best_reason = "No inventory match"
    for row in inventory:
        name = _norm(row.get("product_name"))
        if not name or not desc:
            continue
        score = 1.0 if name == desc else SequenceMatcher(None, desc, name).ratio()
        row_size = _size_norm(row.get("packagesize"))
        if size and row_size:
            score += 0.08 if size == row_size else -0.06
        if desc in name or name in desc:
            score = max(score, 0.92)
        if score > best_score:
            best, best_score = row, score
            best_reason = "Product name match"
    return (best, min(best_score, 1.0), best_reason) if best_score >= 0.72 else (None, best_score, "No confident inventory match")


@router.get("/workspace")
def workspace(
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    sku_window: int = Query(56, ge=7, le=120),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _detail, product, reorder, sku = _inventory_rows(context, engine, target_doh, velocity_adjustment, sales_days, sku_window)
    intelligence = buyer_intelligence(product)
    return {
        "controls": {"target_doh": target_doh, "velocity_adjustment": velocity_adjustment, "sales_days": sales_days, "sku_window": sku_window},
        "reorder_asap": records(reorder, limit=500),
        "inventory": records(sku, limit=3000),
        "smart_priorities": records(intelligence["purchase_priorities"], limit=100),
    }


@router.post("/review")
def review_lines(
    payload: POReviewRequest,
    target_doh: int = Query(21, ge=1, le=120),
    velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0),
    sales_days: int = Query(60, ge=7, le=120),
    sku_window: int = Query(56, ge=7, le=120),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    _detail, _product, _reorder, sku = _inventory_rows(context, engine, target_doh, velocity_adjustment, sales_days, sku_window)
    inventory = records(sku, limit=3000)
    result = []
    for item in payload.items:
        match, score, reason = _best_match(item, inventory)
        on_hand = float((match or {}).get("onhandunits") or 0)
        days_supply = float((match or {}).get("days_of_supply") or 0)
        status = str((match or {}).get("status") or "")
        review = match is None or item.quantity > on_hand or "Overstock" in status or "Expiring" in status
        reasons: list[str] = []
        if match is None:
            reasons.append("No confident inventory match")
        else:
            if item.quantity > on_hand:
                reasons.append(f"Order quantity exceeds current on-hand ({on_hand:,.0f})")
            if "Overstock" in status:
                reasons.append("Matched SKU is currently overstocked")
            if "Expiring" in status:
                reasons.append("Matched SKU is expiring soon")
            if not reasons:
                reasons.append("Inventory cross-check passed")
        result.append({
            "sku": item.sku,
            "description": item.description,
            "requested_quantity": item.quantity,
            "matched_product": (match or {}).get("product_name", ""),
            "matched_sku": (match or {}).get("sku", ""),
            "on_hand": on_hand,
            "days_of_supply": days_supply,
            "inventory_status": status,
            "match_score": round(score, 3),
            "match_method": reason,
            "review": review,
            "review_reason": "; ".join(reasons),
        })
    return result


def _pdf(payload: POPdfRequest) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=0.45 * inch, leftMargin=0.45 * inch, topMargin=0.45 * inch, bottomMargin=0.45 * inch)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("po-title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=23, textColor=colors.HexColor("#111111"))
    small = ParagraphStyle("po-small", parent=styles["BodyText"], fontSize=8.5, leading=11)
    right = ParagraphStyle("po-right", parent=small, alignment=TA_RIGHT)
    story = [Paragraph("PURCHASE ORDER", title), Spacer(1, 8)]
    store = "<b>FROM</b><br/>" + "<br/>".join(filter(None, [payload.store_name, payload.store_address.replace("\n", "<br/>"), payload.store_phone, payload.store_contact]))
    vendor = "<b>VENDOR</b><br/>" + "<br/>".join(filter(None, [payload.vendor_name, f"License #: {payload.vendor_license}" if payload.vendor_license else "", payload.vendor_address.replace("\n", "<br/>"), payload.vendor_contact]))
    meta = "<b>PO DETAILS</b><br/>" + "<br/>".join(filter(None, [f"PO #: {payload.po_number}" if payload.po_number else "", f"Date: {payload.po_date}" if payload.po_date else "", f"Terms: {payload.terms}" if payload.terms else ""]))
    header = Table([[Paragraph(store, small), Paragraph(vendor, small), Paragraph(meta, right)]], colWidths=[2.55 * inch, 2.55 * inch, 2.0 * inch])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E6E6E6")), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [header, Spacer(1, 12)]

    table_data = [["SKU", "Description", "Strain", "Size", "Qty", "Price", "Line Total"]]
    subtotal = 0.0
    for item in payload.items:
        total = float(item.quantity) * float(item.price)
        subtotal += total
        table_data.append([item.sku, item.description, item.strain, item.size, f"{item.quantity:,.2f}".rstrip("0").rstrip("."), f"${item.price:,.2f}", f"${total:,.2f}"])
    lines = Table(table_data, repeatRows=1, colWidths=[0.72 * inch, 2.55 * inch, 0.9 * inch, 0.55 * inch, 0.55 * inch, 0.75 * inch, 0.9 * inch])
    lines.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A1A1A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.4), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7D7D7")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F8F8")]), ("ALIGN", (4, 1), (-1, -1), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)
    ]))
    story += [lines, Spacer(1, 10)]

    tax_amount = subtotal * (payload.tax_rate / 100.0)
    total = subtotal + tax_amount - payload.discount + payload.shipping
    totals = [["Subtotal", f"${subtotal:,.2f}"]]
    if payload.discount > 0: totals.append(["Discount", f"-${payload.discount:,.2f}"])
    if payload.tax_rate > 0: totals.append([f"Tax ({payload.tax_rate:g}%)", f"${tax_amount:,.2f}"])
    if payload.shipping > 0: totals.append(["Shipping / Fees", f"${payload.shipping:,.2f}"])
    totals.append(["TOTAL", f"${total:,.2f}"])
    total_table = Table(totals, colWidths=[1.55 * inch, 1.05 * inch], hAlign="RIGHT")
    total_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(total_table)
    if payload.fulfillment_notes:
        story += [Spacer(1, 12), Paragraph("<b>Fulfillment Notes</b>", small), Paragraph(payload.fulfillment_notes.replace("\n", "<br/>"), small)]
    doc.build(story)
    return buf.getvalue()


@router.post("/pdf")
def generate_pdf(payload: POPdfRequest):
    body = _pdf(payload)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", payload.po_number.strip() or "purchase-order")
    return Response(content=body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
