"""Generate the .ico files used by the built executables.

Requires Pillow (``pip install pillow``) — it is NOT a runtime/build
dependency of the project; the generated .ico files in ``assets/icons/``
are committed, so this script only needs to be re-run when the design
changes.

Usage::

    python tools/generate_icons.py

Outputs (into ``assets/icons/``):
    tiktok2mc.ico        main brand icon  (start / gui / app / installer)
    tiktok2mc-update.ico updater variant with an arrow badge (update)
    tiktok2mc-tool.ico   monochrome variant for background tools (server /
                         overlay / test_trigger)

Design: "the stream becomes the block" — a play triangle that dissolves
into pixel squares. Palette (max 3): charcoal, white, one green accent.
Rendered at 4x supersampling and downscaled for clean anti-aliasing.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = SCRIPT_DIR / "assets" / "icons"

CANVAS = 256
S = 4  # supersampling factor
SIZE = CANVAS * S
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

# ---- Palette (3 colors) ----
BG = "#11151a"  # charcoal
FG = "#f5f7f9"  # white
ACCENT = "#2fd67b"  # green accent

# Monochrome replacement for the tool variant.
TOOL_FG = "#8b949e"
TOOL_ACCENT = "#565f69"


def _rounded_square(size: int, color: str, radius: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=color
    )
    return img


def _glyph(size: int, fg: str, accent: str) -> Image.Image:
    """Clean play triangle."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Triangle geometry (fractions of canvas), optically centered.
    x0 = size * 0.26  # base (left)
    x1 = size * 0.72  # apex (right)
    cy = size * 0.5
    hh = size * 0.21  # half height at base

    d.polygon([(x0, cy - hh), (x0, cy + hh), (x1, cy)], fill=fg)
    return layer


def _icon(fg: str, accent: str) -> Image.Image:
    img = _rounded_square(SIZE, BG, int(SIZE * 0.24))
    img.alpha_composite(_glyph(SIZE, fg, accent))
    return img.resize((CANVAS, CANVAS), Image.LANCZOS)


def _badge(img: Image.Image) -> Image.Image:
    """Accent circle with an up arrow, bottom-right (update variant)."""
    size = img.size[0]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r = int(size * 0.20)
    cx = size - r - size // 30
    cy = size - r - size // 30

    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    ring = max(2, size // 56)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BG, width=ring)

    aw = r * 0.9  # arrow half width
    ah = r * 0.9  # arrow half height
    shaft = r * 0.22
    d.polygon(
        [
            (cx, cy - ah),
            (cx + aw, cy + ah * 0.1),
            (cx + shaft, cy + ah * 0.1),
            (cx + shaft, cy + ah),
            (cx - shaft, cy + ah),
            (cx - shaft, cy + ah * 0.1),
            (cx - aw, cy + ah * 0.1),
        ],
        fill=FG,
    )
    img.alpha_composite(layer)
    return img


def make_main() -> Image.Image:
    return _icon(FG, ACCENT)


def make_update() -> Image.Image:
    return _badge(make_main())


def make_tool() -> Image.Image:
    return _icon(TOOL_FG, TOOL_ACCENT)


def save_ico(img: Image.Image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"Wrote {path}")


def main():
    save_ico(make_main(), OUT_DIR / "tiktok2mc.ico")
    save_ico(make_update(), OUT_DIR / "tiktok2mc-update.ico")
    save_ico(make_tool(), OUT_DIR / "tiktok2mc-tool.ico")


if __name__ == "__main__":
    main()
