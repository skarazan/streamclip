import tempfile
import unittest
from pathlib import Path

import numpy as np

from clipfarm.quality import (
    MotionResult, contextual_preroll, duration_budget, inactive_gap_reason,
    closing_beat_end, inspect_media, longest_speech_gap, low_substance_reason,
    remove_idle_gaps,
    needs_visual_bridge, should_cut_idle_gap,
    metadata_violations, remap_profile, retained_duration_reason,
    verify_arc,
)
from clipfarm.transcribe import Word


def words(*items):
    return [Word(float(start), float(end), text)
            for start, end, text in items]


class ArcTests(unittest.TestCase):
    def test_ordered_final_arc_passes(self):
        ws = words(
            (0.2, 1.0, "did you read that message"),
            (4.0, 4.6, "wait what"),
            (8.0, 9.0, "that is absolutely insane"),
        )
        arc = verify_arc(
            "read that message", "absolutely insane", ws, 0, 10,
            trigger_role="chat", button_role="streamer", final=True)
        self.assertTrue(arc.passed, arc.reason)
        self.assertLessEqual(arc.tail_s, 2.75)

    def test_wrong_order_fails(self):
        ws = words(
            (1, 2, "that is absolutely insane"),
            (7, 8, "did you read that message"),
        )
        arc = verify_arc(
            "read that message", "absolutely insane", ws, 0, 10,
            trigger_role="chat", button_role="streamer")
        self.assertFalse(arc.passed)

    def test_npc_button_is_never_a_streamer_payoff(self):
        ws = words((0, 1, "open the door"), (8, 9, "you shall not pass"))
        arc = verify_arc(
            "open the door", "you shall not pass", ws, 0, 10,
            trigger_role="streamer", button_role="npc")
        self.assertFalse(arc.passed)
        self.assertIn("npc", arc.reason)

    def test_long_tail_fails_final_gate(self):
        ws = words((0, 1, "read that"), (5, 6, "no chance"))
        arc = verify_arc(
            "read that", "no chance", ws, 0, 12,
            trigger_role="chat", button_role="streamer", final=True)
        self.assertFalse(arc.passed)
        self.assertTrue(
            "remains" in arc.reason or "early in final" in arc.reason,
            arc.reason)

    def test_source_gate_accepts_valid_arc_inside_oversized_window(self):
        ws = words(
            (10, 11, "we are in the eye of it"),
            (20, 22, "that gas station will be gone"),
        )
        arc = verify_arc(
            "in the eye of it", "gas station will be gone", ws, 0, 60,
            trigger_role="game", button_role="streamer")
        self.assertTrue(arc.passed, arc.reason)

    def test_old_cache_can_verify_spoken_scream_button_without_profile(self):
        ws = words(
            (1, 2, "save the spot in the house"),
            (8, 10, "who has a window in their shower"),
        )
        arc = verify_arc(
            "save the spot", "window in their shower", ws, 0, 12,
            button_kind="scream", trigger_role="game",
            button_role="streamer", profile=None)
        self.assertTrue(arc.passed, arc.reason)
        self.assertEqual(arc.button_kind, "speech")

    def test_scream_requires_acoustic_peak_after_trigger(self):
        ws = words((0, 1, "open the door"), (7, 8, "ahhh"))
        profile = np.full(10, .1)
        profile[8] = .9
        arc = verify_arc(
            "open the door", "AHHH", ws, 0, 10,
            button_kind="scream", trigger_role="streamer",
            button_role="streamer", profile=profile, final=True)
        self.assertTrue(arc.passed, arc.reason)

    def test_scream_with_spoken_button_requires_quote_near_peak(self):
        ws = words((0, 1, "open the door"), (7, 8, "unrelated words"))
        profile = np.full(10, .1)
        profile[8] = .9
        arc = verify_arc(
            "open the door", "lord have mercy", ws, 0, 10,
            button_kind="scream", trigger_role="streamer",
            button_role="streamer", profile=profile, final=True)
        self.assertFalse(arc.passed)

    def test_metadata_claims_must_match_evidence(self):
        ws = words((0, 1, "read that"), (8, 9, "no chance"))
        arc = verify_arc(
            "read that", "no chance", ws, 0, 10,
            trigger_role="chat", button_role="streamer", final=True)
        self.assertIn(
            "scream/jumpscare claim lacks acoustic button",
            metadata_violations("He SCREAMED", "", arc))
        self.assertIn(
            "curiosity title summarizes the sequence with 'then'",
            metadata_violations(
                "He cheers, then gets called out", "What happens *next*?", arc,
                title_strategy="curiosity"))
        self.assertIn(
            "on-screen hook reveals the verified payoff",
            metadata_violations(
                "The crowd noticed something", "Absolutely *insane* no chance",
                verify_arc(
                    "read that", "absolutely insane no chance",
                    words((0, 1, "read that"),
                          (8, 9, "absolutely insane no chance")),
                    0, 10, trigger_role="chat", button_role="streamer",
                    final=True)))

    def test_profile_remap_and_duration_budgets(self):
        profile = np.arange(20)
        np.testing.assert_array_equal(
            remap_profile(profile, [(2, 5), (10, 12)]),
            np.array([2, 3, 4, 10, 11]))
        self.assertLess(duration_budget("stinger")[1],
                        duration_budget("rage_arc")[1])

    def test_duration_limit_applies_to_final_retained_story(self):
        # Long source span, but a valid 38-second edit after dead-air removal.
        self.assertIsNone(retained_duration_reason(
            [(100.0, 119.0), (131.0, 150.0)]))
        # An uninterrupted, content-dense 38-second story is equally valid.
        self.assertIsNone(retained_duration_reason([(100.0, 138.0)]))
        # The actual retained edit—not the source window—owns the hard limit.
        self.assertIn("46.0s", retained_duration_reason([(100.0, 146.0)]))

    def test_trivial_scream_cannot_fill_from_bench(self):
        self.assertEqual(
            low_substance_reason(
                "bench", "scream",
                "comedic overreaction to trivial food ranking"),
            "trivial-trigger scream is not a story")
        self.assertEqual(
            low_substance_reason("post", "scream", "trivial trigger"),
            "trivial-trigger scream is not a story")

    def test_context_preroll_is_semantic_not_fixed(self):
        self.assertEqual(
            contextual_preroll(
                "gotta save him", "game", "heroic declaration"), 1.0)
        self.assertEqual(
            contextual_preroll(
                "all the spectators witnessed a death", "game",
                "he cheers and gets called out"), 6.0)

    def test_inactive_long_gap_rejected_but_active_gameplay_kept(self):
        ws = words((0, 1, "setup"), (12, 13, "payoff"))
        gap = longest_speech_gap(ws, 0, 14)
        self.assertEqual(gap.duration, 11)
        self.assertIsNotNone(
            inactive_gap_reason(11, MotionResult(.010, .8)))
        self.assertIsNone(
            inactive_gap_reason(11, MotionResult(.030, .1)))
        self.assertTrue(
            should_cut_idle_gap(11, MotionResult(.010, .8)))
        self.assertFalse(
            should_cut_idle_gap(11, MotionResult(.030, .1)))
        self.assertTrue(
            should_cut_idle_gap(
                11, MotionResult(.030, .1), preserve_active=False))
        self.assertTrue(needs_visual_bridge("I gotta save him"))
        self.assertTrue(
            needs_visual_bridge("that's a grown man", "game", "scream"))
        self.assertFalse(
            needs_visual_bridge("the spectators witnessed a death"))
        self.assertEqual(
            remove_idle_gaps(0, 20, [type(gap)(5, 15)]),
            [(0, 5.35), (14.65, 20)])

    def test_scream_keeps_nearby_closing_tag(self):
        ws = words(
            (10, 11, "this is sparta"),
            (11.4, 12.2, "I won"),
            (13.0, 14.0, "did I win"),
            (18.0, 19.0, "new topic"),
        )
        self.assertEqual(closing_beat_end(ws, 11, 20), 14)


class MediaTests(unittest.TestCase):
    def test_missing_media_fails_closed(self):
        qa = inspect_media(Path("/definitely/missing.mp4"), run_ocr=False)
        self.assertFalse(qa.passed)


if __name__ == "__main__":
    unittest.main()
