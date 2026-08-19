from __future__ import annotations

from pathlib import Path
import re


APP = Path("app.py")
raw = APP.read_text(encoding="utf-8", newline="")
newline = "\r\n" if raw.count("\r\n") >= max(1, raw.count("\n") // 2) else "\n"

buyer_pattern = re.compile(
    r"section_groups = buyer_section_groups\([\s\S]*?section = st\.sidebar\.radio\([\s\S]*?\)\r?\n\r?\nif section == INVENTORY_COUNTS_SECTION:",
    re.MULTILINE,
)

buyer_replacement = """section_groups = buyer_section_groups(
    is_admin=st.session_state.get(\"is_admin\", False),
    user_role=str(st.session_state.get(\"auth_user_role\") or \"trial\"),
    admin_exports_enabled=_feature_enabled(\"admin_exports\", default_enabled=True),
)
_flat_navigation_active = bool(st.session_state.get(\"flat_navigation_enabled\", False)) and not bool(
    st.session_state.get(\"legacy_navigation_enabled\", False)
)
if _flat_navigation_active:
    _allowed_buyer_sections = [
        page
        for pages in section_groups.values()
        for page in pages
    ]
    section = str(st.session_state.get(\"buyer_section\") or \"\")
    if section not in _allowed_buyer_sections:
        section = _allowed_buyer_sections[0]
        st.session_state[\"buyer_section\"] = section
        st.session_state[\"buyer_section_group\"] = next(
            (
                group
                for group, pages in section_groups.items()
                if section in pages
            ),
            next(iter(section_groups)),
        )
else:
    saved_buyer_section = st.session_state.get(\"buyer_section\")
    saved_retail_area = next(
        (
            group
            for group, sections in section_groups.items()
            if saved_buyer_section in sections
        ),
        next(iter(section_groups)),
    )
    if st.session_state.get(\"buyer_section_group\") not in section_groups:
        st.session_state[\"buyer_section_group\"] = saved_retail_area

    retail_area = st.sidebar.selectbox(
        \"Retail Area\",
        list(section_groups),
        key=\"buyer_section_group\",
        help=\"Choose a task area, then select the tool you need.\",
    )
    visible_section_options = section_groups[retail_area]
    if st.session_state.get(\"buyer_section\") not in visible_section_options:
        st.session_state[\"buyer_section\"] = visible_section_options[0]

    section = st.sidebar.radio(
        \"Tool\",
        visible_section_options,
        key=\"buyer_section\",
        help=\"Buyer Operations tools are grouped to keep navigation clean on desktop and mobile.\",
    )

if section == INVENTORY_COUNTS_SECTION:""".replace("\n", newline)

raw, count = buyer_pattern.subn(buyer_replacement, raw, count=1)
if count != 1:
    raise SystemExit(f"Expected one Buyer navigation block; patched {count}.")

po_anchor = (
    'elif section == "🧾 PO Builder":' + newline
    + '    st.subheader("Purchase Order Builder")' + newline
    + '    st.write("Create professional purchase orders with automatic calculations and PDF export.")' + newline
)
if po_anchor not in raw:
    raise SystemExit("PO Builder anchor not found.")

po_insert = po_anchor + (
    newline
    + '    _product_360_seed = st.session_state.get("product_360_po_seed")' + newline
    + '    if isinstance(_product_360_seed, dict) and _product_360_seed.get("product_name"):' + newline
    + '        with st.container(border=True):' + newline
    + '            st.markdown("#### Product 360 draft item")' + newline
    + '            _p360_qty = int(_product_360_seed.get("quantity") or 0)' + newline
    + '            _p360_cost = float(_product_360_seed.get("unit_cost") or 0.0)' + newline
    + '            _p360_total = float(_product_360_seed.get("estimated_cost") or (_p360_qty * _p360_cost))' + newline
    + '            st.write(f"**{_product_360_seed.get(\'product_name\')}**")' + newline
    + '            st.caption(' + newline
    + '                f"Suggested quantity: {_p360_qty:,} · Unit cost: ${_p360_cost:,.2f} · "' + newline
    + '                f"Estimated line total: ${_p360_total:,.2f}"' + newline
    + '            )' + newline
    + '            st.info("This item was staged from Product 360. Review it against the PO controls below before exporting or sending anything.")' + newline
    + '            if st.button("Clear staged Product 360 item", key="clear_product_360_po_seed"):' + newline
    + '                st.session_state.pop("product_360_po_seed", None)' + newline
    + '                st.rerun()' + newline
)
raw = raw.replace(po_anchor, po_insert, 1)

APP.write_text(raw, encoding="utf-8", newline="")
print("Applied flat navigation compatibility patch to app.py")
# trigger after workflow exists
