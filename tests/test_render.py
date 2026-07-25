import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from clipfarm.config import ffmpeg_path
from clipfarm.render import (
    _opening_filter,
    audio_waveform_peaks,
    build_ass,
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


if __name__ == "__main__":
    unittest.main()
