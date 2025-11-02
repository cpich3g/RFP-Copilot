# Standard library imports
import os
import uuid
from time import sleep

# Third-party imports
import streamlit as st
from PIL import Image

# Local application imports
from doc_summarization import summarize_document

st.markdown("""
    <style>
        .st-emotion-cache-1i6lr5d img { 
            width: 200px !important;  /* Increase the width */
            height: auto !important;  /* Maintain aspect ratio */
        }
        .st-emotion-cache-180ybpv {
            width: 200px !important;  /* Increase the width */
            height: auto !important;  /* Maintain aspect ratio */
    </style>
""", unsafe_allow_html=True)

# Analyze Button styling
st.markdown("""
<style>
/* Analyze Button Hover */
.st-key-analyze_button button {
    transition: all 0.3s ease-in-out;
}

.st-key-analyze_button button:hover {
    box-shadow: 0 0 20px #166ec5;
    transform: scale(1.30);
}

</style>
""", unsafe_allow_html=True)

image_path1 = os.path.join(os.path.dirname(__file__), "static", "image1.png")
LOGO_URL_LARGE = Image.open(image_path1)
image_path2 = os.path.join(os.path.dirname(__file__), "static", "image3.jpg") 

st.logo(
    LOGO_URL_LARGE,
    size="large"
)
col1, col2 = st.columns([1, 3])
with col1:
    st.image(image_path2, use_container_width=True) 
with col2:
    st.title("AI-Powered RFP Analyzer")
st.markdown('''''')

if "session_uid" not in st.session_state:
    st.session_state.session_uid = str(uuid.uuid4())  # Generate a new UID

# Initialize session state variables
if "rfp_uploaded" not in st.session_state:
    st.session_state.rfp_uploaded = False
    st.session_state.rfp_file = None

if "vendor_uploaded" not in st.session_state:
    st.session_state.vendor_uploaded = False
    st.session_state.vendor_file = None

if "vendor_files" not in st.session_state:
    st.session_state.vendor_files = []

if "vendor_summaries" not in st.session_state:
    st.session_state.vendor_summaries = []

if "vendor_agent_reports" not in st.session_state:
    st.session_state.vendor_agent_reports = []

if "vendor_comparison_summary" not in st.session_state:
    st.session_state.vendor_comparison_summary = None

if "vendor_comparison_structured" not in st.session_state:
    st.session_state.vendor_comparison_structured = None

if "vendor_runtime_contexts" not in st.session_state:
    st.session_state.vendor_runtime_contexts = []

if "rfp_summary_ready" not in st.session_state:
    st.session_state.rfp_summary_ready = False

if "vendor_summary_ready" not in st.session_state:
    st.session_state.vendor_summary_ready = False

if "chat_ready" not in st.session_state:
    st.session_state.chat_ready = False

if "process_running" not in st.session_state:
    st.session_state.process_running = False

if "chat_selected_vendor_index" not in st.session_state:
    st.session_state.chat_selected_vendor_index = 0

# Progress Tracking (0 to 5)
progress_stage = 0  
if st.session_state.rfp_uploaded:
    progress_stage = 1  
if st.session_state.vendor_uploaded:
    progress_stage = 2  
if st.session_state.rfp_summary_ready:
    progress_stage = 3  
if st.session_state.vendor_summary_ready:
    progress_stage = 4  
if st.session_state.chat_ready:
    progress_stage = 5  

# Display Progress Bar
progress = st.progress(progress_stage / 5)
st.markdown('''''')
#  Step Indicators
steps = [
    ("Upload Documents", st.session_state.rfp_uploaded and st.session_state.vendor_uploaded),
    ("Summarization", st.session_state.rfp_summary_ready and st.session_state.vendor_summary_ready),
    ("Multi-Agent Analysis", st.session_state.chat_ready),
]

cols = st.columns(len(steps))
for i, (label, completed) in enumerate(steps):
    if completed:
        cols[i].markdown(f"✅ **{label}**")
    else:
        cols[i].markdown(f"🔘 {label}")

st.markdown('''''')
st.markdown('''''')

# **Step 1: Upload RFP Document**
st.subheader("Step 1: Upload RFP Document")
if not st.session_state.rfp_uploaded:
    rfp_file = st.file_uploader("Upload RFP Document", type=["pdf", "docx", "txt"], key="rfp")
    if rfp_file:
        st.session_state.rfp_uploaded = True
        st.session_state.rfp_file = rfp_file
        st.session_state.rfp_summary_ready = False
        st.session_state.vendor_uploaded = False
        st.session_state.vendor_file = None
        st.session_state.vendor_files = []
        st.session_state.vendor_summaries = []
        st.session_state.vendor_agent_reports = []
        st.session_state.vendor_comparison_summary = None
        st.session_state.vendor_comparison_structured = None
        st.session_state.vendor_runtime_contexts = []
        st.session_state.vendor_summary_ready = False
        st.session_state.chat_ready = False
        st.session_state.process_running = False
        st.session_state.chat_selected_vendor_index = 0
        st.rerun()  # Refresh after file upload
else:
    st.success(f"RFP Document Uploaded: {st.session_state.rfp_file.name}")

