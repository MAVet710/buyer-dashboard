from __future__ import annotations

from datetime import datetime
from io import BytesIO

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from reports.report_style import ACCENT_ORANGE, BACKGROUND_DARK, CARD_BG, TEXT_MUTED, TEXT_PRIMARY


def _chart_image(series: pd.Series, title: str, color: str = ACCENT_ORANGE) -> ImageReader | None:
    if not isinstance(series, pd.Series) or series.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.5, 2.2))
    ax.bar(series.index.astype(str), series.values, color=color)
    ax.set_title(title)
    ax.tick_params(axis="x", labelrotation=30)
    fig.tight_layout()
    bio = BytesIO()
    fig.savefig(bio, format="png", dpi=160)
    plt.close(fig)
    bio.seek(0)
    return ImageReader(bio)


def _build_competitor_intelligence_report_pdf(payload: dict) -> bytes:
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    w, h = letter

    snap = payload.get("competitor_snapshot_df")
    snap = snap if isinstance(snap, pd.DataFrame) else pd.DataFrame()
    price = payload.get("price_summary")
    price = price if isinstance(price, pd.DataFrame) else pd.DataFrame()
    assort = payload.get("assortment_summary")
    assort = assort if isinstance(assort, pd.DataFrame) else pd.DataFrame()
    promo = payload.get("promo_summary")
    promo = promo if isinstance(promo, pd.DataFrame) else pd.DataFrame()

    def header(title: str, dark: bool = False):
        c.setFillColor(colors.HexColor(BACKGROUND_DARK if dark else "#ffffff"))
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(ACCENT_ORANGE)); c.rect(28, h - 72, w - 56, 5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(TEXT_PRIMARY if dark else "#111111")); c.setFont("Helvetica-Bold", 20); c.drawString(28, h - 58, title)
        c.setFillColor(colors.HexColor(TEXT_MUTED if dark else "#666666")); c.setFont("Helvetica", 9); c.drawRightString(w - 30, 20, f"Page {c.getPageNumber()}")

    # Cover
    header("Competitor Intelligence Executive Report", dark=True)
    c.setFillColor(colors.HexColor(CARD_BG)); c.rect(28, h - 300, w - 56, 210, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica", 11)
    c.drawString(40, h - 120, f"Snapshot Date: {payload.get('snapshot_metadata', {}).get('snapshot_date', 'Data unavailable')}")
    c.drawString(40, h - 140, f"Competitors Included: {snap['competitor_name'].nunique() if 'competitor_name' in snap.columns and not snap.empty else 0}")
    c.drawString(40, h - 160, f"Categories Captured: {snap['category'].nunique() if 'category' in snap.columns and not snap.empty else 0}")
    c.drawString(40, h - 180, f"Products Captured: {len(snap)}")
    c.drawString(40, h - 210, "Market Read: Promo and assortment pressures summarized in the following sections.")

    # KPI
    c.showPage(); header("KPI Overview")
    c.setFont("Helvetica", 10)
    kpi = [
        f"Competitors detected: {snap['competitor_name'].nunique() if 'competitor_name' in snap.columns and not snap.empty else 0}",
        f"Products captured: {len(snap)}",
        f"Average effective price: {round(pd.to_numeric(snap['effective_price'], errors='coerce').mean(),2) if 'effective_price' in snap.columns and not snap.empty else 'Data unavailable'}",
        f"Promo count: {int((pd.to_numeric(snap['discount_pct'], errors='coerce')>0).sum()) if 'discount_pct' in snap.columns and not snap.empty else 0}",
    ]
    y= h-100
    for line in kpi: c.drawString(30,y,line); y-=18

    # Price Intelligence
    c.showPage(); header("Price Intelligence")
    if not price.empty and 'category' in price.columns and 'avg_effective_price' in price.columns:
        s = price.groupby('category')['avg_effective_price'].mean().sort_values(ascending=False).head(8)
        img = _chart_image(s, "Average Effective Price by Category")
        if img: c.drawImage(img, 30, h-300, width=w-60, height=170, preserveAspectRatio=True)
    c.drawString(30, h-320, "Category price summary included in appendix.")

    c.showPage(); header("Assortment Intelligence")
    if not assort.empty and 'category' in assort.columns and 'rows_saved' in assort.columns:
        s = assort.groupby('category')['rows_saved'].sum().sort_values(ascending=False).head(8)
        img = _chart_image(s, "SKU Count by Category")
        if img: c.drawImage(img, 30, h-300, width=w-60, height=170, preserveAspectRatio=True)

    c.showPage(); header("Promo Pressure")
    if not promo.empty and 'category' in promo.columns and 'promo_count' in promo.columns:
        s = promo.groupby('category')['promo_count'].sum().sort_values(ascending=False).head(8)
        img = _chart_image(s, "Promo Count by Category")
        if img: c.drawImage(img, 30, h-300, width=w-60, height=170, preserveAspectRatio=True)

    c.showPage(); header("Strategic Recommendations")
    recs = payload.get("recommendations", [])
    y = h-90
    for rec in (recs or ["Data unavailable"]):
        c.drawString(30, y, f"• {str(rec)[:110]}"); y -= 18

    c.showPage(); header("Data Quality Notes")
    dq = payload.get("data_quality", {}) or {}
    y = h-90
    for line in [f"Files processed: {dq.get('files_processed', 'Data unavailable')}", f"Rows needing review: {dq.get('rows_needing_review', 'Data unavailable')}", f"Missing price rows: {dq.get('missing_price_count', 'Data unavailable')}"]:
        c.drawString(30, y, line); y -= 18

    c.showPage(); header("Appendix A — Parsed Product Sample")
    if not snap.empty:
        txt = snap.head(15).to_string(index=False)[:3400]
        t = c.beginText(30, h-90)
        t.setFont("Helvetica", 7)
        for ln in txt.split("\n"):
            t.textLine(ln[:130])
        c.drawText(t)

    c.showPage(); header("Appendix B — Category Summary")
    if not assort.empty:
        t = c.beginText(30, h-90); t.setFont("Helvetica", 8)
        for ln in assort.head(24).to_string(index=False).split("\n"):
            t.textLine(ln[:120])
        c.drawText(t)

    c.showPage(); header("Appendix C — File Processing Results")
    fr = pd.DataFrame(payload.get("file_processing_results", []))
    if not fr.empty:
        t = c.beginText(30, h-90); t.setFont("Helvetica", 8)
        for ln in fr.head(24).to_string(index=False).split("\n"):
            t.textLine(ln[:120])
        c.drawText(t)

    c.save(); out.seek(0); return out.read()
