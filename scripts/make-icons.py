"""Draws the Waymark icon (a brass waymarker stone with an upward chevron on warm paper) into
every raster the builds need. frontend/public/favicon.svg is the same drawing by hand.

    uv run --with pillow python scripts/make-icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PAPER = (245, 242, 234, 255)  # --page
BRASS = (138, 106, 31, 255)  # --brass
SS = 8  # supersampling factor


def draw(size: int, rounded: bool) -> Image.Image:
    """The mark in a 32-unit grid, scaled to `size`. `rounded` gives a transparent-cornered
    tile (desktop icons); otherwise full-bleed (Android masks its own shape)."""
    px = size * SS
    u = px / 32
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle((0, 0, px - 1, px - 1), radius=7 * u, fill=PAPER)
    else:
        d.rectangle((0, 0, px, px), fill=PAPER)
    # The stone: 14 wide, semicircular top centred at (16, 13), base at y=27.
    d.ellipse((9 * u, 6 * u, 23 * u, 20 * u), fill=BRASS)
    d.rectangle((9 * u, 13 * u, 23 * u, 27 * u), fill=BRASS)
    # The chevron, with round caps and join.
    pts = [(12.4 * u, 19.2 * u), (16 * u, 15.6 * u), (19.6 * u, 19.2 * u)]
    w = 2.6 * u
    d.line(pts, fill=PAPER, width=round(w))
    for x, y in pts:
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=PAPER)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    packaging = ROOT / "packaging"
    draw(256, rounded=True).save(packaging / "waymark.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [draw(s, rounded=True) for s in sizes]
    frames[-1].save(packaging / "waymark.ico", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    res = ROOT / "android" / "app" / "src" / "main" / "res"
    for density, s in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        draw(s, rounded=False).convert("RGB").save(res / f"mipmap-{density}" / "ic_launcher.png")
    print("Icons written.")


if __name__ == "__main__":
    main()
