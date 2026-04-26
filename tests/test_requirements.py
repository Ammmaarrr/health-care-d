from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.agents import query_agent, reasoning_agent
from backend.core import medical_rules
from backend.core.schemas import Capabilities, ParsedQuery
from backend.routers import desert


class QueryParsingTests(unittest.TestCase):
    def test_high_acuity_terms_become_required_capabilities(self) -> None:
        with patch.object(query_agent, "chat_json", return_value={
            "location": None,
            "state": "Uttar Pradesh",
            "district": None,
            "rural": True,
            "required_capabilities": [],
            "constraints": ["dialysis capability"],
            "doctor_preference": None,
        }):
            parsed = query_agent.parse_query("Find facilities with dialysis capability in rural Uttar Pradesh")

        self.assertIn("dialysis", parsed.required_capabilities)

    def test_challenge_query_maps_appendectomy_and_part_time(self) -> None:
        with patch.object(query_agent, "chat_json", return_value={
            "location": None,
            "state": "Bihar",
            "district": None,
            "rural": True,
            "required_capabilities": ["emergency"],
            "constraints": ["part-time doctors"],
            "doctor_preference": None,
        }):
            parsed = query_agent.parse_query(
                "Find the nearest facility in rural Bihar that can perform an emergency appendectomy "
                "and typically leverages parttime doctors"
            )

        self.assertIn("emergency", parsed.required_capabilities)
        self.assertIn("surgery", parsed.required_capabilities)
        self.assertEqual(parsed.doctor_preference, "part-time")

    def test_neonatal_icu_query_keeps_neonatal_requirement(self) -> None:
        with patch.object(query_agent, "chat_json", return_value={
            "location": None,
            "state": "Bihar",
            "district": None,
            "rural": True,
            "required_capabilities": ["icu", "oxygen"],
            "constraints": [],
            "doctor_preference": None,
        }):
            parsed = query_agent.parse_query("Find neonatal ICU with oxygen in rural Bihar")

        self.assertIn("neonatal", parsed.required_capabilities)
        self.assertIn("icu", parsed.required_capabilities)
        self.assertIn("oxygen", parsed.required_capabilities)


class ReasoningAndTrustTests(unittest.TestCase):
    def test_part_time_doctor_preference_changes_score(self) -> None:
        parsed = ParsedQuery(required_capabilities=["surgery"], doctor_preference="part-time")
        part_time = Capabilities(has_surgery="yes", doctor_type="part-time")
        full_time = Capabilities(has_surgery="yes", doctor_type="full-time")

        self.assertGreater(
            reasoning_agent.score_hospital(part_time, parsed),
            reasoning_agent.score_hospital(full_time, parsed),
        )

    def test_validator_flags_surgery_without_anesthesiologist(self) -> None:
        issues = list(medical_rules.check_contradictions(
            Capabilities(has_surgery="yes", has_anesthesiologist="no", has_oxygen="yes")
        ))

        self.assertTrue(any(issue.capability == "surgery" for issue in issues))


class DesertMapTests(unittest.TestCase):
    def test_missing_new_capability_columns_are_treated_as_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            extraction_path = Path(tmp) / "capabilities.parquet"
            processed_path = Path(tmp) / "hospitals.parquet"
            pd.DataFrame([
                {"facility_id": "1", "state": "Bihar"},
                {"facility_id": "2", "state": "Bihar"},
            ]).to_parquet(extraction_path)
            pd.DataFrame([
                {"facility_id": "1", "pin": "800001", "latitude": 25.6, "longitude": 85.1},
                {"facility_id": "2", "pin": "800001", "latitude": 25.7, "longitude": 85.2},
            ]).to_parquet(processed_path)

            fake_settings = type("FakeSettings", (), {
                "extractions_path": extraction_path,
                "processed_path": processed_path,
            })()
            with patch.object(desert, "settings", fake_settings):
                gaps = desert.desert_map(min_total=1, capability="oncology").gaps
                zones = desert.desert_map_pins(min_per_pin=1, capability="icu", top=5).zones

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].missing_or_uncertain, 2)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].pin, "800001")


if __name__ == "__main__":
    unittest.main()
