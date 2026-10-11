"""Render every icon from the SVGs in this directory. Run through scripts/icons.sh.

Writes to frontend/public (served at the site root) and docs/social-preview.png.
"""

import shutil
import struct
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / "public"
DOCS = HERE.parent.parent / "docs"

# (source SVG, output PNG, size, keep transparent corners)
PNGS = [
    ("icon-small.svg", "favicon-16x16.png", 16, True),
    ("icon-small.svg", "favicon-32x32.png", 32, True),
    ("icon.svg", "favicon-48x48.png", 48, True),
    ("icon.svg", "icon-192.png", 192, True),
    ("icon.svg", "icon-512.png", 512, True),
    ("icon-maskable.svg", "icon-maskable-192.png", 192, False),
    ("icon-maskable.svg", "icon-maskable-512.png", 512, False),
    # iOS rounds the corners itself and shows transparency as black: full bleed.
    ("icon-maskable.svg", "apple-touch-icon.png", 180, False),
    ("icon-maskable.svg", "mstile-150x150.png", 150, False),
]
ICO_SIZES = ["favicon-16x16.png", "favicon-32x32.png", "favicon-48x48.png"]
COPIES = [("icon.svg", "favicon.svg"), ("safari-pinned-tab.svg", "safari-pinned-tab.svg")]


def render_svg(browser: Browser, source: str, output: Path, size: int, transparent: bool) -> None:
    svg = (HERE / source).read_text()
    svg = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    page = browser.new_page(viewport={"width": size, "height": size})
    page.set_content(f'<body style="margin:0;background:transparent">{svg}</body>')
    page.screenshot(path=output, omit_background=transparent)
    page.close()


def write_ico(pngs: list[Path], output: Path) -> None:
    """An .ico holding PNG images (supported by every browser and Windows Vista on)."""
    images = [p.read_bytes() for p in pngs]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for data in images:
        width, height = struct.unpack(">II", data[16:24])  # From the PNG IHDR chunk.
        entries += struct.pack(
            "<BBBBHHII", width % 256, height % 256, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    output.write_bytes(header + entries + b"".join(images))


def main() -> None:
    PUBLIC.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for source, name, size, transparent in PNGS:
            render_svg(browser, source, PUBLIC / name, size, transparent)
            print(f"  {name}")
        page = browser.new_page(viewport={"width": 1280, "height": 640})
        page.goto((HERE / "social-preview.html").as_uri())
        page.screenshot(path=DOCS / "social-preview.png")
        print("  ../docs/social-preview.png")
        browser.close()
    write_ico([PUBLIC / name for name in ICO_SIZES], PUBLIC / "favicon.ico")
    print("  favicon.ico")
    for source, name in COPIES:
        shutil.copyfile(HERE / source, PUBLIC / name)
        print(f"  {name}")


if __name__ == "__main__":
    main()
