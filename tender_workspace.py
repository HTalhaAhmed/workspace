from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import time
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4


DEFAULT_TENDER_PORTALS = [
    "GlobalBid",
    "International Financial Tenders",
    "DG Market",
    "Global Public Procurement Database",
    "World Bank Projects",
    "World Bank Procurement",
    "ADB.org",
    "IADB.org",
    "African Development Bank Group",
    "UNGM",
    "Eurasian Development Bank",
    "ISDB",
    "IBADEA",
    "Global Municipal Tenders Aggregator",
    "CanadaBuys",
    "Ontario Tenders Portal",
    "MERX",
    "BC Bid",
    "Alberta Purchasing Connection",
    "Bids and Tenders",
    "Euna Network",
    "OECM",
]

SOURCE_ALIASES = {
    "world bank procurement": "World Bank Procurement",
    "world bank projects": "World Bank Projects",
    "canada buy": "CanadaBuys",
    "canadabuys": "CanadaBuys",
    "ontario tender": "Ontario Tenders Portal",
    "ontario tenders": "Ontario Tenders Portal",
    "merx": "MERX",
    "bc bid": "BC Bid",
    "alberta": "Alberta Purchasing Connection",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    published_at: Optional[datetime] = None
    closing_at: Optional[datetime] = None
    fit_score: float = 0.0
    blackout_flag: bool = False
    pre_blackout_stage: Optional[str] = None
    bid_cost_hours: float = 0.0
    debrief_booked: bool = False
    scoring_breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionRecord:
    title: str
    source: str
    country: str
    summary: str
    url: str
    published_at: datetime
    closing_at: Optional[datetime] = None


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    reason: str


@dataclass(frozen=True)
class ContactNode:
    name: str
    organization: str
    role: str
    source: str
    email: Optional[str] = None


@dataclass(frozen=True)
class PreRFPSignal:
    description: str
    estimated_release_date: datetime
    source: str
    logged_at: datetime


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


class IngestionAndScoringEngine:
    def normalize_alert(self, source: str, payload: Dict[str, str]) -> IngestionRecord:
        published_at = self._parse_datetime(payload.get("published_at"), field_name="published_at")
        closing_at = self._parse_datetime(payload.get("closing_at"), required=False, field_name="closing_at")
        return IngestionRecord(
            title=payload.get("title", "Untitled Tender").strip(),
            source=source.strip(),
            country=payload.get("country", "Unknown").strip(),
            summary=payload.get("summary", "").strip(),
            url=payload.get("url", "").strip(),
            published_at=published_at,
            closing_at=closing_at,
        )

    def llm_fit_score(self, record: IngestionRecord, focus_region: str = "ontario") -> float:
        text = f"{record.title} {record.summary} {record.country}".lower()
        tokens = set(re.findall(r"[a-z0-9]+", text))
        source_key = self._normalize_source_name(record.source)
        score = 0.0

        if focus_region.lower() in text:
            score += 35

        for keyword in ("cloud", "it", "digital", "infrastructure", "saas"):
            if keyword == "it":
                if keyword in tokens:
                    score += 12
            elif keyword in text:
                score += 12

        if source_key in {
            "canadabuys",
            "oecm",
            "bidsandtenders",
            "eunanetwork",
            "albertapurchasingconnection",
        }:
            score += 10

        now = _utcnow()
        age = now - record.published_at
        if timedelta(0) <= age <= timedelta(hours=24):
            score += 12

        return min(score, 100.0)

    @staticmethod
    def _normalize_source_name(source: str) -> str:
        return "".join(char for char in source.lower() if char.isalnum())

    @staticmethod
    def _parse_datetime(value: Optional[str], required: bool = True, field_name: str = "datetime") -> Optional[datetime]:
        if not value:
            if required:
                raise ValueError(f"Missing required datetime field: {field_name}")
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Invalid datetime format for {field_name}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed


class GateKeeper:
    def gate_0(self, qualified_vehicles: Sequence[str], required_vehicle: Optional[str] = None) -> GateDecision:
        if required_vehicle and required_vehicle not in set(qualified_vehicles):
            return GateDecision(False, f"Missing required vehicle: {required_vehicle}")
        if not qualified_vehicles:
            return GateDecision(False, "No eligible vehicles approved by Gate 0")
        return GateDecision(True, "Gate 0 passed")

    def gate_1(self, fit_score: float, estimated_bid_hours: float, historical_win_rate: float) -> GateDecision:
        if fit_score < 60:
            return GateDecision(False, "Gate 1 rejected due to low fit score")
        if historical_win_rate < 0.12 and estimated_bid_hours >= 80:
            return GateDecision(False, "Gate 1 rejected: high bid volume with weak win rate burns cash")
        return GateDecision(True, "Gate 1 passed")


class ExpiryRadar:
    def upcoming(self, opportunities: Iterable[TenderOpportunity], hours: int = 72) -> List[TenderOpportunity]:
        now = _utcnow()
        threshold = now + timedelta(hours=hours)
        expiring = [
            item
            for item in opportunities
            if item.closing_at is not None and now <= item.closing_at <= threshold
        ]
        return sorted(expiring, key=lambda item: item.closing_at or datetime.max.replace(tzinfo=timezone.utc))


class ApprovalPolicy:
    def __init__(self) -> None:
        self.allowed_approvers = {
            "it manager",
            "director",
            "finance department",
            "council",
        }

    def can_approve(self, role: str) -> bool:
        return role.strip().lower() in self.allowed_approvers

    def require_approval(self, role: str) -> None:
        if not self.can_approve(role):
            raise PermissionError("Approver role is not authorized for procurement")


class OutreachGuard:
    def require_safe_outreach(self, opportunity: TenderOpportunity) -> None:
        if opportunity.blackout_flag or opportunity.stage == "open_solicitation":
            raise PermissionError("Outreach blocked during open solicitation blackout window")


class ContactGraphBuilder:
    def build(
        self,
        geds_contacts: Sequence[Dict[str, str]],
        municipal_directory_contacts: Sequence[Dict[str, str]],
        report_authors: Sequence[Dict[str, str]],
    ) -> List[ContactNode]:
        merged = [*geds_contacts, *municipal_directory_contacts, *report_authors]
        nodes: List[ContactNode] = []
        seen: set[Tuple[str, str, str]] = set()
        for item in merged:
            key = (
                item.get("name", "").strip().lower(),
                item.get("organization", "").strip().lower(),
                item.get("role", "").strip().lower(),
            )
            if not key[0] or key in seen:
                continue
            seen.add(key)
            nodes.append(
                ContactNode(
                    name=item.get("name", "").strip(),
                    organization=item.get("organization", "").strip(),
                    role=item.get("role", "").strip(),
                    source=item.get("source", "directory").strip(),
                    email=item.get("email", "").strip() or None,
                )
            )
        return nodes


class PortalConnector:
    def __init__(self, name: str) -> None:
        self.name = name
        self.logged_in = False

    def login(self, credentials: Dict[str, str]) -> bool:
        if credentials.get("mock_auth_token") == "allow":
            self.logged_in = True
        return self.logged_in

    def search(self, query: str) -> Dict[str, str]:
        if not self.logged_in:
            raise PermissionError(f"Login required for {self.name}")
        return {"portal": self.name, "query": query, "status": "queued"}


class ProcurementSiteScraper:
    def scrape(self) -> List[Dict[str, str]]:
        raise NotImplementedError


class StaticProcurementSiteScraper(ProcurementSiteScraper):
    def __init__(self, records: Sequence[Dict[str, str]]) -> None:
        self._records = [dict(item) for item in records]

    def scrape(self) -> List[Dict[str, str]]:
        return [dict(item) for item in self._records]


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
            f"**Estimated Value (USD):** {opportunity.value_usd:,.2f}\n"
            f"**Fit Score:** {opportunity.fit_score:.1f}\n\n"
            "## Why We Can Win\n"
            f"{strengths_block}\n\n"
            "## Delivery Approach\n"
            "1. Confirm compliance and eligibility requirements.\n"
            "2. Build a mandatory-by-mandatory compliance matrix before drafting narrative.\n"
            "3. Attach named evidence and references tied to the scoring grid.\n"
            "4. Run red-team review before submission.\n\n"
            "## Meeting Copilot Notes\n"
            f"{notes}\n"
        )


