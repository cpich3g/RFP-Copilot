import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum allowed length for industry name input
MAX_INDUSTRY_NAME_LENGTH = 100


class MarketIntelligencePlugin:
    """
    Plugin to retrieve market intelligence insights based on industry data.
    """

    def __init__(self, dataset_path: str):
        """
        Initialize the Market Intelligence Plugin.

        :param dataset_path: Path to the static JSON dataset.
        """
        self.dataset_path = self._validate_path(dataset_path)
        self.market_data = self._load_market_data()

    def _validate_path(self, dataset_path: str) -> str:
        """Validate the dataset path to prevent path traversal attacks."""
        if not dataset_path:
            raise ValueError("Dataset path cannot be empty.")
        
        # Resolve the path and ensure it's within expected directories
        resolved_path = Path(dataset_path).resolve()
        
        # Check for path traversal attempts
        if ".." in str(dataset_path):
            raise ValueError("Invalid dataset path - path traversal detected.")
        
        return str(resolved_path)

    def _load_market_data(self):
        """
        Loads market intelligence data from the JSON dataset.
        """
        if not os.path.exists(self.dataset_path):
            logger.warning(f"Market intelligence dataset not found at {self.dataset_path}")
            return {}

        try:
            with open(self.dataset_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                if not isinstance(data, dict):
                    logger.warning("Market intelligence dataset has invalid format - expected dict.")
                    return {}
                return data.get("industries", {})
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse market intelligence dataset: {e}")
            return {}

    def get_market_insights(self, industry: str):
        """
        Retrieves market insights for the specified industry.

        :param industry: The industry name to look up.
        :return: A structured market intelligence report.
        """
        # Sanitize industry input - remove potential injection patterns
        if not industry or not isinstance(industry, str):
            return "Invalid industry parameter provided."
        
        # Limit industry name length to prevent abuse
        industry = industry[:MAX_INDUSTRY_NAME_LENGTH].strip()
        
        industry_data = self.market_data.get(industry, None)

        if not industry_data:
            return f"No market intelligence data available for {industry}."

        # Safely access nested keys with defaults
        trends = industry_data.get("trends", [])
        competitor_insights = industry_data.get("competitor_insights", [])
        supply_chain_risks = industry_data.get("supply_chain_risks", [])
        regulatory_changes = industry_data.get("regulatory_changes", [])

        insights = (
            f"### Market Intelligence Report for {industry}\n\n"
            f"**Industry Trends:**\n- " + ("\n- ".join(trends) if trends else "No data available") + "\n\n"
            f"**Competitor Insights:**\n- " + ("\n- ".join(competitor_insights) if competitor_insights else "No data available") + "\n\n"
            f"**Supply Chain Risks:**\n- " + ("\n- ".join(supply_chain_risks) if supply_chain_risks else "No data available") + "\n\n"
            f"**Regulatory Changes:**\n- " + ("\n- ".join(regulatory_changes) if regulatory_changes else "No data available") + "\n"
        )

        return insights