#!/usr/bin/env python3
"""Generate an HTML report from the mobile UX audit Markdown."""

from __future__ import annotations

import argparse
import base64
import html
import markdown
import re
from pathlib import Path

CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1f2329;
  --muted: #626a73;
  --line: #dfe3e8;
  --accent: #c7000b;
  --accent-soft: #fff0f1;
  --code: #20242a;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif;
}
.page {
  max-width: 1120px;
  margin: 0 auto;
  padding: 40px 24px 64px;
}
.report {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 36px;
  box-shadow: 0 8px 24px rgba(31, 35, 41, 0.06);
}
h1 {
  margin: 0 0 18px;
  font-size: 30px;
  line-height: 1.25;
}
h2 {
  margin: 34px 0 14px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
  font-size: 22px;
}
h3 {
  margin: 26px 0 10px;
  font-size: 18px;
}
p { margin: 10px 0; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code {
  padding: 2px 5px;
  border-radius: 4px;
  background: #f0f2f5;
  color: var(--code);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.92em;
}
ul, ol { padding-left: 22px; }
li { margin: 5px 0; }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 14px 0 22px;
  table-layout: fixed;
}
th, td {
  border: 1px solid var(--line);
  padding: 10px 12px;
  vertical-align: top;
  word-break: break-word;
}
th {
  background: #f5f6f8;
  text-align: left;
}
.meta {
  margin: 0 0 22px;
  padding: 14px 16px;
  border-left: 4px solid var(--accent);
  background: var(--accent-soft);
  color: var(--muted);
}
.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 18px;
  margin: 20px 0 30px;
}
.shot {
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.shot img {
  width: 100%;
  height: 360px;
  object-fit: contain;
  display: block;
  background: #eef1f5;
}
.shot figcaption {
  padding: 9px 12px;
  color: var(--muted);
  font-size: 13px;
  border-top: 1px solid var(--line);
}
@media (max-width: 720px) {
  .page { padding: 18px 12px 36px; }
  .report { padding: 22px 16px; }
  h1 { font-size: 24px; }
  table { display: block; overflow-x: auto; table-layout: auto; }
  .shot img { height: 300px; }
}
"""


def image_src(report_dir: Path, src: str, embed_images: bool) -> str | None:
    path = (report_dir / src).resolve()
    if not path.exists():
        return None
    if not embed_images:
        return src
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lower().lstrip(".")
    mime = "image/png" if suffix == "png" else f"image/{suffix or 'png'}"
    return f"data:{mime};base64,{data}"


def build_gallery(report_dir: Path, screenshot_dir: Path, image_prefix: str, embed_images: bool, include_full: bool) -> str:
    if not screenshot_dir.is_absolute():
        screenshot_dir = (report_dir / screenshot_dir).resolve()
    shots = [
        ("首屏", screenshot_dir / f"{image_prefix}_top.png"),
        ("滚动后", screenshot_dir / f"{image_prefix}_scroll.png"),
        ("菜单展开", screenshot_dir / f"{image_prefix}_menu.png"),
    ]
    if include_full:
        shots.append(("全页", screenshot_dir / f"{image_prefix}_full.png"))
    items = []
    for label, src in shots:
        display_src = str(src) if src.is_absolute() else src.as_posix()
        resolved = image_src(report_dir, display_src, embed_images)
        if not resolved:
            continue
        items.append(
            f'<figure class="shot"><img src="{html.escape(resolved)}" alt="{html.escape(label)}截图">'
            f"<figcaption>{html.escape(label)}</figcaption></figure>"
        )
    if not items:
        return ""
    return '<h2>截图证据</h2><div class="gallery">' + "\n".join(items) + "</div>"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--image-prefix", default="https_skills_huaweicloud_com")
    parser.add_argument("--screenshot-dir", default="../screenshots")
    parser.add_argument("--embed-images", action="store_true")
    parser.add_argument("--include-full-screenshot", action="store_true", help="Include the very tall full-page screenshot in the gallery.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else input_path.parent / "report.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = input_path.read_text(encoding="utf-8")
    if args.embed_images:
        text = re.sub(
            r"截图证据：\n\n(?:- .+\n){4}",
            "截图证据：已内嵌在 HTML 文件中，可单文件分发。\n",
            text,
        )
    html_body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    gallery = build_gallery(output_path.parent, Path(args.screenshot_dir), args.image_prefix, args.embed_images, args.include_full_screenshot)
    title = "华为云 Skills 门户手机端体验走查报告"
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <article class="report">
      <div class="meta">审计报告 HTML 版。{"截图已内嵌，可单文件分发。" if args.embed_images else "原始证据 JSON 与截图保留在统一 output/mobile run 目录。"}</div>
      {gallery}
      {html_body}
    </article>
  </main>
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
