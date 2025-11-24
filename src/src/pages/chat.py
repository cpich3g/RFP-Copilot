# Standard library imports
import asyncio
import json
import os
import pathlib
import sys
from time import sleep
from typing import Callable, Mapping

# Third-party imports
import streamlit as st
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv
from streamlit_option_menu import option_menu

from agent_framework_session import AgentFrameworkSession
from agent_framework import ChatMessage, TextContent
from rfp_agents import INITIAL_SEQUENCE_ORDER, VendorContext
from workflows.vendor_workflow import run_full_vendor_process, VendorWorkflowResult

# Application-specific imports
from app import AGENT_NAMES, create_chat_client, get_agent_prompts, get_reasoning_options
from plugins.legal_compliance_plugin import LegalCompliancePlugin
from plugins.vendor_evaluation_plugin import VendorEvaluationPlugin
from plugins.market_intelligence_plugin import MarketIntelligencePlugin
from components.settings_drawer import render_global_settings
# from speech import transcribe_real_time_audio

# Custom config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
st.set_page_config(layout="wide")

# Load environment variables
load_dotenv()

MARKET_INTELLIGENCE_DATASET = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "documents", "market-intelligence.json")
)

# Function to load CSS styles from a file
def load_css(file_path):  
    with open(file_path, encoding="utf-8") as f:  
        st.html(f"<style>{f.read()}</style>")

css_path = pathlib.Path(__file__).resolve().parent.parent / "style.css"
if css_path.exists():
    load_css(css_path)
else:
    st.warning(f"CSS file not found at {css_path}")

legal_policy_index = os.getenv("LEGAL_POLICY_INDEX")
supplier_insights_index = os.getenv("SUPPLIER_INDEX")
# Function to initialize the chat system
async def initialize_chat(stream_handler: Callable[[str, str], None] | None = None):
    session, initial_messages, _ = await build_session_for_vendor(
        st.session_state.chat_selected_vendor_index,
        stream_handler=stream_handler,
    )
    return session, initial_messages


# Initialize session state for chat
if "session_uid" not in st.session_state:
    st.warning("❌ No session UID found! Redirecting to home page...")
    sleep(2)
    st.switch_page("main.py")  # Redirect to home page
    
if "chat" not in st.session_state:
    st.session_state.chat = None
if "responses" not in st.session_state:
    st.session_state.responses = []
if "bootstrap_loaded" not in st.session_state:
    st.session_state.bootstrap_loaded = False
if "welcome_displayed" not in st.session_state:
    st.session_state.welcome_displayed = False
if "chat_selected_vendor_index" not in st.session_state:
    st.session_state.chat_selected_vendor_index = 0
if "vendor_agent_reports" not in st.session_state:
    st.session_state.vendor_agent_reports = []
if "vendor_comparison_summary" not in st.session_state:
    st.session_state.vendor_comparison_summary = None
if "vendor_comparison_structured" not in st.session_state:
    st.session_state.vendor_comparison_structured = None
if "vendor_runtime_contexts" not in st.session_state:
    st.session_state.vendor_runtime_contexts = []

vendor_entries = st.session_state.get("vendor_summaries", [])
if not vendor_entries:
    fallback_vendor_entries = st.session_state.get("vendor_summary_ready")
    if isinstance(fallback_vendor_entries, list):
        vendor_entries = fallback_vendor_entries

if not vendor_entries:
    st.error("Vendor summaries are unavailable. Please rerun the analysis from the home page.")
    sleep(2)
    st.switch_page("main.py")

selected_vendor_index = st.session_state.get("chat_selected_vendor_index", 0)
if vendor_entries:
    selected_vendor_index = max(0, min(selected_vendor_index, len(vendor_entries) - 1))
    st.session_state.chat_selected_vendor_index = selected_vendor_index

def _determine_vendor_label(entry, idx: int) -> str:
    summary_block = entry.get("summary", {}) if isinstance(entry, dict) else {}
    vendor_name = ""
    if isinstance(summary_block, dict):
        vendor_name = summary_block.get("vendor_name", "")
    file_name = entry.get("file_name") if isinstance(entry, dict) else None
    if vendor_name and vendor_name.lower() not in {"", "not specified"}:
        return vendor_name
    if file_name:
        return file_name
    return f"Vendor {idx + 1}"


