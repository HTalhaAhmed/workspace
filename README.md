# workspace

Minimal foundation for a **global AI procurement tender workspace** with:
- predefined global tender portals (including the requested sources)
- municipal portal registration support
- a master pipeline agent to track tender stages
- automatic proposal draft generation
- live meeting copilot talk tracks

## Included tender sources
`GlobalBid`, `International Financial Tenders`, `DG Market`, `Global Public Procurement Database`, `World Bank Projects`, `ADB.org`, `IADB.org`, `African Development Bank Group`, `UNGM`, `Eurasian Development Bank`, `ISDB`, `IBADEA`, `Global Municipal Tenders Aggregator`.

## Quick usage
```python
from tender_workspace import build_default_workspace

workspace = build_default_workspace()
workspace.catalog.register_municipal_portal("Toronto", "Canada")

tender = workspace.ingest_opportunity(
    title="Cloud Procurement Transformation",
    source="UNGM",
    country="Global",
    value_usd=750000,
)
workspace.update_stage(tender.opportunity_id, "proposal_drafting")

proposal = workspace.draft_proposal(
    tender.opportunity_id,
    company_name="Your Company",
    strengths=["Global compliance expertise", "Fast proposal automation"],
)

brief = workspace.meeting_brief(
    tender.opportunity_id,
    stakeholder="Procurement Lead",
    objective="Confirm evaluation timeline",
)
```

## Tests
Run:
```bash
python -m unittest discover -s tests -p 'test_*.py'
```
