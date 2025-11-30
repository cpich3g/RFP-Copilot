"""Plugin to retrieve market intelligence insights based on industry data."""

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MarketIntelligencePlugin:
    """Plugin to retrieve market intelligence insights based on industry data."""

    def __init__(self, dataset_path: str) -> None:
        """Initialize the Market Intelligence Plugin.

        Args:
            dataset_path: Path to the static JSON dataset.
        """
        self.dataset_path = dataset_path
        self._market_data: Optional[Dict[str, Any]] = None

    @property
    def market_data(self) -> Dict[str, Any]:
        """Lazy load and cache market data from the JSON dataset."""
        if self._market_data is None:
            self._market_data = self._load_market_data()
        return self._market_data

    def _load_market_data(self) -> Dict[str, Any]:
        """Load market intelligence data from the JSON dataset.
        
        Returns:
            Dictionary containing industry data, or empty dict on failure.
        """
        if not os.path.exists(self.dataset_path):
            logger.warning("Market intelligence dataset not found at %s", self.dataset_path)
            return {}

        try:
            with open(self.dataset_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                return data.get("industries", {})
        except json.JSONDecodeError as e:
            logger.error("Failed to parse market intelligence dataset: %s", e)
            return {}
        except OSError as e:
            logger.error("Failed to read market intelligence dataset: %s", e)
            return {}

    def get_market_insights(self, industry: str) -> str:
        """Retrieve market insights for the specified industry.

        Args:
            industry: The industry name to look up.
            
        Returns:
            A structured market intelligence report as a Markdown string.
        """
        industry_data = self.market_data.get(industry)

        if not industry_data:
            return f"No market intelligence data available for {industry}."

        # Build report with safe access to potentially missing keys
        sections = [f"### Market Intelligence Report for {industry}\n"]
        
        if trends := industry_data.get("trends"):
            sections.append("**Industry Trends:**\n- " + "\n- ".join(trends))
        
        if competitor_insights := industry_data.get("competitor_insights"):
            sections.append("\n**Competitor Insights:**\n- " + "\n- ".join(competitor_insights))
        
        if supply_chain_risks := industry_data.get("supply_chain_risks"):
            sections.append("\n**Supply Chain Risks:**\n- " + "\n- ".join(supply_chain_risks))
        
        if regulatory_changes := industry_data.get("regulatory_changes"):
            sections.append("\n**Regulatory Changes:**\n- " + "\n- ".join(regulatory_changes))

        return "\n".join(sections)