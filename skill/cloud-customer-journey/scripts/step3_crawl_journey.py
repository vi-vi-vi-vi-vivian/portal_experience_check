#!/usr/bin/env python3
"""Best-effort crawl for Huawei Cloud journey stages."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


STAGES = ["感知", "下单", "支付", "使用", "续费", "变更", "退订"]
LOGIN_REQUIRED_STAGES = {"支付", "使用", "续费", "变更", "退订"}
SITE_URLS = {
    "intl": {
        "console": "https://console-intl.huaweicloud.com/?locale=en-us",
        "account": "https://account-intl.huaweicloud.com/usercenter/?locale=en-us#/userindex/allview",
        "payment": "https://account-intl.huaweicloud.com/usercenter/?locale=en-us#/userindex/creditsList",
        "login": "https://auth.huaweicloud.com/authui/login.html?locale=en-us&service={service}",
    },
    "cn": {
        "console": "https://console.huaweicloud.com/console/?region=cn-east-3#/home",
        "account": "https://account.huaweicloud.com/usercenter/?region=cn-east-3#/userindex/allview",
        "payment": "https://account.huaweicloud.com/usercenter/?region=cn-east-3#/ordercenter/userindex/unpaidOrder",
        "login": "https://auth.huaweicloud.com/authui/login.html#/login",
    },
}
PRODUCT_PROFILES: dict[str, dict[str, Any]] = {
    # Product-specific aliases and console fallbacks. Generic products still use
    # URL-derived keywords and do not inherit these entry labels.
    "obs": {
        "match": ["obs"],
        "aliases": ["对象存储服务 OBS", "对象存储服务", "Object Storage Service", "OBS"],
        "console_urls": {
            "cn": "https://console.huaweicloud.com/obs/?region=cn-east-3#/obs/manager/buckets",
            "intl": "https://console-intl.huaweicloud.com/obs/?region=ap-southeast-1#/obs/manager/buckets",
        },
        "usage_url_markers": ["obs"],
        "usage_text_markers": ["对象存储服务", "Object Storage Service", "桶列表", "Buckets"],
        "usage_entry_labels": ["桶列表", "总览", "资源包管理", "总用量", "Buckets", "Overview", "Bucket List"],
    },
    "modelarts": {
        "match": ["modelarts"],
        "aliases": ["ModelArts", "AI开发平台ModelArts", "模型训推平台 ModelArts", "魔坊"],
        "console_urls": {
            "cn": "https://console.huaweicloud.com/modelarts/?region=cn-east-3#/dashboard",
            "intl": "https://console-intl.huaweicloud.com/modelarts/?region=ap-southeast-1#/manage/dashboard",
        },
        "usage_url_markers": ["modelarts"],
        "usage_text_markers": ["ModelArts", "AI开发平台ModelArts", "模型训推平台 ModelArts"],
        "usage_entry_labels": ["ModelArts", "总览", "Dashboard"],
        "order_url_markers": ["resource-pool"],
        "change_url_markers": ["resource-pool"],
    },
    "tokenplan": {
        "match": ["tokenplan"],
        "aliases": ["Token Plan", "TokenPlan", "智果园", "MaaS"],
        "console_urls": {
            "cn": "https://console.huaweicloud.com/modelarts/?region=cn-southwest-2#/model-studio/resourcePlanManagement",
        },
        "usage_url_markers": ["resourceplanmanagement"],
        "usage_text_markers": ["Token Plan", "智果园", "MaaS", "资源计划"],
        "usage_entry_labels": ["Token Plan", "资源计划", "Resource Plan"],
        "order_url_markers": ["resourceplanmanagement"],
        "order_text_markers": ["订阅 Token Plan"],
        "usage_required_url_markers": ["resourceplanmanagement"],
    },
}
STAGE_EN = {
    "感知": "awareness",
    "下单": "order",
    "支付": "payment",
    "使用": "usage",
    "续费": "renewal",
    "变更": "change",
    "退订": "unsubscribe",
}
CLICK_PATTERNS = {
    "下单": ["立即订阅", "立即购买", "立即选购", "去购买", "免费试用", "购买", "Buy", "Purchase", "Subscribe", "Get Started", "Free Trial"],
    "支付": ["立即购买", "提交订单", "确认订单", "下一步", "Pay", "Submit Order", "Confirm Order", "Checkout"],
    "续费": ["续费", "批量续费", "自动续费", "Renew", "Renewal"],
    "变更": ["变更", "规格变更", "升级", "降级", "Change", "Modify", "Upgrade", "Downgrade"],
    "退订": ["退订", "退费", "释放", "取消订阅", "Unsubscribe", "Refund", "Release", "Cancel"],
}
ORDER_CONFIG_PATTERNS = ["购买须知", "套餐配置", "配置费用", "自动续费", "我已阅读并同意", "Purchase notice", "Package configuration", "Auto-renewal"]
ORDER_STEP_PATTERNS = ["立即订阅", "立即购买", "立即选购", "去购买", "免费试用", "购买", "Buy", "Purchase", "Subscribe", "Get Started", "Free Trial", "开通"]
PAYMENT_URL_MARKERS = ["servicepay", "cashier", "payment"]
PAYMENT_TEXT_MARKERS = ["支付确认", "确认支付", "在线支付", "收银台", "应付金额", "支付方式"]


def has_huawei_cookies(auth_state: Path) -> bool:
    if not auth_state.exists():
        return False
    try:
        state = json.loads(auth_state.read_text(encoding="utf-8"))
    except Exception:
        return False
    return any("huaweicloud.com" in c.get("domain", "") for c in state.get("cookies", []))


def is_login_page(page: Page) -> bool:
    url = page.url.lower()
    if "auth.huaweicloud.com" in url and "login" in url:
        return True
    try:
        text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return False
    login_markers = ["welcome to huawei cloud", "password login", "iam user", "register"]
    return "auth.huaweicloud.com" in url or all(marker in text for marker in login_markers[:2])


def login_url(site: str, service_url: str) -> str:
    template = SITE_URLS[site]["login"]
    if "{service}" not in template:
        return template
    return template.format(service=urllib.parse.quote(service_url, safe=""))


def capture_login_state(p, root: Path, auth_state: Path, profile_dir: Path, wait_seconds: int, site: str) -> bool:
    profile_dir.mkdir(parents=True, exist_ok=True)
    auth_state.parent.mkdir(parents=True, exist_ok=True)
    service_url = SITE_URLS[site]["console"]
    context = p.chromium.launch_persistent_context(
        str(profile_dir),
        headless=False,
        viewport={"width": 1440, "height": 1000},
        locale="en-US",
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page.goto(login_url(site, service_url), wait_until="domcontentloaded", timeout=60000)
    print(f"Login required. Complete Huawei Cloud login in the opened browser within {wait_seconds}s.")
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not is_login_page(page):
            break
        time.sleep(1)
    state = context.storage_state(path=str(auth_state))
    context.close()
    huawei_cookies = [c for c in state.get("cookies", []) if "huaweicloud.com" in c.get("domain", "")]
    if not huawei_cookies:
        print(f"Warning: login state was not captured: {auth_state}")
        return False
    print(f"Saved login state: {auth_state} ({len(huawei_cookies)} Huawei Cloud cookies)")
    return True


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def pattern_regex(patterns: list[str]) -> re.Pattern[str]:
    escaped = [re.escape(p) for p in patterns]
    return re.compile("|".join(escaped), re.I)


def wait_after_action(page: Page, timeout: int = 15000) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(3000)


def dismiss_blocking_overlays(page: Page) -> int:
    """Best-effort close for visible modal notices that can be dismissed."""
    try:
        closed = page.evaluate(
            r"""() => {
              const visible = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
              };
              const overlaySelector = [
                '[role=dialog]', '[aria-modal=true]',
                '[class*=modal]', '[class*=Modal]', '[class*=dialog]', '[class*=Dialog]',
                '[class*=popup]', '[class*=Popup]', '[class*=drawer]', '[class*=Drawer]',
                '[class*=notice]', '[class*=Notice]', '[class*=announcement]', '[class*=Announcement]',
                '[class*=upgrade]', '[class*=Upgrade]'
              ].join(',');
              const overlays = Array.from(document.querySelectorAll(overlaySelector)).filter(visible);
              for (const el of Array.from(document.querySelectorAll('div,section,aside'))) {
                if (!visible(el)) continue;
                const text = (el.innerText || el.textContent || '').slice(0, 500);
                if (!/服务声明|升级公告|公告|声明|满意度评价|rate your experience/i.test(text)) continue;
                const s = getComputedStyle(el);
                const z = Number(s.zIndex) || 0;
                if (s.position === 'fixed' || s.position === 'sticky' || z >= 100) overlays.push(el);
              }
              let count = 0;
              const closeTexts = /^(关闭|确定|确认|知道了|我知道了|我已知晓|已阅读|我已阅读|同意|接受|不再提示|稍后再说|Close|OK|Got it|Agree)$/i;
              for (const overlay of overlays) {
                for (const box of Array.from(overlay.querySelectorAll('input[type=checkbox]'))) {
                  if (!box.checked && !box.disabled && visible(box)) {
                    box.click();
                    count += 1;
                  }
                }
                const clickables = Array.from(overlay.querySelectorAll('button,a,[role=button],span[class*=close],i[class*=close],svg[class*=close]'));
                const target = clickables.find(el => {
                  if (!visible(el)) return false;
                  const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                  const cls = String(el.className || '');
                  return closeTexts.test(text) || /close|cancel|confirm|ok|sure|known/i.test(cls);
                });
                if (target) {
                  target.click();
                  count += 1;
                  continue;
                }
                const text = (overlay.innerText || overlay.textContent || '').slice(0, 500);
                if (/满意度评价|rate your experience/i.test(text)) {
                  const r = overlay.getBoundingClientRect();
                  const topRight = Array.from(document.elementsFromPoint(Math.max(0, r.right - 28), Math.max(0, r.top + 28)));
                  const close = topRight.find(el => visible(el) && el !== overlay);
                  if (close) {
                    close.click();
                    count += 1;
                  }
                }
              }
              return count;
            }"""
        )
    except Exception:
        closed = 0
    if closed:
        page.wait_for_timeout(1000)
    return int(closed or 0)


def wait_for_text_stable(page: Page, min_wait_ms: int = 8000, max_wait_ms: int = 30000) -> None:
    deadline = time.time() + max_wait_ms / 1000
    page.wait_for_timeout(min_wait_ms)
    last = ""
    stable_count = 0
    while time.time() < deadline:
        try:
            text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            text = ""
        signature = f"{len(text)}:{text[-300:]}"
        if signature == last and text.strip():
            stable_count += 1
            if stable_count >= 2:
                return
        else:
            stable_count = 0
            last = signature
        page.wait_for_timeout(2000)


def wait_for_render_stable(page: Page, stage: str, max_wait_ms: int = 45000) -> None:
    """Wait for visual assets, fonts, and lazy sections before screenshotting."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    try:
        page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
    except Exception:
        pass

    if stage == "感知":
        try:
            height = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
            viewport = page.viewport_size or {"height": 1000}
            step = max(600, int(viewport.get("height", 1000) * 0.75))
            for y in range(0, min(int(height), 6000), step):
                page.evaluate("(value) => window.scrollTo(0, value)", y)
                page.wait_for_timeout(700)
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(1200)
        except Exception:
            pass

    deadline = time.time() + max_wait_ms / 1000
    last_signature = ""
    stable_count = 0
    while time.time() < deadline:
        try:
            state = page.evaluate(
                """() => {
                  const visible = el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
                  };
                  const sheets = Array.from(document.styleSheets);
                  let cssRules = 0;
                  for (const sheet of sheets) {
                    try { cssRules += sheet.cssRules ? sheet.cssRules.length : 0; } catch (e) {}
                  }
                  const viewportBottom = innerHeight + 300;
                  const imgs = Array.from(document.images).filter(img => {
                    const r = img.getBoundingClientRect();
                    return r.top < viewportBottom && r.bottom > -300 && visible(img);
                  });
                  const pendingImgs = imgs.filter(img => !img.complete || img.naturalWidth === 0).length;
                  const skeletons = Array.from(document.querySelectorAll('[class*=skeleton],[class*=loading],[class*=spin],[class*=placeholder]')).filter(visible).length;
                  const keyEls = Array.from(document.querySelectorAll('h1,h2,[class*=card],button,a,[role=button]')).filter(visible);
                  const rectSig = keyEls.slice(0, 80).map(el => {
                    const r = el.getBoundingClientRect();
                    return `${Math.round(r.x)},${Math.round(r.y)},${Math.round(r.width)},${Math.round(r.height)}`;
                  }).join('|');
                  return {
                    ready: document.readyState,
                    cssRules,
                    pendingImgs,
                    skeletons,
                    keyCount: keyEls.length,
                    bodyLen: (document.body.innerText || '').length,
                    rectSig
                  };
                }"""
            )
        except Exception:
            page.wait_for_timeout(1000)
            continue
        signature = f"{state.get('ready')}:{state.get('cssRules')}:{state.get('pendingImgs')}:{state.get('skeletons')}:{state.get('keyCount')}:{state.get('bodyLen')}:{state.get('rectSig')}"
        visually_ready = (
            state.get("ready") == "complete"
            and int(state.get("cssRules") or 0) > 0
            and int(state.get("pendingImgs") or 0) == 0
            and int(state.get("skeletons") or 0) == 0
            and int(state.get("keyCount") or 0) >= 8
        )
        if visually_ready and signature == last_signature:
            stable_count += 1
            if stable_count >= 2:
                return
        else:
            stable_count = 0
            last_signature = signature
        page.wait_for_timeout(1200)


