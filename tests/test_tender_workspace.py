import unittest

from tender_workspace import DEFAULT_TENDER_PORTALS, build_default_workspace


class TenderWorkspaceTests(unittest.TestCase):
    def test_default_sources_include_requested_portals(self):
        workspace = build_default_workspace()
        names = {source.name for source in workspace.catalog.list_sources()}
        self.assertTrue(set(DEFAULT_TENDER_PORTALS).issubset(names))

    def test_pipeline_monitor_and_stage_updates(self):
        workspace = build_default_workspace()
        opportunity = workspace.ingest_opportunity(
            title="AI Procurement Enablement",
            source="UNGM",
            country="Global",
            value_usd=500000,
        )
        workspace.update_stage(opportunity.opportunity_id, "proposal_drafting")
        summary = workspace.monitor()
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["proposal_drafting"], 1)

    def test_proposal_and_meeting_copilot_outputs(self):
        workspace = build_default_workspace()
        opportunity = workspace.ingest_opportunity(
            title="Municipal Smart Infrastructure",
            source="GlobalBid",
            country="Canada",
            value_usd=1200000,
        )
        proposal = workspace.draft_proposal(
            opportunity.opportunity_id,
            company_name="Example Procurement AI",
            strengths=["Strong municipal delivery history", "Automated compliance workflows"],
            meeting_notes="Stakeholder asked for local references.",
        )
        brief = workspace.meeting_brief(
            opportunity.opportunity_id,
            stakeholder="City Procurement Director",
            objective="Secure shortlist confirmation",
        )
        self.assertIn("Proposal Draft", proposal)
        self.assertIn("Example Procurement AI", proposal)
        self.assertIn("Secure shortlist confirmation", brief)


if __name__ == "__main__":
    unittest.main()
