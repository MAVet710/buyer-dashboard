from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from io import BytesIO
import html
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch


LABEL_SIZES = {
    "3.5 × 1.25 in": (3.5, 1.25),
    "3 × 1 in": (3.0, 1.0),
    "4 × 2 in": (4.0, 2.0),
}


@dataclass(frozen=True)
class InventoryLabel:
    product_name: str
    external_package_id: str
    facility_name: str = ""
    organization_name: str = ""
    license_number: str = ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _license_number(state: MutableMapping[str, Any]) -> str:
    for key in ("active_facility_license_number", "facility_license_number", "license_number"):
        value = _clean(state.get(key))
        if value:
            return value
    profile = state.get("demo_company_profile")
    if isinstance(profile, dict):
        value = _clean(profile.get("license_number"))
        if value:
            return value
    try:
        from modules.inventory_receiving import resolve_traceability_credentials

        credentials = resolve_traceability_credentials(state)
        if credentials.configured and credentials.license_number:
            return _clean(credentials.license_number)
    except Exception:
        pass
    return ""


def build_label_records(
    state: MutableMapping[str, Any], rows: pd.DataFrame | list[dict[str, Any]]
) -> list[InventoryLabel]:
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows or [])
    if frame.empty:
        return []
    facility = _clean(state.get("active_facility_name"))
    organization = _clean(state.get("active_organization_name"))
    license_number = _license_number(state)
    package_column = "External Package ID" if "External Package ID" in frame.columns else "Package ID"
    if package_column not in frame.columns or "Product" not in frame.columns:
        return []

    labels: list[InventoryLabel] = []
    seen: set[str] = set()
    for _, row in frame.iterrows():
        package_id = _clean(row.get(package_column))
        product = _clean(row.get("Product"))
        if not package_id or not product:
            continue
        key = package_id.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(
            InventoryLabel(
                product_name=product,
                external_package_id=package_id,
                facility_name=facility,
                organization_name=organization,
                license_number=license_number,
            )
        )
    return labels


def _qr_drawing(value: str, size: float) -> Drawing:
    widget = QrCodeWidget(value)
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    scale = size / max(width, height)
    drawing = Drawing(size, size, transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    return drawing


def _qr_svg(value: str, pixels: int = 128) -> str:
    raw = renderSVG.drawToString(_qr_drawing(value, float(pixels)))
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def _wrap(value: str, max_chars: int) -> list[str]:
    words = _clean(value).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def build_label_pdf(
    labels: list[InventoryLabel], *, size_name: str = "3.5 × 1.25 in", copies: int = 1
) -> bytes:
    width_in, height_in = LABEL_SIZES.get(size_name, LABEL_SIZES["3.5 × 1.25 in"])
    width = width_in * inch
    height = height_in * inch
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height))
    margin = 0.10 * inch
    qr_size = min(height - 2 * margin, 0.92 * inch)
    text_width = width - qr_size - (3 * margin)

    for label in labels:
        for _ in range(max(1, int(copies))):
            y = height - margin
            header = label.facility_name or label.organization_name
            if header:
                pdf.setFont("Helvetica-Bold", 8.2)
                pdf.drawString(margin, y - 8, header[:50])
                y -= 11
            if label.license_number:
                pdf.setFont("Helvetica", 6.8)
                pdf.drawString(margin, y - 7, f"License #{label.license_number}"[:60])
                y -= 10

            pdf.setFont("Helvetica-Bold", 8.2)
            for line in _wrap(label.product_name, max(18, int(text_width / 4.8)))[:3]:
                pdf.drawString(margin, y - 8, line)
                y -= 10

            pdf.setFont("Courier-Bold", 7.6)
            package_lines = _wrap(label.external_package_id, max(18, int(text_width / 4.6)))
            for line in package_lines[:2]:
                pdf.drawString(margin, max(margin + 2, y - 8), line)
                y -= 9

            renderPDF.draw(
                _qr_drawing(label.external_package_id, qr_size),
                pdf,
                width - margin - qr_size,
                (height - qr_size) / 2,
            )
            pdf.showPage()
    pdf.save()
    return output.getvalue()


