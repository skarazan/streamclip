# SPEC: manual crop control in the clip editor

From: COO/Fable. Founder's idea, 2026-08-03. For whoever picks up web work.
Companion: `clipfarm/render.py::action_center_x`, `CONTRACT.md`.

## Why

A 9:16 Short keeps roughly half the width of a 16:9 stream frame. Whatever
sits outside that slice is gone, and the payoff often lives there — slot
reels, loot rolls, killfeeds, scoreboards, a chat overlay being read aloud.
Every founder rejection so far reduced to this: *"the gambling wasn't even in
frame."*

Automatic action-centring (shipped 2026-08-03) fixes the common case for free
by cropping toward whatever is moving. It cannot fix:

- **static payoffs** — a menu, a scoreboard, a paused screen, a chat message.
  Nothing moves, so the detector correctly declines and the default framing
  returns;
- **two things moving** — gameplay on one side, an alert or a video on the
  other, and only the human knows which one the clip is about;
- **taste** — sometimes the streamer's reaction matters more than the event.

There is no cheap automatic answer to those, and paying a vision model per
clip is not worth it at $0.70 COGS. The human already opens the editor to
tighten cuts; letting them drag a box is the cheapest correct fix.

## Behaviour

In the existing timeline editor, next to the trim controls:

1. A **frame preview** of the clip at the current playhead, shown at full
   16:9 with the active 9:16 crop drawn as a movable box.
2. The box is **horizontally draggable** (vertical position is not useful —
   the crop is already full height). Snap points at left / centre / right.
3. **Default is exactly today's output**: whatever the pipeline chose
   (action-centred when it found something, centre otherwise). Opening the
   control and not touching it must change nothing.
4. A **Reset to auto** button returns to the pipeline's own choice.
5. Scrubbing the timeline updates the preview frame so the user can check the
   box across the whole clip, not just one instant.

Store as a single number: `crop_x` = the crop's centre as a fraction of frame
width (0..1), on the existing clip-revision recipe. `null` means auto.

## Wiring

- The recipe already flows web → `clip_edit` → `render_short`; add `crop_x`
  beside the keep-intervals and pass it as `action_x`. **No new render path
  is needed** — `render_short(action_x=…)` already accepts exactly this and
  is what auto-centring uses.
- Additive only: a recipe without `crop_x` behaves as it does today
  (CONTRACT.md rule 1).
- No re-render on drag. Like every other editor control, the box edits the
  recipe; only **Export** encodes.

## Nice-to-have, only if it is free

Show the auto-detected action position as a faint marker on the preview so
the user can see what the machine thought. It is one number the worker
already computes; if surfacing it costs a schema change, skip it.

## Acceptance

- Open the editor on an existing clip, export without touching the box →
  byte-for-byte the same framing as before the feature.
- Drag right on the rejected slot clip (VOD 2821788113 @ 2417s) → the reels
  and the win banner are in frame.
- A clip whose auto-crop already found the action opens with the box on the
  action, not at centre.
