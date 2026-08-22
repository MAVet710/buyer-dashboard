from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
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
    total: float | None = Field(default=None, ge=0)


class POReviewRequest(BaseModel):
    items: list[POLine] = Field(default_factory=list, max_length=500)


class POPdfRequest(BaseModel):
    store_name: str = "Cannabis Store"
    store_address: str = ""
    store_phone: str = ""
    store_contact: str = ""
    store_number: str = ""
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
    detail, product, inv_normalized, sales_normalized, _inventory_source, _sales_source = _model(context, engine, target_doh, velocity_adjustment, sales_days)
    forecast = forecast_view(detail, product)
    reorder = forecast[forecast["reorderpriority"].astype(str).eq("1 – Reorder ASAP")] if not forecast.empty else forecast
    sku = sku_inventory_view(inv_normalized, sales_normalized, sku_window)
    group_keys = ["product_name", "packagesize"]
    agg: dict[str, Any] = {"onhandunits": "sum"}
    if "sku" in inv_normalized.columns: agg["sku"] = "first"
    xref = inv_normalized.groupby(group_keys, dropna=False).agg(agg).reset_index()
    if not sku.empty:
        xref = xref.merge(sku[[column for column in ["product_name", "days_of_supply", "status"] if column in sku.columns]], on="product_name", how="left")
    return detail, product, reorder, sku, xref


@router.get("/workspace")
def workspace(target_doh: int = Query(21, ge=1, le=120), velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0), sales_days: int = Query(60, ge=7, le=120), sku_window: int = Query(56, ge=7, le=120), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _detail, product, reorder, sku, _xref = _inventory_rows(context, engine, target_doh, velocity_adjustment, sales_days, sku_window)
    intelligence = buyer_intelligence(product)
    return {"controls":{"target_doh":target_doh,"velocity_adjustment":velocity_adjustment,"sales_days":sales_days,"sku_window":sku_window},"reorder_asap":records(reorder,limit=500),"inventory":records(sku,limit=3000),"smart_priorities":records(intelligence["purchase_priorities"],limit=100)}


@router.post("/review")
def review_lines(payload: POReviewRequest, target_doh: int = Query(21, ge=1, le=120), velocity_adjustment: float = Query(0.5, ge=0.01, le=5.0), sales_days: int = Query(60, ge=7, le=120), sku_window: int = Query(56, ge=7, le=120), context: RequestContext = Depends(get_request_context), engine: Engine = Depends(get_engine)):
    _detail, _product, _reorder, _sku, xref = _inventory_rows(context, engine, target_doh, velocity_adjustment, sales_days, sku_window)
    inventory = records(xref, limit=5000); result = []
    for item in payload.items:
        normalized_name = _norm(item.description)
        normalized_size = _size_norm(item.size)
        matched = [row for row in inventory if _norm(row.get("product_name")) == normalized_name]
        if item.size.strip():
            matched = [row for row in matched if _size_norm(row.get("packagesize")) == normalized_size]
        on_hand = int(sum(float(row.get("onhandunits") or 0) for row in matched))
        review = on_hand >= 15
        result.append({
            "sku": item.sku,
            "description": item.description,
            "requested_quantity": item.quantity,
            "matched_product": str(matched[0].get("product_name") or "") if matched else "",
            "matched_sku": str(matched[0].get("sku") or "") if matched else "",
            "matched_size": str(matched[0].get("packagesize") or "") if matched else "",
            "on_hand": on_hand,
            "days_of_supply": 0,
            "inventory_status": "",
            "match_score": 1.0 if matched else 0.0,
            "match_method": "Product name + size exact match" if matched and item.size.strip() else "Product name exact match" if matched else "No exact inventory match",
            "review": review,
            "review_reason": ">=15 on hand" if review else "",
        })
    return result


