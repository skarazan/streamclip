import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from clipfarm.config import ffmpeg_path
from clipfarm.render import (
    _opening_filter,
    audit_payoff_visibility,
    audio_lag_seconds,
    audio_waveform_peaks,
    build_ass,
    gameplay_crop_geometry,
    render_editor_proxy,
    render_short,
)
from clipfarm.transcribe import Word


class OpeningFilterTests(unittest.TestCase):
    def test_motion_effects_normalize_source_fps_before_zoompan(self):
        for effect in ("punch_zoom", "impact", "drift_pan"):
            chain = _opening_filter(effect)
            self.assertIn(",fps=30,zoompan=", chain)
            self.assertLess(chain.index("fps=30"), chain.index("zoompan="))


class PayoffVisibilityTests(unittest.TestCase):
    def test_action_crop_keeps_left_and_right_payoffs_visible(self):
        cam = (.72, .04, .25, .32)
        for action_x in (.08, .35, .62):
            with self.subTest(action_x=action_x):
                audit = audit_payoff_visibility(
                    1920, 1080, cam, .42, action_x, required=True)
                self.assertEqual(audit.status, "visible", audit.reason)
                self.assertLessEqual(audit.crop_x1, action_x)
                self.assertGreaterEqual(audit.crop_x2, action_x)

    def test_unknown_visual_carrier_is_recorded_not_claimed_visible(self):
        audit = audit_payoff_visibility(
            1920, 1080, (.72, .04, .25, .32), .42, None, required=True)
        self.assertTrue(audit.passed)
        self.assertEqual(audit.status, "indeterminate")

    def test_hidden_carrier_fails_closed(self):
        # A left-edge carrier can be displaced when the facecam occupies that
        # same edge and the remaining left span is too narrow. Keep this a
        # physically valid 0..1 carrier location, not a synthetic negative x.
        audit = audit_payoff_visibility(
            1920, 1080, (0.0, .1, .05, .2), .42, 0.0, required=True)
        self.assertFalse(audit.passed)
        self.assertEqual(audit.status, "hidden")

    def test_render_and_audit_share_crop_geometry(self):
        crop = gameplay_crop_geometry(
            1920, 1080, (.72, .04, .25, .32), .42, .2)
        self.assertGreater(crop.width, 0)
        self.assertLessEqual(crop.x1, .2)
        self.assertGreaterEqual(crop.x2, .2)


class EditorProxyTests(unittest.TestCase):
    def test_crop_and_facecam_proxies_are_vertical_with_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            subprocess.run([
                ffmpeg_path(), "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=60",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(source),
            ], check=True)
            outputs = [
                render_editor_proxy(source, root / "crop.mp4"),
                render_editor_proxy(
                    source, root / "facecam.mp4", cam=(.72, .04, .25, .32)),
            ]
            peaks = audio_waveform_peaks(source)
            self.assertEqual(len(peaks), 600)
            self.assertTrue(all(0 <= peak <= 1 for peak in peaks))
            self.assertGreater(max(peaks), .5)
            for output in outputs:
                raw = subprocess.check_output([
                    str(Path(ffmpeg_path()).with_name("ffprobe")),
                    "-v", "error", "-show_entries",
                    "stream=codec_type,width,height,r_frame_rate",
                    "-of", "json", str(output),
                ], text=True)
                streams = json.loads(raw)["streams"]
                video = next(s for s in streams if s["codec_type"] == "video")
                self.assertEqual((video["width"], video["height"]), (360, 640))
                self.assertEqual(video["r_frame_rate"], "30/1")
                self.assertTrue(any(s["codec_type"] == "audio" for s in streams))

    def test_final_render_applies_multiple_cuts_in_one_vertical_encode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            subprocess.run([
                ffmpeg_path(), "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(source),
            ], check=True)
            style = {
                "font": "Arial", "font_size": 70,
                "primary_color": "&H00FFFFFF",
                "outline_color": "&H00000000", "outline": 4,
                "highlight_color": "&H0000FFFF",
            }
            words = [Word(.1, .5, "one"), Word(.6, 1.0, "two")]
            ass = build_ass(words, 0, 2, style, root / "captions.ass")
            final = render_short(
                source, ass, root / "final.mp4",
                keep=[(0, 1), (2, 3)], opening_effect="impact")
            split = render_short(
                source, ass, root / "split.mp4",
                cam=(.72, .04, .25, .32), keep=[(0, 1), (2, 3)])
            for output in (final, split):
                raw = subprocess.check_output([
                    str(Path(ffmpeg_path()).with_name("ffprobe")),
                    "-v", "error", "-show_entries",
                    "format=duration:stream=codec_type,width,height",
                    "-of", "json", str(output),
                ], text=True)
                media = json.loads(raw)
                video = next(
                    s for s in media["streams"] if s["codec_type"] == "video")
                self.assertEqual(
                    (video["width"], video["height"]), (1080, 1920))
                self.assertTrue(
                    any(s["codec_type"] == "audio"
                        for s in media["streams"]))
                self.assertAlmostEqual(
                    float(media["format"]["duration"]), 2.0, delta=.15)


class AudioLagTests(unittest.TestCase):
    """The export shifts every clip by whatever this returns, so a wrong
    reading is worse than no reading. Both failures pinned here were measured
    on real downloads (2026-08-12), not imagined."""

    @staticmethod
    def _wav(path: Path, seconds: float, offset: float = 0.0):
        """Aperiodic bursts — a periodic envelope correlates at every period
        and would let a broken search pass."""
        import numpy as np

        rate = 8000
        rng = np.random.default_rng(7)
        gaps = rng.uniform(.35, 1.4, 400)
        edges = np.cumsum(gaps)
        t = np.arange(int((seconds + offset) * rate)) / rate + offset
        loud = (np.searchsorted(edges, t) % 2).astype(np.float32)
        noise = rng.standard_normal(len(t)).astype(np.float32)
        pcm = (noise * (loud * .9 + .02) * 12000).astype(np.int16)
        subprocess.run([
            ffmpeg_path(), "-y", "-v", "error",
            "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
            "-c:a", "aac", str(path),
        ], input=pcm.tobytes(), check=True)
        return path

    def test_recovers_a_known_shift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = self._wav(root / "ref.m4a", 60)
            late = self._wav(root / "late.m4a", 60, offset=5.0)
            self.assertAlmostEqual(audio_lag_seconds(ref, late), 5.0, delta=.2)
            self.assertAlmostEqual(audio_lag_seconds(late, ref), -5.0, delta=.2)

    def test_aligned_pair_shorter_than_max_lag_reports_nothing(self):
        # Measured: a 30s aligned pair searched to +/-30s returned a
        # confident -23.70s off 6.3s of overlap, and one such pair crashed on
        # a negative slice. Refusing the search is the only honest answer.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = self._wav(root / "ref.m4a", 20)
            same = self._wav(root / "same.m4a", 20)
            self.assertEqual(audio_lag_seconds(ref, same, max_lag=30.0), 0.0)

    def test_aligned_pair_with_room_to_search_reports_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = self._wav(root / "ref.m4a", 60)
            same = self._wav(root / "same.m4a", 60)
            self.assertEqual(audio_lag_seconds(ref, same, max_lag=25.0), 0.0)


if __name__ == "__main__":
    unittest.main()
