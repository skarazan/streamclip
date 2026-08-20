import datetime as dt
import math
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.audit_youtube_shorts import (
    duration_bucket,
    main,
    normalize,
    spearman,
    title_features,
)


class ShortsAuditTests(unittest.TestCase):
    def test_duration_buckets_do_not_encode_quality(self):
        self.assertEqual(duration_bucket(5), "0-9s")
        self.assertEqual(duration_bucket(14), "10-14s")
        self.assertEqual(duration_bucket(59), "30-60s")

    def test_tie_aware_spearman(self):
        self.assertAlmostEqual(spearman([1, 2, 3], [10, 20, 30]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3], [30, 20, 10]), -1.0)
        self.assertTrue(math.isfinite(spearman([1, 1, 2], [3, 3, 8])))

    def test_title_features_are_transparent_not_model_labels(self):
        concrete = title_features("JYNXZI AMAZING GOAL IN ROCKETLEAGUE")
        tease = title_features("You won't believe this reaction??")
        self.assertTrue(concrete["payoff_named"])
        self.assertFalse(concrete["withholding"])
        self.assertTrue(tease["withholding"])
        self.assertTrue(tease["question"])

    def test_normalize_deduplicates_and_marks_maturity(self):
        raw = [{
            "id": "abc", "title": "A goal", "duration": 9,
            "view_count": 100, "like_count": 5, "upload_date": "20260801",
        }, {
            "id": "abc", "title": "duplicate", "duration": 9,
            "view_count": 200, "upload_date": "20260801",
        }]
        rows = normalize(raw, dt.date(2026, 8, 19))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["mature_7d"])
        self.assertEqual(rows[0]["likes_per_1k_views"], 50.0)

    def test_known_channel_refuses_a_suspiciously_short_snapshot(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "partial.jsonl"
            source.write_text(
                '{"id":"only-one","upload_date":"20260801",'
                '"title":"One","duration":10,"view_count":12}\n'
            )
            argv = [
                "audit_youtube_shorts.py", "--input", str(source),
                "--channel", "@CheeseDipClips", "--as-of", "2026-08-19",
                "--csv", str(Path(td) / "out.csv"),
                "--report", str(Path(td) / "out.md"),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    SystemExit, "expected at least 60 usable Shorts"
                ):
                    main()
            self.assertFalse((Path(td) / "out.csv").exists())

    def test_floor_can_be_overridden_for_fixture_replays(self):
        with TemporaryDirectory() as td:
            source = Path(td) / "fixture.jsonl"
            source.write_text(
                '{"id":"one","upload_date":"20260801",'
                '"title":"One","duration":10,"view_count":12}\n'
            )
            csv_path, report_path = Path(td) / "out.csv", Path(td) / "out.md"
            argv = [
                "audit_youtube_shorts.py", "--input", str(source),
                "--channel", "@CheeseDipClips", "--expect-at-least", "1",
                "--as-of", "2026-08-19", "--csv", str(csv_path),
                "--report", str(report_path),
            ]
            with patch.object(sys, "argv", argv):
                main()
            self.assertTrue(csv_path.exists())
            self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