def _pdf(payload: POPdfRequest) -> bytes:
    buffer = BytesIO(); pdf = canvas.Canvas(buffer, pagesize=letter); width, height = letter
    left_margin = 0.7 * inch; right_margin = width - 0.7 * inch; top_margin = height - 0.75 * inch; y = top_margin
    pdf.setFont("Helvetica-Bold", 16); pdf.drawString(left_margin, y, "MAVet710 - Purchase Order"); y -= 0.25 * inch
    try: po_date = date.fromisoformat(payload.po_date).strftime("%m/%d/%Y")
    except ValueError: po_date = payload.po_date
    pdf.setFont("Helvetica", 10); pdf.drawString(left_margin, y, f"PO Number: {payload.po_number}"); pdf.drawRightString(right_margin, y, f"Date: {po_date}"); y -= 0.35 * inch
    pdf.setFont("Helvetica-Bold", 11); pdf.drawString(left_margin, y, "Ship To:"); pdf.setFont("Helvetica", 10); y -= 0.18 * inch
    pdf.drawString(left_margin, y, payload.store_name or ""); y -= 0.16 * inch
    for value, prefix in ((payload.store_number,"Store #: "),(payload.store_address,""),(payload.store_phone,"Phone: "),(payload.store_contact,"Buyer: ")):
        if value: pdf.drawString(left_margin, y, prefix + value); y -= 0.16 * inch
    vend_y = top_margin - 0.35 * inch; pdf.setFont("Helvetica-Bold", 11); pdf.drawString(width / 2, vend_y, "Vendor:"); vend_y -= 0.18 * inch; pdf.setFont("Helvetica", 10)
    for value, prefix in ((payload.vendor_name,""),(payload.vendor_license,"License #: "),(payload.vendor_address,""),(payload.vendor_contact,"Contact: ")):
        if value: pdf.drawString(width / 2, vend_y, prefix + value); vend_y -= 0.16 * inch
    y = min(y, vend_y) - 0.15 * inch
    if payload.terms: pdf.setFont("Helvetica-Bold",10); pdf.drawString(left_margin,y,"Payment Terms:"); pdf.setFont("Helvetica",10); pdf.drawString(left_margin+90,y,payload.terms); y -= 0.25*inch
    if payload.fulfillment_notes:
        pdf.setFont("Helvetica-Bold",10); pdf.drawString(left_margin,y,"Notes:"); y -= 0.16*inch; pdf.setFont("Helvetica",9); text=pdf.beginText(); text.setTextOrigin(left_margin,y); text.setLeading(12)
        for line in payload.fulfillment_notes.splitlines(): text.textLine(line)
        pdf.drawText(text); y=text.getY()-0.25*inch
    columns={"line":left_margin,"sku":left_margin+0.4*inch,"desc":left_margin+1.4*inch,"strain":left_margin+3.8*inch,"size":left_margin+4.6*inch,"qty":left_margin+5.2*inch,"unit":left_margin+6.0*inch,"total":left_margin+7.0*inch}
    def header(current_y: float) -> float:
        pdf.setFont("Helvetica-Bold",10); pdf.drawString(columns["line"],current_y,"Ln"); pdf.drawString(columns["sku"],current_y,"SKU"); pdf.drawString(columns["desc"],current_y,"Description"); pdf.drawString(columns["strain"],current_y,"Strain"); pdf.drawString(columns["size"],current_y,"Size"); pdf.drawRightString(columns["qty"]+0.3*inch,current_y,"Qty"); pdf.drawRightString(columns["unit"]+0.7*inch,current_y,"Unit Price"); pdf.drawRightString(columns["total"]+0.8*inch,current_y,"Line Total"); current_y-=0.2*inch; pdf.setLineWidth(0.5); pdf.line(left_margin,current_y,right_margin,current_y); return current_y-0.18*inch
    if y < 2.5*inch: pdf.showPage(); y=height-1*inch; pdf.setFont("Helvetica-Bold",16); pdf.drawString(left_margin,y,"MAVet710 - Purchase Order"); y-=0.4*inch
    y=header(y); pdf.setFont("Helvetica",9); subtotal=0.0
    for index,item in enumerate(payload.items):
        if y < 1.2*inch: pdf.showPage(); y=height-1*inch; pdf.setFont("Helvetica-Bold",10); pdf.drawString(left_margin,y,"SKU Line Items (cont.)"); y=header(y-0.25*inch); pdf.setFont("Helvetica",9)
        line_total=item.total if item.total is not None else item.quantity*item.price; subtotal+=line_total; pdf.drawString(columns["line"],y,str(index+1)); pdf.drawString(columns["sku"],y,item.sku[:10]); pdf.drawString(columns["desc"],y,item.description[:30]); pdf.drawString(columns["strain"],y,item.strain[:10]); pdf.drawString(columns["size"],y,item.size[:8]); pdf.drawRightString(columns["qty"]+0.3*inch,y,f"{int(item.quantity)}"); pdf.drawRightString(columns["unit"]+0.7*inch,y,f"${item.price:,.2f}"); pdf.drawRightString(columns["total"]+0.8*inch,y,f"${line_total:,.2f}"); y-=0.18*inch
    tax=subtotal*(payload.tax_rate/100); total=subtotal+tax-payload.discount+payload.shipping
    if y < 1.8*inch: pdf.showPage(); y=height-1.5*inch
    pdf.setFont("Helvetica-Bold",10); pdf.drawRightString(columns["total"]+0.8*inch,y,f"Subtotal: ${subtotal:,.2f}"); y-=0.2*inch
    for condition,label,value in ((payload.discount>0,"Discount: -",payload.discount),(tax>0,"Tax: ",tax),(payload.shipping>0,"Shipping / Fees: ",payload.shipping)):
        if condition: pdf.drawRightString(columns["total"]+0.8*inch,y,f"{label}${value:,.2f}"); y-=0.2*inch
    pdf.setFont("Helvetica-Bold",11); pdf.drawRightString(columns["total"]+0.8*inch,y,f"TOTAL: ${total:,.2f}"); pdf.showPage(); pdf.save(); body=buffer.getvalue(); buffer.close(); return body


@router.post("/pdf")
def generate_pdf(payload: POPdfRequest):
    body=_pdf(payload); name=re.sub(r"[^A-Za-z0-9._-]+","-",payload.po_number.strip() or "purchase-order"); return Response(content=body,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="PO_{name}_{datetime.now():%Y%m%d}.pdf"'})
