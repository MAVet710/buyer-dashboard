import streamlit as st
import pandas as pd
import numpy as np
import re
import json
import os
import sys
import importlib
import hashlib
import requests
from collections.abc import Mapping
from typing import Any
from datetime import datetime, timedelta
from io import BytesIO
from dotenv import load_dotenv

from compliance_engine import ComplianceRepository, ComplianceSource, format_compliance_answer
from extraction_partner_upload_upgrade import render_extraction_partner_upload_ui
from services.license_client import validate_license_key
from services.doobie_client import DoobieClient
from services.doobie_config import (
    clear_session_doobie_config,
    get_default_doobie_config,
    mask_api_key,
    resolve_doobie_config,
    test_doobie_connection,
)
from services.metrc_client import get_default_metrc_integrator_key, test_metrc_connection
from services.license_session import (
    build_cached_license_session,
    clear_local_license_session,
    get_license_features,
    is_license_recheck_needed,
    license_in_grace_period,
    load_local_license_session,
    save_local_license_session,
)
from ui_polish import (
    load_polished_theme,
    render_section_header,
    render_metric_tiles,
    chart_card_start,
    chart_card_end,
    render_hero,
    render_ai_brief,
    render_sidebar_nav_css,
    render_action_button,
    render_extraction_kpi,
    render_inventory_table_css,
)
from ui_premium import load_premium_shell, render_commandbar, render_sidebar_identity
from user_integrations_store import UserIntegrationsStore
from global_integrations_store import GlobalIntegrationsStore
from services import app_user_store as app_user_store_module
from services.auth_identity import resolve_legacy_identity
from services.auth_workflow import (
    apply_authenticated_session,
    authenticate_any_role,
    clear_authenticated_session,
)
from services.workspace_navigation import (
    AI_INTEGRATIONS_SECTION,
    COMAN_WORKSPACE,
    COMMERCIAL_OPS,
    COMMERCIAL_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
    EXTRACTION_WORKSPACE,
    INVENTORY_COUNTS_SECTION,
    METRC_INTEGRATIONS_SECTION,
    PRODUCTION_OPS,
    RETAIL_OPS,
    WHITE_LABEL_WORKSPACE,
    buyer_section_options,
    can_manage_ai_integrations,
    workspace_options as build_workspace_options,
)
from modules.commercial.ui import render_commercial_workspace
from modules.coman.ui import render_coman_workspace
from modules.data_hub import render_data_hub_workspace
from modules.extraction_quick_entry import (
    build_quick_run_record,
    quick_stage_weight_updates,
    stage_completion_flags,
)
from modules.nomenclature_ui import render_nomenclature_mapper
from modules.inventory_audit.ui import render_inventory_audit_workspace

load_dotenv()

# Streamlit can hot-reload app.py while retaining already-imported service
# modules in the same Python process.  Reload the user store only when the UI
# expects a newer account-management API than the in-memory class provides.
if not hasattr(app_user_store_module.AppUserStore, "update_user"):
    importlib.invalidate_caches()
    app_user_store_module = importlib.reload(app_user_store_module)
AppUserStore = app_user_store_module.AppUserStore

USER_INTEGRATIONS_STORE = UserIntegrationsStore()
GLOBAL_INTEGRATIONS_STORE = GlobalIntegrationsStore()
APP_USER_STORE = AppUserStore()

# Owner mark (non-functional, intentional signature fragment).
# __  ______             __ ____________

# For PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import matplotlib.pyplot as plt

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR PLOTLY
# ------------------------------------------------------------
try:
    import plotly.express as px  # noqa: F401
    import plotly.graph_objects as go  # noqa: F401
    PLOTLY_AVAILABLE = True
except Exception:
    PLOTLY_AVAILABLE = False

# ------------------------------------------------------------
# DOOBIE AI STATUS (single AI backend)
# ------------------------------------------------------------
DOOBIE_PROVIDER_NAME = "DoobieLogic"
# Credential terminology:
# DOOBIE_SERVICE_API_KEY = admin-managed service key for app->Doobie runtime calls.
# DOOBIE_LICENSE_KEY = user/customer entitlement key.
# DOOBIE_ADMIN_API_KEY = Doobie internal admin tooling key (not used in Buyer Dashboard user flow).
# METRC_API_KEY = admin-managed METRC integration key.

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR BCRYPT (PASSWORD HASHING)
# ------------------------------------------------------------
try:
    import bcrypt as _bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    _bcrypt = None  # type: ignore
    BCRYPT_AVAILABLE = False

# ------------------------------------------------------------
# OPTIONAL / SAFE IMPORT FOR DUTCHIE LIVE CLIENT
# ------------------------------------------------------------
try:
    from dutchie_client import DutchieConfig, fetch_dutchie_data
    _DUTCHIE_CLIENT_AVAILABLE = True
except (ImportError, AttributeError):
    _DUTCHIE_CLIENT_AVAILABLE = False

# ------------------------------------------------------------
# EXTRACTION PARTNER INTEL MODULES
# ------------------------------------------------------------
try:
    from extraction_partner_import import (
        load_partner_file,
        map_partner_runs_to_ecc_shape,
        looks_like_partner_extraction_file,
    )
    from extraction_partner_intel import build_extraction_weekly_summary
    _EXTRACTION_PARTNER_INTEL_AVAILABLE = True