# **Step 2: Upload Vendor Proposal(s)**
if st.session_state.rfp_uploaded:
    st.subheader("Step 2: Upload Vendor Proposal Document(s)")
    if not st.session_state.vendor_uploaded:
        vendor_files = st.file_uploader(
            "Upload Vendor Proposal Document(s)",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="vendor",
        )
        if vendor_files:
            uploads = list(vendor_files)
            st.session_state.vendor_uploaded = True
            st.session_state.vendor_files = uploads
            st.session_state.vendor_file = uploads[0] if uploads else None
            st.session_state.vendor_summaries = []
            st.session_state.vendor_agent_reports = []
            st.session_state.vendor_comparison_summary = None
            st.session_state.vendor_comparison_structured = None
            st.session_state.vendor_runtime_contexts = []
            st.session_state.vendor_summary_ready = False
            st.session_state.chat_ready = False
            st.session_state.process_running = False
            st.session_state.chat_selected_vendor_index = 0
            st.rerun()
    else:
        vendor_count = len(st.session_state.vendor_files)
        if vendor_count:
            st.success(f"{vendor_count} Vendor Proposal{'s' if vendor_count > 1 else ''} Uploaded!")
            for uploaded in st.session_state.vendor_files:
                st.caption(f"• {uploaded.name}")
        else:
            st.info("No vendor proposals currently uploaded.")

        if st.button("Upload Different Proposals", key="reset_vendor_upload"):
            st.session_state.vendor_uploaded = False
            st.session_state.vendor_file = None
            st.session_state.vendor_files = []
            st.session_state.vendor_summaries = []
            st.session_state.vendor_agent_reports = []
            st.session_state.vendor_comparison_summary = None
            st.session_state.vendor_comparison_structured = None
            st.session_state.vendor_runtime_contexts = []
            st.session_state.vendor_summary_ready = False
            st.session_state.chat_ready = False
            st.session_state.process_running = False
            st.session_state.chat_selected_vendor_index = 0
            st.rerun()

# **Step 3: Multi-Agent Analysis**
if st.session_state.rfp_uploaded and st.session_state.vendor_uploaded and st.session_state.vendor_files:
    st.subheader("Step 3: Multi-Agent Analysis")

    if st.button("Analyze", icon=":material/cycle:",disabled=st.session_state.process_running, key="analyze_button"):
        st.session_state.process_running = True  # Mark process as running
        st.session_state.vendor_agent_reports = []
        st.session_state.vendor_comparison_summary = None
        st.session_state.vendor_comparison_structured = None
        if len(st.session_state.vendor_summaries) != len(st.session_state.vendor_files):
            st.session_state.vendor_summary_ready = False
        st.session_state.chat_ready = False
        st.rerun()  # Rerun to trigger processing

# **Processing Steps (Runs After Rerun)**
if st.session_state.process_running:
    
    # Step 1: Summarizing RFP
    if not st.session_state.rfp_summary_ready:
        with st.spinner("Summarizing RFP Document..."):
            st.session_state.rfp_file.seek(0)
            st.session_state.rfp_summary_ready = summarize_document(st.session_state.rfp_file, "rfp")
            st.rerun()

    # Step 2: Summarizing Vendor Proposal(s)
    if st.session_state.rfp_summary_ready and not st.session_state.vendor_summary_ready:
        total_vendors = len(st.session_state.vendor_files)
        processed_vendors = len(st.session_state.vendor_summaries)

        if processed_vendors < total_vendors:
            current_file = st.session_state.vendor_files[processed_vendors]
            current_file.seek(0)
            with st.spinner(
                f"Summarizing Vendor Proposal ({processed_vendors + 1}/{total_vendors}) — {current_file.name}..."
            ):
                summary = summarize_document(current_file, "proposal")

            if isinstance(summary, dict):
                summary_payload = summary
            else:
                summary_payload = {
                    "vendor_name": getattr(summary, "vendor_name", "Unknown Vendor"),
                    "legal_summary": getattr(summary, "legal_summary", str(summary)),
                    "overall_summary": str(summary),
                }

            st.session_state.vendor_summaries.append(
                {
                    "file_name": current_file.name,
                    "summary": summary_payload,
                }
            )

            if st.session_state.chat_selected_vendor_index is None:
                st.session_state.chat_selected_vendor_index = 0

            if len(st.session_state.vendor_summaries) == total_vendors:
                st.session_state.vendor_summary_ready = list(st.session_state.vendor_summaries)

            st.rerun()
        else:
            if total_vendors > 0 and st.session_state.vendor_summaries:
                st.session_state.vendor_summary_ready = list(st.session_state.vendor_summaries)
                st.rerun()

    # Step 3: Generating Chat Instance
    if st.session_state.rfp_summary_ready and st.session_state.vendor_summary_ready and not st.session_state.chat_ready:
        with st.spinner("Generating Chat Instance..."):
            sleep(3)
            st.session_state.chat_ready = True
            st.rerun()

    # Step 4: Redirect to Analysis Page
    if st.session_state.chat_ready:
        with st.spinner("All set..."):
            sleep(1)
        with st.spinner("Redirecting to Analysis Page..."):
            sleep(2)
        st.session_state.process_running = False  # Reset process flag
        st.switch_page("pages/chat.py")

st.markdown("---")
st.subheader("Explore the advanced copilots")
cta_col1, cta_col2 = st.columns(2)
if cta_col1.button("📊 Bid Comparison Intelligence", use_container_width=True):
    st.switch_page("pages/1_Bid_Comparison.py")
if cta_col2.button("🤝 Negotiation Strategy Copilot", use_container_width=True):
    st.switch_page("pages/2_Negotiation_Strategy.py")
