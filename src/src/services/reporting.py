"""Helpers for generating downloadable artefacts."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile
from typing import Dict, Iterable

from fpdf import FPDF

from services.bid_analysis_service import BidComparisonResult


def generate_bid_markdown_report(result: BidComparisonResult) -> str:
    lines = ["# Bid Comparison Report", "", f"Generated at: {result.generated_at.isoformat()} UTC", ""]
    lines.append("## Executive Summary")
    lines.append(result.llm_summary or "Summary pending.")
    lines.append("\n## Weighted Scores")
    lines.append("```")
    lines.append(str(result.weight_config))
    lines.append("```")
    lines.append("\n## Supplier Breakdown")
    for score in result.supplier_scores:
        lines.append(f"### {score.supplier}")
        lines.append(f"- Total Score: {score.total_score:.2f}")
        lines.append("- Metrics: " + ", ".join(f"{k}={v}" for k, v in score.metrics.items()))
        if score.risk_flags:
            lines.append("- Risk Flags:")
            lines.extend([f"  - {flag}" for flag in score.risk_flags])
        lines.append("- Rationale:\n  " + score.rationale.replace("\n", "\n  "))
    if result.deltas_vs_rfp:
        lines.append("\n## Key Variations vs RFP")
        lines.extend([f"- {delta}" for delta in result.deltas_vs_rfp])
    lines.append("\n## Normalized Table")
    lines.append(result.to_markdown())
    return "\n".join(lines)


def generate_pdf_from_markdown(markdown_text: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for line in markdown_text.splitlines():
        pdf.multi_cell(0, 10, line)
    return pdf.output(dest="S").encode("latin-1")


def build_bid_report_bundle(result: BidComparisonResult) -> bytes:
    markdown_report = generate_bid_markdown_report(result)
    pdf_bytes = generate_pdf_from_markdown(markdown_report)
    csv_bytes = result.to_csv()
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_file:
        zip_file.writestr("bid-comparison/report.md", markdown_report)
        zip_file.writestr("bid-comparison/report.pdf", pdf_bytes)
        zip_file.writestr("bid-comparison/normalized-table.csv", csv_bytes)
    buffer.seek(0)
    return buffer.getvalue()