def wait_for_stage_ready(page: Page, stage: str) -> None:
    if stage in {"下单", "支付", "续费"}:
        wait_for_text_stable(page, min_wait_ms=12000, max_wait_ms=45000)
    elif stage in {"使用", "变更", "退订"}:
        wait_for_text_stable(page, min_wait_ms=8000, max_wait_ms=30000)
    else:
        wait_for_text_stable(page, min_wait_ms=5000, max_wait_ms=20000)
    wait_for_render_stable(page, stage)


def log_stage(stage: str, message: str) -> None:
    print(f"[{stage}] {message}", flush=True)


def click_first(page: Page, patterns: list[str]) -> bool:
    regex = pattern_regex(patterns)
    links = page.locator("a,button,[role=button]")
    count = min(links.count(), 200)
    for i in range(count):
        item = links.nth(i)
        try:
            text = item.inner_text(timeout=1000).strip()
            if text and regex.search(text):
                href = item.get_attribute("href")
                if href:
                    page.goto(href, wait_until="domcontentloaded", timeout=45000)
                else:
                    item.click(timeout=5000)
                wait_after_action(page)
                return True
        except Exception:
            continue
    for pattern in patterns:
        locator = page.get_by_text(pattern, exact=True)
        if locator.count():
            try:
                locator.first.click(timeout=5000)
                wait_after_action(page)
                return True
            except Exception:
                pass
    return False


