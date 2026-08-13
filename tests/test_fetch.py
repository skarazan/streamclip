import unittest

from clipfarm.fetch import covering_fragments, parse_fragment_timeline

# Shaped like the real thing, including the over-length fragments Twitch
# emits: on VOD 2842062490 the fragments around 4285s ran 11.28s and 11.5s,
# and those are exactly where the yt-dlp route lost 10s.
PLAYLIST = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:12
#EXT-X-PLAYLIST-TYPE:EVENT
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-TWITCH-ELAPSED-SECS:0.000
#EXT-X-TWITCH-TOTAL-SECS:43.851
#EXT-X-PROGRAM-DATE-TIME:2026-08-05T02:01:22.717Z
#EXTINF:10.000,
0.ts
#EXT-X-PROGRAM-DATE-TIME:2026-08-05T02:01:32.717Z
#EXTINF:11.283,
1.ts
#EXTINF:11.284,
2.ts
#EXTINF:11.284,
3.ts
#EXT-X-ENDLIST
"""


class FragmentTimelineTests(unittest.TestCase):
    def test_clock_is_cumulative_extinf_not_index_times_ten(self):
        init, timeline = parse_fragment_timeline(PLAYLIST)
        self.assertIsNone(init)
        self.assertEqual([name for _, _, name in timeline],
                         ["0.ts", "1.ts", "2.ts", "3.ts"])
        starts = [round(start, 3) for start, _, _ in timeline]
        self.assertEqual(starts, [0.0, 10.0, 21.283, 32.567])
        total = timeline[-1][0] + timeline[-1][1]
        self.assertAlmostEqual(total, 43.851, places=3)

    def test_fmp4_init_segment_is_returned(self):
        init, timeline = parse_fragment_timeline(
            '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:10.0,\n0.mp4\n')
        self.assertEqual(init, "init.mp4")
        self.assertEqual(len(timeline), 1)

    def test_start_deep_inside_a_long_fragment_selects_that_fragment(self):
        # The regression case: 32.0 is 10.7s into the fragment that begins at
        # 21.283, and the cut offset has to be that 10.7s.
        _, timeline = parse_fragment_timeline(PLAYLIST)
        covering = covering_fragments(timeline, 32.0, 40.0)
        self.assertEqual([name for _, _, name in covering], ["2.ts", "3.ts"])
        self.assertAlmostEqual(32.0 - covering[0][0], 10.717, places=3)

    def test_a_fragment_ending_exactly_at_the_start_is_not_covering(self):
        _, timeline = parse_fragment_timeline(PLAYLIST)
        covering = covering_fragments(timeline, 10.0, 15.0)
        self.assertEqual([name for _, _, name in covering], ["1.ts"])


if __name__ == "__main__":
    unittest.main()