class LiveCopilot:
    def next_talk_track(self, opportunity: TenderOpportunity, stakeholder: str, objective: str) -> str:
        return (
            f"Talk track for {stakeholder}:\n"
            f"- Objective: {objective}\n"
            f"- Opportunity: {opportunity.title} ({opportunity.source})\n"
            "- Keep discussion at capability-briefing level (no ask) during pre-solicitation.\n"
            "- Ask for expected release timing and decision criteria.\n"
            "- Confirm owner for follow-up and next meeting date."
        )


class MasterPipelineAgent:
    def __init__(
        self,
        catalog: TenderSourceCatalog,
        writer: ProposalWriter,
        copilot: LiveCopilot,
        ingestion_engine: Optional[IngestionAndScoringEngine] = None,
        gate_keeper: Optional[GateKeeper] = None,
        expiry_radar: Optional[ExpiryRadar] = None,
        approval_policy: Optional[ApprovalPolicy] = None,
        outreach_guard: Optional[OutreachGuard] = None,
        contact_graph_builder: Optional[ContactGraphBuilder] = None,
    ) -> None:
        self.catalog = catalog
        self.writer = writer
        self.copilot = copilot
        self.ingestion_engine = ingestion_engine or IngestionAndScoringEngine()
        self.gate_keeper = gate_keeper or GateKeeper()
        self.expiry_radar_engine = expiry_radar or ExpiryRadar()
        self.approval_policy = approval_policy or ApprovalPolicy()
        self.outreach_guard = outreach_guard or OutreachGuard()
        self.contact_graph_builder = contact_graph_builder or ContactGraphBuilder()
        self._opportunities: Dict[str, TenderOpportunity] = {}
        self._signals: List[PreRFPSignal] = []
        self._contacts: List[ContactNode] = []
        self._program_owner_meetings: set[str] = set()
        self._ingested_record_keys: set[str] = set()
        self._record_to_opportunity_id: Dict[str, str] = {}
        self._scrapers: Dict[str, ProcurementSiteScraper] = {}
        self._connectors: Dict[str, PortalConnector] = {
            "sap": PortalConnector("SAP"),
            "alberta_connections": PortalConnector("Alberta Purchasing Connection"),
            "bids_and_tenders": PortalConnector("Bids and Tenders"),
            "euna": PortalConnector("Euna Network"),
        }

    def ingest_opportunity(
        self,
        title: str,
        source: str,
        country: str,
        value_usd: float = 0.0,
        published_at: Optional[datetime] = None,
        closing_at: Optional[datetime] = None,
    ) -> TenderOpportunity:
        canonical_source = self._resolve_source_alias(source)
        if not self.catalog.has_source(canonical_source):
            raise ValueError(f"Unknown tender source: {source}")
        opportunity_id = f"tdr-{uuid4().hex[:10]}"
        opportunity = TenderOpportunity(
            opportunity_id=opportunity_id,
            title=title.strip(),
            source=canonical_source,
            country=country.strip(),
            value_usd=value_usd,
            published_at=published_at,
            closing_at=closing_at,
        )
        self._opportunities[opportunity_id] = opportunity
        return opportunity

    def ingest_portal_alert(self, source: str, payload: Dict[str, str], value_usd: float = 0.0) -> TenderOpportunity:
        canonical_source = self._resolve_source_alias(source)
        if not self.catalog.has_source(canonical_source):
            available_sources = ", ".join(sorted(item.name for item in self.catalog.list_sources()))
            raise ValueError(
                f"Unknown tender source: {source}. Register the source before ingestion. "
                f"Supported sources: {available_sources}"
            )
        record_key = self._scrape_record_key(canonical_source, payload)
        existing_opportunity_id = self._record_to_opportunity_id.get(record_key)
        if existing_opportunity_id is not None:
            return self._opportunities[existing_opportunity_id]
        record = self.ingestion_engine.normalize_alert(canonical_source, payload)
        opportunity = self.ingest_opportunity(
            title=record.title,
            source=canonical_source,
            country=record.country,
            value_usd=value_usd,
            published_at=record.published_at,
            closing_at=record.closing_at,
        )
        opportunity.fit_score = self.ingestion_engine.llm_fit_score(record)
        opportunity.stage = "triage"
        self._record_to_opportunity_id[record_key] = opportunity.opportunity_id
        self._ingested_record_keys.add(record_key)
        return opportunity

    def register_scraper(self, source: str, scraper: ProcurementSiteScraper) -> None:
        canonical_source = self._resolve_source_alias(source)
        if not self.catalog.has_source(canonical_source):
            raise ValueError(f"Unknown tender source for scraper: {source}")
        self._scrapers[canonical_source] = scraper

    def scrape_and_ingest_sources(self, sources: Optional[Sequence[str]] = None, value_usd: float = 0.0) -> List[TenderOpportunity]:
        if sources is None:
            resolved_sources = list(self._scrapers.keys())
        else:
            resolved_sources = []
            for name in sources:
                if not isinstance(name, str):
                    raise ValueError("Source names must be strings")
                stripped_name = name.strip()
                if not stripped_name:
                    continue
                resolved_sources.append(self._resolve_source_alias(stripped_name))
        selected_sources: List[str] = []
        seen_sources: set[str] = set()
        for source_name in resolved_sources:
            if source_name in seen_sources:
                continue
            seen_sources.add(source_name)
            selected_sources.append(source_name)
        ingested: List[TenderOpportunity] = []
        for source_name in selected_sources:
            scraper = self._scrapers.get(source_name)
            if scraper is None:
                raise ValueError(f"No scraper registered for source: {source_name}")
            for payload in scraper.scrape():
                record_key = self._scrape_record_key(source_name, payload)
                if record_key in self._ingested_record_keys:
                    continue
                ingested.append(self.ingest_portal_alert(source_name, payload, value_usd=value_usd))
                self._ingested_record_keys.add(record_key)
        return ingested

    def run_pipeline_loop(
        self,
        iterations: int = 1,
        sources: Optional[Sequence[str]] = None,
        value_usd: float = 0.0,
        interval_seconds: float = 0.0,
    ) -> List[Dict[str, int]]:
        if iterations < 0:
            raise ValueError("iterations must be non-negative")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")

        cycle_results: List[Dict[str, int]] = []
        for cycle in range(iterations):
            ingested = self.scrape_and_ingest_sources(sources=sources, value_usd=value_usd)
            cycle_results.append({
                "cycle": cycle + 1,
                "ingested": len(ingested),
                "total": len(self._opportunities),
            })
            if interval_seconds > 0 and cycle < iterations - 1:
                time.sleep(interval_seconds)

        return cycle_results

    def apply_gate_0(self, opportunity_id: str, qualified_vehicles: Sequence[str], required_vehicle: Optional[str] = None) -> GateDecision:
        decision = self.gate_keeper.gate_0(qualified_vehicles=qualified_vehicles, required_vehicle=required_vehicle)
        self._opportunities[opportunity_id].stage = "gate0_pass" if decision.passed else "killed_gate0"
        return decision

    def apply_gate_1(self, opportunity_id: str, estimated_bid_hours: float, historical_win_rate: float) -> GateDecision:
        opportunity = self._opportunities[opportunity_id]
        decision = self.gate_keeper.gate_1(
            fit_score=opportunity.fit_score,
            estimated_bid_hours=estimated_bid_hours,
            historical_win_rate=historical_win_rate,
        )
        opportunity.stage = "pursuit" if decision.passed else "killed_gate1"
        return decision

    def set_blackout(self, opportunity_id: str, is_open_solicitation: bool) -> None:
        opportunity = self._opportunities[opportunity_id]
        was_blackout = opportunity.blackout_flag
        if is_open_solicitation:
            if not was_blackout:
                opportunity.pre_blackout_stage = opportunity.pre_blackout_stage or opportunity.stage
                opportunity.stage = "open_solicitation"
            opportunity.blackout_flag = True
        else:
            opportunity.blackout_flag = False
            if was_blackout and opportunity.stage == "open_solicitation":
                opportunity.stage = opportunity.pre_blackout_stage or "triage"
            opportunity.pre_blackout_stage = None

    def start_pre_solicitation_conversation(self, opportunity_id: str, contact_name: str) -> str:
        opportunity = self._opportunities[opportunity_id]
        self.outreach_guard.require_safe_outreach(opportunity)
        opportunity.stage = "pre_solicitation_outreach"
        return f"Capability briefing initiated with {contact_name} for {opportunity.title}"

    def register_contacts(
        self,
        geds_contacts: Sequence[Dict[str, str]],
        municipal_directory_contacts: Sequence[Dict[str, str]],
        report_authors: Sequence[Dict[str, str]],
    ) -> List[ContactNode]:
        self._contacts = self.contact_graph_builder.build(
            geds_contacts=geds_contacts,
            municipal_directory_contacts=municipal_directory_contacts,
            report_authors=report_authors,
        )
        return list(self._contacts)

    def log_program_owner_meeting(self, owner_name: str) -> None:
        self._program_owner_meetings.add(owner_name.strip())

    def log_pre_rfp_signal(self, description: str, estimated_release_date: datetime, source: str) -> None:
        normalized_release_date = self._normalize_datetime(estimated_release_date)
        self._signals.append(
            PreRFPSignal(
                description=description.strip(),
                estimated_release_date=normalized_release_date,
                source=source.strip(),
                logged_at=_utcnow(),
            )
        )

    def list_signals(self) -> List[PreRFPSignal]:
        return list(self._signals)

    def weekly_ranked_list(self, limit: int = 25) -> List[TenderOpportunity]:
        ranked = sorted(
            self._opportunities.values(),
            key=lambda item: (
                -item.fit_score,
                item.closing_at or datetime.max.replace(tzinfo=timezone.utc),
            ),
        )
        return ranked[:limit]

    def expiry_radar(self, hours: int = 72) -> List[TenderOpportunity]:
        return self.expiry_radar_engine.upcoming(self._opportunities.values(), hours=hours)

    def update_stage(self, opportunity_id: str, stage: str) -> None:
        self._opportunities[opportunity_id].stage = stage.strip().lower()

    def add_bid_feedback(
        self,
        opportunity_id: str,
        bid_cost_hours: float,
        debrief_obtained: bool,
        scoring_breakdown: Optional[Dict[str, float]] = None,
    ) -> None:
        opportunity = self._opportunities[opportunity_id]
        opportunity.bid_cost_hours = bid_cost_hours
        opportunity.debrief_booked = debrief_obtained
        opportunity.scoring_breakdown = scoring_breakdown or {}

    def require_procurement_approval(self, approver_role: str) -> None:
        self.approval_policy.require_approval(approver_role)

    def connect_account(self, account_name: str, credentials: Dict[str, str]) -> bool:
        connector = self._get_connector(account_name)
        return connector.login(credentials)

    def maneuver_account(self, account_name: str, query: str) -> Dict[str, str]:
        connector = self._get_connector(account_name)
        return connector.search(query)

    def _get_connector(self, account_name: str) -> PortalConnector:
        key = account_name.strip().lower()
        connector = self._connectors.get(key)
        if connector is None:
            supported = ", ".join(sorted(self._connectors.keys()))
            raise ValueError(f"Unsupported account connector: {account_name}. Supported: {supported}")
        return connector

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Datetime values must include timezone information")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _resolve_source_alias(source: str) -> str:
        stripped = source.strip()
        return SOURCE_ALIASES.get(stripped.lower(), stripped)

    @staticmethod
    def _scrape_record_key(source: str, payload: Dict[str, str]) -> str:
        source_key = source.strip().lower()
        url = payload.get("url", "").strip().lower()
        if url:
            return f"{source_key}|{url}"
        title = payload.get("title", "").strip().lower()
        published_at = payload.get("published_at", "").strip().lower()
        return f"{source_key}|{title}|{published_at}"

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
        summary: Dict[str, int] = {"total": len(self._opportunities), "signals": len(self._signals)}
        for item in self._opportunities.values():
            summary[item.stage] = summary.get(item.stage, 0) + 1
        return summary

    def success_metrics(self) -> Dict[str, object]:
        return {
            "named_program_owners_with_meetings": len(self._program_owner_meetings),
            "pre_rfp_signals_logged": len(self._signals),
            "target_meeting_goal_met": len(self._program_owner_meetings) >= 5,
            "target_pre_rfp_goal_met": len(self._signals) >= 2,
            "all_goals_met": len(self._program_owner_meetings) >= 5 and len(self._signals) >= 2,
        }


def build_default_workspace() -> MasterPipelineAgent:
    catalog = TenderSourceCatalog(TenderSource(name=name) for name in DEFAULT_TENDER_PORTALS)
    return MasterPipelineAgent(catalog=catalog, writer=ProposalWriter(), copilot=LiveCopilot())
