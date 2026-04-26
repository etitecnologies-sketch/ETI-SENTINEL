from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    src = repo / "imag" / "ETI SENTINEL-logo.jpg"
    if not src.exists():
        raise SystemExit(f"Arquivo não encontrado: {src}")

    public_dir = repo / "frontend" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    logo_jpg = public_dir / "eti-sentinel-logo.jpg"
    img = Image.open(src)
    img.save(logo_jpg, quality=95)

    base = img.convert("RGBA")
    max_side = max(base.size)
    canvas = Image.new("RGBA", (max_side, max_side), (5, 5, 8, 255))
    x = (max_side - base.size[0]) // 2
    y = (max_side - base.size[1]) // 2
    canvas.paste(base, (x, y), base)

    sizes_png: dict[str, int] = {
        "favicon-16x16.png": 16,
        "favicon-32x32.png": 32,
        "apple-touch-icon.png": 180,
        "android-chrome-192x192.png": 192,
        "android-chrome-512x512.png": 512,
        "logo-512.png": 512,
    }

    for filename, size in sizes_png.items():
        out = canvas.resize((size, size), Image.Resampling.LANCZOS)
        out.save(public_dir / filename, format="PNG", optimize=True)

    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_img = canvas.resize((256, 256), Image.Resampling.LANCZOS)
    ico_img.save(public_dir / "favicon.ico", format="ICO", sizes=ico_sizes)

    manifest = {
        "name": "ETI SENTINEL",
        "short_name": "ETI SENTINEL",
        "icons": [
            {"src": "/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": "#050508",
        "background_color": "#050508",
        "display": "standalone",
    }
    (public_dir / "site.webmanifest").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"OK: ícones gerados em {public_dir}")


if __name__ == "__main__":
    main()

