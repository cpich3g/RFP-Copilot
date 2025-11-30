"""Utilities for analyzing and summarizing RFP and vendor proposal documents."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Iterable

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import AzureOpenAI
from pydantic import BaseModel

from app import get_model_settings, get_reasoning_options

load_dotenv()

DOCUMENT_INTELLIGENCE_ENDPOINT = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
DOCUMENT_INTELLIGENCE_KEY = os.environ["AZURE_DOC_INTELLIGENCE_KEY"]
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_AUTH_MODE = os.getenv("AZURE_OPENAI_AUTH_MODE", "default_credential").lower()
AZURE_OPENAI_SCOPE = os.getenv("AZURE_OPENAI_TOKEN_SCOPE", "https://cognitiveservices.azure.com/.default")

logger = logging.getLogger(__name__)


document_intelligence_client = DocumentIntelligenceClient(
    endpoint=DOCUMENT_INTELLIGENCE_ENDPOINT,
    credential=AzureKeyCredential(DOCUMENT_INTELLIGENCE_KEY),
)

credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _get_azure_ad_token(scope: str = AZURE_OPENAI_SCOPE) -> str:
    return credential.get_token(scope).token


def _build_openai_client() -> AzureOpenAI:
    client_kwargs: Dict[str, Any] = {
        "azure_endpoint": AZURE_OPENAI_ENDPOINT,
        "api_version": AZURE_OPENAI_API_VERSION,
    }

    if AZURE_OPENAI_AUTH_MODE == "api_key":
        if AZURE_OPENAI_KEY:
            client_kwargs["api_key"] = AZURE_OPENAI_KEY
        else:
            logger.warning(
                "AZURE_OPENAI_AUTH_MODE is set to 'api_key' but AZURE_OPENAI_API_KEY is missing; falling back to DefaultAzureCredential."
            )
            client_kwargs["azure_ad_token_provider"] = _get_azure_ad_token
    else:
        try:
            credential.get_token(AZURE_OPENAI_SCOPE)
            client_kwargs["azure_ad_token_provider"] = _get_azure_ad_token
        except Exception as exc:  # pragma: no cover - network credential check
            if AZURE_OPENAI_KEY:
                logger.warning(
                    "DefaultAzureCredential failed to acquire a token (%s); falling back to AZURE_OPENAI_API_KEY.",
                    exc,
                )
                client_kwargs.pop("azure_ad_token_provider", None)
                client_kwargs["api_key"] = AZURE_OPENAI_KEY
            else:
                raise RuntimeError(
                    "DefaultAzureCredential could not acquire a token and no API key fallback is configured."
                ) from exc

    return AzureOpenAI(**client_kwargs)


openai_client = _build_openai_client()

_SUMMARY_MODEL_CONFIG: Dict[str, Dict[str, Any]] = {
    "rfp": {
        "model_settings": get_model_settings("gpt5-mini"),
        "reasoning": get_reasoning_options("gpt5-mini"),
        "max_output_tokens": int(os.getenv("AZURE_OPENAI_GPT5_MINI_MAX_OUTPUT_TOKENS", "4096")),
        "temperature": 0.2,
    },
    "proposal": {
        "model_settings": get_model_settings("gpt5-mini"),
        "reasoning": get_reasoning_options("gpt5-mini"),
        "max_output_tokens": int(os.getenv("AZURE_OPENAI_GPT5_MINI_MAX_OUTPUT_TOKENS", "3072")),
        "temperature": 0.15,
    },
}

_PROMPTS: Dict[str, str] = {
    "rfp": (
        "You are summarizing a Request for Proposal (RFP). The RFP may be for any domain, and your summary should retain "
        "all critical information while ensuring clarity and organization. The summary **must be in Markdown format** "
        "with **clearly defined sections** that allow for easy comparison with vendor proposals.\n\n"
        "Ensure the summary contains the following sections:\n"
        "- **General Information** (Must include: Issued by, Release Date, Proposal Submission Deadline)\n"
        "- **Purpose** (Clearly state the objective of the RFP)\n"
        "- **Technical Requirements** (List any technical criteria, integrations, security expectations, or compliance frameworks)\n"
        "- **Functional Requirements** (Outline required features, user functionalities, and system expectations)\n"
        "- **Legal & Compliance Requirements** (Ensure ALL compliance-related information is included with proper section headers)\n"
        "- **Financial & Support Requirements** (Capture vendor financial stability expectations, SLA conditions, support availability)\n"
        "- **Evaluation Criteria** (Clearly highlight weightage factors if mentioned in the document)\n"
        "- **Submission Requirements** (Specify deadline, format, and proposal structure if provided)\n\n"
        "### Formatting Guidelines:\n"
        "- Use **bold headings** (##, ###) for section titles.\n"
        "- Preserve important **bullet points** and subpoints.\n"
        "- Ensure all compliance-related areas are clearly marked (e.g., Legal & Compliance).\n"
        "- If weightage is present in the RFP, **retain numerical evaluation weightage in the criteria section**.\n"
        "- If any section is missing in the document, **do not remove the section but note its absence**.\n"
        "Maintain the structure **even if some details are missing**, ensuring that missing sections are marked as 'Not specified in the RFP.'"
    ),
    "proposal": (
        "You are summarizing a vendor proposal. Extract all key details that may be required to evaluate the proposal comprehensively. "
        "Your summary must capture:\n"
        "- **Vendor Name**: The official name of the vendor.\n"
        "- **Legal Summary**: Key compliance, security, and regulatory commitments, including adherence to standards such as ISO 27001, SOC 2, GDPR, HIPAA, or any other relevant frameworks.\n"
        "- **Overall Summary**: A detailed overview of the proposal, including:\n"
        "  - **Solution Offering**: Describe the product or service being proposed, including key features and differentiators.\n"
        "  - **Security & Compliance**: Highlight encryption methods, data protection policies, and adherence to compliance frameworks.\n"
        "  - **Service-Level Agreements (SLA)**: Include response times, uptime guarantees, and escalation procedures.\n"
        "  - **Implementation Approach**: Summarize the deployment process, estimated timeline, and key milestones.\n"
        "  - **Financials & Pricing (CRITICAL)**: This is extremely important for procurement decisions. Extract ALL pricing information including:\n"
        "    - Total cost or price (exact figures if available)\n"
        "    - Pricing model (subscription, per-user, fixed fee, tiered, etc.)\n"
        "    - License costs and terms\n"
        "    - Implementation/setup fees\n"
        "    - Annual maintenance or support fees\n"
        "    - Any hidden costs, surcharges, or additional fees\n"
        "    - Payment terms and conditions\n"
        "    - Currency (USD, EUR, etc.)\n"
        "  - **Support & Customer Success**: Describe support models, availability (24/7, business hours), and dedicated account management options.\n"
        "  - **Past Performance & References**: Highlight past client engagements, case studies, or success stories that validate the vendor's capabilities.\n\n"
        "The **overall_summary** must include all major aspects of the proposal, ensuring the summary remains detailed and useful for decision-making.\n"
        "**IMPORTANT**: Always include a dedicated 'Pricing & Cost' section in the overall_summary with all financial details extracted from the proposal.\n"
        "Do not omit any critical financial, security, or SLA details even if they are not explicitly requested in the proposal document.\n"
        "If certain details are missing from the proposal, note them as 'Not specified in the proposal' instead of omitting them.\n\n"
    ),
}



class VendorProposalSummary(BaseModel):
    vendor_name: str
    legal_summary: str
    overall_summary: str


def analyze_document(file_obj) -> str:
    """Analyze the layout of an in-memory document using Azure Document Intelligence."""

    file_obj.seek(0)
    poller = document_intelligence_client.begin_analyze_document("prebuilt-layout", body=file_obj)
    result_json = poller.result()
    return result_json.content


def chunk_text(content: str, max_model_tokens: int, reserved_tokens: int = 1000) -> list[str]:
    """Chunk text into segments that respect model token limits."""

    max_tokens = max_model_tokens - reserved_tokens
    words = content.split()
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for word in words:
        word_length = len(word) + 1
        if current_length + word_length > max_tokens:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_length = word_length
        else:
            current_chunk.append(word)
            current_length += word_length

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def _extract_text_response(response) -> str:
    """Normalize OpenAI Responses API output to a plain text string."""

    output = getattr(response, "output", [])
    for item in output:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []):
            if getattr(content, "type", None) == "output_text":
                text_value = getattr(content, "text", "")
                if isinstance(text_value, str):
                    return text_value
    return ""


def _stringify_segments(segments: Iterable[Any]) -> str:
    """Join mixed-type segments into a single string payload."""

    serialized: list[str] = []
    for segment in segments:
        if isinstance(segment, str):
            serialized.append(segment)
        else:
            serialized.append(json.dumps(segment))
    return " ".join(serialized)


def summarize_chunk(chunk: str, doc_type: str) -> Any:
    """Summarize a content chunk using Azure OpenAI reasoning models via the Responses API."""

    if doc_type not in _SUMMARY_MODEL_CONFIG:
        raise ValueError(f"Unsupported document type '{doc_type}'.")

    config = _SUMMARY_MODEL_CONFIG[doc_type]
    model_settings = config["model_settings"]
    model_name = model_settings.get("deployment_name") or model_settings.get("model_id")
    if not model_name:
        raise ValueError("Model configuration must provide a deployment or model identifier.")

    reasoning_options = config.get("reasoning", {})
    base_kwargs: Dict[str, Any] = {
        "model": model_name,
        "max_output_tokens": config["max_output_tokens"],
        **reasoning_options,
    }
    if not reasoning_options and config.get("temperature") is not None:
        base_kwargs["temperature"] = config["temperature"]

    messages = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": _PROMPTS[doc_type]}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": chunk}],
        },
    ]

    if doc_type == "rfp":
        completion = openai_client.responses.create(input=messages, **base_kwargs)
        return _extract_text_response(completion)

    # For proposals, we use structured output.
    # However, if the model output is truncated or malformed, the parser will fail.
    # We wrap this in a try-except block to handle potential JSON errors gracefully.
    try:
        completion = openai_client.responses.parse(
            input=messages,
            text_format=VendorProposalSummary,
            **base_kwargs,
        )
        parsed = completion.output_parsed
        if parsed is not None:
            return parsed.model_dump()
    except Exception as e:
        logger.warning(f"Failed to parse structured response for proposal: {e}")
        # Fallback: try to get raw text if possible, or return a partial error dict
        # Since 'responses.parse' might not return the raw text easily on failure,
        # we might need to retry with a standard 'create' call or just return a generic error.
        
        # Let's try a standard create call as fallback to at least get the text
        try:
            fallback_completion = openai_client.responses.create(input=messages, **base_kwargs)
            raw_text = _extract_text_response(fallback_completion)
            return {
                "vendor_name": "Unknown (Parse Error)",
                "legal_summary": "Could not parse legal summary.",
                "overall_summary": raw_text
            }
        except Exception as fallback_error:
            logger.error(f"Fallback summarization also failed: {fallback_error}")
            return {
                "vendor_name": "Error",
                "legal_summary": "Error generating summary.",
                "overall_summary": "An error occurred while processing this document."
            }
            
    return {}


def save_summary(summary: Any, doc_type: str) -> Any:
    """Return a normalized summary payload for downstream consumption."""

    if doc_type == "rfp":
        return summary if isinstance(summary, str) else json.dumps(summary)

    if doc_type == "proposal":
        if isinstance(summary, dict):
            return {
                "vendor_name": str(summary.get("vendor_name", "Not specified")),
                "legal_summary": str(summary.get("legal_summary", "Not specified")),
                "overall_summary": str(summary.get("overall_summary", "Not specified")),
            }
        try:
            parsed_summary = json.loads(summary)
        except (json.JSONDecodeError, TypeError):
            return {
                "vendor_name": "Not specified",
                "legal_summary": "Not specified",
                "overall_summary": summary if isinstance(summary, str) else json.dumps(summary),
            }
        else:
            return {
                "vendor_name": str(parsed_summary.get("vendor_name", "Not specified")),
                "legal_summary": str(parsed_summary.get("legal_summary", "Not specified")),
                "overall_summary": str(parsed_summary.get("overall_summary", "Not specified")),
            }

    raise ValueError(f"Unsupported document type '{doc_type}'.")


def summarize_document(file_obj, doc_type: str) -> Any:
    """Summarize an in-memory document without saving it locally."""

    analyze_result = analyze_document(file_obj)
    chunks = chunk_text(analyze_result, 126000)

    if not chunks:
        return save_summary("", doc_type)

    if len(chunks) == 1:
        final_summary = summarize_chunk(chunks[0], doc_type)
    else:
        summaries = [summarize_chunk(chunk, doc_type) for chunk in chunks]
        combined_payload = _stringify_segments(summaries)
        final_summary = summarize_chunk(combined_payload, doc_type)

    return save_summary(final_summary, doc_type)
