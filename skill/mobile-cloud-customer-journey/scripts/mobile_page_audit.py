#!/usr/bin/env python3
"""Mobile UX audit for a single public page."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


TAP_CANDIDATE_JS = r"""() => {
  const riskyText = /删除|退订|支付|提交订单|确认订单|购买|立即购买|开通|释放|注销|Delete|Remove|Pay|Submit|Checkout/i;
  const usefulText = /查看详情|详情|立即了解|了解更多|查看更多|更多|免费试用|开始体验|开始使用|查看全部|Detail|Details|Learn more|More|Try|Start/i;
  const usefulClass = /btn|button|link|detail|more|card|cta/i;
  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' &&
      s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
  };
  const textOf = el => (el.innerText || el.textContent || el.getAttribute('aria-label') ||
    el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 140);
  const pathOf = el => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 6) {
      let part = node.tagName.toLowerCase();
      if (node.id) part += `#${node.id}`;
      const cls = String(node.className || '').trim().split(/\s+/).filter(Boolean).slice(0, 3);
      if (cls.length) part += '.' + cls.join('.');
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const all = Array.from(document.querySelectorAll([
    'a[href]', 'button', '[role=button]', '[onclick]',
    '[class*=btn]', '[class*=button]', '[class*=link]',
    '[class*=detail]', '[class*=more]', '[class*=card]'
  ].join(','))).filter(visible);
  const seen = new Set();
  const candidates = [];
  for (const el of all) {
    const text = textOf(el);
    const label = `${text} ${el.getAttribute('href') || ''} ${el.className || ''}`;
    if (riskyText.test(label)) continue;
    if (!usefulText.test(label) && !usefulClass.test(String(el.className || ''))) continue;
    const r = el.getBoundingClientRect();
    const top = Math.round(r.top + scrollY);
    const key = `${text}|${Math.round(r.x)}|${top}|${Math.round(r.width)}|${Math.round(r.height)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const href = el.href || el.getAttribute('href') || '';
    const importance = (usefulText.test(text) ? 50 : 0) +
      (/查看详情|详情|立即了解|查看更多|了解更多|Detail|More|Learn/i.test(text) ? 30 : 0) +
      (top < innerHeight * 2.8 ? 20 : 0) +
      (el.tagName.toLowerCase() === 'a' ? 8 : 0);
    candidates.push({
      text,
      href,
      tag: el.tagName.toLowerCase(),
      path: pathOf(el),
      className: String(el.className || '').slice(0, 160),
      top,
      left: Math.round(r.left + scrollX),
      width: Math.round(r.width),
      height: Math.round(r.height),
      importance
    });
  }
  return candidates
    .sort((a, b) => b.importance - a.importance || a.top - b.top)
    .slice(0, 18)
    .map((candidate, ordinal) => ({...candidate, ordinal}));
}"""


PREPARE_TAP_CANDIDATE_JS = r"""candidate => {
  const candidates = (%s)();
  const same = item => item.text === candidate.text && item.href === candidate.href &&
    item.path === candidate.path && Math.abs(item.top - candidate.top) < 12;
  const chosen = candidates.find(same) || candidates[candidate.ordinal] ||
    candidates.find(item => item.text === candidate.text && item.href === candidate.href);
  if (!chosen) return {found: false, reason: 'candidate-not-found'};

  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' &&
      s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
  };
  const textOf = el => (el.innerText || el.textContent || el.getAttribute('aria-label') ||
    el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 140);
  const pathOf = el => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 6) {
      let part = node.tagName.toLowerCase();
      if (node.id) part += `#${node.id}`;
      const cls = String(node.className || '').trim().split(/\s+/).filter(Boolean).slice(0, 3);
      if (cls.length) part += '.' + cls.join('.');
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const nodes = Array.from(document.querySelectorAll([
    'a[href]', 'button', '[role=button]', '[onclick]',
    '[class*=btn]', '[class*=button]', '[class*=link]',
    '[class*=detail]', '[class*=more]', '[class*=card]'
  ].join(','))).filter(visible);
  let target = nodes.find(el => {
    const r = el.getBoundingClientRect();
    return textOf(el) === chosen.text &&
      (el.href || el.getAttribute('href') || '') === chosen.href &&
      Math.abs((r.top + scrollY) - chosen.top) < 12;
  });
  if (!target) {
    target = nodes.find(el => textOf(el) === chosen.text &&
      (el.href || el.getAttribute('href') || '') === chosen.href);
  }
  if (!target) return {found: false, reason: 'element-not-found-after-reload', chosen};

  target.scrollIntoView({block: 'center', inline: 'center'});
  const r = target.getBoundingClientRect();
  const cx = Math.min(Math.max(r.left + r.width / 2, 4), innerWidth - 4);
  const cy = Math.min(Math.max(r.top + r.height / 2, 4), innerHeight - 4);
  const hit = document.elementFromPoint(cx, cy);
  let hitInsideTarget = false;
  if (hit) hitInsideTarget = hit === target || target.contains(hit) || hit.contains(target);
  window.__mobileAuditMutations = 0;
  if (window.__mobileAuditObserver) window.__mobileAuditObserver.disconnect();
  window.__mobileAuditObserver = new MutationObserver(records => {
    window.__mobileAuditMutations += records.length;
  });
  window.__mobileAuditObserver.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    characterData: true
  });
  const overlayCount = Array.from(document.querySelectorAll('[role=dialog],[aria-modal=true],[class*=modal],[class*=Modal],[class*=popup],[class*=Popup],[class*=drawer],[class*=Drawer],[class*=toast],[class*=Toast]')).filter(visible).length;
  return {
    found: true,
    x: Math.round(cx),
    y: Math.round(cy),
    target: {...chosen, path: pathOf(target)},
    hit: hit ? {tag: hit.tagName.toLowerCase(), text: textOf(hit), path: pathOf(hit), className: String(hit.className || '').slice(0, 160)} : null,
    hitInsideTarget,
    before: {
      url: location.href,
      scrollY: Math.round(scrollY),
      bodyLength: (document.body.innerText || '').length,
      overlayCount
    }
  };
}""" % TAP_CANDIDATE_JS


AFTER_TAP_JS = r"""before => {
  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' &&
      s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
  };
  const overlayCount = Array.from(document.querySelectorAll('[role=dialog],[aria-modal=true],[class*=modal],[class*=Modal],[class*=popup],[class*=Popup],[class*=drawer],[class*=Drawer],[class*=toast],[class*=Toast]')).filter(visible).length;
  const bodyLength = (document.body.innerText || '').length;
  const mutations = window.__mobileAuditMutations || 0;
  if (window.__mobileAuditObserver) window.__mobileAuditObserver.disconnect();
  return {
    url: location.href,
    scrollY: Math.round(scrollY),
    bodyLength,
    overlayCount,
    mutations,
    urlChanged: location.href !== before.url,
    scrollChanged: Math.abs(Math.round(scrollY) - before.scrollY),
    bodyLengthDelta: Math.abs(bodyLength - before.bodyLength),
    overlayDelta: overlayCount - before.overlayCount
  };
}"""


def safe_name(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_")[:80] or "page"


def default_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def wait_and_scroll(page: Page) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(2500)
    height = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
    viewport = page.viewport_size or {"height": 844}
    step = max(500, int(viewport["height"] * 0.8))
    for y in range(0, min(int(height), 7000), step):
        page.evaluate("(y) => window.scrollTo(0, y)", y)
        page.wait_for_timeout(500)
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(1200)


def audit_dom(page: Page) -> dict[str, Any]:
    return page.evaluate(
        r"""() => {
          const vw = document.documentElement.clientWidth;
          const vh = window.innerHeight;
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' &&
              s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
          };
          const textOf = el => (el.innerText || el.textContent || el.getAttribute('aria-label') ||
            el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 160);
          const pathOf = el => {
            const parts = [];
            let node = el;
            while (node && node.nodeType === 1 && parts.length < 5) {
              let part = node.tagName.toLowerCase();
              if (node.id) part += `#${node.id}`;
              const cls = String(node.className || '').trim().split(/\s+/).filter(Boolean).slice(0, 3);
              if (cls.length) part += '.' + cls.join('.');
              parts.unshift(part);
              node = node.parentElement;
            }
            return parts.join(' > ');
          };
          const isGestureContainer = el => {
            let node = el;
            while (node && node.nodeType === 1) {
              const name = `${node.className || ''} ${node.id || ''}`.toLowerCase();
              const s = getComputedStyle(node);
              if (/swiper|carousel|slick|slider|scroll|tab|marquee/.test(name)) return true;
              if (['auto', 'scroll'].includes(s.overflowX)) return true;
              node = node.parentElement;
            }
            return false;
          };
          const px = value => {
            const m = String(value || '').match(/(-?\d+(?:\.\d+)?)px/);
            return m ? Number(m[1]) : null;
          };
          const nodes = Array.from(document.querySelectorAll('body *')).filter(visible);
          const overflowElements = nodes.map(el => {
            const r = el.getBoundingClientRect();
            return {el, r};
          }).filter(x => !isGestureContainer(x.el) && (x.r.right > vw + 1 || x.r.left < -1))
            .slice(0, 80).map(x => ({
              path: pathOf(x.el), text: textOf(x.el), left: Math.round(x.r.left),
              right: Math.round(x.r.right), width: Math.round(x.r.width),
              className: String(x.el.className || '').slice(0, 140),
              overflowX: getComputedStyle(x.el).overflowX
            }));
          const wideFixed = nodes.filter(el => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            const declared = [s.width, s.minWidth, el.style.width, el.style.minWidth].join(' ');
            return r.width > vw + 1 && /\d{3,}px/.test(declared);
          }).slice(0, 50).map(el => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return {path: pathOf(el), text: textOf(el), width: Math.round(r.width),
              cssWidth: s.width, minWidth: s.minWidth, inline: el.getAttribute('style') || ''};
          });
          const textRisks = nodes.filter(el => {
            const text = textOf(el);
            if (!text || text.length < 8) return false;
            const s = getComputedStyle(el);
            const longToken = /[A-Za-z0-9_:/.-]{24,}/.test(text);
            const horizontal = el.scrollWidth > el.clientWidth + 2;
            const vertical = el.scrollHeight > el.clientHeight + 2 && px(s.height) !== null;
            const weakWrap = !/(break-word|anywhere|break-all)/.test(`${s.wordBreak} ${s.overflowWrap}`);
            return (longToken && weakWrap) || horizontal || vertical;
          }).slice(0, 80).map(el => {
            const s = getComputedStyle(el);
            return {path: pathOf(el), text: textOf(el), clientWidth: el.clientWidth,
              scrollWidth: el.scrollWidth, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight,
              wordBreak: s.wordBreak, overflowWrap: s.overflowWrap, height: s.height};
          });
          const fixedBottom = nodes.filter(el => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return ['fixed', 'sticky'].includes(s.position) && r.bottom >= vh - 4 && r.top < vh;
          }).slice(0, 40).map(el => {
            const s = getComputedStyle(el);
            const cssText = [el.getAttribute('style') || '', ...Array.from(document.styleSheets).flatMap(sheet => {
              try { return Array.from(sheet.cssRules || []); } catch (e) { return []; }
            }).filter(rule => rule.selectorText && el.matches(rule.selectorText)).map(rule => rule.cssText)].join('\n');
            return {path: pathOf(el), text: textOf(el), position: s.position,
              height: Math.round(el.getBoundingClientRect().height),
              bottom: s.bottom, paddingBottom: s.paddingBottom,
              hasSafeAreaInset: /safe-area-inset-bottom/.test(cssText)};
          });
          const clickables = nodes.filter(el => {
            const tag = el.tagName.toLowerCase();
            return tag === 'a' || tag === 'button' || el.getAttribute('role') === 'button' ||
              el.onclick || el.getAttribute('onclick') || el.tabIndex >= 0;
          }).map((el, index) => {
            const r = el.getBoundingClientRect();
            return {index, el, path: pathOf(el), text: textOf(el), tag: el.tagName.toLowerCase(),
              x: r.x, y: r.y, width: r.width, height: r.height, area: r.width * r.height};
          });
          const smallTargets = clickables.filter(c => c.width < 44 || c.height < 44)
            .slice(0, 120).map(({el, ...c}) => ({...c, x: Math.round(c.x), y: Math.round(c.y),
              width: Math.round(c.width), height: Math.round(c.height)}));
          const distance = (a, b) => {
            const ax2 = a.x + a.width, ay2 = a.y + a.height;
            const bx2 = b.x + b.width, by2 = b.y + b.height;
            const dx = Math.max(0, Math.max(b.x - ax2, a.x - bx2));
            const dy = Math.max(0, Math.max(b.y - ay2, a.y - by2));
            return Math.sqrt(dx * dx + dy * dy);
          };
          const closePairs = [];
          for (let i = 0; i < clickables.length && closePairs.length < 80; i++) {
            for (let j = i + 1; j < clickables.length && closePairs.length < 80; j++) {
              if (Math.abs(clickables[i].y - clickables[j].y) > 100 &&
                  Math.abs((clickables[i].y + clickables[i].height) - clickables[j].y) > 16) continue;
              const d = distance(clickables[i], clickables[j]);
              if (d > 0 && d < 8) {
                closePairs.push({
                  distance: Math.round(d * 10) / 10,
                  a: {path: clickables[i].path, text: clickables[i].text, width: Math.round(clickables[i].width), height: Math.round(clickables[i].height)},
                  b: {path: clickables[j].path, text: clickables[j].text, width: Math.round(clickables[j].width), height: Math.round(clickables[j].height)}
                });
              }
            }
          }
          const forms = Array.from(document.querySelectorAll('input, textarea, select')).filter(visible).map(el => {
            const r = el.getBoundingClientRect();
            return {path: pathOf(el), tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '',
              placeholder: el.getAttribute('placeholder') || '', inputmode: el.getAttribute('inputmode') || '',
              autocomplete: el.getAttribute('autocomplete') || '', y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height),
              nearBottom: r.bottom > vh * 0.72};
          });
          const images = Array.from(document.images).filter(visible).map(img => {
            const r = img.getBoundingClientRect();
            const url = img.currentSrc || img.src || '';
            return {path: pathOf(img), alt: img.alt || '', src: url.slice(0, 180),
              ext: (url.match(/\.(avif|webp|svg|png|jpe?g)(?:[?#]|$)/i) || [,'unknown'])[1],
              loading: img.getAttribute('loading') || '', width: Math.round(r.width), height: Math.round(r.height),
              top: Math.round(r.top + scrollY), belowFold: r.top + scrollY > vh};
          });
          const cssRules = [];
          for (const sheet of Array.from(document.styleSheets)) {
            let rules = [];
            try { rules = Array.from(sheet.cssRules || []); } catch (e) { continue; }
            for (const rule of rules) {
              const media = rule.conditionText || '';
              if (rule.selectorText) {
                const css = rule.cssText;
                if (/:hover/.test(rule.selectorText)) cssRules.push({type: 'hover', selector: rule.selectorText, media, css: css.slice(0, 500)});
                if (/(^|[^\w-])(width|min-width)\s*:\s*(?:[7-9]\d{2}|\d{4,})px/.test(css) && !/max-width\s*:\s*(?:768|767|640|600|480|430|414|390|375)px/.test(media)) {
                  cssRules.push({type: 'wide-width', selector: rule.selectorText, media, css: css.slice(0, 500)});
                }
              } else if (rule.cssRules) {
                const nestedMedia = rule.conditionText || '';
                for (const nested of Array.from(rule.cssRules || [])) {
                  const css = nested.cssText || '';
                  if (nested.selectorText && /:hover/.test(nested.selectorText)) cssRules.push({type: 'hover', selector: nested.selectorText, media: nestedMedia, css: css.slice(0, 500)});
                }
              }
              if (cssRules.length > 220) break;
            }
            if (cssRules.length > 220) break;
          }
          return {
            url: location.href,
            title: document.title,
            viewport: {width: vw, height: vh, devicePixelRatio},
            scroll: {
              documentElementScrollWidth: document.documentElement.scrollWidth,
              bodyScrollWidth: document.body.scrollWidth,
              clientWidth: vw,
              scrollHeight: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
            },
            overflowElements,
            wideFixed,
            textRisks,
            fixedBottom,
            clickableSummary: {count: clickables.length},
            smallTargets,
            closePairs,
            forms,
            images,
            imageIssues: images.filter(img => img.belowFold && !/^lazy$/i.test(img.loading)).slice(0, 120),
            cssRules
          };
        }"""
    )


def inspect_after_scroll(page: Page) -> dict[str, Any]:
    page.evaluate("() => window.scrollTo(0, Math.round(window.innerHeight * 1.6))")
    page.wait_for_timeout(800)
    return page.evaluate(
        r"""() => {
          const vh = innerHeight;
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
          };
          const textOf = el => (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 120);
          return Array.from(document.querySelectorAll('a,button,[role=button]')).filter(visible).filter(el => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            const text = textOf(el);
            return ['fixed', 'sticky'].includes(s.position) || (r.bottom > vh - 180 && /购买|咨询|联系|试用|开通|立即|免费|控制台|Buy|Contact|Try/i.test(text));
          }).slice(0, 40).map(el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return {text: textOf(el), position: s.position, x: Math.round(r.x), y: Math.round(r.y),
              width: Math.round(r.width), height: Math.round(r.height)};
          });
        }"""
    )


def inspect_menu(page: Page) -> dict[str, Any]:
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(500)
    result: dict[str, Any] = {"attempted": False, "opened": False, "candidates": []}
    candidates = page.evaluate(
        r"""() => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const textOf = el => (el.innerText || el.textContent || el.getAttribute('aria-label') ||
            el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
          return Array.from(document.querySelectorAll('button,a,[role=button],.menu,.hamburger,[class*=menu],[class*=nav]'))
            .filter(visible).map((el, index) => {
              const r = el.getBoundingClientRect();
              return {index, text: textOf(el), className: String(el.className || '').slice(0, 100),
                width: Math.round(r.width), height: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y)};
            }).filter(c => /menu|nav|hamburger|菜单|导航|☰|更多|展开|全部/i.test(`${c.text} ${c.className}`)).slice(0, 20);
        }"""
    )
    result["candidates"] = candidates
    if not candidates:
        return result
    result["attempted"] = True
    preferred = next(
        (
            c
            for c in candidates
            if c["width"] <= 80
            and c["height"] <= 80
            and not re.search(r"search|搜索", f"{c['text']} {c['className']}", re.I)
            and re.search(r"hamburger|menu|菜单|☰|更多|展开", f"{c['text']} {c['className']}", re.I)
        ),
        candidates[0],
    )
    target = {
        "text": preferred["text"],
        "className": preferred["className"],
        "x": preferred["x"],
        "y": preferred["y"],
        "width": preferred["width"],
        "height": preferred["height"],
    }
    result["clicked_candidate"] = preferred
    clicked = page.evaluate(
        r"""target => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const nodes = Array.from(document.querySelectorAll('button,a,[role=button],.menu,.hamburger,[class*=menu],[class*=nav]')).filter(visible);
          const sameRect = el => {
            const r = el.getBoundingClientRect();
            return Math.abs(r.x - target.x) <= 2 && Math.abs(r.y - target.y) <= 2 &&
              Math.abs(r.width - target.width) <= 2 && Math.abs(r.height - target.height) <= 2;
          };
          const exact = nodes.find(sameRect);
          if (exact) {
            exact.click();
            return true;
          }
          const preferred = nodes.find(el => {
            const r = el.getBoundingClientRect();
            const label = `${el.innerText || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''} ${el.className || ''}`;
            return r.width <= 80 && r.height <= 80 && !/search|搜索/i.test(label) && /hamburger|menu|菜单|☰|更多|展开/i.test(label);
          });
          if (!preferred) return false;
          preferred.click();
          return true;
        }""",
        target,
    )
    if not clicked:
        return result
    page.wait_for_timeout(1200)
    result.update(
        page.evaluate(
            r"""() => {
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0;
              };
              const textOf = el => (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 120);
              const overlays = Array.from(document.querySelectorAll('[role=dialog],[aria-modal=true],[class*=drawer],[class*=Drawer],[class*=menu],[class*=Menu],[class*=nav],[class*=Nav]'))
                .filter(visible).map(el => {
                  const r = el.getBoundingClientRect();
                  const s = getComputedStyle(el);
                  return {text: textOf(el), className: String(el.className || '').slice(0, 120),
                    position: s.position, zIndex: s.zIndex, width: Math.round(r.width), height: Math.round(r.height),
                    x: Math.round(r.x), y: Math.round(r.y)};
                }).filter(o => o.width > innerWidth * 0.5 || o.height > innerHeight * 0.25).slice(0, 20);
              const closeTargets = Array.from(document.querySelectorAll('button,a,[role=button],i,span,svg')).filter(visible).filter(el => /close|关闭|收起|×|x/i.test(`${textOf(el)} ${el.getAttribute('class') || ''} ${el.getAttribute('aria-label') || ''}`)).map(el => {
                const r = el.getBoundingClientRect();
                return {text: textOf(el), width: Math.round(r.width), height: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y)};
              }).slice(0, 20);
              return {opened: overlays.length > 0, bodyOverflow: getComputedStyle(document.body).overflow,
                htmlOverflow: getComputedStyle(document.documentElement).overflow, overlays, closeTargets};
            }"""
        )
    )
    return result


def wait_light(page: Page) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    page.wait_for_timeout(1800)


def collect_tap_candidates(page: Page) -> list[dict[str, Any]]:
    try:
        return list(page.evaluate(TAP_CANDIDATE_JS))
    except Exception as exc:
        return [{"collection_error": str(exc)}]


def classify_tap_result(candidate: dict[str, Any], prepared: dict[str, Any], after: dict[str, Any], popups: list[str], console_errors: list[str]) -> tuple[str, str | None]:
    if not prepared.get("found"):
        return "not-tested", prepared.get("reason") or "candidate not found"
    effective = (
        bool(popups)
        or bool(after.get("urlChanged"))
        or int(after.get("scrollChanged") or 0) > 80
        or int(after.get("overlayDelta") or 0) > 0
        or int(after.get("bodyLengthDelta") or 0) > 80
        or int(after.get("mutations") or 0) > 8
    )
    if effective:
        return "effective", None
    causes = []
    href = candidate.get("href") or ""
    if href and href not in {"#", "javascript:;", "javascript:void(0)", "javascript:void(0);"}:
        causes.append("href-present-but-no-navigation")
    if not prepared.get("hitInsideTarget"):
        causes.append("tap-center-hit-different-element")
    hit = prepared.get("hit") or {}
    if hit.get("tag") == "object" or "object" in str(hit.get("path", "")):
        causes.append("object-or-overlay-may-intercept-tap")
    if console_errors:
        causes.append("console-error-after-tap")
    if not causes:
        causes.append("no-visible-effect")
    return "no-visible-effect", ",".join(causes)


def audit_tap_actions(context, url: str, max_candidates: int = 12) -> dict[str, Any]:
    collector = context.new_page()
    collector.goto(url, wait_until="domcontentloaded", timeout=60000)
    wait_light(collector)
    candidates = collect_tap_candidates(collector)
    collector.close()
    if candidates and candidates[0].get("collection_error"):
        return {"enabled": True, "candidates": [], "results": [], "issues": [], "error": candidates[0]["collection_error"]}

    results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for candidate in candidates[:max_candidates]:
        page = context.new_page()
        console_errors: list[str] = []
        popups: list[str] = []

        def on_console(msg) -> None:
            if msg.type in {"error", "warning"}:
                console_errors.append(msg.text[:500])

        def on_popup(popup) -> None:
            try:
                popup.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            popups.append(popup.url)
            try:
                popup.close()
            except Exception:
                pass

        page.on("console", on_console)
        page.on("popup", on_popup)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            wait_light(page)
            prepared = page.evaluate(PREPARE_TAP_CANDIDATE_JS, candidate)
            if not prepared.get("found"):
                after = {}
                status, possible_cause = classify_tap_result(candidate, prepared, after, popups, console_errors)
            else:
                page.touchscreen.tap(prepared["x"], prepared["y"])
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                after = page.evaluate(AFTER_TAP_JS, prepared["before"])
                status, possible_cause = classify_tap_result(candidate, prepared, after, popups, console_errors)
        except Exception as exc:
            prepared = {"found": False, "reason": f"tap-test-exception: {exc}"}
            after = {}
            status = "not-tested"
            possible_cause = str(exc)
        finally:
            try:
                page.close()
            except Exception:
                pass

        result = {
            "text": candidate.get("text", ""),
            "tag": candidate.get("tag", ""),
            "href": candidate.get("href", ""),
            "path": candidate.get("path", ""),
            "rect": {
                "left": candidate.get("left"),
                "top": candidate.get("top"),
                "width": candidate.get("width"),
                "height": candidate.get("height"),
            },
            "status": status,
            "possibleCause": possible_cause,
            "hit": prepared.get("hit") if isinstance(prepared, dict) else None,
            "hitInsideTarget": prepared.get("hitInsideTarget") if isinstance(prepared, dict) else None,
            "beforeUrl": (prepared.get("before") or {}).get("url") if isinstance(prepared, dict) else None,
            "afterUrl": after.get("url") if isinstance(after, dict) else None,
            "popupUrls": popups,
            "consoleErrors": console_errors[:5],
            "after": after,
        }
        results.append(result)
        if status == "no-visible-effect":
            severity = "P1" if re.search(r"查看详情|详情|立即了解|查看更多|了解更多|Detail|More|Learn", result["text"], re.I) else "P2"
            issues.append({**result, "severity": severity})

    return {
        "enabled": True,
        "candidateCount": len(candidates),
        "testedCount": len(results),
        "issueCount": len(issues),
        "candidates": candidates,
        "results": results,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", default=None, help="Compatibility override. Writes JSON and screenshots into one directory.")
    parser.add_argument("--output-root", default="../../output/mobile")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    base = safe_name(args.url)
    if args.output_dir:
        out_dir = Path(args.output_dir)
        data_dir = out_dir
        screenshots_dir = out_dir
    else:
        output_root = Path(args.output_root)
        run_id = args.run_id or default_run_id()
        out_dir = output_root / base / run_id
        data_dir = out_dir
        screenshots_dir = out_dir / "screenshots"
    data_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    json_path = data_dir / ("_capture.json" if not args.output_dir else f"{base}.json")
    top_png = screenshots_dir / f"{base}_top.png"
    scroll_png = screenshots_dir / f"{base}_scroll.png"
    full_png = screenshots_dir / f"{base}_full.png"
    menu_png = screenshots_dir / f"{base}_menu.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        wait_and_scroll(page)
        page.screenshot(path=str(top_png), full_page=False)
        dom = audit_dom(page)
        tap_actions = audit_tap_actions(context, args.url)
        after_scroll = inspect_after_scroll(page)
        page.screenshot(path=str(scroll_png), full_page=False)
        menu = inspect_menu(page)
        if menu.get("attempted"):
            page.screenshot(path=str(menu_png), full_page=False)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(full_png), full_page=True)
        result = {
            "input_url": args.url,
            "audit_time": datetime.now(timezone.utc).isoformat(),
            "artifacts": {
                "top_screenshot": str(top_png),
                "scroll_screenshot": str(scroll_png),
                "full_screenshot": str(full_png),
                "menu_screenshot": str(menu_png) if menu.get("attempted") else None,
            },
            "dom": dom,
            "tapActionAudit": tap_actions,
            "tapActionIssues": tap_actions.get("issues", []),
            "after_scroll_ctas": after_scroll,
            "menu": menu,
        }
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"json": str(json_path), "artifacts": result["artifacts"]}, ensure_ascii=False, indent=2))
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
