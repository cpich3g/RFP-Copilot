"""Streamlit page for bid comparison and scenario analysis."""
from __future__ import annotations

import json
from typing import Dict, List

import pandas as pd
import plotly.express as px
import streamlit as st

from components.settings_drawer import render_global_settings
from components.weight_editor import render_weight_editor
from services.bid_analysis_service import (
    BidComparisonEngine,
    WeightingConfig,
    parse_rfp_spec,
)
from services.reporting import build_bid_report_bundle

st.set_page_config(page_title="Bid Comparison", layout="wide")

st.markdown(
    """
    <style>
    div[data-testid="stDataFrame"] table tr th {
        position: sticky;
        top: 0;
        z-index: 1;
        backdrop-filter: blur(6px);
        background-color: var(--background-color);
    }
    div[data-testid="stDataFrame"] table tr td:first-child {
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("bid_comparison_result", None)
    st.session_state.setdefault("bid_engine_config", {})
    st.session_state.setdefault("bid_scenarios", [])
    st.session_state.setdefault("bid_comparison_mode", "multi_vendor")


@st.cache_data(show_spinner=False)
def _load_rfp_anchor(uploaded_file):
    try:
        return parse_rfp_spec(uploaded_file)
    except ValueError as exc:
        st.warning(f"Failed to parse RFP spec: {exc}")
        return {}


def _render_settings_drawer() -> Dict[str, str]:
    render_global_settings()
    st.sidebar.markdown("### Comparison Mode")
    mode = st.sidebar.radio(
        "Analysis Type",
        options=["multi_vendor", "multi_rfp"],
        format_func=lambda x: "Multiple Vendors vs Single RFP" if x == "multi_vendor" else "Single Vendor vs Multiple RFPs",
        key="bid_comparison_mode",
    )
    st.sidebar.markdown("---")
    include_outliers = st.sidebar.toggle("Include Outliers", value=True, help="Toggle Z-score filtering on price.")
    missing_strategy = st.sidebar.selectbox(
        "Missing Field Strategy",
        options=["median", "drop"],
        format_func=lambda x: "Impute median" if x == "median" else "Drop rows",
    )
    return {
        "mode": mode,
        "include_outliers": include_outliers,
        "missing_strategy": missing_strategy,
    }


def _render_supplier_scores(scores):
    score_df = pd.DataFrame(
        [
            {
                "Supplier": score.supplier,
                "Composite Score": round(score.total_score, 4),
            }
            for score in scores
        ]
    )
    fig = px.bar(score_df, x="Supplier", y="Composite Score", color="Supplier", text="Composite Score")
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
    fig.update_layout(yaxis_range=[0, 1.05])
    st.plotly_chart(fig, width="stretch")

    metrics_df = pd.DataFrame(
        [
            {
                "supplier": score.supplier,
                **{metric: norm for metric, norm in score.normalized_metrics.items()},
            }
            for score in scores
        ]
    )
    metrics_df = metrics_df.set_index("supplier")
    if not metrics_df.empty:
        for supplier, row in metrics_df.iterrows():
            fig_radar = px.line_polar(
                pd.DataFrame({"metric": row.index, "score": row.values}),
                r="score",
                theta="metric",
                line_close=True,
                range_r=[0, 1],
                title=f"Normalized Scores — {supplier}",
            )
            st.plotly_chart(fig_radar, width="stretch")


def _render_variation_panel(deltas: List[str], scores) -> None:
    st.subheader("Variation & Risk Insights")
    if not deltas:
        st.info("No major deltas detected.")
    else:
        for delta in deltas:
            st.markdown(f"- {delta}")

    critical_flags = [(score.supplier, flag) for score in scores for flag in score.risk_flags]
    if critical_flags:
        st.markdown("**Risk Flags**")
        for supplier, flag in critical_flags:
            st.markdown(f"- **{supplier}:** {flag}")


def _render_supplier_insights(scores) -> None:
    st.markdown("### Supplier Insight Hub")
    if not scores:
        st.info("Run an analysis to unlock supplier playbooks and risk commentary.")
        return
    for score in scores:
        header = f"{score.supplier} — Composite {score.total_score:.2f}"
        with st.expander(header, expanded=False):
            col_metrics, col_flags = st.columns([3, 2])
            with col_metrics:
                st.markdown("**Metric Breakdown**")
                metrics_df = pd.DataFrame(
                    {
                        "Metric": [metric.replace("_", " ").title() for metric in score.metrics.keys()],
                        "Value": [round(value, 2) for value in score.metrics.values()],
                        "Normalized": [round(score.normalized_metrics.get(metric, 0), 2) for metric in score.metrics.keys()],
                    }
                )
                st.dataframe(metrics_df.set_index("Metric"), width="stretch")
            with col_flags:
                st.markdown("**Risk Flags**")
                if score.risk_flags:
                    for flag in score.risk_flags:
                        st.markdown(f"- {flag}")
                else:
                    st.caption("No critical risk flags surfaced.")
            st.markdown("**Narrative Rationale**")
            st.markdown(score.rationale.replace("\n", "  \n"))


def _render_outputs_empty_state():
    st.info(
        "Upload at least one supplier bid, optionally provide an RFP anchor, and press **Analyze Bids** to unlock "
        "the comparison workspace."
    )


def _render_what_if(engine: BidComparisonEngine, baseline_scores: Dict[str, float]):
    st.markdown("---")
    st.subheader("What-if Sandbox")
    st.caption("Adjust weights to simulate alternative scoring scenarios.")
    scenario_weights = render_weight_editor(
        st.session_state.get("bid_scenario_weights", {}),
        title="Scenario Weight Overrides",
        key_prefix="scenario_weight",
    )
    if st.button("Run Scenario", key="run_scenario"):
        try:
            payload = engine.run_scenario(scenario_weights)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.setdefault("bid_scenarios", []).append(payload)
            st.session_state["bid_scenario_weights"] = scenario_weights
            st.success("Scenario computed. See results below.")
    if st.session_state.get("bid_scenarios"):
        st.markdown("### Scenario Results")
        for idx, scenario in enumerate(reversed(st.session_state["bid_scenarios"]), 1):
            st.markdown(f"**Scenario {idx} — Weights**: `{json.dumps(scenario['weights'])}`")
            scenario_df = pd.DataFrame(scenario["scores"])
            if "baseline_total_score" not in scenario_df.columns:
                scenario_df["baseline_total_score"] = scenario_df["supplier"].map(baseline_scores)
                scenario_df["score_delta"] = scenario_df["total_score"] - scenario_df["baseline_total_score"]
            display_cols = [
                "supplier",
                "total_score",
                "baseline_total_score",
                "score_delta",
            ]
            styled = (
                scenario_df[display_cols]
                .rename(
                    columns={
                        "supplier": "Supplier",
                        "total_score": "Scenario Score",
                        "baseline_total_score": "Baseline Score",
                        "score_delta": "Δ Score",
                    }
                )
                .style.background_gradient(subset=["Δ Score"], cmap="PiYG")
                .hide(axis="index")
            )
            st.dataframe(styled, width="stretch")
            st.caption("Positive deltas indicate suppliers gaining under the new weighting mix.")
            top_movers = scenario_df.sort_values("score_delta", ascending=False)
            st.markdown("**Diff Highlights**")
            for _, row in top_movers.head(3).iterrows():
                delta = row.get("score_delta", 0)
                supplier = row.get("supplier", "")
                if abs(delta) < 1e-3:
                    continue
                tone = "improved" if delta > 0 else "declined"
                st.markdown(f"- {supplier} {tone} by {delta:.3f} points")


def _render_multi_vendor_inputs(settings: Dict[str, str]):
    supplier_files = st.file_uploader(
        "Supplier Bid Files (CSV, XLSX, JSON, DOCX)",
        type=["csv", "xls", "xlsx", "json", "docx"],
        accept_multiple_files=True,
        help="Drop in multiple supplier packages with pricing, terms, and delivery details.",
    )
    rfp_spec_file = st.file_uploader(
        "Optional RFP Specification",
        type=["csv", "json", "txt", "md", "docx"],
        help="Anchors such as target price, SLA thresholds, or compliance minimums.",
    )
    weight_overrides = render_weight_editor(st.session_state.get("bid_weights_override"), key_prefix="primary_weight")

    rfp_anchor = _load_rfp_anchor(rfp_spec_file) if rfp_spec_file else {}
    if rfp_anchor:
        st.success("RFP anchors loaded. We'll benchmark bids against them.")

    if st.button("Analyze Bids", type="primary", width="stretch"):
        try:
            weight_config = WeightingConfig(weight_overrides)
            engine = BidComparisonEngine(
                include_outliers=settings["include_outliers"],
                missing_strategy=settings["missing_strategy"],
                weight_config=weight_config,
                rfp_anchor=rfp_anchor,
            )
            result = engine.analyse(supplier_files)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["bid_comparison_result"] = result
            st.session_state["bid_engine_config"] = {
                "include_outliers": settings["include_outliers"],
                "missing_strategy": settings["missing_strategy"],
            }
            st.session_state["bid_weights_override"] = weight_overrides
            st.session_state["bid_engine_instance"] = engine
            st.session_state["bid_baseline_scores"] = {
                score.supplier: score.total_score for score in result.supplier_scores
            }
            st.session_state["bid_baseline_table"] = result.normalized_table.to_dict(orient="records")
            st.success("Bid analysis complete. Jump to the Outputs tab to explore insights.")


def _render_multi_vendor_outputs():
    result = st.session_state.get("bid_comparison_result")
    engine = st.session_state.get("bid_engine_instance")
    baseline_scores = st.session_state.get("bid_baseline_scores", {})
    if not result:
        _render_outputs_empty_state()
        return

    st.markdown("## Normalized Comparison Table")
    st.dataframe(
        result.normalized_table.reset_index(drop=True),
        width="stretch",
        height=420,
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("### Score Breakdown")
        _render_supplier_scores(result.supplier_scores)
    with col2:
        _render_variation_panel(result.deltas_vs_rfp, result.supplier_scores)

    _render_supplier_insights(result.supplier_scores)

    st.subheader("Explainable Summary")
    st.markdown(result.llm_summary or "Summary pending.")

    if engine:
        _render_what_if(engine, baseline_scores)

    bundle_bytes = build_bid_report_bundle(result)
    st.download_button(
        "Download Report Bundle",
        data=bundle_bytes,
        file_name="bid-comparison-report.zip",
        mime="application/zip",
        type="primary",
    )


def _render_multi_rfp_inputs(settings: Dict[str, str]):
    vendor_file = st.file_uploader(
        "Vendor Proposal (CSV, XLSX, JSON, DOCX)",
        type=["csv", "xls", "xlsx", "json", "docx"],
        help="Single vendor bid with line-item pricing, terms, and delivery details.",
    )
    rfp_files = st.file_uploader(
        "RFP Scenarios (CSV, JSON, TXT, MD, DOCX)",
        type=["csv", "json", "txt", "md", "docx"],
        accept_multiple_files=True,
        help="Multiple RFP specification files, each representing a different requirement context.",
    )
    weight_overrides = render_weight_editor(st.session_state.get("bid_weights_override"), key_prefix="primary_weight")

    if st.button("Analyze RFP Scenarios", type="primary", width="stretch"):
        if not vendor_file:
            st.error("Upload a vendor proposal file first.")
            return
        if not rfp_files:
            st.error("Upload at least one RFP scenario file.")
            return
        
        try:
            from services.bid_analysis_service import MultiRFPComparisonEngine
            
            weight_config = WeightingConfig(weight_overrides)
            engine = MultiRFPComparisonEngine(
                include_outliers=settings["include_outliers"],
                missing_strategy=settings["missing_strategy"],
                weight_config=weight_config,
            )
            result = engine.analyse_vendor_across_rfps(vendor_file, rfp_files)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["multi_rfp_result"] = result
            st.session_state["multi_rfp_engine"] = engine
            st.session_state["bid_weights_override"] = weight_overrides
            st.success("RFP scenario analysis complete. Jump to the Outputs tab.")


def _render_multi_rfp_outputs():
    result = st.session_state.get("multi_rfp_result")
    if not result:
        st.info("Upload a vendor proposal and multiple RFP scenarios, then press **Analyze RFP Scenarios** to unlock insights.")
        return

    st.markdown("## RFP Scenario Performance")
    st.dataframe(
        result.scenario_table.reset_index(drop=True),
        width="stretch",
        height=420,
    )

    st.markdown("### Score Breakdown by RFP")
    scenario_df = pd.DataFrame(
        [
            {
                "RFP Scenario": score.rfp_name,
                "Composite Score": round(score.total_score, 4),
            }
            for score in result.rfp_scores
        ]
    )
    fig = px.bar(scenario_df, x="RFP Scenario", y="Composite Score", color="RFP Scenario", text="Composite Score")
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
    fig.update_layout(yaxis_range=[0, 1.05], showlegend=False)
    st.plotly_chart(fig, width="stretch")

    st.markdown("### Variation & Fit Insights")
    if result.variation_notes:
        for note in result.variation_notes:
            st.markdown(f"- {note}")
    else:
        st.info("No major variations detected across RFP scenarios.")

    st.subheader("Explainable Summary")
    st.markdown(result.llm_summary or "Summary pending.")


def main():
    _init_state()
    st.title("Bid Comparison Intelligence")
    
    settings = _render_settings_drawer()
    mode = settings.get("mode", "multi_vendor")

    if mode == "multi_vendor":
        st.markdown(
            "Upload supplier proposals and compare them across configurable weighted criteria."
            " The analysis normalizes data, ranks suppliers, and highlights risks."
        )
    else:
        st.markdown(
            "Upload one vendor proposal and multiple RFP scenarios to see how the vendor performs"
            " across different requirement contexts."
        )

    inputs_tab, outputs_tab = st.tabs(["Inputs", "Outputs & Insights"])

    with inputs_tab:
        if mode == "multi_vendor":
            _render_multi_vendor_inputs(settings)
        else:
            _render_multi_rfp_inputs(settings)

    with outputs_tab:
        if mode == "multi_vendor":
            _render_multi_vendor_outputs()
        else:
            _render_multi_rfp_outputs()


if __name__ == "__main__":
    main()
