#!/usr/bin/env python3
"""
Generate static image assets for the site: favicon PNGs, apple-touch-icon, an
Open Graph social-share image, and an SVG favicon. Run once (or whenever the
branding changes); the outputs are committed as static files.

    python3 make_assets.py

Requires Pillow (already in requirements for the macOS dev environment; not
needed by the weekly GitHub Action).
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# --- Palette (calm sage & stone) -------------------------------------------
CREAM = (250, 248, 244, 255)
INK = (28, 25, 23, 255)
MUTED = (111, 106, 97, 255)
SAGE = (91, 117, 83)
PETAL = (91, 117, 83, 205)  # sage with alpha so overlapping petals deepen

# Assets are served from the repo root; this script lives in scripts/.
HERE = Path(__file__).parent.parent

# macOS system fonts (used only for the OG image text)
SERIF_FONT = "/System/Library/Fonts/NewYork.ttf"
SANS_FONT = "/System/Library/Fonts/Helvetica.ttc"


def draw_lotus(size: int, petal_color=PETAL) -> Image.Image:
    """Return a transparent RGBA image with a centred lotus mark."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cx, cy = size / 2, size * 0.60          # base point of the petals
    ph, pw = size * 0.46, size * 0.165       # petal height / width
    for angle in (-75, -50, -25, 0, 25, 50, 75):
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse([cx - pw / 2, cy - ph, cx + pw / 2, cy], fill=petal_color)
        layer = layer.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)
        img = Image.alpha_composite(img, layer)
    return img


def rounded_bg(size: int, color, radius: int) -> Image.Image:
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=color)
    return bg


def make_icon(size: int, filename: str, with_bg: bool = True):
    """A lotus on a rounded cream tile."""
    canvas = (rounded_bg(size, CREAM, radius=int(size * 0.22))
              if with_bg else Image.new("RGBA", (size, size), (0, 0, 0, 0)))
    lotus = draw_lotus(int(size * 0.78))
    off = (size - lotus.width) // 2
    canvas.alpha_composite(lotus, (off, off))
    canvas.save(HERE / filename)
    print(f"  wrote {filename} ({size}x{size})")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def make_og_image():
    """1200x630 Open Graph / Twitter share image."""
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), CREAM[:3])
    d = ImageDraw.Draw(img)

    # soft border frame for a calm, framed feel
    d.rounded_rectangle([28, 28, W - 28, H - 28], radius=24,
                        outline=(231, 225, 216), width=2)

    # lotus mark, centred near the top
    lotus = draw_lotus(150)
    img.paste(lotus, ((W - lotus.width) // 2, 70), lotus)

    title_font = _font(SERIF_FONT, 104)
    sub_font = _font(SANS_FONT, 33)
    teacher_font = _font(SANS_FONT, 26)
    domain_font = _font(SANS_FONT, 24)

    d.text((W / 2, 300), "Guided Meditations", font=title_font,
           fill=INK[:3], anchor="mm")

    # short centred rule
    d.line([(W / 2 - 110, 372), (W / 2 + 110, 372)], fill=SAGE, width=3)

    d.text((W / 2, 425), "A curated collection from dharma podcasts",
           font=sub_font, fill=MUTED[:3], anchor="mm")
    d.text((W / 2, 500),
           "Tara Brach  ·  Jack Kornfield  ·  Sharon Salzberg  ·  "
           "Joseph Goldstein  ·  Ajahn Brahm",
           font=teacher_font, fill=SAGE, anchor="mm")
    d.text((W / 2, 565), "alastairrushworth.com/meditation",
           font=domain_font, fill=MUTED[:3], anchor="mm")

    img.save(HERE / "og-image.png")
    print("  wrote og-image.png (1200x630)")


def make_favicon_svg():
    petals = []
    cx = cy = 32.0
    base_y = 50.0
    # petal path: base at (32,50), tip up to (32,15)
    petal = "M32 50 C27 42 27 27 32 15 C37 27 37 42 32 50Z"
    for angle in (-75, -50, -25, 0, 25, 50, 75):
        petals.append(
            f'    <path d="{petal}" transform="rotate({angle} {cx} {base_y})"/>'
        )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
        'role="img" aria-label="Lotus">\n'
        '  <rect width="64" height="64" rx="14" fill="#faf8f4"/>\n'
        '  <g fill="#5b7553" fill-opacity="0.82">\n'
        + "\n".join(petals) + "\n"
        "  </g>\n"
        "</svg>\n"
    )
    (HERE / "favicon.svg").write_text(svg, encoding="utf-8")
    print("  wrote favicon.svg")


def main():
    print("Generating assets...")
    make_favicon_svg()
    make_icon(512, "icon-512.png")
    make_icon(180, "apple-touch-icon.png")
    make_icon(32, "favicon-32.png")
    make_og_image()
    print("Done.")


if __name__ == "__main__":
    main()
