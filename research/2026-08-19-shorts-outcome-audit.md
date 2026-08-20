# CheeseDipClips public Shorts outcome audit

**Snapshot:** 2026-08-19
**Channel:** `@CheeseDipClips`
**Videos discovered:** 66
**Complete public rows:** 66
**Mature rows (at least 7 days old):** 63

## What this audit can and cannot answer

This snapshot replaces the earlier hand-copied winner/flop list with
complete public title, duration, date, view, like, and comment fields.
It can reveal associations and matched examples. It **cannot** identify
retention drops or causally separate moment selection from title, edit,
posting time, audience distribution, or channel growth. Private YouTube
Analytics and source-manifest attribution are still required for that.

## Mature-public baseline

- Median views: **2,100**
- Mean views: **4,402**
- Duration vs log-views Spearman rho: **-0.227**
- Post age vs log-views Spearman rho: **-0.005**

The correlation is descriptive, not a duration penalty. A good long
clip may outperform a weak short clip; this only tests whether length
is associated with outcomes in this small channel snapshot. Post age
is reported beside it so channel growth/exposure time is visible as a
basic confound rather than silently ignored.

## Views by duration bucket

| Duration | N | Median views | Mean views |
|---|---:|---:|---:|
| 0-9s | 5 | 11,265 | 14,684 |
| 10-14s | 9 | 2,827 | 5,368 |
| 15-19s | 12 | 3,547 | 5,018 |
| 20-29s | 22 | 976 | 1,653 |
| 30-60s | 15 | 1,671 | 3,930 |

## Views by transparent title feature

| Feature | N | Median views | Mean views |
|---|---:|---:|---:|
| Names a concrete outcome: true | 21 | 2,100 | 6,416 |
| Names a concrete outcome: false | 42 | 2,095 | 3,395 |
| Uses withholding/generic tease: true | 12 | 2,095 | 3,548 |
| Uses withholding/generic tease: false | 51 | 2,100 | 4,603 |
| Contains a question: true | 4 | 2,986 | 3,148 |
| Contains a question: false | 59 | 1,972 | 4,487 |

Feature labels come from explicit regexes in
`scripts/audit_youtube_shorts.py`; they are inspectable heuristics, not
an LLM verdict.

## Highest-view mature Shorts

| Views | Length | Title |
|---:|---:|---|
| 31,884 | 8s | [Why is caseoh so random.](https://www.youtube.com/shorts/PNnEQPuAZAA) |
| 28,091 | 8s | [CaseOh SNAPS at a KID in Roblox!!!!!](https://www.youtube.com/shorts/1LaF3FkiS4o) |
| 21,245 | 14s | [JYNXZI AMAZING GOAL IN ROCKETLEAGUE #jynxzi #rocketleague #funnymoments](https://www.youtube.com/shorts/aXwe9JaqZ44) |
| 20,174 | 16s | [Caseoh SHOOTS his customers and HUNTS DOWN NORBERT  #caseoh #funny](https://www.youtube.com/shorts/IaICt9Yl1x0) |
| 18,571 | 55s | [CaseOh’s best moments in the house always wins!!](https://www.youtube.com/shorts/epxeTnpLSwY) |
| 12,633 | 40s | [CaseOh is charging crazy prices at the Case Ino....](https://www.youtube.com/shorts/nFzUTm64u-0) |
| 11,808 | 16s | [JYNXZI is 2 WINS AWAY from DIAMOND IN ROCKET LEAGUE  #funny#jynxzi](https://www.youtube.com/shorts/HV6DsS3IEss) |
| 11,265 | 6s | [CaseOh reacts to Jynxzi loosing in Minecraft Hardcore..](https://www.youtube.com/shorts/rWk5nSyrqnU) |
| 8,607 | 28s | [Jynxzi catches CORRUPT cops in Gta 5 RP! #shorts #jynxzi](https://www.youtube.com/shorts/gbqiAJTS230) |
| 8,438 | 11s | [Caseoh and Dashe getting mad at a guy over sm shorts..  #funny #caseoh #twitch](https://www.youtube.com/shorts/uK_DVlpqnLo) |

## Lowest-view mature Shorts

| Views | Length | Title |
|---:|---:|---|
| 11 | 18s | [JYNXZI is flabbergasted by the worst hiding spot in the game! #jynxzi #mecchachameleon](https://www.youtube.com/shorts/_Kpi684q3TU) |
| 15 | 23s | [How spooky time be at Caseohs  #caseoh](https://www.youtube.com/shorts/OyFWpQIK7fw) |
| 16 | 22s | [Caseoh GETS CRAZY on a REAL LIFE MONSTER  #caseoh #funny](https://www.youtube.com/shorts/5s16izYRdT4) |
| 34 | 6s | [That was CREEPY](https://www.youtube.com/shorts/ge4xUh0C56w) |
| 38 | 36s | [CASEOH and JYNXZI get eaten in Subnautica 2!!!!](https://www.youtube.com/shorts/HJhhJAZ2VhA) |
| 44 | 21s | [JYNXZI scores a POWER SHOT in Rocket League!  #funny#jynxzi  #rocketleague](https://www.youtube.com/shorts/vyQe0p5lMnE) |
| 44 | 24s | [Caseoh gets eaten by fish in Subnautica 2 #caseoh #jynxzi #subnautica2](https://www.youtube.com/shorts/8Mp7scfvWs8) |
| 223 | 32s | [Case hits a 7 KO in roblox #caseoh](https://www.youtube.com/shorts/TTWcOSfXk7c) |
| 637 | 20s | [CASEOH gets his IMAGES LEAKED!  #caseoh #funny](https://www.youtube.com/shorts/jIT4JsrSBuA) |
| 670 | 29s | [JYNXZI FINDS ABOUT STREAMSNIPERS IN CLASH ROYALE! #jynxzi #clashroyale #controversyvideo](https://www.youtube.com/shorts/0j6u0cPepKA) |

## Near-matched examples

- **482.8x gap.** Same creator and game; adjacent days: “JYNXZI AMAZING GOAL IN ROCKETLEAGUE #jynxzi #rocketleague #funnymoments” (21,245) vs “JYNXZI scores a POWER SHOT in Rocket League!  #funny#jynxzi  #rocketleague” (44). This is useful evidence but still not a
  controlled experiment because the underlying moments differ.
- **3.5x gap.** Same creator and tornado topic: “Caseoh panicked so hard he caused a tornado  #caseoh #funny” (3,882) vs “CaseOh summons a tornado with his weight!  #caseoh #funny” (1,124). This is useful evidence but still not a
  controlled experiment because the underlying moments differ.

## Decision

1. Do not introduce a universal duration penalty from this snapshot.
2. Preserve payoff-forward packaging as a testable hypothesis, not a
   proven cause.
3. Capture keep/discard reasons on every newly shipped clip so moment
   quality and cut quality stop being collapsed into one view count.
4. Add private YouTube Analytics ingestion before using retention as a
   training label. Store `engagedViews`, average view duration/percentage,
   and per-video retention curves against the final edit recipe.
5. Re-run this public snapshot regularly; compare only mature posts and
   keep the raw CSV so every claim is reproducible.