def click_cta_with_fallback(page: Page, patterns: list[str]) -> bool:
    """Click CTA using href navigation, accessible text click, then JS DOM click."""
    regex = pattern_regex(patterns)

    # 1. Prefer explicit href navigation from anchors/buttons.
    locator = page.locator("a[href],button,[role=button]")
    count = min(locator.count(), 300)
    for i in range(count):
        item = locator.nth(i)
        try:
            text = item.inner_text(timeout=800).strip()
            if not text or not regex.search(text):
                continue
            href = item.get_attribute("href")
            if href and not href.startswith("javascript:"):
                page.goto(href, wait_until="domcontentloaded", timeout=60000)
                wait_after_action(page)
                return True
        except Exception:
            continue

    # 2. Use role/text locators, which follow the accessibility tree better than raw DOM order.
    for pattern in patterns:
        candidates = [
            page.get_by_role("link", name=re.compile(re.escape(pattern), re.I)),
            page.get_by_role("button", name=re.compile(re.escape(pattern), re.I)),
            page.get_by_text(pattern, exact=False),
        ]
        for candidate in candidates:
            try:
                if candidate.count():
                    candidate.first.click(timeout=5000)
                    wait_after_action(page)
                    return True
            except Exception:
                continue

    # 3. Last resort: JS DOM click on visible matching elements.
    clicked = page.evaluate(
        r"""patterns => {
          const escapeRegex = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const re = new RegExp(patterns.map(escapeRegex).join('|'), 'i');
          const nodes = Array.from(document.querySelectorAll('a,button,[role=button],input[type=button],input[type=submit]'));
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
          };
          const el = nodes.find(e => visible(e) && re.test((e.innerText || e.value || e.getAttribute('aria-label') || '').trim()));
          if (!el) return false;
          el.click();
          return true;
        }""",
        patterns,
    )
    if clicked:
        wait_after_action(page)
        return True
    return False


def navigate_cta_href(page: Page, patterns: list[str]) -> bool:
    href = page.evaluate(
        r"""patterns => {
          const escapeRegex = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const re = new RegExp(patterns.map(escapeRegex).join('|'), 'i');
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
          };
          const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
            text: (a.innerText || a.textContent || a.getAttribute('aria-label') || '').trim(),
            href: a.href,
            visible: visible(a)
          })).filter(a => a.href && !a.href.startsWith('javascript:') && re.test(a.text));
          const preferred = links.find(a => a.visible && /console\.huaweicloud\.com|account\.huaweicloud\.com/.test(a.href))
            || links.find(a => /console\.huaweicloud\.com|account\.huaweicloud\.com/.test(a.href))
            || links.find(a => a.visible)
            || links[0];
          return preferred ? preferred.href : null;
        }""",
        patterns,
    )
    if not href:
        return False
    page.goto(href, wait_until="domcontentloaded", timeout=60000)
    wait_after_action(page)
    return True


def check_agreements(page: Page) -> int:
    try:
        return page.evaluate(
            """() => {
              const boxes = Array.from(document.querySelectorAll('input[type=checkbox]'));
              let changed = 0;
              for (const box of boxes) {
                const text = (box.closest('label')?.innerText || box.parentElement?.innerText || '').trim();
                const required = /协议|条款|声明|同意|阅读|服务|agreement|terms|agree/i.test(text);
                if (!box.checked && (required || boxes.length <= 3)) {
                  box.click();
                  changed += 1;
                }
              }
              return changed;
            }"""
        )
    except Exception:
        wait_after_action(page)
        return 0


