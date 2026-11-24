"""Render the PNG icons and the social preview image from site/em-logo.svg.

Needs Playwright with Chromium (pip install playwright && playwright install chromium).
Run again after changing the logo:  python scripts/render_brand.py
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[1] / "site"
LOGO = (SITE / "em-logo.svg").read_text(encoding="utf-8")

ICON = """<html><body style="margin:0;background:transparent">
<div style="width:{size}px;height:{size}px">{logo}</div></body></html>"""

OG = """<html><head><style>
body{{margin:0;width:1200px;height:630px;font-family:'Segoe UI Variable Display','Segoe UI',system-ui,sans-serif;
  background:radial-gradient(560px 380px at 8% 0%,#e3d6ff 0%,transparent 70%),
             radial-gradient(520px 360px at 100% 10%,#ffd9d3 0%,transparent 70%),
             radial-gradient(600px 420px at 60% 110%,#f3dcff 0%,transparent 70%),#f8f5fe;color:#251c36;
  display:flex;flex-direction:column;justify-content:center;padding:0 96px;box-sizing:border-box}}
.top{{display:flex;align-items:center;gap:22px}}
.top svg{{width:96px;height:96px;border-radius:26px;box-shadow:0 14px 40px #7b4dff40}}
.name{{font-size:46px;font-weight:800;letter-spacing:-1px}}
.name b{{background:linear-gradient(120deg,#7b4dff,#c04fd8 55%,#ff7a6b);-webkit-background-clip:text;color:transparent}}
h1{{margin:54px 0 18px;font-size:92px;line-height:1;font-weight:800;letter-spacing:-3px}}
h1 span{{background:linear-gradient(120deg,#7b4dff,#c04fd8 55%,#ff7a6b);-webkit-background-clip:text;color:transparent}}
p{{margin:0;font-size:32px;color:#5b4d78;font-weight:500}}
.chips{{display:flex;gap:14px;margin-top:40px}}
.chips span{{padding:10px 22px;border-radius:999px;background:#fff;border:2px solid #e2d6ff;font-size:24px;font-weight:650;color:#5530b8}}
.chips span.c{{color:#b3392c;border-color:#ffd2cb}}
</style></head><body>
<div class="top">{logo}<div class="name"><b>Em</b> Jobs</div></div>
<h1>Road to <span>Product</span></h1>
<p>Stages, VIE et premiers postes product, UX et growth</p>
<div class="chips"><span>Paris</span><span>Londres</span><span class="c">✦ Tech &amp; IA</span></div>
</body></html>"""


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(ICON.format(size=size, logo=LOGO.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)))
            page.screenshot(path=str(SITE / name), omit_background=True)
            page.close()
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        page.set_content(OG.format(logo=LOGO))
        page.screenshot(path=str(SITE / "og-image.png"))
        browser.close()
    print("Icônes et image de partage générées dans site/")


if __name__ == "__main__":
    main()
