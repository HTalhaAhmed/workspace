# workspace

Automation-oriented foundation for a **mass tender outreach workspace** designed for AWS deployment.

## What this now supports
- Global + Canadian source catalog (including **CanadaBuys, Alberta Purchasing Connection, Bids and Tenders, Euna Network, OECM**)
- Municipal portal registration and contact-graph ingestion inputs (GEDS/directories/report authors)
- Normalized portal-alert ingestion schema
- LLM-style fit scoring and weekly ranked review list
- Expiry radar for near-closing opportunities
- Gate 0 and Gate 1 checks to enforce qualification discipline
- Outreach blackout guard for open solicitations (prevents disqualifying outbound)
- Procurement approval policy restricted to: **IT manager, director, finance department, council**
- Proposal drafting with compliance-first structure
- Success metric tracking for meetings and pre-RFP signals
- Account connector scaffolding for **SAP**, **Alberta connections**, **Bids and Tenders**, and **Euna**

## Quick usage
```python
from datetime import timedelta
from tender_workspace import _utcnow, build_default_workspace

workspace = build_default_workspace()

# Register municipal portals and contact graph inputs
workspace.catalog.register_municipal_portal("Toronto", "Canada")
contacts = workspace.register_contacts(
    geds_contacts=[{"name": "Alex Smith", "organization": "Gov", "role": "Program Owner", "source": "GEDS"}],
    municipal_directory_contacts=[],
    report_authors=[],
)

# Ingest alerts from tender portals
opportunity = workspace.ingest_portal_alert("CanadaBuys", {
    "title": "Ontario Cloud IT Services",
    "country": "Ontario, Canada",
    "summary": "Cloud and IT modernization",
    "url": "https://example.test/tender",
    "published_at": _utcnow().isoformat(),
    "closing_at": (_utcnow() + timedelta(days=7)).isoformat(),
})

# Run gates and safe outreach
workspace.apply_gate_0(opportunity.opportunity_id, ["SBIPS"], required_vehicle="SBIPS")
workspace.apply_gate_1(opportunity.opportunity_id, estimated_bid_hours=90, historical_win_rate=0.2)
workspace.start_pre_solicitation_conversation(opportunity.opportunity_id, "Program Owner")

# Track outcomes and success targets
workspace.log_program_owner_meeting("Program Owner")
workspace.log_pre_rfp_signal("Council budget signal", _utcnow() + timedelta(days=30), "council agenda")
metrics = workspace.success_metrics()
```

## Important implementation note
The portal connectors are safe scaffolds for orchestration and integration testing. For production login/navigation in SAP or tender portals, wire these methods to your secure AWS secret manager, browser automation, and compliance controls.

## Tests
Run:
```bash
python -m unittest discover -s tests -p 'test_*.py'
```
