"""Render vertical shorts: crop to 9:16, burn hook title + word captions + watermark."""

import subprocess
from pathlib import Path

from .config import ffmpeg_path
from .transcribe import Word

W, H = 1080, 1920

# Summed column motion energy below this means "nothing is happening" — keep
# the caller's default framing. Frozen scene measured 0.03; a spinning slot
# reel 118. The gap is three orders of magnitude, so the exact value is not
# delicate.
MIN_ACTION_ENERGY = 2.0

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{cap_font},{cap_size},{cap_color},{cap_color},{outline_c},&H80000000,-1,0,0,0,100,100,0,0,{cap_bstyle},{cap_outline},2,5,60,60,0,1
Style: Hook,{hook_font},{hook_size},{hook_color},{hook_color},{outline_c},&H80000000,-1,0,0,0,100,100,0,0,1,{hook_outline},2,5,40,40,0,1
Style: Mark,{wm_font},{wm_size},{wm_color},{wm_color},&H60000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,9,20,36,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Text
"""


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(text: str) -> str:
    return text.replace("{", "").replace("}", "")


def _hook_text(hook: str, keyword_color: str) -> str:
    """Words wrapped in *asterisks* get the keyword color."""
    import re
    def color(m: re.Match) -> str:
        return "{\\c" + keyword_color + "}" + m.group(1) + "{\\r}"
    return re.sub(r"\*([^*]+)\*", color, _clean(hook)).replace("*", "")


def build_ass(words: list[Word], clip_start: float, clip_end: float,
              style: dict, dest: Path, hook: str | None = None,
              hook_color_idx: int = 0, hook_pos: float | None = None,
              res: tuple[int, int] = (W, H)) -> Path:
    W_, H_ = res  # noqa: N806 — vertical shorts by default, 16:9 for comps
    wpl = style.get("words_per_line", 2)
    upper = style.get("uppercase", False)
    pos_y = int(H_ * style.get("caption_pos", 0.72))
    hook_cfg = style.get("hook", {})
    wm_cfg = style.get("watermark", {})
    clip_len = clip_end - clip_start

    header = ASS_HEADER.format(
        w=W_, h=H_,
        cap_font=style["font"], cap_size=style["font_size"],
        cap_color=style["primary_color"], outline_c=style["outline_color"],
        cap_outline=style["outline"],
        # BorderStyle 3 = opaque box behind the line (filled with the outline
        # colour) — the CapCut/Hormozi "pill" caption meta
        cap_bstyle=style.get("border_style", 1),
        hook_font=hook_cfg.get("font", style["font"]),
        hook_size=hook_cfg.get("font_size", 84),
        hook_color=hook_cfg.get("color", "&H00FFFFFF"),
        hook_outline=hook_cfg.get("outline", 7),
        wm_font=wm_cfg.get("font", "Arial"),
        wm_size=wm_cfg.get("font_size", 48),
        wm_color=wm_cfg.get("color", "&H60FFFFFF"),
    )
    lines = []

    # watermark: whole clip, top-right (an9 + margins from style)
    if wm_cfg.get("text"):
        lines.append(
            f"Dialogue: 2,{_ts(0)},{_ts(clip_len)},Mark,,0,0,0,{_clean(wm_cfg['text'])}")

    # hook title: whole clip, upper-middle
    if hook:
        colors = hook_cfg.get("keyword_colors", ["&H0035D622"])
        kc = colors[hook_color_idx % len(colors)]
        hook_y = int(H_ * (hook_pos if hook_pos is not None
                          else hook_cfg.get("pos", 0.30)))
        lines.append(
            f"Dialogue: 1,{_ts(0)},{_ts(clip_len)},Hook,,0,0,0,"
            f"{{\\an5\\pos({W_ // 2},{hook_y})}}{_hook_text(hook, kc)}")

    # speech captions
    in_clip = [w for w in words if clip_start <= w.start < clip_end and w.text]
    for i in range(0, len(in_clip), wpl):
        group = in_clip[i:i + wpl]
        g_end = min(group[-1].end - clip_start + 0.15, clip_len)
        # never overlap the next group's first word, or captions ghost
        if i + wpl < len(in_clip):
            g_end = min(g_end, in_clip[i + wpl].start - clip_start)
        # one event per active word so the pop moves word-by-word
        for j, active in enumerate(group):
            ev_start = active.start - clip_start
            ev_end = group[j + 1].start - clip_start if j + 1 < len(group) else g_end
            if ev_end <= ev_start:
                continue
            parts = []
            for k, w in enumerate(group):
                txt = _clean(w.text)
                if upper:
                    txt = txt.upper()
                if k == j:
                    parts.append(
                        "{\\c" + style["highlight_color"] + "\\fscx110\\fscy110}"
                        + txt + "{\\r}")
                else:
                    parts.append(txt)
            text = " ".join(parts)
            # soft edge blur turns a colored outline into a neon glow
            blur = style.get("caption_blur", 0)
            blur_tag = f"\\blur{blur}" if blur else ""
            lines.append(
                f"Dialogue: 0,{_ts(ev_start)},{_ts(ev_end)},Cap,,0,0,0,"
                f"{{\\an5\\pos({W_ // 2},{pos_y})\\fad(50,0){blur_tag}}}{text}"
            )
    dest.write_text(header + "\n".join(lines), encoding="utf-8")
    return dest


def _dims(video: Path) -> tuple[int, int]:
    ffprobe = str(Path(ffmpeg_path()).parent / "ffprobe")
    if not Path(ffprobe).exists():
        ffprobe = "ffprobe"
    r = subprocess.run(
        [ffprobe, "-v", "error",
         "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True)
    w, h = r.stdout.strip().split("\n")[0].split(",")[:2]
    return int(w), int(h)


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def action_center_x(segment: Path, samples: int = 14,
                    exclude: tuple[float, float] | None = None) -> float | None:
    """Where the moving thing is, as a fraction of frame width.

    The gameplay pane keeps a portrait slice roughly half the frame wide, so a
    centred crop throws away both edges. Slot reels, loot rolls, killfeeds and
    scoreboards live at those edges, which is how a clip ends up being *about*
    something the viewer never sees.

    Frame-difference energy per column finds it without a model: whatever is
    animating during the payoff is the subject. `exclude` masks the cam
    overlay's x-range so a talking head doesn't win every time.

    Returns None when nothing stands out, so the caller keeps its own default
    rather than acting on noise.
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    cap = cv2.VideoCapture(str(segment))
    if not cap.isOpened():
        return None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    prev, energy = None, None
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None and prev.shape == g.shape:
            col = np.abs(g - prev).mean(axis=0)
            energy = col if energy is None else energy + col
        prev = g
    cap.release()
    if energy is None or not len(energy):
        return None
    width = len(energy)
    if exclude:
        a, b = int(exclude[0] * width), int(exclude[1] * width)
        energy[max(0, a):max(0, b)] = 0.0
    # smooth over ~8% of the width: single-column spikes are compression
    # noise, a real subject animates across a region
    win = max(3, int(width * 0.08))
    kern = np.ones(win) / win
    smooth = np.convolve(energy, kern, mode="same")
    # Absolute magnitude decides, not a ratio. Measured: a frozen scene peaks
    # at 0.03 while a spinning slot reel peaks at 118 — but the FROZEN clip
    # has the higher peak-to-median ratio (4.4 vs 2.7), because with no motion
    # the field is pure compression noise. A relative-only guard therefore
    # fires exactly backwards and crops static scenes at random.
    peak = float(smooth.max())
    if peak < MIN_ACTION_ENERGY:
        return None
    return float(int(smooth.argmax())) / width


