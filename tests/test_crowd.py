import unittest

from clipfarm.crowd import cluster_moments


def clip(offset, creator, clip_id=None, duration=30, views=1):
    return {
        "offset": float(offset), "duration": float(duration),
        "creator": creator, "id": clip_id or f"{creator}-{offset}",
        "views": views, "title": f"clip {offset}", "featured": False,
    }


class CrowdClusteringTests(unittest.TestCase):
    def test_chained_starts_do_not_become_one_multi_minute_moment(self):
        # Every adjacent pair is close enough for the old 45-second
        # single-link algorithm, but the endpoints are separate events.
        clips = [
            clip(100 + delta, f"a{delta}") for delta in (0, 3, 6)
        ] + [
            clip(126 + delta, f"b{delta}") for delta in (0, 3, 6)
        ] + [
            clip(152 + delta, f"c{delta}") for delta in (0, 3, 6)
        ]
        moments = cluster_moments(clips, min_clippers=2)
        self.assertGreaterEqual(len(moments), 2)
        self.assertTrue(all(m.end - m.start <= 60 for m in moments))

    def test_duplicate_and_burst_votes_are_deduplicated(self):
        clips = [
            clip(100, "same", "x"),
            clip(100, "same", "x"),
            clip(103, "same", "y"),
            clip(101, "other", "z"),
        ]
        moments = cluster_moments(clips, min_clippers=2)
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0].clippers, 2)
        self.assertEqual(moments[0].clip_count, 2)

    def test_anchor_is_documented_start_evidence(self):
        moment = cluster_moments([
            clip(100, "a"), clip(102, "b"), clip(104, "c"),
        ], min_clippers=2)[0]
        self.assertEqual(moment.anchor_start, 102)
        self.assertEqual(moment.median_start, moment.anchor_start)


if __name__ == "__main__":
    unittest.main()
