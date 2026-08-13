import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx

from clipfarm import fetch
from worker import worker


class SegmentDownloadTests(unittest.TestCase):
    """Twitch serves stream-less husks to some egress IPs.

    `--download-sections` forces yt-dlp to hand the playlist to the ffmpeg
    downloader, which has no per-fragment retry and exits 0 after writing an
    empty container. Seven jobs on one VOD failed this way, each burning a
    full LLM scoring pass first.
    """

    def _husk(self, path):
        path.write_bytes(b"\x00" * 262)   # the size actually observed
        return path

    def test_husk_is_rejected_despite_a_zero_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            husk = self._husk(pathlib.Path(td) / "seg.mp4")
            with self.assertRaises(fetch.SegmentUnavailable):
                fetch._validate_media(
                    husk, fetch._MIN_SEGMENT_BYTES, need_video=True)

    @staticmethod
    def _fake_fragments(calls):
        def fragments(vod_url, start, end, target, quality, tries=3,
                      audio_only=False):
            calls.append((start, end, audio_only))
            target.write_bytes(b"\x00" * fetch._MIN_SEGMENT_BYTES * 2)
            return target
        return fragments

    def test_fragments_are_the_primary_route(self):
        # Reversed 2026-08-12: the yt-dlp route returned valid media of the
        # right length from 10.4s before the requested second, so the route
        # that cuts on our own clock goes first.
        with tempfile.TemporaryDirectory() as td:
            dest = pathlib.Path(td) / "seg.mp4"
            calls, ytdlp_ran = [], []

            def ytdlp(vod_url, start, end, target, quality):
                ytdlp_ran.append(start)
                return self._husk(target)

            with (
                patch.object(fetch, "_ytdlp_segment", ytdlp),
                patch.object(fetch, "_fragment_segment",
                             self._fake_fragments(calls)),
                patch.object(fetch, "_has_video_stream", return_value=True),
                patch.object(fetch, "_alignment_error",
                             lambda *a, **k: (0.0, "")),
                patch.object(fetch.time, "sleep", lambda *_: None),
            ):
                fetch.download_segment(
                    "https://twitch.tv/videos/1", 10.0, 35.0, dest, "worst")
            self.assertEqual(calls, [(10.0, 35.0, False)])
            self.assertEqual(ytdlp_ran, [])

    def test_ytdlp_backs_up_a_dead_fragment_route(self):
        with tempfile.TemporaryDirectory() as td:
            dest = pathlib.Path(td) / "seg.mp4"
            ytdlp_ran = []

            def ytdlp(vod_url, start, end, target, quality):
                ytdlp_ran.append(start)
                target.write_bytes(b"\x00" * fetch._MIN_SEGMENT_BYTES * 2)
                return target

            with (
                patch.object(fetch, "_ytdlp_segment", ytdlp),
                patch.object(fetch, "_fragment_segment",
                             side_effect=fetch.SegmentUnavailable("refused")),
                patch.object(fetch, "_has_video_stream", return_value=True),
                patch.object(fetch, "_alignment_error",
                             lambda *a, **k: (0.0, "")),
                patch.object(fetch.time, "sleep", lambda *_: None),
            ):
                fetch.download_segment(
                    "https://twitch.tv/videos/1", 10.0, 35.0, dest, "worst")
            self.assertEqual(ytdlp_ran, [10.0])

    def test_a_download_from_the_wrong_ten_seconds_is_refused(self):
        """Valid media, of exactly the requested length, from a moment nobody
        selected. Nothing downstream can tell — so the download must not
        count as success."""
        with tempfile.TemporaryDirectory() as td:
            dest = pathlib.Path(td) / "seg.mp4"
            calls = []
            fragments = self._fake_fragments(calls)

            with (
                patch.object(fetch, "_ytdlp_segment",
                             lambda v, s, e, t, q: fragments(v, s, e, t, q)),
                patch.object(fetch, "_fragment_segment", fragments),
                patch.object(fetch, "_has_video_stream", return_value=True),
                patch.object(fetch, "_alignment_error",
                             lambda *a, **k: (-10.4, "")),
                patch.object(fetch.time, "sleep", lambda *_: None),
            ):
                with self.assertRaises(fetch.SegmentUnavailable) as caught:
                    fetch.download_segment(
                        "https://twitch.tv/videos/1", 10.0, 35.0, dest,
                        "worst")
            self.assertIn("landed -10.4s", str(caught.exception))
            self.assertFalse(dest.exists())

    def test_every_route_dead_raises_and_leaves_no_husk_behind(self):
        with tempfile.TemporaryDirectory() as td:
            dest = pathlib.Path(td) / "seg.mp4"
            dead = fetch.SegmentUnavailable("refused")

            with (
                patch.object(fetch, "_ytdlp_segment",
                             lambda *a, **k: self._husk(a[3])),
                patch.object(fetch, "_fragment_segment", side_effect=dead),
                patch.object(fetch.time, "sleep", lambda *_: None),
            ):
                with self.assertRaises(fetch.SegmentUnavailable):
                    fetch.download_segment(
                        "https://twitch.tv/videos/1", 10.0, 35.0, dest, "worst")
            # a leftover husk is what broke captions, facecam and render
            self.assertFalse(dest.exists())


