import unittest
from datetime import timedelta

from tender_workspace import DEFAULT_TENDER_PORTALS, StaticProcurementSiteScraper, _utcnow, build_default_workspace


class TenderWorkspaceTests(unittest.TestCase):
    def test_default_sources_include_requested_portals(self):
        workspace = build_default_workspace()
        names = {source.name for source in workspace.catalog.list_sources()}
        self.assertTrue(set(DEFAULT_TENDER_PORTALS).issubset(names))
        self.assertIn("OECM", names)
        self.assertIn("CanadaBuys", names)
        self.assertIn("World Bank Procurement", names)
        self.assertIn("Ontario Tenders Portal", names)
        self.assertIn("MERX", names)
        self.assertIn("BC Bid", names)

    def test_blackout_blocks_outreach(self):
        workspace = build_default_workspace()
        opportunity = workspace.ingest_opportunity(
            title="Ontario Cloud Modernization",
            source="CanadaBuys",
            country="Canada",
            value_usd=300000,
        )
        workspace.update_stage(opportunity.opportunity_id, "pursuit")
        workspace.set_blackout(opportunity.opportunity_id, True)
        with self.assertRaises(PermissionError):
            workspace.start_pre_solicitation_conversation(opportunity.opportunity_id, "Program Owner A")
        workspace.set_blackout(opportunity.opportunity_id, False)
        self.assertEqual(workspace.monitor()["pursuit"], 1)
        result = workspace.start_pre_solicitation_conversation(opportunity.opportunity_id, "Program Owner A")
        self.assertIn("Capability briefing initiated", result)

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

        euna_boost = workspace.ingest_portal_alert(
            "Euna Network",
            {
                "title": "General Services",
                "country": "Canada",
                "summary": "",
                "url": "https://example.test/d",
                "published_at": _utcnow().isoformat(),
            },
        )
        generic = workspace.ingest_portal_alert(
            "GlobalBid",
            {
                "title": "General Services",
                "country": "Canada",
                "summary": "",
                "url": "https://example.test/e",
                "published_at": _utcnow().isoformat(),
            },
        )
        self.assertGreater(euna_boost.fit_score, generic.fit_score)
        future_published = workspace.ingest_portal_alert(
            "CanadaBuys",
            {
                "title": "Ontario Cloud Infrastructure and IT Services",
                "country": "Ontario, Canada",
                "summary": "Cloud and IT managed services for digital infrastructure.",
                "url": "https://example.test/future",
                "published_at": (_utcnow() + timedelta(days=1)).isoformat(),
            },
        )
        self.assertLess(future_published.fit_score, high_fit.fit_score)
        with self.assertRaises(ValueError) as err:
            workspace.ingest_portal_alert("Unregistered Portal", {"title": "X"})
        self.assertIn("Supported sources:", str(err.exception))
        with self.assertRaises(ValueError):
            workspace.ingest_portal_alert(
                "CanadaBuys",
                {
                    "title": "Missing timestamp alert",
                    "country": "Canada",
                    "summary": "No publication timestamp",
                    "url": "https://example.test/missing",
                },
            )
        with self.assertRaises(ValueError) as invalid_published:
            workspace.ingest_portal_alert(
                "CanadaBuys",
                {
                    "title": "Bad published timestamp",
                    "country": "Canada",
                    "summary": "Invalid publication timestamp",
                    "url": "https://example.test/bad-published",
                    "published_at": "not-a-date",
                },
            )
        self.assertIn("published_at", str(invalid_published.exception))
        with self.assertRaises(ValueError) as invalid_closing:
            workspace.ingest_portal_alert(
                "CanadaBuys",
                {
                    "title": "Bad closing timestamp",
                    "country": "Canada",
                    "summary": "Invalid closing timestamp",
                    "url": "https://example.test/bad-closing",
                    "published_at": _utcnow().isoformat(),
                    "closing_at": "not-a-date",
                },
            )
        self.assertIn("closing_at", str(invalid_closing.exception))

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
        with self.assertRaises(ValueError):
            workspace.log_pre_rfp_signal("Naive date signal", (_utcnow() + timedelta(days=60)).replace(tzinfo=None), "municipal plan")

        signals = workspace.list_signals()
        self.assertTrue(all(signal.estimated_release_date.tzinfo is not None for signal in signals))

        metrics = workspace.success_metrics()
        self.assertTrue(metrics["all_goals_met"])

    def test_approval_and_portal_connector_scaffold(self):
        workspace = build_default_workspace()
        workspace.require_procurement_approval("IT manager")
        with self.assertRaises(PermissionError):
            workspace.require_procurement_approval("procurement intern")

        logged_in = workspace.connect_account("sap", {"mock_auth_token": "allow"})
        self.assertTrue(logged_in)
        result = workspace.maneuver_account("sap", "open active procurements")
        self.assertEqual(result["status"], "queued")
        with self.assertRaises(ValueError) as err:
            workspace.connect_account("unknown_system", {"mock_auth_token": "allow"})
        self.assertIn("Supported:", str(err.exception))
        self.assertIn("sap", str(err.exception))

    def test_multi_source_scraping_ingestion(self):
        workspace = build_default_workspace()
        workspace.register_scraper(
            "canada buy",
            StaticProcurementSiteScraper(
                [
                    {
                        "title": "Ontario Cloud Platform Services",
                        "country": "Ontario, Canada",
                        "summary": "Cloud operations tender",
                        "url": "https://example.test/canadabuys",
                        "published_at": _utcnow().isoformat(),
                    }
                ]
            ),
        )
        workspace.register_scraper(
            "merx",
            StaticProcurementSiteScraper(
                [
                    {
                        "title": "Municipal Digital Services",
                        "country": "Canada",
                        "summary": "IT modernization",
                        "url": "https://example.test/merx",
                        "published_at": _utcnow().isoformat(),
                    }
                ]
            ),
        )
        workspace.register_scraper(
            "bc bid",
            StaticProcurementSiteScraper(
                [
                    {
                        "title": "BC Infrastructure Cloud",
                        "country": "British Columbia, Canada",
                        "summary": "Cloud transformation",
                        "url": "https://example.test/bcbid",
                        "published_at": _utcnow().isoformat(),
                    }
                ]
            ),
        )

        ingested = workspace.scrape_and_ingest_sources(["canada buy", "merx", "MERX", "bc bid"])
        self.assertEqual(len(ingested), 3)
        self.assertEqual({"CanadaBuys", "MERX", "BC Bid"}, {item.source for item in ingested})
        alias_ingested = workspace.scrape_and_ingest_sources(["canadabuys"])
        self.assertEqual(len(alias_ingested), 1)
        self.assertEqual(alias_ingested[0].source, "CanadaBuys")
        self.assertEqual(workspace.scrape_and_ingest_sources([]), [])
        self.assertEqual(workspace.scrape_and_ingest_sources(["", "   "]), [])
        with self.assertRaises(ValueError):
            workspace.scrape_and_ingest_sources(["oecm"])
        with self.assertRaises(ValueError):
            workspace.scrape_and_ingest_sources(["merx", 123])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
