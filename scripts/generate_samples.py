"""Generate synthetic Bangladesh NID sample images for the demo UI.

Produces fixtures/samples/nid_front_synthetic.png and nid_back_synthetic.png.
Content mirrors fixtures/demo_response.json so the "Use sample NID images"
button in the UI, run in demo mode, tells a consistent story end to end.

These are entirely synthetic — no real NID layout, watermark, or security
feature is reproduced. They exist only to give evaluators something to
click through without needing a real ID card.

Known limitation: Pillow's basic text layout does not perform complex-script
shaping (no libraqm), so Bengali conjuncts and reordering vowel signs may
render slightly out of visual order. The text stays legible and unambiguous
for a synthetic sample; this does not affect the real extraction pipeline,
which reads pixels via Gemini, not this script's font rendering.

Usage: python scripts/generate_samples.py
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1000, 630
BACKGROUND = (245, 240, 230)  # #F5F0E6
INK = (30, 30, 30)
MUTED = (90, 90, 90)
PHOTO_BOX = (170, 170, 170)
BORDER = (150, 140, 120)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "samples"

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf", None),
    (r"C:\Windows\Fonts\NirmalaB.ttf", None),
    (r"C:\Windows\Fonts\Nirmala.ttc", 0),  # actual Windows Bengali-capable font shipped by default
    ("/System/Library/Fonts/Supplemental/Kohinoor Bangla.ttc", 0),
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path, index in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            if index is not None:
                return ImageFont.truetype(path, size, index=index)
            return ImageFont.truetype(path, size)
        except OSError:
            continue

    print(
        "WARNING: no Bengali-capable font found on this system; "
        "Bengali text in the synthetic samples may render as boxes. "
        "That's acceptable for a synthetic demo sample.",
        file=sys.stderr,
    )
    return ImageFont.load_default()


def _fonts():
    return {
        "banner": _load_font(26),
        "heading": _load_font(20),
        "label": _load_font(18),
        "value": _load_font(20),
        "small": _load_font(15),
    }


def _draw_header(draw: ImageDraw.ImageDraw, fonts: dict) -> None:
    draw.rectangle([0, 0, WIDTH, 78], fill=(0, 91, 60))
    draw.text(
        (WIDTH / 2, 24),
        "গণপ্রজাতন্ত্রী বাংলাদেশ সরকার",
        font=fonts["banner"],
        fill=(255, 255, 255),
        anchor="mm",
    )
    draw.text(
        (WIDTH / 2, 58),
        "জাতীয় পরিচয় পত্র / National ID Card",
        font=fonts["label"],
        fill=(230, 230, 230),
        anchor="mm",
    )


def _draw_field(draw, x, y, label, value, fonts):
    draw.text((x, y), label, font=fonts["label"], fill=MUTED)
    draw.text((x, y + 26), value, font=fonts["value"], fill=INK)


def generate_front(fonts: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(img)

    _draw_header(draw, fonts)
    draw.rectangle([4, 4, WIDTH - 5, HEIGHT - 5], outline=BORDER, width=2)

    # Placeholder photo box, left side.
    photo_x, photo_y = 60, 130
    draw.rectangle(
        [photo_x, photo_y, photo_x + 200, photo_y + 240],
        fill=PHOTO_BOX,
        outline=BORDER,
        width=2,
    )
    draw.text(
        (photo_x + 100, photo_y + 120),
        "PHOTO",
        font=fonts["label"],
        fill=(240, 240, 240),
        anchor="mm",
    )

    # Right side fields.
    fx = 300
    fy = 120
    row_h = 66

    _draw_field(draw, fx, fy, "নাম:", "মোঃ রহিম উদ্দিন", fonts)
    _draw_field(draw, fx, fy + row_h, "Name:", "Md. Rahim Uddin", fonts)
    _draw_field(draw, fx, fy + row_h * 2, "পিতা:", "মোঃ আব্দুল করিম", fonts)
    _draw_field(draw, fx, fy + row_h * 3, "মাতা:", "আমেনা বেগম", fonts)
    _draw_field(draw, fx, fy + row_h * 4, "জন্ম তারিখ:", "১৫ জানুয়ারি ১৯৯৮", fonts)
    _draw_field(draw, fx, fy + row_h * 5, "NID No:", "1234567890", fonts)

    draw.text(
        (WIDTH / 2, HEIGHT - 22),
        "SYNTHETIC SAMPLE — NOT A REAL DOCUMENT",
        font=fonts["small"],
        fill=(160, 60, 60),
        anchor="mm",
    )

    return img


def _draw_barcode(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
    # Deterministic pseudo-barcode: alternating bars of varying width.
    pattern = [3, 1, 2, 1, 1, 4, 2, 1, 3, 2, 1, 1, 2, 4, 1, 3, 1, 2, 2, 1, 4, 1, 1, 3]
    unit = w / sum(pattern)
    cursor = x
    draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 255), outline=BORDER)
    black = False
    for segment in pattern:
        seg_w = segment * unit
        if black:
            draw.rectangle([cursor, y + 4, cursor + seg_w, y + h - 4], fill=(20, 20, 20))
        cursor += seg_w
        black = not black


def generate_back(fonts: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(img)

    draw.rectangle([4, 4, WIDTH - 5, HEIGHT - 5], outline=BORDER, width=2)

    fx = 60
    fy = 60
    row_h = 66

    draw.text((fx, fy), "ঠিকানা (Address):", font=fonts["heading"], fill=INK)
    _draw_field(draw, fx, fy + row_h, "উপস্থিত ঠিকানা:", "বাসা ১২, রোড ৪, ধানমন্ডি, ঢাকা", fonts)

    draw.text((fx, fy + row_h * 2 + 20), "স্থায়ী ঠিকানা (Permanent Address):", font=fonts["heading"], fill=INK)
    _draw_field(
        draw,
        fx,
        fy + row_h * 3 + 20,
        "",
        "দক্ষিণপাড়া গ্রাম, সদর ডাকঘর, কুমিল্লা",
        fonts,
    )

    _draw_barcode(draw, fx, HEIGHT - 140, WIDTH - fx * 2, 70)

    draw.text(
        (WIDTH / 2, HEIGHT - 22),
        "SYNTHETIC SAMPLE — NOT A REAL DOCUMENT",
        font=fonts["small"],
        fill=(160, 60, 60),
        anchor="mm",
    )

    return img


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fonts = _fonts()

    front_path = OUTPUT_DIR / "nid_front_synthetic.png"
    back_path = OUTPUT_DIR / "nid_back_synthetic.png"

    generate_front(fonts).save(front_path, format="PNG")
    generate_back(fonts).save(back_path, format="PNG")

    print(f"Wrote {front_path}")
    print(f"Wrote {back_path}")


if __name__ == "__main__":
    main()