def _split_filter(segment: Path, cam: tuple[float, float, float, float],
                  top_frac: float, source: str = "0:v",
                  action_x: float | None = None) -> str:
    """Facecam on top, gameplay below. cam = (x,y,w,h) fractions of source.

    `action_x` (0..1) centres the gameplay slice on whatever is moving. The
    slice is only about half the frame wide, so a centred crop drops both
    edges — where slot reels, loot rolls, killfeeds and scoreboards live. That
    is the founder's "the gambling wasn't even in frame": the moment was fine,
    the framing ate the payoff.

    Letterboxing the whole 16:9 frame into the pane was tried instead and
    rejected on sight — at 9:16 the game becomes a small strip between blurred
    bars. Cropping to the action keeps it full-bleed.
    """
    sw, sh = _dims(segment)
    top_h = _even(H * top_frac)
    bot_h = H - top_h


    # The cam is cropped EXACTLY, then fitted into the pane against a blurred
    # blow-up of itself. Reshaping the crop to the pane's aspect was the
    # source of every "camera is messed up": shrinking sliced the top of his
    # head off, and growing dragged in whatever sat next to the cam — a slab
    # of gameplay or empty desk parked beside his face.
    fx, fy, fw, fh = cam
    cx, cy, cw, ch = fx * sw, fy * sh, fw * sw, fh * sh
    cw, ch = min(cw, sw), min(ch, sh)
    cx = max(0, min(cx, sw - cw))
    cy = max(0, min(cy, sh - ch))
    fit_h = (cw / ch) < (W / top_h)   # tall cam -> fit the pane's height

    # gameplay: tallest crop matching the bottom pane's aspect, centred on the
    # action when we know where it is. This slice is only about half the frame
    # wide, so "centre" silently discards both edges — where slot reels, loot
    # rolls and killfeeds live.
    g_ar = W / bot_h
    gw, gh = sh * g_ar, sh
    if gw > sw:
        gw, gh = sw, sw / g_ar
    gy = (sh - gh) / 2
    gx = ((action_x * sw - gw / 2) if action_x is not None
          else (sw - gw) / 2)
    gx = max(0.0, min(gx, sw - gw))

    # the source's own cam overlay already fills the top pane — keep the
    # gameplay crop clear of it so the streamer isn't shown twice. Sliding
    # only works when a full-width slice fits beside the cam; big overlays
    # leave none, so shrink the crop into the widest clear span and let the
    # gameplay zoom rather than duplicate him.
    # pad the exclusion: the detected box tracks the head, and a cam overlay
    # spills past it (shoulders, hood, chair)
    pad = 0.06 * sw
    cam_x1, cam_x2 = max(0.0, fx * sw - pad), min(sw, (fx + fw) * sw + pad)
    if gx < cam_x2 and gx + gw > cam_x1:
        left, right = cam_x1, sw - cam_x2
        # prefer the side the action is on, not merely the wider side
        want_left = (action_x is not None and action_x * sw < cam_x1
                     and left >= gw)
        if want_left or (left >= right and not (action_x is not None
                                                and action_x * sw > cam_x2
                                                and right >= gw)):
            span_x, span_w = 0.0, left
        else:
            span_x, span_w = cam_x2, right
        if span_w >= gw:
            centre = (action_x * sw - gw / 2) if action_x is not None \
                else span_x + (span_w - gw) / 2
            gx = min(max(span_x, centre), min(span_x + span_w - gw, sw - gw))
        else:
            gw, gh = span_w, min(span_w / g_ar, sh)
            gw = gh * g_ar
            gx, gy = span_x + (span_w - gw) / 2, (sh - gh) / 2

    ccrop = f"crop={_even(cw)}:{_even(ch)}:{int(cx)}:{int(cy)}"
    fit = f"scale=-2:{top_h}" if fit_h else f"scale={W}:-2"
    return (
        f"[{source}]split=3[cb][cf][g];"
        # blurred blow-up of the cam fills whatever the fitted crop leaves —
        # never neighbouring screen content
        f"[cb]{ccrop},scale={W}:{top_h},gblur=sigma=24,eq=brightness=-0.06[bg];"
        f"[cf]{ccrop},{fit}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[top];"
        f"[g]crop={_even(gw)}:{_even(gh)}:{int(gx)}:{int(gy)},"
        f"scale={W}:{bot_h}[bot];"
        f"[top][bot]vstack"
    )