vendor_display_names = [_determine_vendor_label(entry, idx) for idx, entry in enumerate(vendor_entries)]


# Define agent metadata for consistent styling and labeling
AGENT_LOGOS = {
    AGENT_NAMES["rfp_compliance"]: "📜",
    AGENT_NAMES["legal_compliance"]: "⚖️",
    AGENT_NAMES["vendor_evaluation"]: "🏢",
    AGENT_NAMES["market_intelligence"]: "📊",
    AGENT_NAMES["negotiation_strategy"]: "🤝",
    AGENT_NAMES["evaluation_report"]: "📑",
}

BRAND_NAME = "Sobha Realty"

AGENT_DISPLAY_NAMES = {
    AGENT_NAMES["rfp_compliance"]: "RFP Compliance",
    AGENT_NAMES["legal_compliance"]: "Legal Compliance",
    AGENT_NAMES["vendor_evaluation"]: "Vendor Evaluation",
    AGENT_NAMES["market_intelligence"]: "Market Intelligence",
    AGENT_NAMES["negotiation_strategy"]: "Negotiation Strategy",
    AGENT_NAMES["evaluation_report"]: "Evaluation Report",
}

USER_LOGO = "https://cdn.pixabay.com/photo/2016/03/31/17/33/avatar-1293744_1280.png"
SYSTEM_LOGO = "https://cdn.pixabay.com/photo/2016/03/31/18/43/gear-1294576_1280.png"
image_path3 = os.path.join(os.path.dirname(__file__), "..", "static", "image3.jpg")

# Welcome message variable
WELCOME_MESSAGE = "Hello! Welcome to the Group Agent Chat System. Feel free to ask any questions and our agents will respond!"


async def ensure_vendor_context(vendor_index: int) -> tuple[VendorContext, str]:
    cached_contexts: list[dict[str, object] | None] = st.session_state.get("vendor_runtime_contexts", [])
    if vendor_index < len(cached_contexts):
        cached_entry = cached_contexts[vendor_index]
        if isinstance(cached_entry, dict):
            context = cached_entry.get("context")
            label = cached_entry.get("vendor_label")
            if isinstance(context, VendorContext) and isinstance(label, str):
                return context, label

    selected_record = vendor_entries[vendor_index] if vendor_entries else {}
    proposal_summary = selected_record.get("summary", {}) if isinstance(selected_record, dict) else {}
    proposal_summary_payload: Mapping[str, str] | str
    if isinstance(proposal_summary, dict):
        proposal_summary_payload = proposal_summary
    else:
        proposal_summary_payload = str(proposal_summary)

    vendor_label = vendor_display_names[vendor_index] if vendor_index < len(vendor_display_names) else f"Vendor {vendor_index + 1}"
    rfp_summary = st.session_state.get("rfp_summary_ready", "")

    azure_endpoint = os.environ.get("AZURE_AI_SEARCH_ENDPOINT")
    azure_api_key = os.environ.get("AZURE_AI_SEARCH_API_KEY")

    policy_context = "Azure AI Search legal policy index is not configured."
    if azure_endpoint and azure_api_key and legal_policy_index:
        legal_search_client = SearchClient(
            endpoint=azure_endpoint,
            index_name=legal_policy_index,
            credential=AzureKeyCredential(azure_api_key),
        )
        legal_compliance_plugin = LegalCompliancePlugin(
            search_client=legal_search_client,
            vendor_legal_summary=(proposal_summary_payload.get("legal_summary", "") if isinstance(proposal_summary_payload, Mapping) else ""),
        )
        policy_context = await legal_compliance_plugin.check_compliance()

    vendor_insights = "Azure AI Search supplier insights index is not configured."
    if azure_endpoint and azure_api_key and supplier_insights_index:
        vendor_search_client = SearchClient(
            endpoint=azure_endpoint,
            index_name=supplier_insights_index,
            credential=AzureKeyCredential(azure_api_key),
        )
        vendor_evaluation_plugin = VendorEvaluationPlugin(
            search_client=vendor_search_client,
            vendor_name=
            (
                (proposal_summary_payload.get("vendor_name") if isinstance(proposal_summary_payload, Mapping) else None)
                or vendor_label
                or "Unknown Vendor"
            ),
        )
        vendor_insights = await vendor_evaluation_plugin.get_vendor_insights()

    market_intelligence_plugin = MarketIntelligencePlugin(MARKET_INTELLIGENCE_DATASET)
    market_insights = market_intelligence_plugin.get_market_insights("Cloud Computing")

    context = VendorContext(
        rfp_summary=rfp_summary,
        proposal_summary=proposal_summary_payload,
        policy_context=policy_context,
        vendor_insights=vendor_insights,
        market_insights=market_insights,
    )

    while len(cached_contexts) <= vendor_index:
        cached_contexts.append(None)
    cached_contexts[vendor_index] = {"context": context, "vendor_label": vendor_label}
    st.session_state.vendor_runtime_contexts = cached_contexts

    return context, vendor_label


