import subprocess
from pathlib import Path
import hashlib

from app.config import FFMPEG_BIN, THUMBNAILS_DIR, IMAGE_EXTENSIONS, TEMP_DIR


def _thumb_path(file_path: str) -> Path:
    h = hashlib.md5(file_path.encode()).hexdigest()
    return THUMBNAILS_DIR / f"{h}.jpg"


async def get_thumbnail(file_path: str) -> Path | None:
    thumb = _thumb_path(file_path)
    if thumb.exists():
        return thumb

    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return _image_thumbnail(file_path, thumb)
    return _video_thumbnail(file_path, thumb)


def _video_thumbnail(file_path: str, thumb: Path) -> Path | None:
    cmd = [
        FFMPEG_BIN, "-y", "-i", file_path,
        "-ss", "00:00:02", "-vframes", "1",
        "-vf", "scale=320:-1",
        "-q:v", "5",
        str(thumb)
    ]
    subprocess.run(cmd, capture_output=True)
    return thumb if thumb.exists() else None


def _image_thumbnail(file_path: str, thumb: Path) -> Path | None:
    from PIL import Image
    img = Image.open(file_path)
    img.thumbnail((320, 320))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(str(thumb), "JPEG", quality=80)
    img.close()
    return thumb


# ---------------------------------------------------------------------------
# YouTube-quality thumbnails and intro/outro cards (PIL text rendering)
# ---------------------------------------------------------------------------