except (ImportError, AttributeError):
    _EXTRACTION_PARTNER_INTEL_AVAILABLE = False

if not _EXTRACTION_PARTNER_INTEL_AVAILABLE:
    def _partner_norm_col(name: str) -> str:
        return (
            str(name)
            .strip()
            .lower()
            .replace("/", " ")
            .replace("-", " ")
            .replace(".", " ")
            .replace("(", " ")
            .replace(")", " ")
        )


    def load_partner_file(uploaded_file) -> pd.DataFrame:
        raw = uploaded_file.getvalue()
        file_name = str(getattr(uploaded_file, "name", "")).lower()
        if file_name.endswith((".xlsx", ".xls")):
            return pd.read_excel(BytesIO(raw))
        return pd.read_csv(BytesIO(raw))


    def looks_like_partner_extraction_file(uploaded_file) -> bool:
        try:
            df = load_partner_file(uploaded_file)
        except Exception:
            return False
        cols = {_partner_norm_col(c) for c in df.columns}
        required = {
            "run_date",
            "run date",
            "input_weight_g",
            "input weight g",
            "finished_output_g",
            "finished output g",
        }
        return len(cols.intersection(required)) >= 3


    def _partner_pick(df: pd.DataFrame, aliases: list[str], default=None):
        col_map = {_partner_norm_col(c): c for c in df.columns}
        for alias in aliases:
            norm_alias = _partner_norm_col(alias)
            if norm_alias in col_map:
                return df[col_map[norm_alias]]
        return default


    def map_partner_runs_to_ecc_shape(df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame()
        out["run_date"] = pd.to_datetime(_partner_pick(df, ["run_date", "run date", "date"]), errors="coerce").dt.date.astype(str)
        out["state"] = _partner_pick(df, ["state"], default="Other")
        out["license_name"] = _partner_pick(df, ["license_name", "facility", "facility_name"], default="")
        out["client_name"] = _partner_pick(df, ["client_name", "client", "partner"], default="In House")
        out["batch_id_internal"] = _partner_pick(df, ["batch_id_internal", "batch_id", "batch", "run_id"], default="")
        out["metrc_package_id_input"] = _partner_pick(df, ["metrc_package_id_input", "input_package_id"], default="")
        out["metrc_package_id_output"] = _partner_pick(df, ["metrc_package_id_output", "output_package_id"], default="")
        out["metrc_manifest_or_transfer_id"] = _partner_pick(df, ["metrc_manifest_or_transfer_id", "transfer_id"], default="")
        out["method"] = _partner_pick(df, ["method", "extraction_method"], default="BHO")
        out["product_type"] = _partner_pick(df, ["product_type", "output_type"], default="Other")
        out["downstream_product"] = _partner_pick(df, ["downstream_product", "downstream"], default="N/A")
        out["process_stage"] = _partner_pick(df, ["process_stage", "stage"], default="Intake")
        out["input_material_type"] = _partner_pick(df, ["input_material_type", "input_type"], default="Other")
        out["input_weight_g"] = pd.to_numeric(_partner_pick(df, ["input_weight_g", "input_weight", "input_g"], default=0), errors="coerce").fillna(0)
        out["intermediate_output_g"] = pd.to_numeric(_partner_pick(df, ["intermediate_output_g", "intermediate_g"], default=0), errors="coerce").fillna(0)
        out["finished_output_g"] = pd.to_numeric(_partner_pick(df, ["finished_output_g", "finished_output", "output_g"], default=0), errors="coerce").fillna(0)
        out["residual_loss_g"] = pd.to_numeric(_partner_pick(df, ["residual_loss_g", "residual_g", "waste_g"], default=0), errors="coerce").fillna(0)
        out["yield_pct"] = pd.to_numeric(_partner_pick(df, ["yield_pct", "yield"], default=0), errors="coerce").fillna(0)
        out["post_process_efficiency_pct"] = pd.to_numeric(_partner_pick(df, ["post_process_efficiency_pct", "post_efficiency_pct"], default=0), errors="coerce").fillna(0)
        out["operator"] = _partner_pick(df, ["operator"], default="")
        out["machine_line"] = _partner_pick(df, ["machine_line", "line"], default="")
        out["status"] = _partner_pick(df, ["status"], default="Processing")
        out["toll_processing"] = pd.Series(_partner_pick(df, ["toll_processing", "is_toll"], default=False)).astype(bool)
        out["processing_fee_usd"] = pd.to_numeric(_partner_pick(df, ["processing_fee_usd", "processing_fee"], default=0), errors="coerce").fillna(0)
        out["est_revenue_usd"] = pd.to_numeric(_partner_pick(df, ["est_revenue_usd", "estimated_revenue_usd", "revenue_usd"], default=0), errors="coerce").fillna(0)
        out["estimated_revenue_usd"] = out["est_revenue_usd"]
        out["cogs_usd"] = pd.to_numeric(_partner_pick(df, ["cogs_usd", "total_cogs_usd", "cogs"], default=0), errors="coerce").fillna(0)
        out["total_cogs_usd"] = out["cogs_usd"]
        out["raw_material_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["raw_material_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["processing_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["processing_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["packaging_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["packaging_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["labor_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["labor_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["overhead_cogs_usd"] = pd.to_numeric(_partner_pick(df, ["overhead_cogs_usd"], default=0), errors="coerce").fillna(0)
        out["unit_size_g"] = pd.to_numeric(_partner_pick(df, ["unit_size_g"], default=0), errors="coerce").fillna(0)
        out["unit_price_usd"] = pd.to_numeric(_partner_pick(df, ["unit_price_usd"], default=0), errors="coerce").fillna(0)
        out["packaging_yield_loss_g"] = pd.to_numeric(_partner_pick(df, ["packaging_yield_loss_g"], default=0), errors="coerce").fillna(0)
        out["coa_status"] = _partner_pick(df, ["coa_status"], default="Pending")
        out["qa_hold"] = pd.Series(_partner_pick(df, ["qa_hold"], default=False)).astype(bool)
        out["notes"] = _partner_pick(df, ["notes"], default="")
        return out


    def build_extraction_weekly_summary(run_df: pd.DataFrame) -> pd.DataFrame:
        if run_df is None or run_df.empty:
            return pd.DataFrame()
        df = run_df.copy()
        dt = pd.to_datetime(df.get("run_date"), errors="coerce")
        df["week_start"] = (dt.dt.normalize() - pd.to_timedelta(dt.dt.weekday, unit="D")).dt.date.astype(str)
        df["finished_output_g"] = pd.to_numeric(df.get("finished_output_g", 0), errors="coerce").fillna(0)
        df["yield_pct"] = pd.to_numeric(df.get("yield_pct", 0), errors="coerce").fillna(0)
        df["est_revenue_usd"] = pd.to_numeric(df.get("estimated_revenue_usd", df.get("est_revenue_usd", 0)), errors="coerce").fillna(0)
        df["cogs_usd"] = pd.to_numeric(df.get("total_cogs_usd", df.get("cogs_usd", 0)), errors="coerce").fillna(0)
        df["qa_hold"] = pd.Series(df.get("qa_hold", False)).astype(bool)
        weekly = (
            df.groupby("week_start", dropna=True)
            .agg(
                extraction_runs=("batch_id_internal", "count"),
                finished_output_g=("finished_output_g", "sum"),
                avg_yield_pct=("yield_pct", "mean"),
                est_revenue_usd=("est_revenue_usd", "sum"),
                cogs_usd=("cogs_usd", "sum"),
                qa_hold_runs=("qa_hold", "sum"),
            )
            .reset_index()
            .sort_values("week_start", ascending=False)
        )
        weekly["gross_margin_pct"] = weekly.apply(
            lambda r: ((r["est_revenue_usd"] - r["cogs_usd"]) / r["est_revenue_usd"] * 100) if r["est_revenue_usd"] else 0.0,
            axis=1,
        )
        return weekly

# ------------------------------------------------------------
# DELIVERY IMPACT MODULE
# ------------------------------------------------------------
try:
    from delivery_impact import (
        parse_manifest_pdf_bytes,
        parse_manifest_csv_xlsx_bytes,
        parse_sales_report_bytes as _parse_sales_report_bytes,
        normalize_sales_report_dataframe as _normalize_sales_report_dataframe,
        match_manifest_to_sales,
        compute_delivery_kpis,
        compute_weekday_wow_kpis,
        build_time_series,
        build_wow_time_series,
        DELIVERY_WINDOW_DAYS,
    )
    _DELIVERY_IMPACT_AVAILABLE = True
except (ImportError, AttributeError, SyntaxError) as _di_import_err:
    _DELIVERY_IMPACT_AVAILABLE = False
    print(
        f"[buyer-dashboard] WARNING: delivery_impact could not be imported: "
        f"{type(_di_import_err).__name__}: {_di_import_err}",
        file=sys.stderr,
    )


def hash_password(plain: str) -> str:
    """Hash a plaintext password witЫn;пkh‘йм¶»§q«^uCB€Y€Щ]Z[Ь›ЩXЭШШXЪY\И›Э›Ы™H[™›ЭЩ]Z[Ь›ЩXЭШШXЪY™[\NѓB€ћNѓB€Щ™Y€HЩ]Z[Ь›ЩXЭШШXЪYЦИњЭXШ]YЫЬћH‹њ›ЩXЭЫ[YH‹њЭZ[—Э\H‹њXЪШYЩ\Ъ^™H‹ќ[љ]ЬЫЫ—WKЫЬJ
CB€Щ™Y–Иќ[љ]ЬЫЫ—HHќЧЫќ[Y\љXКЩ™Y–Иќ[љ]ЬЫЫ—K\њ›ЬњПHЫЩ\ЩHЉK™љ[J
CB€ЩЭЬH
B€Щ™Y‹њЫЬќЭ[Y\Кќ[љ]ЬЫЫ‹\ШЩ[™[™ПQ[ЩJCB€™Ь›Э\ћJИњЭXШ]YЫЬћH‹њЭZ[—Э\H‹њXЪШYЩ\Ъ^™H—K›ЬOQ[ЩKЫЬќQ[ЩJVИњ›ЩXЭЫ[YH—CB€\J[X™H€‹‹љ›Ъ[Љ\Э\JЭЉKљXY
JKќЫ\Э

JJCB€њ™\Щ]Ъ[™^

CB€њ™[[YJЫЫ[[њП^Ињ›ЩXЭЫ[YHЋ€ќЬЬ›ЩXЭИџJCB€
CB€™[Ь™\—Ь›ЭЬИH™[Ь™\—Ь›ЭЬЛ›Y\™ЩJЩЭЬЫЏVИњЭXШ]YЫЬћH‹њЭZ[—Э\H‹њXЪШYЩ\Ъ^™H—KЭПH›YќЉCB€™[Ь™\—Ь›ЭЬЦИќЬЬ›ЩXЭИ—HH™[Ь™\—Ь›ЭЬЦИќЬЬ›ЩXЭИ—K™љ[J€ЉCB€^Щ\^Щ\[ЫЋѓB€Y€ќЬЬ›ЩXЭИ€›Э[€™[Ь™\—Ь›ЭЬЛЫЫ[[њОѓB€™[Ь™\—Ь›ЭЬЦИќЬЬ›ЩXЭИ—HH€ѓBѓB€Ъ]Э™^[™\Љј'дв€™[Ь™\€Ь›ЬЬЛT™Y™\™[ЩH
њ›ЫH[ќ™[ќЬћH\Ъ›Ш\™
H‹^[™YUќYJNѓB€Y€™[Ь™\—Ь›ЭЬЛ™[\NѓB€ЭњЭXШЩ\ЬКё§!H›И][\И›YЩЩY	Ф™[Ь™\€TРT	И[€HЭ\њ™[ќ\Ъ›Ш\™љY]Л€ЉCB€[ЩNѓB€Ъ\ЧЬљXЩHHќ[љ]ШЫЬЭ€[€™[Ь™\—Ь›ЭЬЛЫЫ[[њИ[™™[Ь™\—Ь›ЭЬЦИќ[љ]ШЫЬЭ—K™Э

K[ћJ
CB€ЭШ\[ЫЉB€€ЉЉћЫ[Љ™[Ь™\—Ь›ЭЬК_H[™JКJЉ€›YЩЩY\И
”™[Ь™\€TРT
€њ›ЫH[Э\€\Э[ќ™[ќЬћH\Ъ›Ш\™ШY€ѓB€•\ЩHHќ]Ы€™[ЭИИќ[ЛXY[HИHЛЬ€™]љY]И[™]љYX[›ЭЬИљ\њЭ€ѓB€
И
B€€<'д¬€
ЉђЭ\њ™[ќљXЩJЉ€H[ќ™[ќЬћH	РЭ\њ™[ќљXЩIИ0нИ€
ЪЫ\Ш[HYќ\ЭY[ќ
K€ѓB€Y€Ъ\ЧЬљXЩH[ЩH€ѓB€
CB€
CB€Ю™Y—ШЫЫИHИњЭXШ]YЫЬћH‹њЭZ[—Э\H‹њXЪШYЩ\Ъ^™H‹›Ыљ[™[љ]И‹]™Э[љ]Ь\™^H‹™^\ЫЫљ[™‹њ™[Ь™\њ]H—CB€Y€Ъ\ЧЬљXЩNѓB€™[Ь™\—Ь›ЭЬИH™[Ь™\—Ь›ЭЬЛЫЬJ
CB€™[Ь™\—Ь›ЭЬЦИђЭ\њ™[ќљXЩH—HH
B€ќЧЫќ[Y\љXК™[Ь™\—Ь›ЭЬЦИќ[љ]ШЫЬЭ—K\њ›ЬњПHЫЩ\ЩHЉK™љ[J
HИѓB€
Kњ›Э[™
ЉCB€Ю™Y—ШЫЫЛ\[™
ђЭ\њ™[ќљXЩHЉCB€Y€ќЬЬ›ЩXЭИ€[€™[Ь™\—Ь›ЭЬЛЫЫ[[њОѓB€Ю™Y—ШЫЫЛ\[™
ќЬЬ›ЩXЭИЉCB€Ю™Y—ШЫЫИHШИ›Ь€И[€Ю™Y—ШЫЫИY€И[€™[Ь™\—Ь›ЭЬЛЫЫ[[њЧCB€Э™]Yњ[YJ™[Ь™\—Ь›ЭЬЦЧЮ™Y—ШЫЫЧKњ™\Щ]Ъ[™^
›ЬUќYJKЪYHњЭ™]ЪЉCBѓB€Y€Эќ]ЫЉё§ҐHY[™[Ь™\€TРT[™\ИИИ‹Щ^OHњЧЮ™Y—ШYШ[ЉNѓB€ШYYHB€›Ь€ЛЬ€[€™[Ь™\—Ь›ЭЬЛљ]\њ›ЭЬК
NѓB€ШШ]HЭЉЬ‹™Щ]
њЭXШ]YЫЬћH‹€ЉJCB€ЬЭZ[€HЭЉЬ‹™Щ]
њЭZ[—Э\H‹€ЉJCB€ЬЪ^™HHЭЉЬ‹™Щ]
њXЪШYЩ\Ъ^™H‹€ЉJCB€Щ\ШИH€‹љ›Ъ[Љљ[\Љ›Ы™KЧШШ]ЬЭZ[‹ЬЪ^™WJJCB€ЭЬЬ]ИHЭЉЬ‹™Щ]
ќЬЬ›ЩXЭИ‹€ЉJKњЭљ\

CB€ЭЬHЭЬЬ]ЛњЬ]
‹ЉVМKњЭљ\

HY€ЭЬЬ]И[ЩHЩ\ШГB€ћNѓB€Ь]HH[ќ
Ь‹™Щ]
њ™[Ь™\њ]H‹
JCB€Ь]HHЬ]HY€Ь]H€[ЩHCB€^Щ\
[YQ\њ›Ь‹\Q\њ›ЬЉNѓB€Ь]HHCB€ћNѓB€Ь]ЧШЫЬЭHќЧЫќ[Y\љXКЬ‹™Щ]
ќ[љ]ШЫЬЭ‹
K\њ›ЬњПHЫЩ\ЩHЉCB€ЬљXЩHH›Ш]
Ь]ЧШЫЬЭ
HИ€Y€››ЭJЬ]ЧШЫЬЭ
H[ЩHЊB€^Щ\
[YQ\њ›Ь‹\Q\њ›ЬЉNѓB€ЬљXЩHHЊB€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\Л\[™
ГB€”ТХHЋ€€‹B€‘\ШЬљ\[Ы€Ћ€ЭЬY€ЭЬ[ЩHЩ\ШЛB€”ЭZ[€Ћ€ЬЭZ[‹B€”Ъ^™HЋ€ЬЪ^™KB€”]X[ќ]HЋ€Ь]KB€”љXЩHЋ€›Э[™
ЬљXЩKЉKB€•Э[Ћ€ЊB€JCB€ШYY
ПHCB€ЭњЭXШЩ\ЬК€ђYYЧШYYH][JКHИHЛ€љ[[€љXЩ\И™[ЭЛ€ЉCB€ЬШY™WЬ™\ќ[Љ
CB€[ЩNѓB€Эљ[™›КB€ј'дЁHЫИИ
Љј'дв€[ќ™[ќЬћH\Ъ›Ш\™
Љ€[™\ШY[Э\€љ[\Иљ\њЭ8 %ѓB€”™[Ь™\€TРT][\ИЪ[[€\X\€\™H›Ь€]ZXЪИИЬ™X][Ы‹€ѓB€
CBѓB€Э›X\љЩЭЫЉ‹KKHЉCB€B€И[љ]X[^™HЩ\ЬЪ[Ы€Э]H›Ь€ГB€Y€	ЬЧЪ][\ЙИ›Э[€ЭњЩ\ЬЪ[Ы—ЬЭ]NѓB€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\ИHЧCB€B€ИЭЬ™H[™™[™Ь€[™›Ь›X][ЫѓB€Э›X\љЩЭЫЉ€ИИИ<'двИЬ™\€[™›Ь›X][Ы€ЉCB€ЫЫKЫЫ‹ЫЫИHЭЫЫ[[њККCB€B€Ъ]ЫЫNѓB€ЭЬ™WЫ[YHHЭќ^Ъ[њ]
”ЭЬ™H[YH‹[YOHђШ[›Xљ\ИЭЬ™HЉCB€ЭЬ™WШY™\ЬИHЭќ^Ш\™XJ”ЭЬ™HY™\ЬИ‹[YOHЊLЊИXZ[€ЭђЪ]KЭ]HLЊНH‹ZYЪLL
CB€B€Ъ]ЫЫЋѓB€™[™Ь—Ы[YHHЭќ^Ъ[њ]
•™[™Ь€[YH‹[YOH€ЉCB€™[™Ь—ШY™\ЬИHЭќ^Ш\™XJ•™[™Ь€Y™\ЬИ‹[YOH€‹ZYЪLL
CB€B€Ъ]ЫЫОѓB€ЧЫќ[X™\€HЭќ^Ъ[њ]
”Иќ[X™\€‹[YOY€”Л^Щ]][YK››ЭК
KњЭ™ќ[YJ	ЙVI[IY	К_HЉCB€ЧЩ]HHЭ™]WЪ[њ]
”И]H‹[YOY]][YK››ЭК
K™]J
JCB€B€И[™H][\ГB€Э›X\љЩЭЫЉ€ИИИ<'дй€[™H][\ИЉCB€B€Ъ]Э™›Ь›JYЪ][WЩ›Ь›HЉNѓB€ЫЫKЫЫ‹ЫЫЛЫЫЫЫKЫЫ€HЭЫЫ[[њКМ‹Л‹‹KWJCB€B€Ъ]ЫЫNѓB€ЪЭHHЭќ^Ъ[њ]
”ТХHЉCB€Ъ]ЫЫЋѓB€\ШЬљ\[Ы€HЭќ^Ъ[њ]
‘\ШЬљ\[Ы€ЉCB€Ъ]ЫЫОѓB€ЭZ[€HЭќ^Ъ[њ]
”ЭZ[€ЉCB€Ъ]ЫЫѓB€Ъ^™HHЭќ^Ъ[њ]
”Ъ^™HЉCB€Ъ]ЫЫNѓB€]X[ќ]HHЭ›ќ[X™\—Ъ[њ]
”]H‹Z[—Э[YOLK[YOLJCB€Ъ]ЫЫЋѓB€љXЩHHЭ›ќ[X™\—Ъ[њ]
”љXЩH‹Z[—Э[YOLЊ[YOLЊЭ\LЊJCB€B€ЭX›Z]YHЭ™›Ь›WЬЭX›Z]Шќ]ЫЉё§ҐHY][HЉCB€Y€ЭX›Z]Y[™\ШЬљ\[ЫЋѓB€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\Л\[™
ГB€	ФТХIО€ЪЭKB€	С\ШЬљ\[Ы‰О€\ШЬљ\[Ы‹B€	ФЭZ[‰О€ЭZ[‹B€	ФЪ^™IО€Ъ^™KB€	Ф]X[ќ]IО€]X[ќ]KB€	ФљXЩIО€љXЩKB€	ХЭ[	О€]X[ќ]H
€љXЩCB€JCB€ЬШY™WЬ™\ќ[Љ
CB€B€И\Ь^HЭ\њ™[ќ][\ГB€Y€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\ОѓB€Э›X\љЩЭЫЉ€ИИИИЭ\њ™[ќ][\ИЉCB€][\ЧЩ€H‘]Qњ[YJЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\КCBѓB€ИKKKH[ќ™[ќЬћHЬ›ЬЬЛ\™Y™\™[ЩHKKKCB€Ъ[ќ—Ю™Y€HШќZ[Ъ[ќ—Ю™Y—ЭX›J
CB€Y€Ъ[ќ—Ю™Y€\И›Ы™NѓB€ЭШ\[ЫЉB€ј'дЁH\ШY[ќ™[ќЬћHЫ€[ќ™[ќЬћH\Ъ›Ш\™И[X›HИ[ќ™[ќЬћHЬ›ЬЬЛXЪXЪЛ€ѓB€
CBѓB€Ы—Ъ[™Ы\ЭHЧCB€™]љY]ЧЫ\ЭHЧCB€™]љY]ЧЬ™X\ЫЫ—Ы\ЭHЧCB€›Ь€Ъ][H[€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\ОѓB€ЫЫ—Ъ[™HB€Y€Ъ[ќ—Ю™Y€\И›Э›Ы™NѓB€Ы›Ь›WЩ\ШИHЫ›Ь›X[^™WЩ›Ь—ЫX]Ъ
Ъ][K™Щ]
‘\ШЬљ\[Ы€‹€ЉJCB€ЬЧЬЪ^™WЬ]ИHЭЉЪ][K™Щ]
”Ъ^™H‹€ЉJKњЭљ\

CB€ЬЪ^™WЬ™\Щ[ќH›ЫЫ
ЬЧЬЪ^™WЬ]КCB€Ы›Ь›WЬЪ^™HHЫ›Ь›X[^™WЬЪ^™WЩ›Ь—ЫX]Ъ
ЬЧЬЪ^™WЬ]КCB€ЫX]Ъ\ИHЪ[ќ—Ю™Y–ЧЪ[ќ—Ю™Y–И››Ь›WЫ[YH—HOHЫ›Ь›WЩ\ШЧCB€Y€ЬЪ^™WЬ™\Щ[ќѓB€ЫX]Ъ\ИHЫX]Ъ\ЦЧЫX]Ъ\ЦИ››Ь›WЬЪ^™H—HOHЫ›Ь›WЬЪ^™WCB€ЫЫ—Ъ[™H[ќ
ЫX]Ъ\ЦИ›Ыљ[™ЭЭ[—KњЭ[J
JCB€Ы—Ъ[™Ы\Э\[™
ЫЫ—Ъ[™
CB€Ь™]љY]ИHЪ[ќ—Ю™Y€\И›Э›Ы™H[™ЫЫ—Ъ[™ЏHЧФ‘U’QUЧХ‘TТУB€™]љY]ЧЫ\Э\[™
Ь™]љY]КCB€™]љY]ЧЬ™X\ЫЫ—Ы\Э\[™
€ЏЏ^ФЧФ‘U’QUЧХ‘TТУHЫ€[™€Y€Ь™]љY]И[ЩH€ЉCBѓB€][\ЧЩ–И“Ы€[™
[ќЉH—HHЫ—Ъ[™Ы\ЭB€][\ЧЩ–И”™]љY]ПИ—HH™]љY]ЧЫ\ЭB€][\ЧЩ–И”™]љY]И™X\ЫЫ€—HH™]љY]ЧЬ™X\ЫЫ—Ы\ЭBѓB€Y€[ћJ™]љY]ЧЫ\Э
NѓB€ЭќШ\›љ[™КB€€ё¦Ё;о#ИЫ™HЬ€[Ь™HИ[™H][\И[™XYH]™HЏ^ФЧФ‘U’QUЧХ‘TТУH[љ]ИЫ€[™€ѓB€”™]љY]И›YЩЩY][\И™Y›Ь™H\Ъ\Ъ[™Л€ѓB€
CBѓB€Э™]Yњ[YJ][\ЧЩ‹ЪYHњЭ™]ЪЉCB€B€ИЭXќЭ[B€ЭXќЭ[HЭ[J][VЙХЭ[	ЧH›Ь€][H[€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\КCB€B€ИШ[Э[][ЫњГB€Э›X\љЩЭЫЉ€ИИИ<'д¬Э[ИЉCB€ЫЫKЫЫ‹ЫЫИHЭЫЫ[[њККCB€B€Ъ]ЫЫNѓB€^Ь]HHЭ›ќ[X™\—Ъ[њ]
•^]H
	JH‹Z[—Э[YOLЊX^Э[YOLLЊ[YOLЊЭ\LЊJCB€Ъ]ЫЫЋѓB€\ШЫЭ[ќHЭ›ќ[X™\—Ъ[њ]
‘\ШЫЭ[ќ
	
H‹Z[—Э[YOLЊ[YOLЊЭ\LKЊ
CB€Ъ]ЫЫОѓB€Ъ\[™ИHЭ›ќ[X™\—Ъ[њ]
”Ъ\[™И
	
H‹Z[—Э[YOLЊ[YOLЊЭ\LKЊ
CB€B€^Ш[[Э[ќHЭXќЭ[
€
^Ь]HИL
CB€Э[HЭXќЭ[
И^Ш[[Э[ќH\ШЫЭ[ќ
ИЪ\[™ГB€ЭњЩ\ЬЪ[Ы—ЬЭ]Kњ›ЬЬЩYЬЧЭЭ[H›Ш]
Э[
CB€B€И\Ь^HЭ[ГB€Э›X\љЩЭЫЉ‹KKHЉCB€Э[ЧШЫЫKЭ[ЧШЫЫ€HЭЫЫ[[њКМЛWJCB€Ъ]Э[ЧШЫЫЋѓB€Э›X\љЩЭЫЉ€ЉЉ”ЭXќЭ[ЉЉ€	ЬЭXќЭ[‹Њ™џHЉCB€Y€^Ь]H€ѓB€Э›X\љЩЭЫЉ€ЉЉ•^
Э^Ь]_IJNЉЉ€	Э^Ш[[Э[ќ‹Њ™џHЉCB€Y€\ШЫЭ[ќ€ѓB€Э›X\љЩЭЫЉ€ЉЉ‘\ШЫЭ[ќЉЉ€IЩ\ШЫЭ[ќ‹Њ™џHЉCB€Y€Ъ\[™И€ѓB€Э›X\љЩЭЫЉ€ЉЉ”Ъ\[™ОЉЉ€	ЬЪ\[™О‹Њ™џHЉCB€Э›X\љЩЭЫЉ€€ИИИ
Љ•Э[ЉЉ€	ЭЭ[‹Њ™џHЉCB€B€ИXЭ[Ы€ќ]ЫњГB€ЫЫKЫЫ‹ЫЫИHЭЫЫ[[њККCB€Ъ]ЫЫNѓB€Y€Эќ]ЫЉј'ед{о#ИЫX\€[][\ИЉNѓB€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\ИHЧCB€ЬШY™WЬ™\ќ[Љ
CB€B€Ъ]ЫЫЋѓB€Y€Эќ]ЫЉј'дбЩ[™\]H€ЉNѓB€ИЩ[™\]HѓB€—ШќY™™\€Hћ]\ТSК
CB€ИHШ[ќ\ЛђШ[ќ\К—ШќY™™\‹YЩ\Ъ^™O[]\ЉCB€ЪYZYЪH]\ѓB€B€ИXY\ѓB€ЛњЩ]›Ыќ
’[™]XШKP›Ы‹Њ
CB€Л™]ФЭљ[™КJљ[ЪZYЪHJљ[Ъ”TђТTСHФ‘T€ЉCB€B€ИИ[™›ГB€ЛњЩ]›Ыќ
’[™]XШH‹L
CB€Л™]ФЭљ[™КJљ[ЪZYЪHKЊКљ[Ъ€”Иќ[X™\Ћ€ЬЧЫќ[X™\џHЉCB€Л™]ФЭљ[™КJљ[ЪZYЪHKЌJљ[Ъ€‘]N€ЬЧЩ]_HЉCB€B€ИЭЬ™H[™›ГB€ЛњЩ]›Ыќ
’[™]XШKP›Ы‹LЉCB€Л™]ФЭљ[™КJљ[ЪZYЪHЉљ[Ъ‘”“УN€ЉCB€ЛњЩ]›Ыќ
’[™]XШH‹L
CB€HHZYЪH‹ЊЉљ[ЪB€Л™]ФЭљ[™КJљ[ЪKЭЬ™WЫ[YJCB€›Ь€[™H[€ЭЬ™WШY™\ЬЛњЬ]
	Ч‰КNѓB€HOHЊMJљ[ЪB€Л™]ФЭљ[™КJљ[ЪK[™JCB€B€И™[™Ь€[™›ГB€ЛњЩ]›Ыќ
’[™]XШKP›Ы‹LЉCB€Л™]ФЭљ[™К
љ[ЪZYЪHЉљ[Ъ•О€ЉCB€ЛњЩ]›Ыќ
’[™]XШH‹L
CB€HHZYЪH‹ЊЉљ[ЪB€Л™]ФЭљ[™К
љ[ЪK™[™Ь—Ы[YJCB€›Ь€[™H[€™[™Ь—ШY™\ЬЛњЬ]
	Ч‰КNѓB€HOHЊMJљ[ЪB€Л™]ФЭљ[™К
љ[ЪK[™JCB€B€И][\ИX›CB€HHZYЪHЛЌJљ[ЪB€ЛњЩ]›Ыќ
’[™]XШKP›Ы‹L
CB€Л™]ФЭљ[™КJљ[ЪK”ТХHЉCB€Л™]ФЭљ[™КЉљ[ЪK‘\ШЬљ\[Ы€ЉCB€Л™]ФЭљ[™К
љ[ЪK”ЭZ[€ЉCB€Л™]ФЭљ[™КJљ[ЪK”Ъ^™HЉCB€Л™]ФЭљ[™КKЌJљ[ЪK”]HЉCB€Л™]ФЭљ[™КЉљ[ЪK”љXЩHЉCB€Л™]ФЭљ[™К‹ЌКљ[ЪK•Э[ЉCB€B€Л›[™JJљ[ЪHHЊJљ[ЪЛЌJљ[ЪHHЊJљ[Ъ
CB€B€HOHЊЌJљ[ЪB€ЛњЩ]›Ыќ
’[™]XШH‹JCB€›Ь€][H[€ЭњЩ\ЬЪ[Ы—ЬЭ]KњЧЪ][\ОѓB€Л™]ФЭљ[™КJљ[ЪKЭЉ][VЙФТХIЧJVО“PVФТХWУS‘ХФ—JCB€Л™]ФЭљ[™КЉљ[ЪKЭЉ][VЙС\ШЬљ\[Ы‰ЧJVО“PVСTРФ’TSУ—УS‘ХФ—JCB€Л™]ФЭљ[™К
љ[ЪKЭЉ][VЙФЭZ[‰ЧJVО“PVФХђRS—УS‘ХФ—JCB€Л™]ФЭљ[™КJљ[ЪKЭЉ][VЙФЪ^™IЧJVО“PVФТV‘WУS‘ХФ—JCB€Л™]ФЭљ[™КKЌJљ[ЪKЭЉ][VЙФ]X[ќ]IЧJJCB€Л™]ФЭљ[™КЉљ[ЪK€‰Ъ][VЙФљXЩIЧN‹Њ™џHЉCB€Л™]ФЭљ[™К‹ЌКљ[ЪK€‰Ъ][VЙХЭ[	ЧN‹Њ™џHЉCB€HOHЊЉљ[ЪB€Y€HЉљ[Ъ€И™]ИYЩHY€™YYYB€ЛњЪЭФYЩJ
CB€HHZYЪHJљ[ЪB€B€ИЭ[ГB€HOHЊКљ[ЪB€Л›[™JKЌJљ[ЪKЛЌJљ[ЪJCB€HOHЊЌJљ[ЪB€ЛњЩ]›Ыќ
’[™]XШH‹L
CB€Л™]ФЭљ[™КЉљ[ЪK”ЭXќЭ[€ЉCB€Л™]ФЭљ[™К‹ЌКљ[ЪK€‰ЬЭXќЭ[‹Њ™џHЉCB€B€Y€^Ь]H€ѓB€HOHЊЉљ[ЪB€Л™]ФЭљ[™КЉљ[ЪK€•^
Э^Ь]_IJN€ЉCB€Л™]ФЭљ[™К‹ЌКљ[ЪK€‰Э^Ш[[Э[ќ‹Њ™џHЉCB€B€Y€\ШЫЭ[ќ€ѓB€HOHЊЉљ[ЪB€Л™]ФЭљ[™КЉљ[ЪK‘\ШЫЭ[ќ€ЉCB€Л™]ФЭљ[™К‹ЌКљ[ЪK€‹IЩ\ШЫЭ[ќ‹Њ™џHЉCB€B€Y€Ъ\[™И€ѓB€HOHЊЉљ[ЪB€Л™]ФЭљ[™КЉљ[ЪK”Ъ\[™О€ЉCB€Л™]ФЭљ[™К‹ЌКљ[ЪK€‰ЬЪ\[™О‹Њ™џHЉCB€B€HOHЊЌJљ[ЪB€Л›[™JЉљ[ЪKЛЌJљ[ЪJCB€HOHЊЌJљ[ЪB€ЛњЩ]›Ыќ
’[™]XШKP›Ы‹LЉCB€Л™]ФЭљ[™КЉљ[ЪK•ХS€ЉCB€Л™]ФЭљ[™К‹ЌКљ[ЪK€‰ЭЭ[‹Њ™џHЉCB€B€ЛњШ]™J
CB€—ШќY™™\‹њЩYZК
CB€B€Э™ЭЫ›ШYШќ]ЫЉB€X™[Hј'дйHЭЫ›ШY€‹B€]O\—ШќY™™\‹B€љ[WЫ[YOY€”ЧЮЬЧЫќ[X™\џWЮЩ]][YK››ЭК
KњЭ™ќ[YJ	ЙVI[IY	К_Kњ€‹B€Z[YOH\XШ][Ы‹Ь€ѓB€
CB€[ЩNѓB€Эљ[™›Кј'дa€Y][\ИИ[Э\€\Ъ\ЩHЬ™\€\Ъ[™ИH›Ь›HX›Э™HЉCBѓB€И“УХTѓBњЭ›X\љЩЭЫЉ‹KKHЉCBћYX\€H]][YK››ЭК
KћYX\ѓBњЭ›X\љЩЭЫЉ‰П]€Ы\ЬПH™›ЫЭ\€ЏћУPСS”СWС“УХTџH8 (€0ЄHЮYX\џOЩ]Џ‰Л[њШY™WШ[ЭЧЪ[UќYJCB