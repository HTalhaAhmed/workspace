import unittest
from datetime import timedelta, timezone

from tender_workspace import DEFAULT_TENDER_PORTALS, _utcnow, build_default_workspace


class TenderWorkspaceTests(unittest.TestCase):
    def test_default_sources_include_requested_portals(self):
        workspace = build_default_workspace()
        names = {source.name for source in workspace.catalog.list_sources()}
        self.assertTrue(set(DEFAULT_TENDER_PORTALS).issubset(names))
        self.assertIn("OECM", names)
        self.assertIn("CanadaBuys", names)

    def test_blackout_blocks_outreach(self):
        workspace = build_default_workspace()
        opportunity = workspace.ingest_opportunity(
            title="Ontario Cloud Modernization",
            source="CanadaBuys",
            country="Canada",
            value_usd=300000,
        )
        workspace.set_blackout(opportunity.opportunity_id, True)
        with self.assertRaises(PermissionError):
            workspace.start_pre_solicitation_conversation(opportunity.opportunity_id, "Program Owner A")

    def test_ingestion_scoring_ranking_and_expiry(self):
        workspace = build_default_workspace()
        soon = (_utcnow() + timedelta(hours=6)).isoformat()
        later = (_utcnow() + timedelta(days=12)).isoformat()

        high_fit = workspace.ingest_portal_alert(
            "CanadaBuys",
            {
                "title": "Ontario Cloud Infrastructure and IT Services",
                "country": "Ontario, Canada",
                "summary": "Cloud and IT managed services for digital infrastructure.",
                "url": "https://example.test/a",
                "published_at": _utcnow().isoformat(),
                "closing_at": soon,
            },
        )
        low_fit = workspace.ingest_portal_alert(
            "GlobalBid",
            {
                "title": "General construction support",
                "country": "Chile",
                "summary": "Facilities upkeep",
                "url": "https://example.test/b",
                "published_at": _utcnow().isoformat(),
                "closing_at": later,
            },
        )

        ranked = workspace.weekly_ranked_list()
        self.assertEqual(ranked[0].opportunity_id, high_fit.opportunity_id)
        self.assertGreater(high_fit.fit_score, low_fit.fit_score)

        expiring = workspace.expiry_radar(hours=12)
        self.assertEqual(len(expiring), 1)
        self.assertEqual(expiring[0].opportunity_id, high_fit.opportunity_id)

    def test_gate_flow_feedback_and_success_metrics(self):
        workspace = build_default_workspace()
        opportunity = workspace.ingest_portal_alert(
            "OECM",
            {
                "title": "Ontario Digital Cloud Enablement",
                "country": "Ontario, Canada",
                "summary": "Cloud IT transformation for municipal services",
                "url": "https://example.test/c",
                "published_at": _utcnow().isoformat(),
            },
        )

        gate0 = workspace.apply_gate_0(opportunity.opportunity_id, ["SBIPS", "P2P"], required_vehicle="SBIPS")
        self.assertTrue(gate0.passed)

        gate1 = workspace.apply_gate_1(opportunity.opportunity_id, estimated_bid_hours=100, historical_win_rate=0.2)
        self.assertTrue(gate1.passed)

        workspace.add_bid_feedback(
            opportunity.opportunity_id,
            bid_cost_hours=95,
            debrief_obtained=True,
            scoring_breakdown={"technical": 82.0, "price": 76.0},
        )
        for idx in range(5):
            workspace.log_program_owner_meeting(f"Owner {idx}")
        workspace.log_pre_rfp_signal("Council cloud budget uplift", _utcnow() + timedelta(days=30), "council agenda")
        workspace.log_pre_rfp_signal("Departmental IT plan", _utcnow() + timedelta(days=45), "federal plan")

        metrics = workspace.success_metrics()
        self.assertTrue(metrics["all_goals_met"])

    def test_approval_and_portal_connector_scaffold(self):
        workspace = build_default_workspace()
        workspace.require_procurement_approval("IT manager")
        with self.assertRaises(PermissionError):
            workspace.require_procurement_approval("procurement intern")

        logged_in = workspace.connect_account("sap", {"username": "demo", "password": "secret"})
        self.assertTrue(logged_in)
        result = workspace.maneuver_account("sap", "open active procurements")
        self.assertEqual(result["status"], "queued")


if __name__ == "__main__":
    unittest.main()
