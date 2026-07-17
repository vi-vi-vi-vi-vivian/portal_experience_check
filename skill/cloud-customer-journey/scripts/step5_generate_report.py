#!/usr/bin/env python3
"""Generate a self-contained HTML report from stage_analysis.json."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from pathlib import Path
from typing import Any

STAGES = ["感知", "下单", "支付", "使用", "续费", "变更", "退订"]
SEVERITY_LABEL = {"p0": "阻断", "p1": "重要", "p2": "建议"}
SEVERITY_ORDER = {"p0": 0, "p1": 1, "p2": 2}
MARKER_COLOR = {"p0": "#c6262e", "p1": "#b96b00", "p2": "#147a5c"}
COMMON_UI_TERMS = [
    "定价", "表格", "购买", "立即购买", "控制台", "桶列表", "总览", "资源包管理", "支付", "收银台",
    "续费", "退订", "变更", "搜索", "对象存储服务", "OBS", "标准存储", "低频访问存储",
    "归档存储", "深度归档存储", "规格", "升级", "降级", "查看详情", "产品价格", "价格详情",
]
STAGE_LEVEL_TERMS = [
    "入口不可达", "未到达", "页面错误", "登录态", "空白", "无法进入", "不可达", "跳转到",
    "未进入", "没有到达", "流程阻断",
]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def image_data_uri(path: str | None, root: Path) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    if not p.exists():
        return ""
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def resolve_path(path: str | None, root: Path) -> Path | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    return p if p.exists() else None


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def normalize_severity(issue: dict[str, Any]) -> str:
    severity = str(issue.get("severity", "p2")).lower()
    if severity in {"high", "严重", "阻断"}:
        return "p0"
    if severity in {"medium", "中", "重要"}:
        return "p1"
    return severity if severity in SEVERITY_LABEL else "p2"


def marker_id(stage: str, index: int) -> str:
    return f"{stage}-{index}"


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def text_tokens(value: Any, limit: int = 12) -> list[str]:
    text = compact_text(value)
    if not text:
        return []
    tokens: list[str] = []
    for term in COMMON_UI_TERMS:
        if term.lower() in text.lower() and term not in tokens:
            tokens.append(term)
    parts = [text]
    for sep in ["、", "/", "，", ",", "·", " ", "：", ":", "；", ";", "。", "（", "）", "(", ")"]:
        parts = [chunk for part in parts for chunk in part.split(sep)]
    for part in parts:
        part = re.sub(r"^[“”'\"<>《》【】\[\]]+|[“”'\"<>《》【】\[\]]+$", "", part.strip())
        if len(part) >= 2 and part not in tokens:
            tokens.append(part)
    return tokens[:limit]


def issue_signals(issue: dict[str, Any]) -> list[tuple[str, str]]:
    signals: list[tuple[str, str]] = []
    for value in issue.get("locate") or []:
        value = compact_text(value)
        if value:
            signals.append((value, "locate"))
            signals.extend((token, "locate_token") for token in text_tokens(value, 8))
    evidence = compact_text(issue.get("evidence") or "")
    signals.extend((token, "evidence") for token in text_tokens(evidence[:260], 12))
    title_area = " ".join(compact_text(issue.get(key) or "") for key in ["title", "area"])
    signals.extend((token, "title") for token in text_tokens(title_area, 8))
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for token, source in signals:
        key = (token.lower(), source)
        if key not in seen:
            seen.add(key)
            deduped.append((token, source))
    return deduped[:28]


def is_stage_level_issue(issue: dict[str, Any]) -> bool:
    locate = [compact_text(value) for value in issue.get("locate") or [] if compact_text(value)]
    if locate:
        return False
    combined = compact_text(" ".join(str(issue.get(key) or "") for key in ["title", "area", "evidence"]))
    return any(term in combined for term in STAGE_LEVEL_TERMS)


def summarize(value: Any, max_len: int = 96) -> str:
    text = compact_text(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def split_suggestion(value: Any) -> tuple[str, str]:
    text = compact_text(value)
    if not text:
        return "", ""
    patterns = [
        r"修改前[:：]?(?P<before>.*?)(?:->|→|修改后[:：])(?P<after>.*)",
        r"现状[:：](?P<before>.*?)(?:建议[:：]|修改为[:：])(?P<after>.*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return summarize(match.group("before"), 120), clean_recommendation(match.group("after"))
    return summarize(text, 120), clean_recommendation(text)


def issue_suggestion_parts(issue: dict[str, Any]) -> tuple[str, str]:
    before = compact_text(issue.get("suggestion_before"))
    after = compact_text(issue.get("suggestion_after"))
    if before or after:
        return summarize(before, 120), clean_recommendation(after)
    return split_suggestion(issue.get("suggestion"))


def clean_recommendation(value: Any, max_len: int = 140) -> str:
    text = compact_text(value)
    text = re.sub(r"^(?:->|→)?\s*修改后[:：]\s*", "", text)
    text = re.sub(r"^建议[:：]\s*", "", text)
    return summarize(text, max_len)


def issue_description(issue: dict[str, Any], max_len: int = 180) -> str:
    current, _ = issue_suggestion_parts(issue)
    evidence = summarize(issue.get("evidence"), max_len)
    if not current:
        return evidence
    if not evidence:
        return current
    if current in evidence or evidence in current:
        return summarize(evidence if len(evidence) >= len(current) else current, max_len)
    return summarize(f"{evidence} 当前表现：{current}", max_len)


def candidate_elements(page: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in ["element_rects", "buttons", "visual_details"]:
        for item in page.get(key) or []:
            try:
                x, y, w, h = float(item.get("x", 0)), float(item.get("y", 0)), float(item.get("w", 0)), float(item.get("h", 0))
            except Exception:
                continue
            if w < 8 or h < 8:
                continue
            text = str(item.get("text") or item.get("href") or "").strip()
            if not text:
                continue
            if item.get("visible") is False:
                continue
            area = w * h
            tag = str(item.get("tag") or "").lower()
            if w > 1100 and h > 240:
                continue
            if key == "element_rects" and tag in {"div", "section", "main", "body"} and area > 90000:
                continue
            merged = dict(item)
            merged.update({"x": x, "y": y, "w": w, "h": h, "_source": key, "_text": text})
            items.append(merged)
    return items


def score_element(element: dict[str, Any], signals: list[tuple[str, str]], issue: dict[str, Any]) -> int:
    raw_text = str(element.get("_text") or "")
    text = str(element.get("_text") or "").lower()
    title = str(issue.get("title") or "").lower()
    evidence = str(issue.get("evidence") or "").lower()
    locate_values = [str(item).lower() for item in issue.get("locate") or []]
    score = 0
    for token, source in signals:
        needle = token.lower()
        if not needle:
            continue
        source_weight = {"locate": 42, "locate_token": 24, "evidence": 12, "title": 4}.get(source, 2)
        if text == needle and source == "locate":
            score += 92
        if needle in text:
            score += source_weight + min(len(needle), 12)
        elif source == "locate" and text and text in needle:
            score += 38
        if needle in title:
            score += 1
        if needle in evidence:
            score += 1
    if text and len(text) >= 2 and text in evidence:
        score += min(len(text), 20)
    if any(value and value in text for value in locate_values):
        score += 32
    if "定价" in title and any(term in text for term in ["标准存储", "低频访问存储", "归档存储", "深度归档存储", "价格"]):
        score += 18
    if "控制台" in title and "控制台" in text:
        score += 18
    if any(term in title for term in ["顶部", "导航栏"]) and float(element.get("y", 9999)) < 160:
        score += 25
    if "使用阶段" in title and any(term in text for term in ["对象存储服务", "obs", "桶列表", "总览"]):
        score += 18
    if element.get("_source") in {"buttons", "visual_details"}:
        score += 2
    if str(element.get("tag") or "").lower() in {"a", "button"}:
        score += 3
    area = float(element.get("w", 0)) * float(element.get("h", 0))
    if area > 120000:
        score -= 28
    elif area > 60000:
        score -= 12
    if len(raw_text) > 160:
        score -= 12
    return score


def issue_rect(issue: dict[str, Any], elements: list[dict[str, Any]]) -> dict[str, Any] | None:
    if is_stage_level_issue(issue):
        return None
    signals = issue_signals(issue)
    if not signals:
        return None
    ranked = sorted(
        ((score_element(element, signals, issue), element) for element in elements),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 50:
        return None
    score, element = ranked[0]
    confidence = "high" if score >= 70 else "medium"
    if confidence != "high":
        return None
    return {"x": element["x"], "y": element["y"], "w": element["w"], "h": element["h"], "score": score, "confidence": confidence}


def draw_marker(draw: ImageDraw.ImageDraw, rect: dict[str, float], label: str, color: str, image_size: tuple[int, int]) -> None:
    width, height = image_size
    x = max(0, min(width - 1, int(rect["x"])))
    y = max(0, min(height - 1, int(rect["y"])))
    w = max(18, int(rect["w"]))
    h = max(18, int(rect["h"]))
    x2 = max(x + 18, min(width - 1, x + w))
    y2 = max(y + 18, min(height - 1, y + h))
    stroke = 2
    draw.rounded_rectangle([x, y, x2, y2], radius=6, outline=color, width=stroke)
    radius = 13
    cx = min(width - radius - 2, max(radius + 2, x))
    cy = min(height - radius - 2, max(radius + 2, y))
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color, outline="white", width=2)
    try:
        font = ImageFont.truetype("Arial Unicode.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
    text = str(label)
    bbox = draw.textbbox((0, 0), text, font=font)
    tx = cx - (bbox[2] - bbox[0]) / 2
    ty = cy - (bbox[3] - bbox[1]) / 2 - 1
    draw.text((tx, ty), text, fill="white", font=font)


def annotated_screenshot(
    stage: str,
    item: dict[str, Any],
    page: dict[str, Any],
    issues: list[dict[str, Any]],
    root: Path,
    output_dir: Path,
) -> tuple[str | None, dict[int, dict[str, Any]]]:
    screenshot = resolve_path(item.get("screenshot_path"), root)
    if not screenshot or not issues:
        return item.get("screenshot_path"), {}
    output_dir.mkdir(parents=True, exist_ok=True)
    elements = candidate_elements(page)
    markers: dict[int, dict[str, Any]] = {}
    try:
        image = Image.open(screenshot).convert("RGBA")
    except Exception:
        return item.get("screenshot_path"), {}
    draw = ImageDraw.Draw(image)
    for index, issue in enumerate(issues, start=1):
        rect = issue_rect(issue, elements)
        if not rect:
            continue
        sev = normalize_severity(issue)
        color = MARKER_COLOR.get(sev, "#1f5fbf")
        draw_marker(draw, rect, str(index), color, image.size)
        markers[index] = {"rect": rect, "color": color}
    if not markers:
        return item.get("screenshot_path"), {}
    out = output_dir / f"annotated_{stage}.png"
    image.convert("RGB").save(out)
    return str(out.relative_to(root)), markers


def issue_card(stage: str, issue: dict[str, Any], index: int, has_marker: bool) -> str:
    sev = normalize_severity(issue)
    locate = ", ".join(issue.get("locate") or [])
    mid = marker_id(stage, index)
    marker = f"<span class='marker-ref {sev}'>#{index}</span>" if has_marker else "<span class='marker-ref missing'>未定位</span>"
    _, recommendation = issue_suggestion_parts(issue)
    return f"""
    <article class="issue-card {sev}" id="issue-{esc(mid)}">
      <div class="issue-top">{marker}<span>{esc(SEVERITY_LABEL[sev])}</span><strong>{esc(stage)} · {esc(issue.get('title'))}</strong></div>
      <p><b>定位：</b>{esc(locate)}</p>
      <p><b>问题说明：</b>{esc(issue_description(issue, 260))}</p>
      <p><b>建议修改：</b>{esc(recommendation)}</p>
      <details>
        <summary>标准依据</summary>
        <p><b>标准：</b>{esc(issue.get('standard'))}</p>
      </details>
    </article>
    """


def issue_row(issue: dict[str, Any], include_stage: str | None = None, marker: str | None = None) -> str:
    sev = normalize_severity(issue)
    stage_cell = f"<td>{esc(include_stage)}</td>" if include_stage else ""
    marker_cell = f"<td>{esc(marker or '')}</td>" if marker is not None else ""
    title = issue.get("title") or issue.get("area") or "未命名问题"
    locate = ", ".join(issue.get("locate") or [])
    _, recommendation = issue_suggestion_parts(issue)
    return f"""
    <tr class="{sev}">
      {stage_cell}
      {marker_cell}
      <td><span class="badge">{esc(SEVERITY_LABEL[sev])}</span></td>
      <td>{esc(title)}</td>
      <td>{esc(locate or "阶段级问题")}</td>
      <td>{esc(issue_description(issue, 150))}</td>
      <td>{esc(recommendation)}</td>
    </tr>
    """


def issue_table(rows: str, include_stage: bool = False) -> str:
    stage_head = "<th>阶段</th><th>标注</th>" if include_stage else ""
    if not include_stage and "data-has-marker" in rows:
        stage_head = "<th>标注</th>"
    return f"""
    <table class="issue-table">
      <thead><tr>{stage_head}<th>级别</th><th>当前问题</th><th>定位</th><th>问题说明</th><th>建议修改</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