def check_visible_checkboxes(page: Page) -> int:
    try:
        return page.evaluate(
            """() => {
              const boxes = Array.from(document.querySelectorAll('input[type=checkbox]'));
              let changed = 0;
              for (const box of boxes) {
                const r = box.getBoundingClientRect();
                const s = getComputedStyle(box);
                const visible = r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                if (visible && !box.checked && !box.disabled) {
                  box.click();
                  changed += 1;
                }
              }
              return changed;
            }"""
        )
    except Exception:
        wait_after_action(page)
        return 0


def profile_for_target(target_url: str) -> dict[str, Any]:
    lowered = target_url.lower()
    for profile in PRODUCT_PROFILES.values():
        if any(marker.lower() in lowered for marker in profile.get("match", [])):
            return profile
    return {}


def marker_in_url_or_text(url: str, text: str, markers: list[str]) -> bool:
    lowered_url = url.lower()
    lowered_text = text.lower()
    return any(marker.lower() in lowered_url or marker.lower() in lowered_text for marker in markers if marker)


def is_console_page_url(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    return host in {"console.huaweicloud.com", "console-intl.huaweicloud.com"}


def page_is_purchase_flow(page: Page, profile: dict[str, Any] | None = None) -> bool:
    url = page.url.lower()
    url_markers = ["purchase", "order", "buy", "subscribe", "config"]
    if profile:
        url_markers.extend(profile.get("order_url_markers", []))
    if any(token.lower() in url for token in url_markers):
        return True
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        text = ""
    text_markers = ["立即购买", "提交订单", "确认订单", "服务声明", "购买后不支持退订"]
    if profile:
        text_markers.extend(profile.get("order_text_markers", []))
    return any(token in text for token in text_markers)


def page_is_payment_flow(page: Page) -> bool:
    url = page.url.lower()
    if any(token in url for token in PAYMENT_URL_MARKERS):
        return True
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        text = ""
    return any(token in text for token in PAYMENT_TEXT_MARKERS)


def submit_order_to_payment(page: Page, patterns: list[str], profile: dict[str, Any] | None = None, retries: int = 3) -> bool:
    for _ in range(retries):
        dismiss_blocking_overlays(page)
        check_agreements(page)
        dismiss_blocking_overlays(page)
        if click_cta_with_fallback(page, patterns):
            dismiss_blocking_overlays(page)
            if page_is_payment_flow(page):
                return True
            if not page_is_purchase_flow(page, profile):
                return True
        try:
            page.mouse.wheel(0, 900)
        except Exception:
            pass
        page.wait_for_timeout(1500)
    return False


def console_product_landed(page: Page, product_keywords: list[str], profile: dict[str, Any]) -> bool:
    url = page.url.lower()
    if not is_console_page_url(page.url):
        return False
    is_console_home = (
        "#/home" in url
        or url.rstrip("/").endswith("console.huaweicloud.com/console")
        or url.rstrip("/").endswith("console-intl.huaweicloud.com")
    )
    profile_markers = profile.get("usage_url_markers", [])
    if profile_markers and any(marker.lower() in url for marker in profile_markers):
        return True
    if is_console_home:
        return False
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        text = ""
    if marker_in_url_or_text(page.url, text, profile.get("usage_text_markers", [])):
        return True
    keyword_markers = [keyword for keyword in product_keywords if len(keyword.strip()) >= 3]
    return marker_in_url_or_text(page.url, text, keyword_markers)


def click_console_search_result(page: Page, product_keywords: list[str], profile: dict[str, Any]) -> bool:
    preferred = [str(item) for item in profile.get("usage_text_markers", []) if str(item).strip()]
    aliases = [str(item) for item in profile.get("aliases", []) if str(item).strip()]
    candidates = preferred + aliases + [str(item) for item in product_keywords if len(str(item).strip()) >= 3]
    action_labels = [str(item) for item in profile.get("usage_entry_labels", []) if str(item).strip()]
    clicked = page.evaluate(
        r"""payload => {
          const candidates = payload.candidates || [];
          const actionLabels = payload.actionLabels || [];
          const visible = el => {
            const style = window.getComputedStyle(el);
            const box = el.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && box.width > 0 && box.height > 0;
          };
          const normalized = candidates.map(value => String(value).toLowerCase()).filter(Boolean);
          const normalizedActions = actionLabels.map(value => String(value).toLowerCase()).filter(Boolean);
          const nodes = Array.from(document.querySelectorAll('a,button,[role="button"],[class*="search"],[class*="result"],[class*="item"],[class*="list"],[class*="row"],div,li,tr'));
          const matches = nodes
            .filter(visible)
            .map(el => ({el, text: (el.innerText || el.textContent || '').trim()}))
            .filter(item => item.text && normalized.some(token => item.text.toLowerCase().includes(token)))
            .filter(item => !['INPUT', 'TEXTAREA'].includes(item.el.tagName));
          matches.sort((a, b) => {
            const aPreferred = normalized.some(token => a.text.toLowerCase().startsWith(token)) ? 0 : 1;
            const bPreferred = normalized.some(token => b.text.toLowerCase().startsWith(token)) ? 0 : 1;
            const aAction = normalizedActions.some(token => a.text.toLowerCase().includes(token)) ? 0 : 1;
            const bAction = normalizedActions.some(token => b.text.toLowerCase().includes(token)) ? 0 : 1;
            return aAction - bAction || aPreferred - bPreferred || a.text.length - b.text.length;
          });
          for (const match of matches) {
            const containers = [
              match.el.closest('a,button,[role="button"]'),
              match.el.closest('li,[class*="result"],[class*="item"],[class*="card"],[class*="search"],[class*="list"],[class*="row"],tr'),
              match.el.parentElement,
              match.el
            ].filter(Boolean);
            for (const container of containers) {
              const all = [container, ...Array.from(container.querySelectorAll('a,button,[role="button"],div,span'))].filter(visible);
              const action = all.find(el => normalizedActions.some(label => (el.innerText || el.textContent || '').trim().toLowerCase() === label))
                || all.find(el => normalizedActions.some(label => (el.innerText || el.textContent || '').trim().toLowerCase().includes(label)))
                || all.find(el => normalized.some(label => (el.innerText || el.textContent || '').trim().toLowerCase().includes(label)))
                || all[0];
              if (!action) continue;
              action.scrollIntoView({block: 'center', inline: 'center'});
              action.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, cancelable: true, view: window}));
              action.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
              action.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
              action.click();
              return true;
            }
          }
          return false;
        }""",
        {"candidates": list(dict.fromkeys(candidates)), "actionLabels": list(dict.fromkeys(action_labels))},
    )
    if clicked:
        for _ in range(4):
            wait_after_action(page)
            if console_product_landed(page, product_keywords, profile):
                return True
    return False


def console_search_has_product_result(page: Page, product_keywords: list[str], profile: dict[str, Any]) -> bool:
    markers = (
        [str(item) for item in product_keywords if len(str(item).strip()) >= 3]
        + [str(item) for item in profile.get("usage_text_markers", [])]
        + [str(item) for item in profile.get("aliases", [])]
    )
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    return marker_in_url_or_text("", text, markers)


def search_console_product(
    page: Page,
    console_url: str,
    product_keywords: list[str],
    profile: dict[str, Any],
    fallback_url: str | None = None,
) -> bool:
    page.goto(console_url, wait_until="domcontentloaded", timeout=60000)
    wait_after_action(page)
    for keyword in product_keywords:
        inputs = page.locator("input[placeholder],input[type=search],input[type=text]")
        count = min(inputs.count(), 20)
        for i in range(count):
            item = inputs.nth(i)
            try:
                if not item.is_visible(timeout=800):
                    continue
                item.fill(keyword, timeout=3000)
                page.wait_for_timeout(1000)
                item.press("Enter", timeout=3000)
                wait_after_action(page)
                if console_product_landed(page, product_keywords, profile):
                    return True
                if click_console_search_result(page, product_keywords, profile):
                    return True
                found_result = console_search_has_product_result(page, product_keywords, profile)
                for result_text in product_keywords:
                    try:
                        result = page.get_by_text(result_text, exact=False)
                        if result.count():
                            result.first.click(timeout=5000)
                            wait_after_action(page)
                            if console_product_landed(page, product_keywords, profile):
                                return True
                    except Exception:
                        continue
                if found_result and fallback_url:
                    page.goto(fallback_url, wait_until="domcontentloaded", timeout=60000)
                    wait_for_stage_ready(page, "使用")
                    if console_product_landed(page, product_keywords, profile):
                        return True
            except Exception:
                continue
    return False


def find_account_link(page: Page, patterns: list[str], required_domain: str = "account.huaweicloud.com") -> bool:
    regex = pattern_regex(patterns)
    links = page.locator("a[href]")
    count = min(links.count(), 400)
    for i in range(count):
        item = links.nth(i)
        try:
            text = item.inner_text(timeout=800).strip()
            href = item.get_attribute("href") or ""
            if required_domain in href and (regex.search(text) or regex.search(href)):
                page.goto(href, wait_until="domcontentloaded", timeout=60000)
                wait_after_action(page)
                return True
        except Exception:
            continue
    return False


def flatten_ax_links(node: dict[str, Any] | None) -> list[dict[str, str]]:
    if not node:
        return []
    found: list[dict[str, str]] = []
    if node.get("role") == "link":
        name = str(node.get("name") or "")
        url = str(node.get("url") or "")
        if name or url:
            found.append({"text": name, "href": url})
    for child in node.get("children") or []:
        found.extend(flatten_ax_links(child))
    return found


def find_account_billing_url_from_console(page: Page, console_url: str, patterns: list[str]) -> str | None:
    page.goto(console_url, wait_until="domcontentloaded", timeout=60000)
    wait_for_stage_ready(page, "使用")
    js_match = page.evaluate(
        r"""patterns => {
          const escapeRegex = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const re = new RegExp(patterns.map(escapeRegex).join('|'), 'i');
          const anchors = Array.from(document.querySelectorAll('a'));
          const normalized = anchors.map(a => ({
            text: (a.innerText || a.textContent || a.getAttribute('aria-label') || '').trim(),
            href: a.href || a.getAttribute('href') || ''
          }));
          const match = normalized.find(a => a.href.includes('account.huaweicloud.com') && (re.test(a.text) || re.test(a.href)));
          return match ? match.href : null;
        }""",
        patterns,
    )
    if js_match:
        return js_match

    try:
        snapshot = page.accessibility.snapshot(root=None, interesting_only=False)
    except Exception:
        snapshot = None
    regex = pattern_regex(patterns)
    for link in flatten_ax_links(snapshot):
        href = link.get("href") or ""
        text = link.get("text") or ""
        if "account.huaweicloud.com" in href and (regex.search(text) or regex.search(href)):
            return href
    return None


def navigate_account_billing_from_console(page: Page, console_url: str, patterns: list[str], stage: str) -> bool:
    billing_url = find_account_billing_url_from_console(page, console_url, patterns)
    if not billing_url:
        return False
    page.goto(billing_url, wait_until="domcontentloaded", timeout=60000)
    wait_for_stage_ready(page, stage)
    return True


def go_account_or_click(page: Page, account_url: str, patterns: list[str], product_console_url: str | None = None) -> bool:
    page.goto(account_url, wait_until="domcontentloaded", timeout=60000)
    wait_after_action(page)
    if find_account_link(page, patterns):
        return True
    if click_cta_with_fallback(page, patterns):
        return True
    if product_console_url:
        page.goto(product_console_url, wait_until="domcontentloaded", timeout=60000)
        wait_after_action(page)
        return click_cta_with_fallback(page, patterns)
    return False


def maybe_cn_product_url(url: str, site: str) -> str:
    if site != "cn":
        return url
    return re.sub(r"/intl/en-us/product/", "/product/", url)


def product_slug_from_url(url: str) -> str:
    stem = Path(urllib.parse.urlparse(url).path).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or "product"


def product_keywords_from_url(url: str, profile: dict[str, Any] | None = None) -> list[str]:
    stem = Path(urllib.parse.urlparse(url).path).stem
    keywords = []
    if stem:
        keywords.append(stem)
    if profile:
        keywords.extend(profile.get("aliases", []))
    return list(dict.fromkeys(keywords))


def product_console_url_for_target(profile: dict[str, Any], urls: dict[str, str], site: str) -> str:
    return profile.get("console_urls", {}).get(site) or urls["console"]


def renewal_url_for_account(account_url: str) -> str:
    base = account_url.split("#", 1)[0]
    return f"{base}#/userindex/renewalManagement"


def page_is_order_config(page: Page) -> bool:
    if page_is_payment_flow(page):
        return False
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        text = ""
    if any(token in text for token in ORDER_CONFIG_PATTERNS):
        return True
    url = page.url.lower()
    return any(token in url for token in ["purchase", "order", "buy", "subscribe", "config"]) and any(
        marker in text for marker in ["¥", "￥", "$", "协议", "terms", "agreement", "购买", "Buy"]
    )


def click_order_cta(page: Page) -> bool:
    target = page.evaluate(
        r"""() => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
          };
          const disabled = el => {
            const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
            return el.disabled || el.getAttribute('aria-disabled') === 'true' || /disabled|is-disabled/.test(String(el.className || '')) || /补货|售罄|Restocking|Sold out/i.test(text);
          };
          const nodes = Array.from(document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit],div,span'));
          const exact = /^(立即订阅|立即购买|立即选购|去购买|购买|Buy|Purchase|Subscribe|开通|Get Started|Free Trial)$/i;
          const current = location.href.split('#')[0] + location.hash;
          const scored = [];
          for (const el of nodes) {
            if (!visible(el) || disabled(el)) continue;
            const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
            if (!exact.test(text)) continue;
            const target = el.closest('button,a,[role=button]') || el;
            if (!visible(target) || disabled(target)) continue;
            const href = target.href || target.getAttribute('href') || '';
            if (href && (href === location.href || href === current || href.endsWith(location.hash))) continue;
            const r = target.getBoundingClientRect();
            const inNav = !!target.closest('nav,header,aside,[class*=nav],[class*=menu],[class*=sidebar],[class*=header]');
            let score = 0;
            if (/^(立即购买|购买|Buy|Purchase)$/i.test(text)) score += 50;
            if (target.tagName === 'BUTTON' || target.getAttribute('role') === 'button') score += 20;
            if (!inNav) score += 20;
            if (r.top > 120 && r.left > 200) score += 10;
            score += Math.min(10, r.width / 40);
            scored.push({text, x: r.left + r.width / 2, y: r.top + r.height / 2, score});
          }
          scored.sort((a, b) => b.score - a.score);
          if (!scored.length) return false;
          return scored[0];
        }"""
    )
    if target:
        print(f"[下单] order CTA target={target.get('text')} x={target.get('x'):.1f} y={target.get('y'):.1f}", flush=True)
        page.mouse.click(float(target["x"]), float(target["y"]))
        wait_after_action(page)
        return True
    print("[下单] order CTA target not found", flush=True)
    return False


def explore_to_order_config(page: Page, max_steps: int = 3) -> bool:
    """Follow visible order CTAs until an order configuration page is reached."""
    for _ in range(max_steps):
        dismiss_blocking_overlays(page)
        wait_for_stage_ready(page, "下单")
        if page_is_order_config(page):
            return True
        before_url = page.url
        before_text = ""
        try:
            before_text = page.locator("body").inner_text(timeout=3000)[:1000]
        except Exception:
            pass
        clicked = click_order_cta(page) or click_cta_with_fallback(page, ORDER_STEP_PATTERNS)
        if not clicked:
            return page_is_order_config(page)
        dismiss_blocking_overlays(page)
        if page_is_order_config(page):
            return True
        try:
            after_text = page.locator("body").inner_text(timeout=3000)[:1000]
        except Exception:
            after_text = ""
        if page.url == before_url and after_text == before_text:
            return False
    return page_is_order_config(page)


def stage_goal_reached(
    record: dict[str, Any],
    target_url: str,
    product_keywords: list[str],
    profile: dict[str, Any],
) -> tuple[bool, str]:
    stage = record.get("stage")
    url = record.get("url") or ""
    text = record.get("body_text") or ""
    if record.get("entry_not_found") or record.get("login_required") or record.get("blank_page"):
        return False, record.get("blocked_reason") or "Stage page was not reachable."
    if stage == "感知":
        return True, ""
    if url == target_url:
        return False, f"{stage} stage stayed on the product awareness page instead of reaching the target journey page."
    if stage == "下单":
        lowered = url.lower()
        ok = (
            any(token in lowered for token in ["purchase", "order", "buy", "subscribe", "config"])
            or any(token in text for token in ORDER_CONFIG_PATTERNS)
        )
        return ok, "Order stage did not reach an order configuration or purchase preparation page."
    if stage == "支付":
        lowered = url.lower()
        ok = any(token in lowered for token in PAYMENT_URL_MARKERS) or any(token in text for token in PAYMENT_TEXT_MARKERS)
        return ok, "Payment stage did not reach a servicePay, cashier, or payment confirmation page."
    if stage == "使用":
        lowered = url.lower()
        is_console_home = (
            "#/home" in lowered
            or lowered.rstrip("/").endswith("console.huaweicloud.com/console")
            or lowered.rstrip("/").endswith("console-intl.huaweicloud.com")
        )
        ok = (
            is_console_page_url(url)
            and url != target_url
            and not is_console_home
            and (
                marker_in_url_or_text(url, text, product_keywords)
                or marker_in_url_or_text(url, text, profile.get("usage_url_markers", []))
                or marker_in_url_or_text(url, text, profile.get("usage_text_markers", []))
            )
        )
        return ok, "Usage stage did not reach a usable console page."
    if stage == "续费":
        ok = "renewal" in url.lower()
        return ok, "Renewal stage did not reach renewal management."
    if stage == "变更":
        lowered = url.lower()
        ok = (
            "allview" not in lowered
            and (
                any(token in lowered for token in ["change", "modify", "resize", "upgrade", "downgrade"])
                or marker_in_url_or_text(url, text, profile.get("change_url_markers", []))
                or marker_in_url_or_text(url, text, profile.get("change_text_markers", []))
                or "规格变更" in text
                or "变更套餐" in text
            )
        )
        return ok, "Change stage did not reach a product change page."
    if stage == "退订":
        lowered = url.lower()
        ok = (
            "usercenter" in lowered
            and "allview" not in lowered
            and (
                any(token in lowered for token in ["unsubscribe", "refund", "cancel"])
                or "云服务退订" in text
                or "退订资源" in text
                or "退费" in text
            )
        )
        return ok, "Unsubscribe stage did not reach cloud service unsubscribe management."
    return True, ""


def extract_page(page: Page, root: Path, stage: str, index: int, screenshot_dir: Path) -> dict[str, Any]:
    shot_dir = screenshot_dir
    shot_dir.mkdir(parents=True, exist_ok=True)
    stage_en = STAGE_EN[stage]
    screenshot = shot_dir / f"screenshot_{index}_{stage_en}.png"
    region = shot_dir / f"region_{index}_{stage_en}_top.png"
    page.screenshot(path=str(screenshot), full_page=True)
    page.screenshot(path=str(region), full_page=False)

    body_text = page.locator("body").inner_text(timeout=10000)
    structured_html = page.locator("body").evaluate("el => el.outerHTML")
    buttons = page.evaluate(
        """() => Array.from(document.querySelectorAll('button,a,[role=button]')).slice(0,160).map(e => {
          const r = e.getBoundingClientRect();
          return {text:(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,140),
            href:e.href||e.getAttribute('href')||'', isDisabled:!!(e.disabled||e.getAttribute('aria-disabled')==='true'||/disabled/i.test(e.className||'')),
            x:Math.round(r.x+scrollX), y:Math.round(r.y+scrollY), w:Math.round(r.width), h:Math.round(r.height)}
        }).filter(x => x.text)"""
    )
    links = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]')).slice(0,200).map(e => ({
          text:(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,140), href:e.href
        })).filter(x => x.text && !x.href.startsWith('javascript:'))"""
    )
    visual_details = page.evaluate(
        """() => Array.from(document.querySelectorAll('button,a,input,select,textarea,[role=button],[class*=btn],[class*=price],[class*=card],[class*=title]')).slice(0,160).map(e => {
          const s = getComputedStyle(e), r = e.getBoundingClientRect();
          return {tag:e.tagName.toLowerCase(), text:(e.innerText||e.value||e.getAttribute('aria-label')||'').trim().slice(0,120),
            fontSize:s.fontSize, color:s.color, bgColor:s.backgroundColor, opacity:s.opacity,
            isDisabled:!!(e.disabled||e.getAttribute('aria-disabled')==='true'||/disabled/i.test(e.className||'')),
            x:Math.round(r.x+scrollX), y:Math.round(r.y+scrollY), w:Math.round(r.width), h:Math.round(r.height), cls:String(e.className||'').slice(0,160)}
        }).filter(x => x.text || x.w > 20)"""
    )
    element_rects = page.evaluate(
        """() => Array.from(document.querySelectorAll('button,a,h1,h2,h3,h4,input,select,textarea,[class*=btn],[class*=price],[class*=title],[class*=nav],[class*=card],[class*=notice],[class*=alert],[class*=tip]')).slice(0,220).map(e => {
          const r = e.getBoundingClientRect();
          return {tag:e.tagName.toLowerCase(), text:(e.innerText||e.value||e.getAttribute('aria-label')||'').trim().slice(0,120),
            x:Math.round(r.x+scrollX), y:Math.round(r.y+scrollY), w:Math.round(r.width), h:Math.round(r.height)}
        }).filter(x => x.text && x.w > 0 && x.h > 0)"""
    )
    prices = []
    for match in re.finditer(r"(?:USD|US\$|\$|¥|￥)\s?[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s?(?:USD|CNY|yuan|/month|/year)", body_text, re.I):
        text = match.group(0)
        if text not in {p["text"] for p in prices}:
            prices.append({"text": text})

    record = {
        "stage": stage,
        "url": page.url,
        "title": page.title(),
        "screenshot_path": rel(root, screenshot),
        "region_screenshots": [rel(root, region)],
        "body_text": body_text[:24000],
        "structured_html": structured_html[:80000],
        "buttons": buttons,
        "links": links,
        "price_info": prices[:60],
        "visual_details": visual_details,
        "element_rects": element_rects,
    }
    if is_login_page(page):
        record["entry_not_found"] = True
        record["login_required"] = True
        record["blocked_reason"] = "Redirected to Huawei Cloud login page; valid auth state is required for this stage."
    elif not body_text.strip() and not buttons and not links:
        record["entry_not_found"] = True
        record["blank_page"] = True
        record["blocked_reason"] = "Page loaded without visible text, links, or buttons."
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--auth-state", default="../../output/web/_runtime/auth_cookie.json")
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--ensure-login", action="store_true", help="Open a headed login browser when auth state is missing.")
    parser.add_argument("--use-login-profile", action="store_true", help="Crawl with the persistent login profile instead of importing storage_state.")
    parser.add_argument("--site", choices=sorted(SITE_URLS), default="intl")
    parser.add_argument("--login-wait-seconds", type=int, default=180)
    parser.add_argument("--profile-dir", default="../../output/web/_runtime/huaweicloud_login_profile")
    parser.add_argument("--output", default="../../output/web/manual/_crawl.json")
    parser.add_argument("--screenshot-dir", default=None)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    target_url = maybe_cn_product_url(args.url, args.site)
    product_slug = product_slug_from_url(target_url)
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    auth_state = Path(args.auth_state)
    if not auth_state.is_absolute():
        auth_state = root / auth_state
    profile_dir = Path(args.profile_dir)
    if not profile_dir.is_absolute():
        profile_dir = root / profile_dir
    screenshot_dir = Path(args.screenshot_dir) if args.screenshot_dir else root / "../../output/web/manual/screenshots"
    if not screenshot_dir.is_absolute():
        screenshot_dir = root / screenshot_dir
    urls = SITE_URLS[args.site]
    product_profile = profile_for_target(target_url)
    product_keywords = product_keywords_from_url(target_url, product_profile)
    product_console_url = product_console_url_for_target(product_profile, urls, args.site)

    stages = STAGES if args.all else [args.stage or "感知"]
    output.parent.mkdir(parents=True, exist_ok=True)

    pages: list[dict[str, Any]] = []
    missing: list[str] = []
    with sync_playwright() as p:
        needs_login = bool(LOGIN_REQUIRED_STAGES.intersection(stages))
        if needs_login and not has_huawei_cookies(auth_state):
            if args.ensure_login:
                capture_login_state(p, root, auth_state, profile_dir, args.login_wait_seconds, args.site)
            else:
                print(
                    "Warning: no valid auth state found at "
                    f"{auth_state}. Login-required stages will likely be blocked. "
                    "Run step2_login_handler.py first or rerun step3 with --ensure-login."
                )

        browser = None
        if args.use_login_profile or args.ensure_login:
            context = p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=not args.headed,
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                args=["--disable-blink-features=AutomationControlled"],
            )
        else:
            browser = p.chromium.launch(headless=not args.headed, args=["--disable-blink-features=AutomationControlled"])
            context_args: dict[str, Any] = {"viewport": {"width": 1440, "height": 1000}, "locale": "en-US"}
            if has_huawei_cookies(auth_state):
                context_args["storage_state"] = str(auth_state)
            context = browser.new_context(**context_args)
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        for stage in stages:
            try:
                log_stage(stage, "start")
                if stage == "感知":
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(5000)
                    dismiss_blocking_overlays(page)
                elif stage == "下单":
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    wait_for_stage_ready(page, "感知")
                    dismiss_blocking_overlays(page)
                    clicked = navigate_cta_href(page, CLICK_PATTERNS[stage]) or click_cta_with_fallback(page, CLICK_PATTERNS[stage])
                    dismiss_blocking_overlays(page)
                    purchase_ready = explore_to_order_config(page)
                    dismiss_blocking_overlays(page)
                    log_stage(stage, f"CTA clicked={clicked}; purchase_ready={purchase_ready}; url={page.url}")
                elif stage == "支付":
                    if not page_is_order_config(page):
                        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(3000)
                        dismiss_blocking_overlays(page)
                        click_cta_with_fallback(page, CLICK_PATTERNS["下单"])
                        dismiss_blocking_overlays(page)
                        explore_to_order_config(page)
                    submitted = submit_order_to_payment(page, CLICK_PATTERNS[stage], profile=product_profile, retries=3)
                    log_stage(stage, f"submit clicked={submitted}; url={page.url}")
                elif stage == "使用":
                    found_product = search_console_product(
                        page,
                        urls["console"],
                        product_keywords,
                        product_profile,
                        fallback_url=product_console_url,
                    )
                    log_stage(stage, f"console search found={found_product}; url={page.url}")
                    required_markers = product_profile.get("usage_required_url_markers", [])
                    if found_product and required_markers and not any(marker.lower() in page.url.lower() for marker in required_markers):
                        log_stage(stage, "console search did not land on the configured product management page; using product fallback")
                        found_product = False
                    if not found_product:
                        page.goto(product_console_url, wait_until="domcontentloaded", timeout=60000)
                        wait_for_stage_ready(page, stage)
                    dismiss_blocking_overlays(page)
                    checked = check_visible_checkboxes(page)
                    log_stage(stage, f"checked visible checkboxes={checked}; url={page.url}")
                    page.wait_for_timeout(2000)
                elif stage == "续费":
                    navigated = go_account_or_click(page, urls["account"], CLICK_PATTERNS[stage])
                    if not navigated or "renewal" not in page.url.lower():
                        page.goto(renewal_url_for_account(urls["account"]), wait_until="domcontentloaded", timeout=60000)
                        wait_for_stage_ready(page, stage)
                        navigated = "renewal" in page.url.lower()
                    dismiss_blocking_overlays(page)
                    log_stage(stage, f"renewal navigation={navigated}; url={page.url}")
                elif stage == "变更":
                    navigated = navigate_account_billing_from_console(page, urls["console"], CLICK_PATTERNS[stage], stage)
                    log_stage(stage, f"console account-link navigation={navigated}; url={page.url}")
                    if not navigated:
                        page.goto(product_console_url, wait_until="domcontentloaded", timeout=60000)
                        wait_for_stage_ready(page, stage)
                        dismiss_blocking_overlays(page)
                        clicked = click_cta_with_fallback(page, CLICK_PATTERNS[stage])
                        dismiss_blocking_overlays(page)
                        log_stage(stage, f"product-console fallback clicked={clicked}; url={page.url}")
                elif stage == "退订":
                    navigated = navigate_account_billing_from_console(page, urls["console"], CLICK_PATTERNS[stage], stage)
                    log_stage(stage, f"console account-link navigation={navigated}; url={page.url}")
                    if not navigated:
                        page.goto(product_console_url, wait_until="domcontentloaded", timeout=60000)
                        wait_for_stage_ready(page, stage)
                        dismiss_blocking_overlays(page)
                        clicked = click_cta_with_fallback(page, CLICK_PATTERNS[stage])
                        dismiss_blocking_overlays(page)
                        log_stage(stage, f"product-console fallback clicked={clicked}; url={page.url}")
                else:
                    click_cta_with_fallback(page, CLICK_PATTERNS.get(stage, []))
                wait_for_stage_ready(page, stage)
                dismiss_blocking_overlays(page)
                log_stage(stage, f"ready for screenshot; url={page.url}")
                record = extract_page(page, root, stage, len(pages) + 1, screenshot_dir)
                ok, reason = stage_goal_reached(record, target_url, product_keywords, product_profile)
                if not ok:
                    record["entry_not_found"] = True
                    record["stage_goal_not_reached"] = True
                    record["blocked_reason"] = reason
                    log_stage(stage, f"not reached: {reason}")
                else:
                    log_stage(stage, "covered")
                pages.append(record)
            except Exception as exc:
                log_stage(stage, f"error: {exc}")
                missing.append(stage)
                pages.append({"stage": stage, "entry_not_found": True, "error": str(exc)})
        context.close()
        if browser:
            browser.close()

    covered = [p["stage"] for p in pages if not p.get("entry_not_found") and not p.get("login_required")]
    result = {
        "input_url": target_url,
        "original_input_url": args.url,
        "product_slug": product_slug,
        "crawl_time": datetime.now(timezone.utc).isoformat(),
        "stages_covered": covered,
        "stages_missing": [s for s in STAGES if s not in covered],
        "auth_state_path": rel(root, auth_state),
        "auth_state_loaded": has_huawei_cookies(auth_state),
        "target_product_keywords": product_keywords,
        "pages": pages,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
