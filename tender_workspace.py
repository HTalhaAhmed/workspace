from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
from uuid import uuid4


DEFAULT_TENDER_PORTALS = [
    "GlobalBid",
    "International Financial Tenders",
    "DG Market",
    "Global Public Procurement Database",
    "World Bank Projects",
    "ADB.org",
    "IADB.org",
    "African Development Bank Group",
    "UNGM",
    "Eurasian Development Bank",
    "ISDB",
    "IBADEA",
    "Global Municipal Tenders Aggregator",
]


@dataclass(frozen=True)
class TenderSource:
    name: str
    category: str = "global"
    endpoint: Optional[str] = None


@dataclass
class TenderOpportunity:
    opportunity_id: str
    title: str
    source: str
    country: str
    value_usd: float = 0.0
    stage: str = "discovered"


class TenderSourceCatalog:
    def __init__(self, sources: Optional[Iterable[TenderSource]] = None) -> None:
        self._sources: Dict[str, TenderSource] = {}
        for source in sources or []:
            self.add_source(source.name, source.category, source.endpoint)

    def add_source(self, name: str, category: str = "global", endpoint: Optional[str] = None) -> None:
        key = name.strip().lower()
        if not key:
            raise ValueError("Source name is required")
        self._sources[key] = TenderSource(name=name.strip(), category=category.strip().lower(), endpoint=endpoint)

    def register_municipal_portal(self, city: str, country: str, endpoint: Optional[str] = None) -> None:
        name = f"{city.strip()}, {country.strip()} Municipal Tenders"
        self.add_source(name=name, category="municipal", endpoint=endpoint)

    def has_source(self, name: str) -> bool:
        return name.strip().lower() in self._sources

    def list_sources(self, category: Optional[str] = None) -> List[TenderSource]:
        if category is None:
            return list(self._sources.values())
        category_key = category.strip().lower()
        return [source for source in self._sources.values() if source.category == category_key]


class ProposalWriter:
    def generate(
        self,
        opportunity: TenderOpportunity,
        company_name: str,
        strengths: List[str],
        meeting_notes: str = "",
    ) -> str:
        strengths_block = "\n".join(f"- {item}" for item in strengths) if strengths else "- To be refined"
        notes = meeting_notes.strip() or "No meeting notes captured yet."
        return (
            f"# Proposal Draft: {opportunity.title}\n\n"
            f"**Company:** {company_name}\n"
            f"**Source:** {opportunity.source}\n"
            f"**Country:** {opportunity.country}\n"
            f"**Estimated Value (USD):** {opportunity.value_usd:,.2f}\n\n"
            "## Why We Can Win\n"
            f"{strengths_block}\n\n"
            "## Delivery Approach\n"
            "1. Confirm compliance and eligibility requirements.\n"
            "2. Align technical and commercial offer to tender objectives.\n"
            "3. Submit clarifications early and maintain stakeholder follow-up.\n\n"
            "## Meeting Copilot Notes\n"
            f"{notes}\n"
        )


class LiveCopilot:
    def next_talk_track(self, opportunity: TenderOpportunity, stakeholder: str, objective: str) -> str:
        return (
            f"Talk track for {stakeholder}:\n"
            f"- Objective: {objective}\n"
            f"- Opportunity: {opportunity.title} ({opportunity.source})\n"
            "- Ask for evaluation criteria weighting and decision timeline.\n"
            "- Confirm any local compliance or municipal filing constraints.\n"
            "- Close with a concrete next step and owner."
        )


class MasterPipelineAgent:
    def __init__(self, catalog: TenderSourceCatalog, writer: ProposalWriter, copilot: LiveCopilot) -> None:
        self.catalog = catalog
        self.writer = writer
        self.copilot = copilot
        self._opportunities: Dict[str, TenderOpportunity] = {}

    def ingest_opportunity(self, title: str, source: str, country: str, value_usd: float = 0.0) -> TenderOpportunity:
        if not self.catalog.has_source(source):
            raise ValueError(f"Unknown tender source: {source}")
        opportunity_id = f"tdr-{uuid4().hex[:10]}"
        opportunity = TenderOpportunity(
            opportunity_id=opportunity_id,
            title=title.strip(),
            source=source.strip(),
            country=country.strip(),
            value_usd=value_usd,
        )
        self._opportunities[opportunity_id] = opportunity
        return opportunity

    def update_stage(self, opportunity_id: str, stage: str) -> None:
        self._opportunities[opportunity_id].stage = stage.strip().lower()

    def draft_proposal(
        self,
        opportunity_id: str,
        company_name: str,
        strengths: List[str],
        meeting_notes: str = "",
    ) -> str:
        return self.writer.generate(self._opportunities[opportunity_id], company_name, strengths, meeting_notes)

    def meeting_brief(self, opportunity_id: str, stakeholder: str, objective: str) -> str:
        return self.copilot.next_talk_track(self._opportunities[opportunity_id], stakeholder, objective)

    def monitor(self) -> Dict[str, int]:
        summary: Dict[str, int] = {"total": len(self._opportunities)}
        for item in self._opportunities.values():
            summary[item.stage] = summary.get(item.stage, 0) + 1
        return summary


def build_default_workspace() -> MasterPipelineAgent:
    catalog = TenderSourceCatalog(TenderSource(name=name) for name in DEFAULT_TENDER_PORTALS)
    return MasterPipelineAgent(catalog=catalog, writer=ProposalWriter(), copilot=LiveCopilot())
