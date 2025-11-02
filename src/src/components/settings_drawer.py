"""Reusable settings drawer for Streamlit pages."""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st


def render_global_settings() -> Dict[str, Any]:
    panel = st.sidebar
    panel.header("Global Settings")
    api_source = panel.selectbox(
        "LLM Provider",
        options=["Azure OpenAI"],
        index=0,
        disabled=True,
    )
    telemetry = panel.toggle("Anonymize Analytics", value=True)
    theme = panel.selectbox("Theme", options=["System", "Light", "Dark"], index=0)
    return {
        "api_source": api_source,
        "telemetry": telemetry,
        "theme": theme,
    }