def priority_row(stage: str, issue: dict[str, Any], marker: str) -> str:
    sev = normalize_severity(issue)
    _, recommendation = issue_suggestion_parts(issue)
    return f"""
    <tr class="{sev}">
      <td>{esc(stage)}</td>
      <td>{esc(marker)}</td>
      <td><span class="badge">{esc(SEVERITY_LABEL[sev])}</span></td>
      <td>{esc(issue.get("title") or issue.get("area") or "未命名问题")}</td>
      <td>{esc(issue_description(issue, 150))}</td>
      <td>{esc(recommendation)}</td>
    </tr>
    """


def priority_table(rows: str) -> str:
    return f"""
    <table class="issue-table priority-table">
      <thead><tr><th>阶段</th><th>标注</th><th>级别</th><th>当前问题</th><th>问题说明</th><th>建议修改</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--analysis", default="../../output/web/manual/audit.json")
    parser.add_argument("--crawl-result", default="../../output/web/manual/_crawl.json")
    parser.add_argument("--output", default="../../output/web/manual/report.html")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    analysis_path = root / args.analysis
    crawl_path = root / args.crawl_result
    analysis = load_json(analysis_path)
    crawl = load_json(crawl_path)
    stage_analysis = analysis.get("stage_analysis", {})
    pages_by_stage = {page.get("stage"): page for page in crawl.get("pages", [])}
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    annotation_dir = output.parent / "screenshots" / "annotations"

    all_issues: list[tuple[str, dict[str, Any]]] = []
    issue_markers: dict[tuple[str, int], bool] = {}
    for stage in STAGES:
        item = stage_analysis.get(stage) or {}
        for issue in item.get("issues", []):
            all_issues.append((stage, issue))
    all_issues.sort(key=lambda pair: (SEVERITY_ORDER.get(normalize_severity(pair[1]), 9), STAGES.index(pair[0]) if pair[0] in STAGES else 99))

    counts = {sev: 0 for sev in SEVERITY_LABEL}
    for _, issue in all_issues:
        counts[normalize_severity(issue)] += 1

    journey_overview = []
    stage_cards = []
    for stage in STAGES:
        item = stage_analysis.get(stage) or {}
        stage_issues = sorted(
            item.get("issues", []) if item else [],
            key=lambda issue: SEVERITY_ORDER.get(normalize_severity(issue), 9),
        )
        stage_counts = {sev: 0 for sev in SEVERITY_LABEL}
        for issue in stage_issues:
            stage_counts[normalize_severity(issue)] += 1
        total = len(stage_issues)
        status = "未分析" if not item else ("无问题" if total == 0 else f"{total} 个问题")
        journey_overview.append(
            f"""
            <a class="journey-step" href="#stage-{esc(stage)}">
              <span>{esc(stage)}</span>
              <strong>{esc(status)}</strong>
              <small>阻断 {stage_counts["p0"]} · 重要 {stage_counts["p1"]} · 建议 {stage_counts["p2"]}</small>
            </a>
            """
        )
        if not item:
            stage_cards.append(f"<section class='stage missing'><h2>{esc(stage)}</h2><p>未覆盖或未分析。</p></section>")
            continue
        page = pages_by_stage.get(stage) or {}
        annotated_path, markers = annotated_screenshot(stage, item, page, stage_issues, root, annotation_dir)
        for idx in range(1, len(stage_issues) + 1):
            issue_markers[(stage, idx)] = idx in markers
        img = image_data_uri(annotated_path or item.get("annotated_screenshot") or item.get("screenshot_path"), root)
        detail_cards = "".join(
            issue_card(stage, issue, idx, idx in markers)
            for idx, issue in enumerate(stage_issues, start=1)
        )
        marker_note = (
            "<p class='marker-note'>截图中的编号与下方问题详情一一对应；“未可靠定位”表示该问题来自流程或页面状态，或定位置信度不足，不强行标注控件。</p>"
            if stage_issues
            else ""
        )
        stage_cards.append(f"""
        <section class="stage" id="stage-{esc(stage)}">
          <h2>{esc(stage)} <span>{esc(item.get('score', '-'))}/10</span></h2>
          <p class="url">{esc(item.get('url'))}</p>
          {marker_note}
          {"<figure class='screenshot'><img src='" + img + "' alt='" + esc(stage) + " annotated screenshot'><figcaption>标注截图：编号对应下方问题详情</figcaption></figure>" if img else ""}
          <div class="issues">
            {f'<div class="issue-details">{detail_cards}</div>' if detail_cards else "<p>无证据充分的问题。</p>"}
          </div>
        </section>
        """)

    stage_issue_positions: dict[tuple[str, int], int] = {}
    for stage in STAGES:
        for idx, issue in enumerate((stage_analysis.get(stage) or {}).get("issues", []), start=1):
            stage_issue_positions[(stage, id(issue))] = idx
    issue_list = ""
    for stage, issue in all_issues:
        idx = stage_issue_positions.get((stage, id(issue)), 0)
        issue_list += issue_row(issue, include_stage=stage, marker=f"#{idx}" if idx and issue_markers.get((stage, idx)) else "未可靠定位")
    priority_list = ""
    for stage, issue in all_issues:
        if normalize_severity(issue) not in {"p0", "p1"}:
            continue
        idx = stage_issue_positions.get((stage, id(issue)), 0)
        priority_list += priority_row(stage, issue, f"#{idx}" if idx and issue_markers.get((stage, idx)) else "未可靠定位")
    stage_nav = "".join(f'<a class="nav-child" href="#stage-{esc(stage)}">{esc(stage)}</a>' for stage in STAGES)
    title = "华为云产品客户旅程体验审查报告"
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{
  --ink:#18202f;--muted:#667085;--line:#d9dee8;--panel:#ffffff;--page:#f4f6f8;
  --red:#c6262e;--amber:#b96b00;--green:#147a5c;--blue:#1f5fbf;--cyan:#0e7490;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:var(--page);line-height:1.55}}
header{{background:#ffffff;border-bottom:1px solid var(--line)}}
.hero{{max-width:1240px;margin:0 auto;padding:30px 28px 24px;display:grid;grid-template-columns:1fr auto;gap:24px;align-items:end}}
.eyebrow{{margin:0 0 8px;color:var(--blue);font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}
h1{{margin:0;font-size:30px;line-height:1.15;letter-spacing:0;font-weight:760}}
.meta{{margin-top:10px;color:var(--muted);font-size:13px;word-break:break-all}}
.stamp{{border:1px solid var(--line);background:#f9fafb;padding:12px 14px;min-width:190px}}
.stamp span{{display:block;color:var(--muted);font-size:12px}}
.stamp strong{{display:block;font-size:18px;margin-top:2px}}
main{{max-width:1440px;margin:0 auto;padding:24px 28px 64px}}
.report-shell{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:22px;align-items:start}}
.side-nav{{position:sticky;top:18px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px}}
.side-nav strong{{display:block;font-size:13px;color:var(--muted);margin:4px 0 10px}}
.side-nav a{{display:block;text-decoration:none;color:var(--ink);font-size:14px;padding:8px 10px;border-radius:6px}}
.side-nav a:hover{{background:#eef2f6;color:var(--blue)}}
.nav-group{{margin:2px 0}}
.nav-parent{{font-weight:700}}
.nav-children{{margin:2px 0 8px 8px;padding-left:10px;border-left:1px solid var(--line)}}
.side-nav .nav-child{{font-size:13px;color:#4b5563;padding:6px 10px}}
.content-section{{scroll-margin-top:20px}}
.stage-section{{background:transparent;border:0;padding:0;margin:0}}
.stage-section>.section-title{{margin:20px 0 10px}}
.section-header{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:0 0 14px}}
.section-header h2{{margin:0;font-size:22px}}
.section-header p{{margin:6px 0 0;color:var(--muted);font-size:13px}}
.summary{{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:12px;margin-bottom:18px}}
.metric{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px 16px 14px;position:relative;overflow:hidden}}
.metric::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--blue)}}
.metric:nth-child(2)::before{{background:var(--red)}}.metric:nth-child(3)::before{{background:var(--amber)}}.metric:nth-child(4)::before{{background:var(--green)}}
.metric b{{display:block;font-size:32px;line-height:1;font-variant-numeric:tabular-nums}}
.metric span{{display:block;margin-top:8px;color:var(--muted);font-size:13px}}
.journey{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;margin-bottom:22px}}
.section-title{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0 0 14px}}
.section-title h2{{margin:0;font-size:18px}}
.section-title p{{margin:0;color:var(--muted);font-size:13px}}
.journey-grid{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}}
.journey-step{{display:flex;min-height:112px;flex-direction:column;justify-content:space-between;text-decoration:none;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:12px;background:#fbfcfd;transition:transform .12s ease,border-color .12s ease,background .12s ease}}
.journey-step:hover{{transform:translateY(-1px);border-color:#9aa8bd;background:#fff}}
.journey-step span{{display:block;font-size:13px;color:var(--muted)}}
.journey-step strong{{display:block;font-size:20px;margin:4px 0;font-variant-numeric:tabular-nums}}
.journey-step small{{display:block;font-size:12px;color:#6b7280}}
.priority{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;margin-bottom:22px}}
.stage{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px 18px 20px;margin:16px 0}}
.stage.missing{{opacity:.72}}
.stage h2{{display:flex;justify-content:space-between;align-items:center;margin:0 0 8px;font-size:21px}}
.stage h2 span{{font-size:14px;color:var(--muted);font-weight:600}}
.url{{color:var(--muted);font-size:12px;word-break:break-all;margin:0 0 12px}}
img{{display:block;max-width:100%;border:1px solid var(--line);border-radius:6px;margin:14px 0;background:#fff}}
.screenshot{{margin:14px 0 16px}}
.screenshot img{{margin:0}}
.screenshot figcaption{{font-size:12px;color:var(--muted);margin-top:7px}}
.marker-note{{margin:10px 0 12px;color:#475467;font-size:13px;background:#f7fafc;border:1px solid var(--line);border-radius:6px;padding:9px 11px}}
.issue-table{{width:100%;border-collapse:separate;border-spacing:0;background:white;border:1px solid var(--line);border-radius:8px;overflow:hidden;table-layout:fixed}}
.issue-table th,.issue-table td{{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
.issue-table th{{font-size:12px;background:#eef2f6;color:#4b5563;font-weight:760;letter-spacing:.02em}}
.issue-table tr:last-child td{{border-bottom:0}}
.issue-table th:nth-child(1),.issue-table td:nth-child(1){{width:76px}}
.issue-table th:nth-child(2),.issue-table td:nth-child(2){{width:74px}}
.issue-table th:nth-child(3),.issue-table td:nth-child(3){{width:112px}}
.issue-table th:nth-child(4),.issue-table td:nth-child(4){{width:150px}}
.issue-table th:nth-last-child(2),.issue-table td:nth-last-child(2){{width:28%}}
.issue-table th:last-child,.issue-table td:last-child{{width:20%}}
.all-issues .issue-table th:nth-child(1),.all-issues .issue-table td:nth-child(1){{width:72px}}
.all-issues .issue-table th:nth-child(2),.all-issues .issue-table td:nth-child(2){{width:88px}}
.all-issues .issue-table th:nth-child(3),.all-issues .issue-table td:nth-child(3){{width:74px}}
.priority-table th:nth-child(1),.priority-table td:nth-child(1){{width:74px}}
.priority-table th:nth-child(2),.priority-table td:nth-child(2){{width:88px}}
.priority-table th:nth-child(3),.priority-table td:nth-child(3){{width:74px}}
.badge{{display:inline-block;min-width:42px;text-align:center;padding:3px 8px;border-radius:999px;font-size:12px;font-weight:700;color:white}}
tr.p0 .badge{{background:var(--red)}}tr.p1 .badge{{background:var(--amber)}}tr.p2 .badge{{background:var(--green)}}
tr.p0 td:first-child{{border-left:4px solid var(--red)}}tr.p1 td:first-child{{border-left:4px solid var(--amber)}}tr.p2 td:first-child{{border-left:4px solid var(--green)}}
.issue-details{{display:grid;gap:12px;margin-top:14px}}
.issue-card{{border:1px solid var(--line);border-radius:8px;padding:14px 15px;background:#fff}}
.issue-card.p0{{border-left:5px solid var(--red)}}.issue-card.p1{{border-left:5px solid var(--amber)}}.issue-card.p2{{border-left:5px solid var(--green)}}
.issue-top{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
.issue-top strong{{font-size:15px}}
.issue-top>span:not(.marker-ref){{font-size:12px;color:#fff;border-radius:999px;padding:2px 8px;background:#6b7280}}
.issue-card.p0 .issue-top>span:not(.marker-ref){{background:var(--red)}}.issue-card.p1 .issue-top>span:not(.marker-ref){{background:var(--amber)}}.issue-card.p2 .issue-top>span:not(.marker-ref){{background:var(--green)}}
.marker-ref{{display:inline-flex;align-items:center;justify-content:center;min-width:34px;height:28px;border-radius:999px;color:#fff;font-weight:800;font-size:13px}}
.marker-ref.p0{{background:var(--red)}}.marker-ref.p1{{background:var(--amber)}}.marker-ref.p2{{background:var(--green)}}.marker-ref.missing{{background:#8a94a6;min-width:52px}}
.issue-card p{{margin:8px 0;color:#344054}}
.issue-card b{{color:#111827}}
.issue-card details{{margin-top:10px;border-top:1px solid var(--line);padding-top:8px}}
.issue-card summary{{cursor:pointer;color:var(--blue);font-size:13px;font-weight:700}}
.all-issues{{margin-top:24px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;scroll-margin-top:20px}}
.all-issues h2{{margin:0 0 14px;font-size:20px}}
@media(max-width:1100px){{.report-shell{{grid-template-columns:1fr}}.side-nav{{position:static;display:flex;gap:6px;overflow:auto}}.side-nav strong,.nav-children{{display:none}}.side-nav a{{white-space:nowrap}}}}
@media(max-width:1020px){{.hero{{grid-template-columns:1fr}}.summary{{grid-template-columns:1fr 1fr}}.journey-grid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:760px){{main{{padding:18px}}.hero{{padding:24px 18px}}.summary{{grid-template-columns:1fr}}.issue-table{{font-size:13px;table-layout:auto}}.issue-table th,.issue-table td{{padding:10px}}}}
@media(prefers-reduced-motion:reduce){{.journey-step{{transition:none}}.journey-step:hover{{transform:none}}}}
</style>
</head>
<body>
<header>
  <div class="hero">
    <div>
      <p class="eyebrow">Customer Journey Audit</p>
      <h1>{title}</h1>
      <div class="meta">目标：{esc(crawl.get("input_url") or analysis.get("input_url"))}</div>
    </div>
    <div class="stamp"><span>生成时间</span><strong>{esc(datetime.now().strftime("%Y-%m-%d %H:%M"))}</strong></div>
  </div>
</header>
<main>
  <div class="report-shell">
    <aside class="side-nav" aria-label="报告导航">
      <strong>报告导航</strong>
      <div class="nav-group"><a class="nav-parent" href="#overview">问题汇总与旅程总览</a></div>
      <div class="nav-group">
        <a class="nav-parent" href="#stage-detail">阶段详细报告</a>
        <div class="nav-children">{stage_nav}</div>
      </div>
      <div class="nav-group"><a class="nav-parent" href="#issue-list">问题清单</a></div>
    </aside>
    <div class="report-content">
      <section id="overview" class="content-section">
        <div class="section-header">
          <h2>问题汇总与旅程总览</h2>
          <p>汇总整体问题数量，并按客户旅程阶段展示风险分布。</p>
        </div>
        <section class="summary">
          <div class="metric"><b>{len(all_issues)}</b><span>问题总数</span></div>
          <div class="metric"><b>{counts["p0"]}</b><span>阻断问题</span></div>
          <div class="metric"><b>{counts["p1"]}</b><span>重要问题</span></div>
          <div class="metric"><b>{counts["p2"]}</b><span>建议问题</span></div>
        </section>
        <section class="journey">
          <div class="section-title"><h2>客户旅程总览</h2><p>点击阶段查看截图与问题详情</p></div>
          <div class="journey-grid">{''.join(journey_overview)}</div>
        </section>
        <section class="priority">
          <div class="section-title"><h2>优先处理清单</h2><p>仅展示阻断和重要问题</p></div>
          {priority_table(priority_list) if priority_list else "<p>暂无阻断或重要问题。</p>"}
        </section>
      </section>
      <section id="stage-detail" class="content-section stage-section">
        <div class="section-header">
          <h2>阶段详细报告</h2>
          <p>共 {len(STAGES)} 个阶段，逐阶段展示截图、页面地址和问题详情。</p>
        </div>
        {''.join(stage_cards)}
      </section>
      <section id="issue-list" class="all-issues content-section">
        <div class="section-header">
          <h2>问题清单</h2>
          <p>按严重级别从高到低排序，便于直接进入修复排期。</p>
        </div>
        {issue_table(issue_list, include_stage=True) if issue_list else "<p>暂无问题。</p>"}
      </section>
    </div>
  </div>
</main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