async def build_session_for_vendor(
    vendor_index: int,
    *,
    stream_handler: Callable[[str, str], None] | None = None,
) -> tuple[AgentFrameworkSession, list[dict[str, str]], str]:
    prompt_instructions = get_agent_prompts()
    context, vendor_display_name = await ensure_vendor_context(vendor_index)

    session = AgentFrameworkSession(
        agent_prompts=prompt_instructions,
        rfp_summary=context.rfp_summary,
        proposal_summary=context.proposal_summary,
        policy_context=context.policy_context,
        vendor_insights=context.vendor_insights,
        market_insights=context.market_insights,
    )

    initial_messages = await session.bootstrap(stream_handler=stream_handler)
    return session, initial_messages, vendor_display_name


async def generate_comparison_summary(reports: list[dict[str, object]]) -> str | None:
    if not reports:
        return None

    chat_client = create_chat_client(model_variant="gpt5-mini")
    reasoning_options = get_reasoning_options("gpt5-mini")
    chat_options = dict(reasoning_options)
    chat_options.pop("reasoning", None)
    system_prompt = (
        "You are an expert procurement analyst. Compare multiple vendor proposals using the agent outputs. "
        "Synthesize key strengths, risks, and compliance findings, rank the vendors, and recommend the best fit."
    )

    vendor_sections: list[str] = []
    for report in reports:
        vendor_label = report.get("vendor_label", "Unknown Vendor")
        agent_outputs = report.get("agent_outputs", {})
        section_lines = [f"Vendor: {vendor_label}"]
        if isinstance(agent_outputs, dict):
            for agent_name, summary in agent_outputs.items():
                section_lines.append(f"{agent_name}:")
                section_lines.append(str(summary))
        vendor_sections.append("\n".join(section_lines))

    comparison_prompt = (
        "\n\n---\n\n".join(vendor_sections)
        + "\n\nProvide a ranked comparison of the vendors. "
        "**You must present the comparison as a Markdown table** with columns for: "
        "Vendor Name, Rank, Key Strengths, Key Risks, Compliance Status, and Overall Score. "
        "After the table, provide a brief conclusion with a clear recommendation."
    )

    messages = [
        ChatMessage(role="system", contents=[TextContent(text=system_prompt)]),
        ChatMessage(role="user", contents=[TextContent(text=comparison_prompt)]),
    ]

    response = await chat_client.get_response(
        messages=messages,
        additional_properties=chat_options or None,
    )
    return response.text if response and getattr(response, "text", None) else None


async def perform_multi_vendor_analysis() -> None:
    if not vendor_entries:
        return

    prompt_instructions = get_agent_prompts()
    contexts: list[tuple[VendorContext, str]] = []
    for idx in range(len(vendor_entries)):
        contexts.append(await ensure_vendor_context(idx))

    workflow_tasks: list[asyncio.Task[VendorWorkflowResult]] = []
    for idx, (context, vendor_label) in enumerate(contexts):
        workflow_tasks.append(
            asyncio.create_task(
                run_full_vendor_process(
                    agent_prompts=prompt_instructions,
                    vendor_label=vendor_label,
                    context=context,
                )
            )
        )

    vendor_results = await asyncio.gather(*workflow_tasks)

    reports: list[dict[str, object]] = [
        {
            "vendor_index": idx,
            "vendor_label": result.vendor_label,
            "agent_outputs": result.agent_outputs,
        }
        for idx, result in enumerate(vendor_results)
    ]

    comparison_summary = await generate_comparison_summary(reports)

    st.session_state.vendor_agent_reports = reports
    st.session_state.vendor_comparison_summary = comparison_summary
    st.session_state.vendor_comparison_structured = {
        "vendors": [
            {
                "vendor_label": result.vendor_label,
                "agent_outputs": result.agent_outputs,
            }
            for result in vendor_results
        ]
    }


