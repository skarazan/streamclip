# Payoff-visibility check against the six founder labels

**Run:** 2026-08-19
**VOD:** `2821788113`
**Pipeline under test:** v12.3

Claude correctly noted that the geometry check had unit coverage but had not
been replayed against the six founder-labelled clips. The live clip ledger has
four dislikes and two likes. Two labels repeat the same slot moment and two
repeat the same router moment, leaving four unique source passages.

Fresh source segments were downloaded at the recorded absolute bounds. Motion
was probed only from the recorded trigger through the recorded button, using
the cached facecam box and the same crop geometry the renderer uses.

| Source passage | Founder labels | Motion carrier | v12.3 result |
|---|---:|---:|---|
| Slot/pots, 2409–2440s | 2 discard | 91.5% | Visible after action crop |
| Router/QR story, 5847–5887s | 2 keep | 6.3% | Not required; spoken payoff |
| Wheel/72,000 points, 9875–9913s | 1 discard | 68.3% | Visible after action crop |
| Button/key, 20399–20427s | 1 discard | 95.1% | Visible after action crop |

## Falsification result

The check does **not** separate founder taste: it flags zero of four discarded
labels. It therefore must not be described or tuned as a selection-quality
classifier.

That result does not show that the geometry is wrong. The rejected renders
predate action-centering; the slot payoff was outside the old crop. On the same
source today, v12.3 finds motion at the far right and moves the final crop to
include it. The benchmark changes the composition that received the original
label, so “reject the old clip” and “is the carrier visible in the new render”
are different questions.

The defensible role of this feature is narrower:

- `action_center_x` proposes a crop around a moving carrier;
- `audit_payoff_visibility` verifies that facecam avoidance and edge clamping
  did not move that located carrier back out of the rendered pane;
- `indeterminate` records that static UI was not proven visible;
- completed-clip feedback measures whether `cause_not_visible` still occurs.

Keep the check as a cheap render invariant and evidence field. Do not claim it
will convert the current keeper rate or reject weak game moments. If new
feedback continues to report `cause_not_visible`, motion localization has
failed its operational test and needs a static-UI/vision replacement. Moment
taste remains gated on the larger multi-creator label set described in the
Opus review.
