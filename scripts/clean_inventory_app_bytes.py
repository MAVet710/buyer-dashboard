from pathlib import Path
import re
import subprocess

APP = Path("app.py")
WORKFLOW = Path(".github/workflows/clean-inventory-app-bytes.yml")
SCRIPT = Path("scripts/clean_inventory_app_bytes.py")

data = subprocess.check_output(["git", "show", "origin/main:app.py"])


def sep_for(chunk: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in chunk else b"\n"


# Insert imports without touching any other line endings.
import_pattern = re.compile(
    rb"from services\.buyer_intelligence_brief import \(\r?\n"
    rb"    buyer_intelligence_ai_enabled,\r?\n"
    rb"    generate_buyer_intelligence_brief,\r?\n"
    rb"\)\r?\n"
)
match = import_pattern.search(data)
if not match:
    raise SystemExit("buyer intelligence import anchor not found")
sep = sep_for(match.group(0))
replacement = sep.join(
    [
        b"from services.buyer_intelligence_brief import (",
        b"    buyer_intelligence_ai_enabled,",
        b"    generate_buyer_intelligence_brief,",
        b")",
        b"from services.inventory_check import (",
        b"    generate_inventory_check,",
        b"    inventory_check_ai_enabled,",
        b")",
        b"",
    ]
)
data = data[: match.start()] + replacement + data[match.end() :]

# Replace only the legacy function body.
start_token = b"def ai_inventory_check(detail_view, doh_threshold, data_source):"
end_token = b"def _feature_enabled("
start = data.find(start_token)
if start < 0:
    raise SystemExit("inventory function start not found")
end = data.find(end_token, start)
if end < 0:
    raise SystemExit("inventory function end not found")
# Preserve the newline bytes immediately preceding the next function.
chunk = data[start:end]
sep = sep_for(chunk)
function_lines = [
    b"def ai_inventory_check(detail_view, doh_threshold, data_source):",
    b"    \"\"\"Run a data-backed inventory check through the Gemini Inventory Agent.\"\"\"",
    b"    product_view = st.session_state.get(\"detail_product_cached_df\")",
    b"    if not isinstance(product_view, pd.DataFrame):",
    b"        product_view = None",
    b"    return generate_inventory_check(",
    b"        detail_view=detail_view,",
    b"        product_view=product_view,",
    b"        doh_threshold=doh_threshold,",
    b"        data_source=data_source,",
    b"    )",
    b"",
    b"",
]
function_bytes = sep.join(function_lines)
data = data[:start] + function_bytes + data[end:]

# Replace only the Inventory Check button/connection gate.
ui_pattern = re.compile(
    rb"        if not _doobie_ai_access_enabled\(\):\r?\n"
    rb"            st\.info\(\"Connect Doobie AI to enable this feature\.\"\)\r?\n"
    rb"        elif _doobie_ai_status\(\) == \"connected\":\r?\n"
    rb"            if st\.button\(\"Run AI check on current view\"\):\r?\n"
    rb"                with st\.spinner\(\"Having the AI look over this slice like a buyer\.\.\.\"\):\r?\n"
    rb"                    ai_summary = ai_inventory_check\(detail_view, doh_threshold, data_source\)\r?\n"
    rb"                st\.markdown\(ai_summary\)\r?\n"
    rb"        else:\r?\n"
    rb"            st\.info\(\"Doobie AI is currently unavailable\.\"\)\r?\n"
)
match = ui_pattern.search(data)
if not match:
    raise SystemExit("inventory UI gate not found")
sep = sep_for(match.group(0))
ui_bytes = sep.join(
    [
        b"        if st.button(\"Run AI check on current view\"):",
        b"            with st.spinner(\"Checking SKU coverage, velocity, and overstock risk...\"):",
        b"                ai_summary = ai_inventory_check(detail_view, doh_threshold, data_source)",
        b"            st.markdown(ai_summary)",
        b"            if not inventory_check_ai_enabled():",
        b"                st.caption(\"Gemini is unavailable, so this result is the deterministic data-backed inventory check.\")",
        b"",
    ]
)
data = data[: match.start()] + ui_bytes + data[match.end() :]

APP.write_bytes(data)

for path in (WORKFLOW, SCRIPT):
    if path.exists():
        path.unlink()
