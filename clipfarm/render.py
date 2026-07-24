"""Render vertical shorts: crop to 9:16, burn hook title + word captions + watermark."""

import subprocess
from pathlib import Path

from .config import ffmpeg_path
from .transcribe import Word

W, H = 1080, 1920

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


def _split_filter(segment: Path, cam: tuple[float, float, float, float],
                  top_frac: float) -> str:
    """Facecam on top, gameplay below. cam = (x,y,w,h) fractions of source."""
    sw, sh = _dims(segment)
    top_h = _even(H * top_frac)
    bot_h = H - top_h

    # cam crop matched to the top pane's aspect by GROWING the deficient
    # side, never shrinking: shrinking + re-centering sliced the top of the
    # streamer's head off and zoomed into his mouth. Growing adds
    # surrounding webcam area instead, which reads naturally.
    fx, fy, fw, fh = cam
    cx, cy, cw, ch = fx * sw, fy * sh, fw * sw, fh * sh
    target_ar = W / top_h
    if cw / ch > target_ar:          # too wide -> grow height
        grow = cw / target_ar - ch
        cy -= grow / 2
        ch += grow
    else:                             # too tall -> grow width
        grow = ch * target_ar - cw
        cx -= grow / 2
        cw += grow
    if cw > sw:                       # only now shrink, to fit the source
        ch *= sw / cw
        cw = sw
    if ch > sh:
        cw *= sh / ch
        ch = sh
    cx = max(0, min(cx, sw - cw))
    cy = max(0, min(cy, sh - ch))

    # gameplay: tallest centered crop matching the bottom pane's aspect
    g_ar = W / bot_h
    gw, gh = sh * g_ar, sh
    if gw > sw:
        gw, gh = sw, sw / g_ar
    gx, gy = (sw - gw) / 2, (sh - gh) / 2

    # the source's own cam overlay already fills the top pane — slide the
    # gameplay crop sideways so it doesn't appear a second time below
    cam_x1, cam_x2 = fx * sw, (fx + fw) * sw
    if gw < sw and gx < cam_x2 and gx + gw > cam_x1:
        if (cam_x1 + cam_x2) / 2 < sw / 2:
            gx = min(cam_x2, sw - gw)   # cam on the left -> slide right
        else:
            gx = max(cam_x1 - gw, 0.0)  # cam on the right -> slide left

    return (
        f"[0:v]split=2[c][g];"
        f"[c]crop={_even(cw)}:{_even(ch)}:{int(cx)}:{int(cy)},"
        f"scale={W}:{top_h}[top];"
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
        "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"silence cut failed: {r.stderr[-2000:]}")
    return dest


def render_short(segment: Path, ass_file: Path, dest: Path, crop: str = "center",
                 cam: tuple[float, float, float, float] | None = None,
                 top_frac: float = 0.42, brand: str = "") -> Path:
    if crop == "left":
        x = "0"
    elif crop == "right":
        x = "iw-ih*9/16"
    else:
        x = "(iw-ih*9/16)/2"
    # escape path for the ass filter (colons, quotes)
    ass_path = str(ass_file).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    if cam:
        vf = _split_filter(segment, cam, top_frac) + f",ass={ass_path}"
    else:
        vf = f"crop=ih*9/16:ih:{x}:0,scale={W}:{H},ass={ass_path}"
    if brand:
        vf += "," + _brand_drawtext(brand)
    cmd = [
        ffmpeg_path(), "-y", "-v", "error",
        "-i", str(segment),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"render failed: {r.stderr[-2000:]}")
    return dest