class AdminFlagTests(unittest.TestCase):
    """A Stripe checkout must never revoke admin rights.

    `plan` belongs to billing, which rewrites it on checkout and cancellation.
    A test checkout once stripped the founder's own-channel bypass and locked
    them out of /admin/costs, so admin status lives in `users.is_admin`.
    """

    def test_billing_cannot_revoke_admin_by_rewriting_plan(self):
        founder = {"plan": "founder", "is_admin": True}
        self.assertTrue(worker.is_admin(founder))
        for billing_written_plan in ("starter", "creator", "churned"):
            with self.subTest(plan=billing_written_plan):
                after_checkout = {**founder, "plan": billing_written_plan}
                self.assertTrue(worker.is_admin(after_checkout))

    def test_plan_remains_the_marker_before_the_migration(self):
        # 20260725_admin_flag.sql not applied yet: the column is simply absent
        # from the row, and the legacy plan values still grant the bypass.
        self.assertTrue(worker.is_admin({"plan": "founder"}))
        self.assertTrue(worker.is_admin({"plan": "internal"}))
        self.assertFalse(worker.is_admin({"plan": "starter"}))

    def test_explicit_false_revokes_regardless_of_plan(self):
        self.assertFalse(worker.is_admin({"plan": "founder", "is_admin": False}))


class CreditContractTests(unittest.TestCase):
    def test_atomic_reservation_is_authoritative(self):
        response = Mock()
        response.json.return_value = [{"ok": True, "balance": 7}]
        job = {"id": "job-1", "user_id": "user-1"}
        with patch.object(worker, "sb", return_value=response) as request:
            self.assertEqual(worker.reserve_job_credits(job, 1), (True, 7))
        request.assert_called_once_with(
            "POST",
            "/rest/v1/rpc/reserve_job_credits",
            json={"p_job": "job-1", "p_user": "user-1", "p_amount": 1},
        )
        self.assertNotIn("_legacy_credit_cost", job)

    def test_pre_migration_single_worker_bridge_is_explicit(self):
        job = {"id": "job-2", "user_id": "user-2"}
        missing_rpc = httpx.HTTPStatusError(
            "missing RPC",
            request=httpx.Request("POST", "https://example.test/rpc"),
            response=httpx.Response(404),
        )
        with (
            patch.object(worker, "sb", side_effect=missing_rpc),
            patch.object(worker, "get_user", return_value={"credits": 2}),
        ):
            self.assertEqual(worker.reserve_job_credits(job, 1), (True, 1))
        self.assertEqual(job["_legacy_credit_cost"], 1)

    def test_pre_migration_bridge_still_refuses_empty_balance(self):
        job = {"id": "job-3", "user_id": "user-3"}
        missing_rpc = httpx.HTTPStatusError(
            "missing RPC",
            request=httpx.Request("POST", "https://example.test/rpc"),
            response=httpx.Response(404),
        )
        with (
            patch.object(worker, "sb", side_effect=missing_rpc),
            patch.object(worker, "get_user", return_value={"credits": 0}),
        ):
            self.assertEqual(worker.reserve_job_credits(job, 1), (False, 0))
        self.assertNotIn("_legacy_credit_cost", job)


class ContractFilesTests(unittest.TestCase):
    def test_claim_contract_limits_one_running_job_per_user(self):
        migration = (
            worker.Path(__file__).resolve().parents[1]
            / "infra/migrations/20260725_service_contract.sql"
        ).read_text()
        self.assertIn("active.user_id = candidate.user_id", migration)
        self.assertIn("active.status = 'running'", migration)
        self.assertIn("for update skip locked", migration)

    def test_editor_stream_contract_requires_partial_content(self):
        route = (
            worker.Path(__file__).resolve().parents[1]
            / "web/app/app/api/edit-jobs/[id]/media/route.js"
        ).read_text()
        self.assertIn('status: object.ContentRange ? 206 : 200', route)
        self.assertIn('"Content-Range"', route)
        self.assertIn('"Accept-Ranges"', route)


if __name__ == "__main__":
    unittest.main()
