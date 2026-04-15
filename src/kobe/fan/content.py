"""Programmatic content generators for the Project KOBE holographic fan.

Each public function renders a short MP4 clip (512x512 default, 30 FPS, H.264
yuv420p, pure-black background — the fan treats black as transparent) and
returns its path. Outputs are hash-deduplicated: same inputs → same hash →
no rewrite. Pure functions: no bus, no asyncio, no module-level mutable
state. Heavy deps (imageio/numpy/trimesh) are lazy-imported so bare `import
kobe.fan.content` works without the hologram optional extras.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import structlog
from PIL import Image, ImageDraw, ImageFont

from kobe.config import Settings

log = structlog.get_logger(__name__)

# Theme tokens (RGB) — mirror the browser HUD palette.
CYAN, MAGENTA, AMBER = (0x00, 0xD4, 0xFF), (0xFF, 0x3A, 0xF5), (0xF5, 0xB5, 0x00)
GREEN, RED, WHITE, BLACK = (0x00, 0xE6, 0x76), (0xFF, 0x3A, 0x3A), (0xFF, 0xFF, 0xFF), (0, 0, 0)


# --- helpers ---------------------------------------------------------------
def _content_dir(settings: Settings) -> Path:
    d = Path(settings.hologram_output_dir) / "content"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hash(*parts: object) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(repr(p).encode("utf-8")); h.update(b"|")
    return h.hexdigest()[:10]


def _blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] * (1 - t) + b[0] * t), int(a[1] * (1 - t) + b[1] * t),
            int(a[2] * (1 - t) + b[2] * t))


def _canvas(res: int) -> Image.Image:
    return Image.new("RGB", (res, res), BLACK)


def _writer(path: Path, fps: int):
    import imageio  # lazy
    return imageio.get_writer(str(path), fps=fps, codec="libx264",
                              pixelformat="yuv420p", quality=8, macro_block_size=1)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _tsize(draw, text, font):
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except Exception:
        return int(draw.textlength(text, font=font)), 8


def _to_np(img: Image.Image):
    import numpy as np  # lazy
    return np.asarray(img.convert("RGB"), dtype=np.uint8)


# --- 1. rotating logo ------------------------------------------------------
def render_rotating_logo(settings: Settings, *, text: str = "KOBE",
                         seconds: float = 3.0) -> Path:
    """Rotating KOBE glyph on black. Loops cleanly (first == last frame)."""
    res, fps = int(settings.hologram_resolution), int(settings.hologram_fps)
    seconds = max(0.5, float(seconds))
    frames = max(2, int(round(seconds * fps)))
    out = _content_dir(settings) / f"logo_{_hash('logo', text, res, fps, frames)}.mp4"
    if out.exists():
        return out

    c = res // 2
    rad = int(res * 0.36)
    f_big = _font(max(18, res // 8))
    f_sm = _font(max(12, res // 22))

    with _writer(out, fps) as w:
        for i in range(frames):
            phase = i / frames  # endpoint excluded → clean loop
            angle = phase * 2 * math.pi
            img = _canvas(res)
            draw = ImageDraw.Draw(img)
            bbox_o = (c - rad, c - rad, c + rad, c + rad)
            for d in range(36):  # dashed outer cyan ring
                a0 = angle + d * (2 * math.pi / 36)
                a1 = a0 + (2 * math.pi / 36) * 0.55
                draw.arc(bbox_o, math.degrees(a0), math.degrees(a1), fill=CYAN, width=3)
            r2 = int(rad * 0.72)
            bbox_i = (c - r2, c - r2, c + r2, c + r2)
            for d in range(18):  # counter-rotating magenta accent
                a0 = -angle * 1.3 + d * (2 * math.pi / 18)
                a1 = a0 + (2 * math.pi / 18) * 0.35
                draw.arc(bbox_i, math.degrees(a0), math.degrees(a1), fill=MAGENTA, width=2)
            col = _blend(WHITE, CYAN, 0.5 + 0.5 * math.sin(phase * 2 * math.pi))
            tw, th = _tsize(draw, text, f_big)
            draw.text((c - tw // 2, c - th // 2 - res // 40), text, fill=col, font=f_big)
            sub = "HOLOGRAM"
            sw, sh = _tsize(draw, sub, f_sm)
            draw.text((c - sw // 2, c + th // 2 + res // 60), sub, fill=AMBER, font=f_sm)
            w.append_data(_to_np(img))
    log.info("rendered.logo", path=str(out), frames=frames)
    return out


# --- 2. progress ring ------------------------------------------------------
def render_progress_ring(settings: Settings, *, pct: float, stage: str,
                         filename: str = "") -> Path:
    """Circular progress ring with percentage in the center and stage below."""
    res, fps = int(settings.hologram_resolution), int(settings.hologram_fps)
    pct_clamped = max(0.0, min(100.0, float(pct)))
    # Bucket pct to nearest 5% so jittery telemetry doesn't thrash renders.
    pct_r = int(round(pct_clamped / 5.0) * 5)
    stage_n = (stage or "unknown").strip().lower()
    fname_n = (filename or "")[:40]
    color = {"idle": CYAN, "preparing": AMBER, "printing": GREEN,
             "paused": AMBER, "finished": GREEN, "failed": RED}.get(stage_n, CYAN)

    frames = max(2, int(round(2.5 * fps)))
    out = _content_dir(settings) / f"printer_{_hash('printer', pct_r, stage_n, fname_n, res, fps)}.mp4"
    if out.exists():
        return out

    c = res // 2
    r_o, r_i = int(res * 0.40), int(res * 0.34)
    f_pct = _font(max(22, res // 7))
    f_stage = _font(max(12, res // 22))
    f_file = _font(max(10, res // 30))
    sweep = (pct_r / 100.0) * 360.0

    with _writer(out, fps) as w:
        for i in range(frames):
            phase = i / frames
            img = _canvas(res)
            draw = ImageDraw.Draw(img)
            bbox_o = (c - r_o, c - r_o, c + r_o, c + r_o)
            draw.arc(bbox_o, 0, 360, fill=(40, 40, 50), width=max(3, res // 80))
            if sweep > 0:
                draw.arc(bbox_o, -90, -90 + sweep, fill=color, width=max(5, res // 55))
            # Breathing head-bead orbits the arc end.
            ha = math.radians(-90 + sweep)
            bax, bay = c + r_o * math.cos(ha), c + r_o * math.sin(ha)
            br = 3 + 2 * math.sin(phase * 2 * math.pi)
            draw.ellipse((bax - br, bay - br, bax + br, bay + br), fill=WHITE)
            draw.ellipse((c - r_i, c - r_i, c + r_i, c + r_i), outline=(30, 30, 35), width=1)
            pct_str = f"{pct_r}%"
            pw, ph = _tsize(draw, pct_str, f_pct)
            draw.text((c - pw // 2, c - ph // 2 - res // 30), pct_str, fill=WHITE, font=f_pct)
            lbl = stage_n.upper()
            sw, sh = _tsize(draw, lbl, f_stage)
            draw.text((c - sw // 2, c + ph // 2 - res // 80), lbl, fill=color, font=f_stage)
            if fname_n:
                disp = fname_n if len(fname_n) <= 22 else fname_n[:20] + ".."
                fw, fh = _tsize(draw, disp, f_file)
                draw.text((c - fw // 2, c + r_i - fh - 4), disp, fill=AMBER, font=f_file)
            w.append_data(_to_np(img))
    log.info("rendered.printer", path=str(out), pct=pct_r, stage=stage_n)
    return out


# --- 3. spotify waveform (simulated) ---------------------------------------
def render_spotify_waveform(settings: Settings, *, is_playing: bool,
                            track: str = "", artist: str = "") -> Path:
    """Animated bar visualizer. Deterministic sin pattern seeded from track."""
    res, fps = int(settings.hologram_resolution), int(settings.hologram_fps)
    track = (track or "").strip()
    artist = (artist or "").strip()
    frames = max(2, int(round(3.0 * fps)))
    out = _content_dir(settings) / f"spotify_{_hash('spotify', is_playing, track[:60], artist[:60], res, fps)}.mp4"
    if out.exists():
        return out

    n_bars = 24
    seed = hashlib.sha1((track or "silence").encode("utf-8")).digest()
    phases = [(seed[i % len(seed)] / 255.0) * 2 * math.pi for i in range(n_bars)]
    freqs = [0.8 + (seed[(i + 5) % len(seed)] / 255.0) * 1.6 for i in range(n_bars)]

    cx, cy = res // 2, res // 2
    area_w, area_h = int(res * 0.82), int(res * 0.36)
    gap = 2
    bw = max(2, (area_w - gap * (n_bars - 1)) // n_bars)
    min_h = max(3, res // 80)
    max_h = area_h // 2
    f_track = _font(max(12, res // 26))
    f_artist = _font(max(10, res // 34))
    f_label = _font(max(10, res // 30))

    with _writer(out, fps) as w:
        for i in range(frames):
            phase = i / frames
            img = _canvas(res)
            draw = ImageDraw.Draw(img)
            amp = 1.0 if is_playing else 0.15  # paused = near-flat
            x0 = cx - (n_bars * bw + (n_bars - 1) * gap) // 2
            for b in range(n_bars):
                v1 = 0.5 + 0.5 * math.sin(phase * 2 * math.pi * freqs[b] + phases[b])
                v2 = 0.5 + 0.5 * math.sin(phase * 2 * math.pi * freqs[b] * 1.7 + phases[b] * 1.3)
                h = int(min_h + (max_h - min_h) * (0.45 * v1 + 0.55 * v2) * amp)
                x = x0 + b * (bw + gap)
                col = _blend(CYAN, MAGENTA, h / max_h if max_h else 0)
                draw.rectangle((x, cy - h, x + bw, cy + h), fill=col)

            # Play/pause glyph top-center.
            gy = int(res * 0.15)
            gs = max(8, res // 30)
            if is_playing:
                draw.polygon([(cx - gs // 2, gy - gs // 2), (cx - gs // 2, gy + gs // 2),
                              (cx + gs // 2, gy)], fill=GREEN)
            else:
                draw.rectangle((cx - gs // 2, gy - gs // 2, cx - gs // 6, gy + gs // 2), fill=AMBER)
                draw.rectangle((cx + gs // 6, gy - gs // 2, cx + gs // 2, gy + gs // 2), fill=AMBER)

            label_y = cy + max_h + max(8, res // 40)
            if track:
                disp = track if len(track) <= 28 else track[:26] + ".."
                tw, th = _tsize(draw, disp, f_track)
                draw.text((cx - tw // 2, label_y), disp, fill=WHITE, font=f_track)
                label_y += th + 4
            if artist:
                disp = artist if len(artist) <= 30 else artist[:28] + ".."
                tw, th = _tsize(draw, disp, f_artist)
                draw.text((cx - tw // 2, label_y), disp, fill=CYAN, font=f_artist)
            if not track and not artist:
                msg = "NO PLAYBACK"
                tw, th = _tsize(draw, msg, f_label)
                draw.text((cx - tw // 2, label_y), msg, fill=AMBER, font=f_label)
            w.append_data(_to_np(img))
    log.info("rendered.spotify", path=str(out), track=track[:40], is_playing=is_playing)
    return out


# --- 4. gesture flash ------------------------------------------------------
def _draw_swipe(draw, res, c, phase, direction, color):
    al = int(res * 0.4)
    thick = max(4, res // 40)
    y = c
    span = res + al * 1.2
    start_x = int(-al * 0.6 + phase * span) if direction > 0 else int(res + al * 0.6 - phase * span)
    end_x = start_x + direction * al
    draw.line([(start_x, y), (end_x, y)], fill=color, width=thick)
    head = max(10, res // 20)
    draw.polygon([(end_x, y), (end_x - direction * head, y - head),
                  (end_x - direction * head, y + head)], fill=color)
    for k in range(1, 5):  # trailing dots
        tx = end_x - direction * al - direction * k * head
        r = max(2, thick - k)
        draw.ellipse((tx - r, y - r, tx + r, y + r), fill=color)


def _draw_point(draw, res, c, phase, color):
    base_y, tip_y = c + int(res * 0.22), c - int(res * 0.08)
    thick = max(8, res // 24)
    draw.rectangle((c - thick // 2, tip_y, c + thick // 2, base_y), fill=color)
    draw.ellipse((c - thick, tip_y - thick, c + thick, tip_y + thick), fill=color)
    pr = int(res * 0.05 + phase * res * 0.35)
    pc = _blend(color, BLACK, phase)
    draw.ellipse((c - pr, tip_y - pr - res // 10, c + pr, tip_y + pr - res // 10),
                 outline=pc, width=max(2, res // 120))


def _draw_confirm(draw, res, c, phase, color):
    thick = max(6, res // 28)
    grow = min(1.0, phase / 0.6)
    p1 = (c - res // 6, c)
    p2 = (c - res // 30, c + res // 8)
    p3 = (c + res // 4, c - res // 6)
    if grow < 0.5:
        t = grow / 0.5
        cur = (int(p1[0] + (p2[0] - p1[0]) * t), int(p1[1] + (p2[1] - p1[1]) * t))
        draw.line([p1, cur], fill=color, width=thick)
    else:
        draw.line([p1, p2], fill=color, width=thick)
        t = (grow - 0.5) / 0.5
        cur = (int(p2[0] + (p3[0] - p2[0]) * t), int(p2[1] + (p3[1] - p2[1]) * t))
        draw.line([p2, cur], fill=color, width=thick)
    bt = max(0.0, phase - 0.4) / 0.6
    if bt > 0:
        rays = 16
        r0 = int(res * 0.18 + bt * res * 0.08)
        r1 = int(res * 0.26 + bt * res * 0.20)
        rc = _blend(color, BLACK, bt * 0.6)
        for k in range(rays):
            a = k * (2 * math.pi / rays)
            draw.line([(c + r0 * math.cos(a), c + r0 * math.sin(a)),
                       (c + r1 * math.cos(a), c + r1 * math.sin(a))],
                      fill=rc, width=max(2, res // 120))


def _draw_dismiss(draw, res, c, phase, color):
    shake = int(math.sin(phase * 2 * math.pi * 4.0) * res * 0.03)
    cx = c + shake
    arm = int(res * 0.22)
    thick = max(6, res // 26)
    draw.line([(cx - arm, c - arm), (cx + arm, c + arm)], fill=color, width=thick)
    draw.line([(cx - arm, c + arm), (cx + arm, c - arm)], fill=color, width=thick)
    ring = int(res * 0.32)
    draw.ellipse((cx - ring, c - ring, cx + ring, c + ring),
                 outline=_blend(color, BLACK, 0.5), width=2)


def _draw_generic(draw, res, c, phase, color):
    pr = int(res * 0.18 + math.sin(phase * 2 * math.pi) * res * 0.04)
    draw.ellipse((c - pr, c - pr, c + pr, c + pr), outline=color, width=max(3, res // 80))


def render_gesture_flash(settings: Settings, *, gesture: str,
                         seconds: float | None = None) -> Path:
    """Short flash clip keyed to one of the five KOBE gesture names."""
    res, fps = int(settings.hologram_resolution), int(settings.hologram_fps)
    name = (gesture or "").strip().lower()
    secs = max(0.3, float(seconds) if seconds is not None else float(settings.hologram_gesture_flash_s))
    frames = max(2, int(round(secs * fps)))
    out = _content_dir(settings) / f"gesture_{name or 'unknown'}_{_hash('gesture', name, round(secs, 2), res, fps)}.mp4"
    if out.exists():
        return out

    c = res // 2
    f_lbl = _font(max(14, res // 20))
    with _writer(out, fps) as w:
        for i in range(frames):
            phase = i / frames
            img = _canvas(res)
            draw = ImageDraw.Draw(img)
            if name == "swipe_left":
                _draw_swipe(draw, res, c, phase, -1, CYAN)
            elif name == "swipe_right":
                _draw_swipe(draw, res, c, phase, +1, CYAN)
            elif name == "point":
                _draw_point(draw, res, c, phase, MAGENTA)
            elif name == "confirm":
                _draw_confirm(draw, res, c, phase, GREEN)
            elif name == "dismiss":
                _draw_dismiss(draw, res, c, phase, RED)
            else:
                _draw_generic(draw, res, c, phase, WHITE)
            if name:
                label = name.upper().replace("_", " ")
                tw, th = _tsize(draw, label, f_lbl)
                alpha = 1.0 - abs(phase - 0.5) * 2.0
                col = _blend(BLACK, WHITE, 0.35 + 0.65 * max(0.0, alpha))
                draw.text((c - tw // 2, res - th - res // 20), label, fill=col, font=f_lbl)
            w.append_data(_to_np(img))
    log.info("rendered.gesture", path=str(out), gesture=name, seconds=secs)
    return out


# --- 5. STL rotation (best-effort; offscreen GL may be unavailable) --------
def render_stl_rotation(settings: Settings, *, stl_path: str,
                        seconds: float = 4.0) -> Path | None:
    """Slowly rotate an STL/OBJ around Y. None if offscreen GL is unavailable."""
    path = Path(stl_path).expanduser()
    if not path.is_file():
        log.warning("stl.missing", path=str(path))
        return None
    res, fps = int(settings.hologram_resolution), int(settings.hologram_fps)
    frames = max(2, int(round(float(seconds) * fps)))
    try:
        st = path.stat()
        file_key = f"{path.name}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        file_key = str(path)
    out = _content_dir(settings) / f"stl_{_hash('stl', file_key, res, fps, frames)}.mp4"
    if out.exists():
        return out

    try:
        import trimesh  # lazy
        from trimesh import transformations as tft  # type: ignore

        mesh = trimesh.load(str(path), force="mesh")
        if mesh is None or getattr(mesh, "is_empty", True):
            log.warning("stl.empty", path=str(path))
            return None
        # Center + normalize so the model fits regardless of source units.
        try:
            mesh.apply_translation(-mesh.centroid)
            scale = float(mesh.extents.max()) or 1.0
            mesh.apply_scale(1.0 / scale)
        except Exception:  # noqa: BLE001
            pass

        scene = trimesh.Scene(mesh)
        node = list(scene.graph.nodes_geometry)[0]
        with _writer(out, fps) as w:
            for i in range(frames):
                rot = tft.rotation_matrix((i / frames) * 2 * math.pi, [0.0, 1.0, 0.0])
                scene.graph.update(frame_to=node, matrix=rot)
                png = scene.save_image(resolution=(res, res), visible=False)
                if not png:
                    log.warning("stl.render_empty_frame", frame=i)
                    return None
                w.append_data(_to_np(_load_png_rgb(png, res)))
    except Exception as exc:  # noqa: BLE001 — offscreen GL can raise many ways;
        # we specifically don't catch BaseException so asyncio.CancelledError
        # / KeyboardInterrupt / SystemExit still propagate (CancelledError is
        # BaseException on 3.11+).
        log.warning("stl.offscreen_failed", path=str(path), error=repr(exc))
        try:
            if out.exists():
                out.unlink()
        except OSError:
            pass
        return None

    log.info("rendered.stl", path=str(out), seconds=seconds)
    return out


def _load_png_rgb(png_bytes: bytes, res: int) -> Image.Image:
    from io import BytesIO
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    if img.size != (res, res):
        img = img.resize((res, res), Image.LANCZOS)
    bg = _canvas(res)
    bg.paste(img, (0, 0))
    return bg
