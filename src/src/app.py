import json
import os
import logging
from functools import lru_cache
from typing import Any, Dict

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential
from jinja2 import Environment, FileSystemLoader

# Define agent names
AGENT_NAMES = {
    "rfp_compliance": "RFPCompliance",
    "legal_compliance": "LegalCompliance",
    "vendor_evaluation": "VendorEvaluation",
    "market_intelligence": "MarketIntelligence",
    "negotiation_strategy": "NegotiationStrategy",
    "evaluation_report": "EvaluationReport",
}
BID_COMPARISON_AGENT = "BidComparisonStrategist"
NEGOTIATION_PREBRIEF_AGENT = "NegotiationPrebriefAgent"
NEGOTIATION_LIVE_AGENT = "NegotiationLiveCopilot"

logger = logging.getLogger(__name__)

_MODEL_VARIANTS: Dict[str, Dict[str, Any]] = {
    "gpt5-mini": {
        "deployment_env": "AZURE_OPENAI_GPT5_MINI_DEPLOYMENT_NAME",
        "reasoning_effort": os.environ.get("AZURE_OPENAI_GPT5_MINI_REASONING_EFFORT", "medium"),
        "service_tier": os.environ.get("AZURE_OPENAI_GPT5_MINI_SERVICE_TIER"),
    },
    "gpt5": {
        "deployment_env": "AZURE_OPENAI_GPT5_DEPLOYMENT_NAME",
        "reasoning_effort": os.environ.get("AZURE_OPENAI_GPT5_REASONING_EFFORT", "high"),
        "service_tier": os.environ.get("AZURE_OPENAI_GPT5_SERVICE_TIER", "priority"),
    },
}

_LEGACY_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
_credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
_azure_oai_scope = os.environ.get("AZURE_OPENAI_TOKEN_SCOPE", "https://cognitiveservices.azure.com/.default")


def _resolve_model_settings(model_variant: str) -> Dict[str, Any]:
    variant = model_variant.lower()
    config = _MODEL_VARIANTS.get(variant)
    if not config:
        raise ValueError(f"Unsupported model variant '{model_variant}'. Supported variants: {list(_MODEL_VARIANTS)}")

    deployment_name = os.environ.get(config["deployment_env"]) or (
        os.environ.get(_LEGACY_DEPLOYMENT_ENV) if variant == "gpt5-mini" else None
    )

    if not deployment_name:
        raise ValueError(
            f"Environment variable '{config['deployment_env']}' is required for model variant '{model_variant}'."
        )

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT environment variable must be set.")

    return {
        "endpoint": endpoint,
        "deployment_name": deployment_name,
        "reasoning_effort": config.get("reasoning_effort"),
        "service_tier": config.get("service_tier"),
    }


def get_reasoning_options(model_variant: str) -> Dict[str, Any]:
    """Return provider-specific reasoning options for the requested model variant."""

    settings = _resolve_model_settings(model_variant)
    options: Dict[str, Any] = {}
    if settings.get("reasoning_effort"):
        options.setdefault("reasoning", {"effort": settings["reasoning_effort"]})
    if settings.get("service_tier"):
        options.setdefault("service_tier", settings["service_tier"])
    return options


def get_model_settings(model_variant: str) -> Dict[str, Any]:
    """Expose resolved model configuration (endpoint, deployment, reasoning defaults)."""

    return _resolve_model_settings(model_variant).copy()


@lru_cache(maxsize=None)
def create_chat_client(*, model_variant: str = "gpt5-mini") -> AzureOpenAIChatClient:
    """Instantiate an Azure OpenAI chat client for the requested model variant."""

    settings = _resolve_model_settings(model_variant)

    client_kwargs: dict[str, object] = {
        "endpoint": settings["endpoint"],
        "deployment_name": settings["deployment_name"],
    }

    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    auth_mode = os.environ.get("AZURE_OPENAI_AUTH_MODE", "default_credential").lower()

    def _get_token() -> str:
        return _credential.get_token(_azure_oai_scope).token

    if auth_mode == "api_key":
        if api_key:
            client_kwargs["api_key"] = api_key
        else:
            logger.warning(
                "AZURE_OPENAI_AUTH_MODE is set to 'api_key' but AZURE_OPENAI_API_KEY is missing; falling back to DefaultAzureCredential."
            )
            client_kwargs["ad_token_provider"] = _get_token
    else:
        if api_key and auth_mode not in {"default_credential", "managed_identity"}:
            logger.info(
                "Using DefaultAzureCredential for Azure OpenAI (override mode '%s'); API key is available as manual fallback.",
                auth_mode,
            )
        try:
            _credential.get_token(_azure_oai_scope)
            client_kwargs["ad_token_provider"] = _get_token
        except Exception as exc:  # pragma: no cover - network credential check
            if api_key:
                logger.warning(
                    "DefaultAzureCredential failed to acquire a token (%s); falling back to AZURE_OPENAI_API_KEY.",
                    exc,
                )
                client_kwargs.pop("ad_token_provider", None)
                client_kwargs["api_key"] = api_key
            else:
                raise RuntimeError(
                    "DefaultAzureCredential could not acquire a token and no API key fallback is configured."
                ) from exc

    api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
    if api_version:
        client_kwargs["api_version"] = api_version

    return AzureOpenAIChatClient(**client_kwargs)

# Function to extract agent prompts
def get_agent_prompts() -> dict:
    """Loads agent prompts from a Jinja template."""
    # Path to the directory of app.py
    script_dir = os.path.dirname(__file__)
    env = Environment(loader=FileSystemLoader(script_dir))
    template = env.get_template("agent_prompts.jinja")
    
    try:
        return json.loads(template.render())
    except json.JSONDecodeError as e:
        print(f"\n[ERROR] Jinja Prompt - JSON Parsing Failed: {e}")
        return {}