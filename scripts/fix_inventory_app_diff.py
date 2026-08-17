from pathlib import Path
import subprocess

APP_PATH = Path("app.py")
WORKFLOW_PATH = Path(".github/workflows/fix-inventory-app-diff.yml")
SCRIPT_PATH = Path("scripts/fix_inventory_app_diff.py")

base = subprocess.check_output(["git", "show", "origin/main:app.py"])
uses_crlf = b"\r\n" in base
text = base.decode("utf-8").replace("\r\n", "\n")

import_anchor = """from services.buyer_intelligence_brief import (
    buyer_intelligence_ai_enabled,
    generate_buyer_intelligence_brief,
)
"""
import_replacement = import_anchor + """from services.inventory_check import (
    generate_inventory_check,
    inventory_check_ai_enabled,
)
"""
if import_anchor not in text:
    raise SystemExit("buyer intelligence import anchor not found in normalized main app.py")
text = text.replace(import_anchor, import_replacement, 1)

start = text.index("def ai_inventory_check(detail_view, doh_threshold, data_source):")
end = text.index("\ndef _feature_enabled(", start)
new_function = '''def ai_inventory_check(detail_view, doh_threshold, data_source):
    """Run a data-backed inventory check through the Gemini Inventory Agent."""
    product_view = st.session_state.get("detail_product_cached_df")
    if not isinstance(product_view, pd.DataFrame):
        product_view = None
    return generate_inventory_check(
        detail_view=detail_view,
        product_view=product_view,
        doh_threshold=doh_threshold,
        data_source=data_source,
    )
'''
text = text[:start] + new_function + text[end:]

old_ui = '''        if not _doobie_ai_access_enabled():
            st.info("Connect Doobie AI to enable this feature.")
        elif _doobie_ai_status() == "connected":
            if st.button("Run AI check on current view"):
                with st.spinner("Having the AI look over this slice like a buyer..."):
                    ai_summary = ai_inventory_check(detail_view, doh_threshold, data_source)
                st.markdown(ai_summary)
        else:
            st.info("Doobie AI is currently unavailable.")
'''
new_ui = '''        if st.button("Run AI check on current view"):
            with st.spinner("Checking SKU coverage, velocity, and overstock risk..."):
                ai_summary = ai_inventory_check(detail_view, doh_threshold, data_source)
            st.markdown(ai_summary)
            if not inventory_check_ai_enabled():
                st.caption("Gemini is unavailable, so this result is the deterministic data-backed inventory check.")
'''
if old_ui not in text:
    raise SystemExit("legacy inventory AI UI block not found in normalized main app.py")
text = text.replace(old_ui, new_ui, 1)

if uses_crlf:
    text = text.replace("\n", "\r\n")
APP_PATH.write_bytes(text.encode("utf-8"))

for cleanup in (WORKFLOW_PATH, SCRIPT_PATH):
    if cleanup.exists():
        cleanup.unlink()