if (
    vendor_entries
    and st.session_state.get("vendor_summary_ready")
    and not st.session_state.get("vendor_agent_reports")
):
    try:
        with st.spinner("Running multi-vendor agent analysis..."):
            asyncio.run(perform_multi_vendor_analysis())
    except Exception as exc:
        st.error(f"Multi-vendor analysis failed: {exc}")


menu_options: list[str] = ["Bid Comparison"]
menu_icons: list[str] = ["trophy"]
vendor_option_map: dict[str, int] = {}

for idx, _ in enumerate(vendor_display_names, start=1):
    option_label = f"Proposal {idx} Agent Output"
    vendor_option_map[option_label] = idx - 1
    menu_options.append(option_label)
    menu_icons.append("file-earmark-text")

menu_options.append("Negotiation Strategy")
menu_icons.append("hand-thumbs-up")
menu_options.append("Chat Console")
menu_icons.append("chat")

with st.sidebar:
    if st.button("➕ New Analysis", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.switch_page("main.py")
    
    st.divider()
    render_global_settings()
    st.image(image_path3, width=160)
    selected_section = option_menu(
        menu_title=BRAND_NAME,
        options=menu_options,
        icons=menu_icons,
        menu_icon="building",
        default_index=0,
        key="chat_sidebar_menu",
    )

previous_vendor_index = st.session_state.get("chat_selected_vendor_index", 0)
active_vendor_index = previous_vendor_index
if selected_section in vendor_option_map:
    active_vendor_index = vendor_option_map[selected_section]

if vendor_entries:
    active_vendor_index = max(0, min(active_vendor_index, len(vendor_entries) - 1))
else:
    active_vendor_index = 0

if active_vendor_index != previous_vendor_index:
    st.session_state.chat_selected_vendor_index = active_vendor_index
    st.session_state.chat = None
    st.session_state.responses = []
    st.session_state.bootstrap_loaded = False
    st.session_state.welcome_displayed = False

selected_vendor_index = st.session_state.get("chat_selected_vendor_index", active_vendor_index)



if selected_section == "Bid Comparison":
    st.header("🏆 Multi-Vendor Comparison")
    comparison_summary = st.session_state.get("vendor_comparison_summary")
    reports = st.session_state.get("vendor_agent_reports", [])
    structured_payload = st.session_state.get("vendor_comparison_structured")

    if comparison_summary:
        st.markdown(comparison_summary)
    else:
        st.info("Run the analysis from the home page to see the consolidated comparison.")

    if structured_payload:
        st.download_button(
            "⬇️ Download structured comparison (JSON)",
            data=json.dumps(structured_payload, indent=2),
            file_name="vendor-comparison.json",
            mime="application/json",
            width="content",
        )

    if reports:
        st.markdown("### Per-Vendor Agent Highlights")
        for report in reports:
            vendor_label = report.get("vendor_label", "Unknown Vendor")
            agent_outputs = report.get("agent_outputs", {})
            with st.expander(vendor_label, expanded=False):
                if isinstance(agent_outputs, dict):
                    for agent_name, summary in agent_outputs.items():
                        display_name = agent_name if isinstance(agent_name, str) else str(agent_name)
                        st.markdown(f"**{display_name}**")
                        st.write(summary)
                else:
                    st.write(agent_outputs)

    st.divider()

    rfp_summary = st.session_state.get("rfp_summary_ready")
    if rfp_summary:
        with st.expander("📄 View RFP Summary", expanded=False):
            st.write(rfp_summary)

    if vendor_entries:
        with st.expander("📑 View Vendor Proposal Summaries", expanded=False):
            for idx, entry in enumerate(vendor_entries):
                summary_block = entry.get("summary", {}) if isinstance(entry, dict) else entry
                vendor_label = vendor_display_names[idx] if idx < len(vendor_display_names) else f"Vendor {idx + 1}"
                st.markdown(f"### {vendor_label}")
                if isinstance(summary_block, dict):
                    st.markdown(f"**Vendor Name:** {summary_block.get('vendor_name', vendor_label)}")
                    st.markdown("**Legal Summary**")
                    st.write(summary_block.get("legal_summary", "Not specified"))
                    st.markdown("**Overall Summary**")
                    st.write(summary_block.get("overall_summary", "Not specified"))
                else:
                    st.write(summary_block)
                if idx < len(vendor_entries) - 1:
                    st.divider()

elif selected_section in vendor_option_map:
    vendor_index = vendor_option_map[selected_section]
    vendor_label = vendor_display_names[vendor_index] if vendor_index < len(vendor_display_names) else f"Vendor {vendor_index + 1}"
    st.header(f"📄 {vendor_label} Agent Output")

    reports = st.session_state.get("vendor_agent_reports", [])
    vendor_report = next((report for report in reports if report.get("vendor_index") == vendor_index), None)
    if vendor_report is None and vendor_index < len(reports):
        vendor_report = reports[vendor_index]

    if vendor_report and isinstance(vendor_report, dict):
        agent_outputs = vendor_report.get("agent_outputs", {}) or {}
        export_payload = {
            "vendor_label": vendor_label,
            "agent_outputs": agent_outputs,
        }
        st.download_button(
            label="⬇️ Download agent outputs (JSON)",
            data=json.dumps(export_payload, indent=2),
            file_name=f"proposal-{vendor_index + 1}-agents.json",
            mime="application/json",
            width="content",
        )

        proposal_entry = vendor_entries[vendor_index] if vendor_index < len(vendor_entries) else {}
        proposal_summary = proposal_entry.get("summary", {}) if isinstance(proposal_entry, dict) else proposal_entry
        with st.expander("📑 Proposal Summary", expanded=False):
            if isinstance(proposal_summary, Mapping):
                st.markdown(f"**Vendor Name:** {proposal_summary.get('vendor_name', vendor_label)}")
                st.markdown("**Legal Summary**")
                st.write(proposal_summary.get("legal_summary", "Not specified"))
                st.markdown("**Overall Summary**")
                st.write(proposal_summary.get("overall_summary", "Not specified"))
            else:
                st.write(proposal_summary)

        st.markdown("### Agent Findings")
        if agent_outputs:
            for agent_name in INITIAL_SEQUENCE_ORDER:
                display_name = AGENT_DISPLAY_NAMES.get(agent_name, agent_name)
                agent_text = agent_outputs.get(agent_name)
                with st.expander(display_name, expanded=False):
                    if agent_text:
                        st.markdown(agent_text)
                    else:
                        st.info("No output recorded for this agent.")
        else:
            st.info("Agent outputs are not available for this proposal yet.")
    else:
        st.info("Run the analysis from the home page to generate agent outputs for this proposal.")

elif selected_section == "Negotiation Strategy":
    st.header("🤝 Negotiation Strategy Playbook")
    reports = st.session_state.get("vendor_agent_reports", [])
    if not reports:
        st.info("Run the analysis from the home page to collect negotiation guidance.")
    else:
        for idx, report in enumerate(reports):
            vendor_label = report.get("vendor_label") or (
                vendor_display_names[idx] if idx < len(vendor_display_names) else f"Vendor {idx + 1}"
            )
            agent_outputs = report.get("agent_outputs", {}) if isinstance(report, dict) else {}
            negotiation_guidance = agent_outputs.get(AGENT_NAMES["negotiation_strategy"])
            evaluation_snapshot = agent_outputs.get(AGENT_NAMES["evaluation_report"])

            with st.expander(f"{vendor_label}", expanded=(idx == 0)):
                if negotiation_guidance:
                    st.markdown("#### Negotiation Guidance")
                    st.markdown(negotiation_guidance)
                else:
                    st.info("Negotiation strategy is not available for this vendor yet.")

                if evaluation_snapshot:
                    st.markdown("#### Evaluation Snapshot")
                    st.markdown(evaluation_snapshot)

elif selected_section == "Chat Console":
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(image_path3, width=140)
    with col2:
        st.title("Agent Group Chat")
        current_vendor_label = (
            vendor_display_names[selected_vendor_index]
            if selected_vendor_index < len(vendor_display_names)
            else f"Vendor {selected_vendor_index + 1}"
        )
        st.caption(f"Analyzing proposal from: **{current_vendor_label}**")
        if vendor_entries:
            chat_vendor_idx = st.selectbox(
                "Switch vendor conversation",
                options=list(range(len(vendor_entries))),
                format_func=lambda idx: vendor_display_names[idx],
                index=selected_vendor_index,
                key="chat_vendor_switch",
            )
            if chat_vendor_idx != st.session_state.chat_selected_vendor_index:
                st.session_state.chat_selected_vendor_index = chat_vendor_idx
                st.session_state.chat = None
                st.session_state.responses = []
                st.session_state.bootstrap_loaded = False
                st.session_state.welcome_displayed = False
                st.rerun()
        comparison_summary = st.session_state.get("vendor_comparison_summary")
        if comparison_summary:
            with st.expander("📊 View multi-vendor recommendation", expanded=False):
                st.markdown(comparison_summary)
    
    just_bootstrapped = False

    if st.session_state.chat is None:
        bootstrap_stream_context: dict[str, dict[str, object]] = {}

        def bootstrap_stream_handler(agent_name: str, chunk: str) -> None:
            if not chunk:
                return

            context = bootstrap_stream_context.get(agent_name)
            if context is None:
                agent_logo = AGENT_LOGOS.get(agent_name, "🤖")
                message_container = st.chat_message("assistant", avatar=agent_logo)
                placeholder = message_container.empty()
                header = f"**{agent_name} Agent:**\n\n"
                placeholder.markdown(header)
                context = {"placeholder": placeholder, "buffer": header}
                bootstrap_stream_context[agent_name] = context

            context = bootstrap_stream_context[agent_name]
            context["buffer"] += chunk
            placeholder = context["placeholder"]
            if hasattr(placeholder, "markdown"):
                placeholder.markdown(context["buffer"])

        session, initial_messages = asyncio.run(initialize_chat(stream_handler=bootstrap_stream_handler))
        st.session_state.chat = session
        if not st.session_state.bootstrap_loaded:
            st.session_state.responses.extend(initial_messages)
            st.session_state.bootstrap_loaded = True
            just_bootstrapped = True

    if not st.session_state.welcome_displayed:
        with st.chat_message("assistant", avatar=SYSTEM_LOGO):
            st.markdown("**System:**")
            st.markdown(WELCOME_MESSAGE)
        st.session_state.welcome_displayed = True

    # Display previous responses with correct emoji mapping
    if not just_bootstrapped:
        for response in st.session_state.get("responses", []):
            role = response["role"]
            content = response["content"]

            if role == "user":
                with st.chat_message("user", avatar=USER_LOGO):
                    st.markdown("**You:**")  
                    st.markdown(content)
            else:
                agent_logo = AGENT_LOGOS.get(role, "🤖")  
                with st.chat_message("assistant", avatar=agent_logo):
                    st.markdown(f"**{role} Agent:**")  
                    st.markdown(content)

    # Handle new user input
    prompt = st.chat_input("Enter your message:", key="chat_input")      
    
    if prompt:
        # Display the new user message with the correct format
        with st.chat_message("user", avatar=USER_LOGO):
            st.markdown("**You:**")
            st.markdown(prompt)

        st.session_state.responses.append({"role": "user", "content": prompt})

        stream_context: dict[str, dict[str, object]] = {}
        streamed_content: dict[str, str] = {}

        def stream_handler(agent_name: str, chunk: str) -> None:
            if not chunk:
                return

            context = stream_context.get(agent_name)
            if context is None:
                agent_logo = AGENT_LOGOS.get(agent_name, "🤖")
                message_container = st.chat_message("assistant", avatar=agent_logo)
                placeholder = message_container.empty()
                header = f"**{agent_name} Agent:**\n\n"
                placeholder.markdown(header)
                context = {"placeholder": placeholder, "buffer": header}
                stream_context[agent_name] = context
                streamed_content[agent_name] = ""

            context = stream_context[agent_name]
            context["buffer"] += chunk
            context_placeholder = context["placeholder"]
            if hasattr(context_placeholder, "markdown"):
                context_placeholder.markdown(context["buffer"])
            streamed_content[agent_name] = streamed_content.get(agent_name, "") + chunk

        agent_responses = asyncio.run(
            st.session_state.chat.handle_user_prompt_streaming(
                prompt,
                stream_handler=stream_handler,
            )
        )

        for agent_name, agent_text in agent_responses:
            if not agent_text:
                agent_text = streamed_content.get(agent_name, "")
            if not agent_text:
                continue
            st.session_state.responses.append({"role": agent_name, "content": agent_text})

        st.rerun()