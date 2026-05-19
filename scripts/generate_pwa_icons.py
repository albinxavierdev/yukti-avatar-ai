#!/usr/bin/env python3
"""Generate PNG icons for the PWA manifest (no external deps beyond Pillow)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "static" / "icons"


def draw_icon(size: int, maskable: bool = False) -> "Image.Image":
    from PIL import Image, ImageDraw, ImageFont

    pad = int(size * 0.12) if maskable else 0
    img = Image.new("RGBA", (size, size), (7, 10, 18, 255))
    draw = ImageDraw.Draw(img)
    inner = size - 2 * pad
    margin = pad + int(inner * 0.08)
    box = [margin, margin, size - margin, size - margin]
    draw.rounded_rectangle(box, radius=int(inner * 0.22), fill=(8, 145, 178, 255))
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(124, 58, 237, 230),
    )
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size * 0.42))
    except OSError:
        font = ImageFont.load_default()
    text = "Y"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - size * 0.04), text, fill=(255, 255, 255, 255), font=font)
    return img


def main() -> None:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Install Pillow: pip install Pillow")
        raise SystemExit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(OUT / "icon-192.png", "PNG")
    draw_icon(512).save(OUT / "icon-512.png", "PNG")
    draw_icon(512, maskable=True).save(OUT / "icon-maskable-512.png", "PNG")
    print(f"PWA icons written to {OUT}")


if __name__ == "__main__":
    main()