# Bold faces first (they read better at thumbnail size), with regular and
# Linux DejaVu fallbacks. All cover Turkish glyphs (ş ğ ı ö ü ç).
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont
    for cand in _FONT_CANDIDATES:
        try:
            if Path(cand).exists():
                return ImageFont.truetype(cand, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10
    except Exception:
        return ImageFont.load_default()


def _wrap_by_width(draw, text: str, font, max_width: float) -> list[str]:
    """Greedy word-wrap measured in pixels for the given font."""
    words = (text or "").split()
    if not words:
        return []
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _probe_duration(video_path: str) -> float:
    from app.services.ffmpeg_service import _get_duration
    try:
        return float(_get_duration(video_path))
    except Exception:
        return 0.0


def _extract_frame(video_path: str, t: float, out_path: Path,
                   w: int, h: int) -> Path | None:
    cmd = [
        FFMPEG_BIN, "-y", "-ss", f"{max(0.0, t):.2f}", "-i", video_path,
        "-frames:v", "1",
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        "-q:v", "3", str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    return out_path if out_path.exists() else None


def _frame_score(img) -> float:
    """Heuristic 'good thumbnail frame' score: detail + mid brightness + colour."""
    from PIL import ImageStat, ImageFilter
    gray = img.convert("L")
    mean = ImageStat.Stat(gray).mean[0]
    # Prefer mid brightness (~130); penalise near-black / blown-out frames.
    brightness = max(0.0, 1.0 - abs(mean - 130.0) / 130.0)
    sharpness = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).stddev[0]
    rgb = ImageStat.Stat(img).mean
    colourfulness = (abs(rgb[0] - rgb[1]) + abs(rgb[1] - rgb[2]) + abs(rgb[0] - rgb[2]))
    return sharpness + brightness * 40.0 + colourfulness * 0.3


def generate_youtube_thumbnail(
    video_path: str,
    output_path: str,
    title: str | None = None,
    badge: str | None = None,
    width: int = 1280,
    height: int = 720,
) -> Path | None:
    """Pick the best frame from a rendered video and overlay a title.

    Samples several frames across the middle of the clip, scores them on
    sharpness / brightness / colour, then draws the title (and an optional
    corner badge) over the winner. Returns the JPEG path, or None on failure.
    """
    from PIL import Image

    duration = _probe_duration(video_path)
    if duration and duration > 1.0:
        lo, hi, n = duration * 0.1, duration * 0.9, 8
        times = [lo + (hi - lo) * k / (n - 1) for k in range(n)]
    else:
        times = [0.5, 1.0, 1.5, 2.0]

    tmp = TEMP_DIR / f"thumbcand_{hashlib.md5(video_path.encode()).hexdigest()[:8]}.jpg"
    best_img = None
    best_score = -1.0
    try:
        for t in times:
            if not _extract_frame(video_path, t, tmp, width, height):
                continue
            try:
                img = Image.open(tmp).convert("RGB")
            except Exception:
                continue
            try:
                score = _frame_score(img)
            except Exception:
                score = 0.0
            if score > best_score:
                best_score = score
                if best_img is not None:
                    best_img.close()
                best_img = img.copy()
            img.close()
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

    if best_img is None:
        return None

    try:
        if best_img.size != (width, height):
            best_img = _cover_resize(best_img, width, height)
        if title:
            _draw_thumbnail_text(best_img, title, badge)
        best_img.convert("RGB").save(str(output_path), "JPEG", quality=88)
        return Path(output_path)
    except Exception:
        return None
    finally:
        best_img.close()


def _cover_resize(img, w: int, h: int):
    from PIL import Image
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    resized = img.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.LANCZOS)
    left = (resized.width - w) // 2
    top = (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _draw_thumbnail_text(base, title: str, badge: str | None = None) -> None:
    from PIL import Image, ImageDraw
    W, H = base.size
    draw = ImageDraw.Draw(base)

    # Bottom scrim for legible text over any frame.
    scrim_h = int(H * 0.45)
    grad = Image.new("L", (1, scrim_h))
    for y in range(scrim_h):
        grad.putpixel((0, y), int(210 * (y / max(1, scrim_h - 1))))
    base.paste((0, 0, 0), (0, H - scrim_h), grad.resize((W, scrim_h)))

    margin = int(W * 0.05)
    font_size = int(H * 0.11)
    font = _load_font(font_size)
    lines = _wrap_by_width(draw, title, font, W - margin * 2)[:3]
    line_h = font_size * 1.15
    y = H - margin - line_h * len(lines)
    stroke = max(2, font_size // 16)
    for ln in lines:
        draw.text((margin, y), ln, font=font, fill=(255, 255, 255),
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += line_h

    if badge:
        bsize = int(H * 0.058)
        bfont = _load_font(bsize)
        pad = int(H * 0.018)
        tw = draw.textlength(badge, font=bfont)
        draw.rectangle(
            [margin, margin, margin + tw + pad * 2, margin + bsize + pad * 2],
            fill=(220, 30, 40),
        )
        draw.text((margin + pad, margin + pad), badge, font=bfont, fill=(255, 255, 255))


def make_card_image(
    main_text: str,
    output_path: str,
    sub_text: str | None = None,
    bg: tuple[int, int, int] = (15, 17, 23),
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Render a centred title card (intro/outro) as a PNG.

    The image is later turned into a short clip by the slideshow encoder, so it
    matches the batch render resolution (1920x1080).
    """
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    margin = int(width * 0.08)
    max_w = width - margin * 2

    # Accent bar above the title.
    bar_w, bar_h = int(width * 0.12), max(4, int(height * 0.012))
    bar_y = int(height * 0.30)
    draw.rectangle(
        [(width - bar_w) // 2, bar_y, (width + bar_w) // 2, bar_y + bar_h],
        fill=(80, 140, 240),
    )

    font_size = int(height * 0.12)
    font = _load_font(font_size)
    lines = _wrap_by_width(draw, main_text, font, max_w)[:3]
    line_h = font_size * 1.2

    sub_size = int(height * 0.05)
    sub_font = _load_font(sub_size) if sub_text else None
    sub_gap = int(height * 0.04) if sub_text else 0
    sub_total = (sub_size * 1.3 + sub_gap) if sub_text else 0

    total_h = line_h * len(lines) + sub_total
    y = bar_y + bar_h + int(height * 0.06)
    if y + total_h > height - margin:
        y = max(margin, (height - total_h) / 2)

    stroke = max(1, font_size // 24)
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        draw.text(((width - tw) / 2, y), ln, font=font, fill=(245, 245, 248),
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += line_h

    if sub_text and sub_font is not None:
        y += sub_gap
        tw = draw.textlength(sub_text, font=sub_font)
        draw.text(((width - tw) / 2, y), sub_text, font=sub_font, fill=(170, 178, 198))

    img.save(str(output_path), "PNG")
    img.close()
    return Path(output_path)
