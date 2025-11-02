"""Reusable Streamlit component for weight editing."""
from __future__ import annotations

from typing import Dict

import pandas as pd
import streamlit as st

from services.bid_analysis_service import DEFAULT_METRIC_WEIGHTS


def render_weight_editor(
    initial_weights: Dict[str, float] | None = None,
    *,
    title: str | None = "Weighting Configuration",
    key_prefix: str = "weight",
) -> Dict[str, float]:
    if title:
        st.subheader(title)
    st.caption("Adjust the importance of each criterion; weights will normalize automatically.")
    weights = initial_weights or DEFAULT_METRIC_WEIGHTS.copy()
    edited_weights = {}
    cols = st.columns(3)
    items = list(weights.items())
    for idx, (metric, value) in enumerate(items):
        with cols[idx % 3]:
            edited_weights[metric] = st.slider(
                metric.replace("_", " ").title(),
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                value=float(value),
                key=f"{key_prefix}_{metric}",
            )
    st.caption(
        "Weights are normalized, so relative proportions matter. Set at least one weight above zero."
    )
    return edited_weights