def render_landscape(segment: Path, ass_file: Path, dest: Path,
                     badge: str | None = None) -> Path:
    """16:9 1080p re-encode with burned captions — compilation building block.
    The source stream frame is already landscape; no cropping, full context.
    Uniform codec/fps/audio params so segments concat losslessly. `badge`
    (e.g. "#5") burns a countdown tag top-left for retention."""
    ass_path = str(ass_file).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    vf = (f"scale=1920:1080:force_original_aspect_ratio=decrease,"
          f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,ass={ass_path}")
    if badge:
        txt = badge.replace(":", "\\:").replace("'", "’")
        vf += (f",drawtext=text='{txt}':fontcolor=white:fontsize=90:"
               f"borderw=6:bordercolor=black@0.9:x=48:y=40")
    cmd = [
        ffmpeg_path(), "-y", "-v", "error",
        "-fflags", "+genpts", "-i", str(segment),
        "-vf", vf,
        # yt-dlp keyframe-cut segments can start audio and video at different
        # PTS; force CFR video + resampled audio pinned to 0 so every segment
        # is self-synced and concatenation can't accumulate A/V drift
        "-vsync", "cfr", "-af", "aresample=async=1:first_pts=0",
        "-r", "30", "-video_track_timescale", "30000",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"landscape render failed: {r.stderr[-2000:]}")
    return dest


def _brand_drawtext(brand: str, h_frac: float = 0.035,
                    size: int = 30) -> str:
    """Small always-on channel watermark — consistent editorial identity is
    the cheapest reused-content-policy armor an automated channel has."""
    font = Path(__file__).parent / "fonts" / "Montserrat-ExtraBold.ttf"
    txt = brand.replace("\\", "").replace("'", "").replace(":", "\\:")
    return (f"drawtext=text='{txt}':fontfile='{font}':fontsize={size}:"
            f"fontcolor=white@0.55:borderw=2:bordercolor=black@0.35:"
            f"x=(w-tw)/2:y=h*{h_frac}")


def title_card(text: str, dest: Path, dur: float = 0.9,
               brand: str = "") -> Path:
    """Branded inter-clip card for compilations (1920x1080, silent, CFR 30).
    Light 'curated show' framing — reads as editorial, not raw repost."""
    font = Path(__file__).parent / "fonts" / "Montserrat-ExtraBold.ttf"
    txt = text.replace("\\", "").replace("'", "").replace(":", "\\:")[:70]
    # Montserrat-XB is ~0.62em wide per char: shrink to fit 1920 with margin
    size = min(64, int(1740 / (0.62 * max(len(txt), 1))))
    vf = (f"drawtext=text='{txt}':fontfile='{font}':fontsize={size}:"
          f"fontcolor=white:x=(w-tw)/2:y=(h-th)/2")
    if brand:
        b = brand.replace("\\", "").replace("'", "").replace(":", "\\:")
        vf += (f",drawtext=text='{b}':fontfile='{font}':fontsize=36:"
               f"fontcolor=white@0.5:x=(w-tw)/2:y=h*0.82")
    cmd = [
        ffmpeg_path(), "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=0x101012:s=1920x1080:d={dur},fps=30",
        "-f", "lavfi", "-i",
        f"anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(dur), "-vf", vf, "-shortest",
        # stream params MUST match render_landscape exactly — the concat
        # demuxer silently mangles timestamps on mixed timebases/fps (the
        # half-speed-video bug)
        "-vsync", "cfr", "-r", "30", "-video_track_timescale", "30000",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"title card failed: {r.stderr[-2000:]}")
    return dest


def cut_silences(segment: Path, keep: list[tuple[float, float]],
                 dest: Path) -> Path:
    """Jump-cut a downloaded segment to the given keep-intervals (seconds,
    relative to segment start). CFR + per-part aresample keeps A/V sync
    across the concat (same lesson as the compiler)."""
    parts, pads = [], []
    for i, (s, e) in enumerate(keep):
        parts.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,"
            f"aresample=async=1:first_pts=0[a{i}];")
        pads.append(f"[v{i}][a{i}]")
    fc = ("".join(parts) + "".join(pads)
          + f"concat=n={len(keep)}:v=1:a=1[v][a]")
    cmd = [
        ffmpeg_path(), "-y", "-v", "error",
        "-i", str(segment),
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-fps_mode", "cfr", "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-video_track_timescale", "30000",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"silence cut failed: {r.stderr[-2000:]}")
    return dest


def render_editor_proxy(
        segment: Path, dest: Path,
        cam: tuple[float, float, float, float] | None = None,
        top_frac: float = 0.42, crop: str = "center") -> Path:
    """Fast continuous 360x640 proxy for interactive timing edits.

    Layout is locked to the final 9:16 composition, but captions/hooks stay in
    the browser so timeline changes require no encode. One-second keyframes
    make cut-to-cut seeking responsive.
    """
    pw, ph = 360, 640
    sw, sh = _dims(segment)
    if cam:
        top_h = _even(ph * top_frac)
        bot_h = ph - top_h
        fx, fy, fw, fh = cam
        cx, cy = max(0, int(fx * sw)), max(0, int(fy * sh))
        cw, ch = max(2, int(fw * sw)), max(2, int(fh * sh))
        cw, ch = min(cw, sw - cx), min(ch, sh - cy)
        g_ar = pw / bot_h
        gw, gh = sh * g_ar, sh
        if gw > sw:
            gw, gh = sw, sw / g_ar
        gx, gy = (sw - gw) / 2, (sh - gh) / 2
        vf = (
            f"[0:v]split=2[c][g];"
            f"[c]crop={cw}:{ch}:{cx}:{cy},"
            f"scale={pw}:{top_h}:force_original_aspect_ratio=decrease,"
            f"pad={pw}:{top_h}:(ow-iw)/2:(oh-ih)/2:black[top];"
            f"[g]crop={_even(gw)}:{_even(gh)}:{_even(gx)}:{_even(gy)},"
            f"scale={pw}:{bot_h}[bot];"
            f"[top][bot]vstack,fps=30,setsar=1[v]"
        )
    else:
        if crop == "left":
            x = 0
        elif crop == "right":
            x = max(0, sw - sh * 9 / 16)
        else:
            x = max(0, (sw - sh * 9 / 16) / 2)
        vf = (
            f"[0:v]crop={_even(sh * 9 / 16)}:{sh}:{_even(x)}:0,"
            f"scale={pw}:{ph},fps=30,setsar=1[v]"
        )
    cmd = [
        ffmpeg_path(), "-y", "-v", "error", "-i", str(segment),
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "30",
        "-sc_threshold", "0", "-r", "30",
        "-c:a", "aac", "-b:a", "96k", "-ar", "48000",
        "-video_track_timescale", "30000", "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"editor proxy failed: {r.stderr[-2000:]}")
    return dest


def audio_waveform_peaks(media: Path, bins: int = 600) -> list[float]:
    """Return normalized mono audio peaks for the browser timeline."""
    import numpy as np

    cmd = [
        ffmpeg_path(), "-v", "error", "-i", str(media),
        "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        return []
    samples = np.abs(
        np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32))
    if not len(samples):
        return []
    edges = np.linspace(0, len(samples), bins + 1, dtype=int)
    peaks = np.array([
        float(samples[edges[i]:edges[i + 1]].max())
        if edges[i + 1] > edges[i] else 0.0
        for i in range(bins)
    ], dtype=np.float32)
    # A percentile scale keeps ordinary speech legible when one scream peaks.
    scale = max(1.0, float(np.percentile(peaks, 95)))
    normalized = np.sqrt(np.clip(peaks / scale, 0, 1))
    return [round(float(value), 3) for value in normalized]


def _opening_filter(effect: str) -> str:
    """A restrained first-second motion pattern on the completed 9:16 frame.

    zoompan runs after layout/captions so every template behaves the same for
    split and full-frame clips. Effects settle to 1.0 rather than looping;
    their job is to catch the first glance, not distract from the story.
    """
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if effect == "punch_zoom":
        z = "z='if(lte(on,18),1.12-0.12*on/18,1)'"
        return f",fps=30,zoompan={z}:{center}:d=1:s={W}x{H}:fps=30,setsar=1"
    if effect == "impact":
        z = ("z='if(lte(on,3),1+0.08*on/3,"
             "if(lte(on,18),1.08-0.08*(on-3)/15,1))'")
        return f",fps=30,zoompan={z}:{center}:d=1:s={W}x{H}:fps=30,setsar=1"
    if effect == "drift_pan":
        z = "z='if(lte(on,24),1.06-0.06*on/24,1)'"
        x = "x='if(lte(on,24),(iw-iw/zoom)*(1-on/24),0)'"
        return (f",fps=30,zoompan={z}:{x}:y='ih/2-(ih/zoom/2)':"
                f"d=1:s={W}x{H}:fps=30,setsar=1")
    return ""


def render_short(segment: Path, ass_file: Path, dest: Path, crop: str = "center",
                 cam: tuple[float, float, float, float] | None = None,
                 top_frac: float = 0.42, brand: str = "",
                 opening_effect: str = "clean",
                 keep: list[tuple[float, float]] | None = None,
                 action_x: float | None = None) -> Path:
    """Render a final 9:16 short.

    ``keep`` contains source-relative intervals. When supplied, trimming,
    concatenation, layout, captions and encoding happen in one ffmpeg graph.
    This avoids the old cut_silences intermediate and its second H.264 encode.
    """
    if action_x is not None:
        # full-frame path is a fixed slice too, and cuts the same payoffs the
        # split path did — centre it on the action when we located it.
        # Resolved numerically: ffmpeg parses a comma inside clip() as a
        # filter separator, so an expression here silently breaks the graph.
        _sw, _sh = _dims(segment)
        _cw = _sh * 9 / 16
        x = str(int(max(0.0, min(action_x * _sw - _cw / 2, _sw - _cw))))
    elif crop == "left":
        x = "0"
    elif crop == "right":
        x = "iw-ih*9/16"
    else:
        x = "(iw-ih*9/16)/2"
    # escape path for the ass filter (colons, quotes)
    ass_path = str(ass_file).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    trimmed = bool(keep)
    source_label = "cutv" if trimmed else "0:v"
    if cam:
        vf = _split_filter(segment, cam, top_frac, source=source_label,
                           action_x=action_x)
        vf += f",setsar=1,ass={ass_path}"
    else:
        vf = (f"[{source_label}]crop=ih*9/16:ih:{x}:0,"
              f"scale={W}:{H},setsar=1,ass={ass_path}" if trimmed else
              f"crop=ih*9/16:ih:{x}:0,scale={W}:{H},setsar=1,ass={ass_path}")
    if brand:
        vf += "," + _brand_drawtext(brand)
    vf += _opening_filter(opening_effect)
    cmd = [
        ffmpeg_path(), "-y", "-v", "error",
        "-i", str(segment),
    ]
    if opening_effect == "impact":
        # Generated locally: no licensed sound asset or external dependency.
        cmd += [
            "-f", "lavfi", "-t", "0.32", "-i",
            "sine=frequency=70:sample_rate=48000",
        ]
    if trimmed:
        parts, pads = [], []
        for i, (start, end) in enumerate(keep or []):
            parts.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},"
                f"setpts=PTS-STARTPTS[v{i}];"
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"aresample=async=1:first_pts=0[a{i}];")
            pads.append(f"[v{i}][a{i}]")
        graph = ("".join(parts) + "".join(pads)
                 + f"concat=n={len(keep or [])}:v=1:a=1[cutv][cuta];"
                 + vf + "[outv];")
        if opening_effect == "impact":
            graph += (
                "[cuta]aresample=async=1:first_pts=0[base];"
                "[1:a]afade=t=out:st=0.04:d=0.25,volume=0.16[sfx];"
                "[base][sfx]amix=inputs=2:duration=first:"
                "dropout_transition=0:normalize=0[outa]")
        else:
            graph += "[cuta]aresample=async=1:first_pts=0[outa]"
        cmd += ["-filter_complex", graph, "-map", "[outv]", "-map", "[outa]"]
    else:
        cmd += ["-vf", vf]
    cmd += [
        "-fps_mode", "cfr", "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
    ]
    if opening_effect == "impact" and not trimmed:
        cmd += [
            "-filter_complex",
            "[0:a]aresample=async=1:first_pts=0[base];"
            "[1:a]afade=t=out:st=0.04:d=0.25,volume=0.16[sfx];"
            "[base][sfx]amix=inputs=2:duration=first:"
            "dropout_transition=0:normalize=0[a]",
            "-map", "0:v:0", "-map", "[a]",
        ]
    elif not trimmed:
        cmd += ["-af", "aresample=async=1:first_pts=0"]
    cmd += [
        "-video_track_timescale", "30000",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"render failed: {r.stderr[-2000:]}")
    return dest