def build_print_html(
    labels: list[InventoryLabel], *, size_name: str = "3.5 × 1.25 in", copies: int = 1
) -> str:
    width, height = LABEL_SIZES.get(size_name, LABEL_SIZES["3.5 × 1.25 in"])
    blocks: list[str] = []
    for label in labels:
        for _ in range(max(1, int(copies))):
            header = label.facility_name or label.organization_name
            blocks.append(
                f"""
                <section class="label">
                  <div class="copy">
                    {f'<div class="facility">{html.escape(header)}</div>' if header else ''}
                    {f'<div class="license">License #{html.escape(label.license_number)}</div>' if label.license_number else ''}
                    <div class="product">{html.escape(label.product_name)}</div>
                    <div class="package">{html.escape(label.external_package_id)}</div>
                  </div>
                  <div class="qr">{_qr_svg(label.external_package_id, 132)}</div>
                </section>
                """
            )
    return f"""
    <!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size:{width}in {height}in; margin:0; }}
      body {{ margin:0; font-family:Arial,sans-serif; background:#111; color:#111; }}
      .toolbar {{ position:sticky;top:0;padding:8px;background:#111;text-align:right;z-index:2; }}
      button {{ background:#ff9a3c;border:0;border-radius:7px;padding:8px 12px;font-weight:700;cursor:pointer; }}
      .label {{ box-sizing:border-box;width:{width}in;height:{height}in;background:white;padding:.09in .1in;display:flex;align-items:center;gap:.08in;page-break-after:always;overflow:hidden; }}
      .copy {{ flex:1;min-width:0; }} .facility {{ font-weight:800;font-size:10px; }}
      .license {{ font-size:8px;margin-top:1px; }} .product {{ font-weight:800;font-size:10px;line-height:1.05;margin-top:4px; }}
      .package {{ font-family:monospace;font-weight:800;font-size:9px;line-height:1.05;margin-top:5px;word-break:break-all; }}
      .qr {{ width:.92in;height:.92in;display:flex;align-items:center;justify-content:center;flex:0 0 .92in; }} .qr svg {{ width:100%;height:100%; }}
      @media print {{ body {{ background:white; }} .toolbar {{ display:none; }} .label {{ margin:0; }} }}
    </style></head><body><div class="toolbar"><button onclick="window.print()">Print labels</button></div>{''.join(blocks)}</body></html>
    """


def open_inventory_label_dialog(
    state: MutableMapping[str, Any], rows: pd.DataFrame | list[dict[str, Any]]
) -> int:
    labels = build_label_records(state, rows)
    state["inventory_label_records"] = [label.__dict__ for label in labels]
    state["inventory_label_open"] = bool(labels)
    return len(labels)


def render_inventory_label_dialog(state: MutableMapping[str, Any]) -> None:
    if not state.get("inventory_label_open"):
        return
    labels = [InventoryLabel(**row) for row in state.get("inventory_label_records", []) if isinstance(row, dict)]
    if not labels:
        state["inventory_label_open"] = False
        return

    def body() -> None:
        top = st.columns([3, 1])
        with top[0]:
            st.caption("INVENTORY / LABELS")
            st.markdown("## Print inventory labels")
            st.caption("QR encodes the External Package ID. Contact information is intentionally omitted.")
        if top[1].button("Close", key="inventory_label_close"):
            state["inventory_label_open"] = False
            st.rerun()

        size_name = st.selectbox("Label size", list(LABEL_SIZES), key="inventory_label_size")
        copies = st.number_input("Copies per package", min_value=1, max_value=100, value=1, step=1, key="inventory_label_copies")
        st.caption(f"{len(labels)} package label(s) · {len(labels) * int(copies)} total print(s)")
        html_doc = build_print_html(labels, size_name=size_name, copies=int(copies))
        components.html(html_doc, height=250, scrolling=True)
        pdf = build_label_pdf(labels, size_name=size_name, copies=int(copies))
        st.download_button(
            "Download print-ready PDF",
            data=pdf,
            file_name="buyer_dash_inventory_labels.pdf",
            mime="application/pdf",
            width="stretch",
        )

    if hasattr(st, "dialog"):
        @st.dialog("Print inventory labels", width="large")
        def dialog() -> None:
            body()
        dialog()
    else:
        with st.container(border=True):
            body()
