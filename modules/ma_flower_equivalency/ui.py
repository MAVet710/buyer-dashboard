"""Streamlit UI for the Massachusetts flower-equivalency calculator."""

from __future__ import annotations

import html
import json

import streamlit as st
import streamlit.components.v1 as components

from modules.ma_flower_equivalency.logic import (
    EquivalencyResult,
    EquivalencyValidationError,
    calculate_concentrate_equivalency,
    calculate_edible_equivalency,
    calculate_infused_preroll_equivalency,
    format_equivalency,
)
from ui_polish import render_section_header


CONCENTRATE_CATEGORIES = {
    "Dabs / Concentrate",
    "Vape Cart",
    "Disposable Vape",
}
EDIBLE_CATEGORIES = {
    "Edible",
    "Infused Edible / Beverage",
}
PRODUCT_CATEGORIES = [
    "Dabs / Concentrate",
    "Vape Cart",
    "Disposable Vape",
    "Edible",
    "Infused Edible / Beverage",
    "Infused Pre-Roll",
]


def _input_css() -> None:
    st.markdown(
        """
        <style>
        .ma-equivalency-note {
            border: 1px solid rgba(255, 154, 60, .28);
            border-left: 4px solid #ff9a3c;
            border-radius: 12px;
            padding: .8rem .95rem;
            margin: .2rem 0 1rem;
            background: rgba(255, 154, 60, .07);
        }
        .ma-equivalency-note strong { color: #ffb870; }
        .ma-result-card {
            border: 1px solid rgba(255, 255, 255, .12);
            border-radius: 16px;
            padding: 1rem 1.1rem;
            background: linear-gradient(145deg, rgba(30, 35, 30, .96), rgba(16, 18, 16, .98));
            min-height: 138px;
        }
        .ma-result-label {
            text-transform: uppercase;
            letter-spacing: .08em;
            font-size: .72rem;
            opacity: .72;
        }
        .ma-result-value { font-size: 2rem; font-weight: 760; margin: .15rem 0; }
        .ma-result-help { font-size: .82rem; opacity: .72; }
        .ma-breakdown {
            border: 1px solid rgba(255, 255, 255, .1);
            border-radius: 14px;
            padding: .85rem 1rem;
            background: rgba(255, 255, 255, .025);
            line-height: 1.65;
        }
        @media (max-width: 640px) {
            .ma-result-card { min-height: 0; }
            .ma-result-value { font-size: 1.65rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _text_number(label: str, *, key: str, help_text: str, value: str = "") -> str:
    return st.text_input(
        label,
        key=key,
        value=value,
        placeholder="Enter a value",
        help=help_text,
    )


def _copy_button(value: str) -> None:
    safe_value = json.dumps(value)
    components.html(
        f"""
        <button id="copy-equivalency" type="button" aria-label="Copy Dutchie flower equivalency value"
          style="width:100%;min-height:42px;border:0;border-radius:10px;background:#ff9a3c;color:#1b1308;font-weight:750;cursor:pointer;">
          Copy value
        </button>
        <div id="copy-status" role="status" aria-live="polite"
          style="height:20px;margin-top:5px;text-align:center;font:12px sans-serif;color:#b9c4b9;"></div>
        <script>
          const button = document.getElementById('copy-equivalency');
          const status = document.getElementById('copy-status');
          button.addEventListener('click', async () => {{
            const value = {safe_value};
            try {{
              await navigator.clipboard.writeText(value);
              status.textContent = 'Copied ' + value;
            }} catch (error) {{
              const fallback = document.createElement('textarea');
              fallback.value = value;
              document.body.appendChild(fallback);
              fallback.select();
              document.execCommand('copy');
              fallback.remove();
              status.textContent = 'Copied ' + value;
            }}
          }});
        </script>
        """,
        height=70,
    )


def _result_card(label: str, value: str, help_text: str) -> None:
    st.markdown(
        f"""
        <div class="ma-result-card">
            <div class="ma-result-label">{html.escape(label)}</div>
            <div class="ma-result-value">{html.escape(value)}</div>
            <div class="ma-result-help">{html.escape(help_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_results(result: EquivalencyResult, category: str, inputs: dict[str, str]) -> None:
    per_unit = format_equivalency(result.per_unit)
    total = format_equivalency(result.package_total)
    unit_label = "Per joint" if category == "Infused Pre-Roll" else "Per unit"
    total_label = (
        "Package flower equivalency"
        if category == "Infused Pre-Roll"
        else "Total package/cart flower equivalency"
    )

    left, right = st.columns(2)
    with left:
        _result_card(unit_label, per_unit, "Full precision retained until display.")
    with right:
        _result_card(total_label, total, "Numeric value to enter in Dutchie.")

    st.markdown("#### Calculation breakdown")
    if category in CONCENTRATE_CATEGORIES:
        breakdown = (
            f"{inputs['grams']} g/concentration × 5.6 = **{per_unit}** per unit  \n"
            f"{per_unit} × {result.quantity} package unit(s) = **{total}**"
        )
    elif category in EDIBLE_CATEGORIES:
        breakdown = (
            f"{inputs['active_thc_mg']} mg active THC × 0.056 = **{per_unit}** per unit  \n"
            f"{per_unit} × {result.quantity} package unit(s) = **{total}**"
        )
    else:
        flower = format_equivalency(result.flower_weight_per_joint or result.per_unit)
        infusion_equiv = format_equivalency(result.infusion_equivalency_per_joint or result.per_unit)
        breakdown = (
            f"Flower portion: {inputs['finished']} g finished − {inputs['infusion']} g infusion = **{flower} g** per joint  \n"
            f"Infusion equivalency: {inputs['infusion']} g × 5.6 = **{infusion_equiv}** per joint  \n"
            f"Per-joint equivalency: {flower} + {infusion_equiv} = **{per_unit}**  \n"
            f"Package: {per_unit} × {result.quantity} joint(s) = **{total}**"
        )
    with st.container(border=True):
        st.markdown(breakdown)
    st.markdown("#### Dutchie entry value")
    value_col, copy_col = st.columns([2, 1])
    with value_col:
        st.text_input(
            "Unformatted numeric result",
            value=total,
            disabled=True,
            help="Copy this package/cart flower-equivalency value into Dutchie.",
        )
    with copy_col:
        _copy_button(total)


def render_ma_flower_equivalency() -> None:
    """Render the responsive Retail calculator workspace."""
    _input_css()
    render_section_header(
        "MA Flower Equivalency",
        "Calculate the Dutchie flower-equivalency value for one package.",
        kicker="RETAIL OPS · PACKAGE CONFIGURATION",
    )
    st.markdown(
        """
        <div class="ma-equivalency-note">
          <strong>Operational package-entry calculator.</strong>
          This is not a consumer dosage calculator. For infused pre-rolls, the finished weight
          must include both flower and infusion material.
        </div>
        """,
        unsafe_allow_html=True,
    )

    category = st.selectbox(
        "Product category",
        PRODUCT_CATEGORIES,
        key="ma_equivalency_category",
        help="Choose the Dutchie package category you are configuring.",
    )

    result: EquivalencyResult | None = None
    validation_error: EquivalencyValidationError | None = None
    inputs: dict[str, str] = {}

    with st.form("ma_flower_equivalency_form", border=True):
        if category in CONCENTRATE_CATEGORIES:
            grams_col, quantity_col = st.columns(2)
            with grams_col:
                inputs["grams"] = _text_number(
                    "Grams/concentration per unit (g)",
                    key="ma_equivalency_grams",
                    help_text="Enter G/C in grams, such as 0.5, 1, or 2.",
                )
            with quantity_col:
                inputs["quantity"] = _text_number(
                    "Package quantity (whole units)",
                    key="ma_equivalency_quantity",
                    help_text="The number of identical units; defaults to 1.",
                    value="1",
                )
            submitted = st.form_submit_button("Calculate equivalency", type="primary", width="stretch")
            if submitted:
                try:
                    result = calculate_concentrate_equivalency(inputs["grams"], inputs["quantity"])
                except EquivalencyValidationError as exc:
                    validation_error = exc
        elif category in EDIBLE_CATEGORIES:
            thc_col, quantity_col = st.columns(2)
            with thc_col:
                inputs["active_thc_mg"] = _text_number(
                    "Labeled active THC per unit (mg)",
                    key="ma_equivalency_active_thc_mg",
                    help_text="Use active THC only - not TAC, THCA, CBD, or total cannabinoids.",
                )
            with quantity_col:
                inputs["quantity"] = _text_number(
                    "Package quantity (whole units)",
                    key="ma_equivalency_quantity",
                    help_text="The number of identical units; defaults to 1.",
                    value="1",
                )
            submitted = st.form_submit_button("Calculate equivalency", type="primary", width="stretch")
            if submitted:
                try:
                    result = calculate_edible_equivalency(inputs["active_thc_mg"], inputs["quantity"])
                except EquivalencyValidationError as exc:
                    validation_error = exc
        else:
            finished_col, infusion_col, count_col = st.columns(3)
            with finished_col:
                inputs["finished"] = _text_number(
                    "Finished weight per joint (g)",
                    key="ma_equivalency_finished_g",
                    help_text="Includes both flower and infusion material.",
                )
            with infusion_col:
                inputs["infusion"] = _text_number(
                    "Infusion material per joint (g)",
                    key="ma_equivalency_infusion_g",
                    help_text="Enter only the infusion portion in grams.",
                )
            with count_col:
                inputs["joint_count"] = _text_number(
                    "Joints in package (whole number)",
                    key="ma_equivalency_joint_count",
                    help_text="The number of finished joints in one package.",
                )
            submitted = st.form_submit_button("Calculate equivalency", type="primary", width="stretch")
            if submitted:
                try:
                    result = calculate_infused_preroll_equivalency(
                        inputs["finished"],
                        inputs["infusion"],
                        inputs["joint_count"],
                    )
                except EquivalencyValidationError as exc:
                    validation_error = exc

    if validation_error is not None:
        st.error(validation_error.message, icon="⚠️")
    elif result is not None:
        _render_results(result, category, inputs)
    else:
        st.info("Complete the required fields, then calculate the package value.")

    st.caption(
        "For Massachusetts adult-use Dutchie package configuration. Confirm operational values "
        "with your compliance team before changing live inventory."
    )
