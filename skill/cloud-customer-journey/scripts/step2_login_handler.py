#!/usr/bin/env python3
"""Open Huawei Cloud in a headed browser and save login state."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright


SITE_URLS = {
    "intl": {
        "www": "https://www.huaweicloud.com/intl/en-us/",
        "console": "https://console-intl.huaweicloud.com/?locale=en-us",
        "account": "https://account-intl.huaweicloud.com/usercenter/?locale=en-us#/userindex/allview",
        "verify": [],
        "login": "https://auth.huaweicloud.com/authui/login.html?locale=en-us&service={service}",
    },
    "cn": {
        "www": "https://www.huaweicloud.com/",
        "console": "https://console.huaweicloud.com/console/?region=cn-east-3#/home",
        "account": "https://console.huaweicloud.com/console/?region=cn-east-3#/home",
        "verify": [],
        "login": "https://auth.huaweicloud.com/authui/login.html#/login",
    },
}


def login_url(site: str, service_url: str) -> str:
    template = SITE_URLS[site]["login"]
    if "{service}" not in template:
        return template
    return template.format(service=urllib.parse.quote(service_url, safe=""))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def huawei_cookies_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in state.get("cookies", []) if "huaweicloud.com" in c.get("domain", "")]


def cookie_file_has_huawei_cookies(path: Path) -> bool:
    return bool(huawei_cookies_from_state(load_json(path)))


def is_login_page(page: Page) -> bool:
    url = page.url.lower()
    if "auth.huaweicloud.com" in url and ("login.html" in url or "authui/login" in url or "/login" in url):
        return True
    try:
        text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return False
    login_markers = ["welcome to huawei cloud", "password login", "iam user", "register"]
    cn_login_markers = ["欢迎使用华为云", "密码登录", "iam用户", "去注册"]
    return (
        "auth.huaweicloud.com" in url
        or all(marker in text for marker in login_markers[:2])
        or all(marker.lower() in text for marker in cn_login_markers[:2])
    )


def is_probably_logged_in(page) -> bool:
    try:
        url = page.url.lower()
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return False
    if "auth.huaweicloud.com" in url and "login" in url:
        return False
    logged_out_markers = ["sign in", "log in", "login", "register", "sign up"]
    logged_in_markers = ["log out", "logout", "my account", "billing & costs", "console"]
    if any(marker in text for marker in logged_in_markers) and not ("sign in" in text and "sign up" in text):
        return True
    return not any(marker in text for marker in logged_out_markers)


def install_anti_detection(context: BrowserContext, anti_detection: Path | None) -> None:
    if anti_detection and anti_detection.exists():
        context.add_init_script(path=str(anti_detection))
    else:
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")


def install_risk_interception(context: BrowserContext) -> None:
    def handle(route):
        url = route.request.url.lower()
        if "accountguard.js" in url:
            print(f"Blocked risk script: {route.request.url}")
            route.abort()
            return
        route.continue_()

    context.route("**/*", handle)


def goto_best_effort(page: Page, url: str, wait_ms: int = 3000) -> bool:
    try:
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(wait_ms)
        return True
    except Exception as exc:
        print(f"Warning: failed to open {url}: {exc}")
        return False


def warmup_cookies(page: Page, urls: dict[str, Any]) -> None:
    print("Warming up Huawei Cloud cookies on www, console, and account URLs.")
    original_url = page.url
    for url in [urls["www"], urls["console"], urls["account"], *urls.get("verify", [])]:
        goto_best_effort(page, url, wait_ms=4000)
    if original_url and not original_url.startswith("about:"):
        goto_best_effort(page, original_url, wait_ms=1000)


def page_has_visible_login_prompt(page: Page) -> bool:
    url = page.url.lower()
    if "auth.huaweicloud.com" in url and ("login" in url or "authui" in url):
        return True
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return False
    login_groups = [
        ("welcome to huawei cloud", "password login"),
        ("欢迎使用华为云", "密码登录"),
        ("iam用户", "密码登录"),
    ]
    return any(all(marker.lower() in text for marker in group) for group in login_groups)


def is_authenticated_console(page: Page) -> bool:
    url = page.url.lower()
    console_hosts = ("console.huaweicloud.com", "console-intl.huaweicloud.com")
    if not any(host in url for host in console_hosts):
        return False
    if "auth.huaweicloud.com" in url or "login" in url:
        return False
    if page_has_visible_login_prompt(page):
        return False
    try:
        text = page.locator("body").inner_text(timeout=5000).strip()
    except Exception:
        text = ""
    return bool(text)


def validate_console_target(page: Page, url: str) -> bool:
    goto_best_effort(page, url, wait_ms=7000)
    if is_login_page(page) or page_has_visible_login_prompt(page):
        print(f"Cookie validation failed: redirected to login page from {url}: {page.url}")
        return False
    try:
        text = page.locator("body").inner_text(timeout=5000).strip()
    except Exception:
        text = ""
    if not text:
        print(f"Cookie validation failed: blank page from {url}: {page.url}")
        return False
    print(f"Cookie validation target passed: {url} -> {page.url}")
    return True


def validate_cookie_state(p, auth_state: Path, anti_detection: Path | None, urls: dict[str, Any]) -> bool:
    if not auth_state.exists():
        print(f"Cookie validation: missing file: {auth_state}")
        return False
    if auth_state.stat().st_size == 0:
        print(f"Cookie validation: empty file: {auth_state}")
        return False
    if not cookie_file_has_huawei_cookies(auth_state):
        print(f"Cookie validation: no huaweicloud.com cookies in {auth_state}")
        return False

    print(f"Cookie validation: loading {auth_state}")
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    context = browser.new_context(storage_state=str(auth_state), viewport={"width": 1440, "height": 1000}, locale="en-US")
    install_anti_detection(context, anti_detection)
    page = context.new_page()
    try:
        if not validate_console_target(page, urls["www"]):
            return False
        if not validate_console_target(page, urls["console"]):
            return False
        for url in urls.get("verify", []):
            if not validate_console_target(page, url):
                return False
        print("Cookie validation passed: www and console URLs are accessible.")
        return True
    finally:
        context.close()
        browser.close()


def fill_first(page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count():
                target = locator.first
                if target.is_visible(timeout=1500):
                    target.fill(value, timeout=5000)
                    return True
        except Exception:
            continue
    return False


def click_first(page, selectors: list[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count():
                target = locator.first
                if target.is_visible(timeout=1500):
                    target.click(timeout=5000)
                    return True
        except Exception:
            continue
    return False


def attempt_password_login(page, site: str, service_url: str, username: str, password: str) -> bool:
    page.goto(login_url(site, service_url), wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    user_ok = fill_first(
        page,
        [
            'input[name="userAccount"]',
            'input[name="account"]',
            'input[name="username"]',
            'input[id*="user"]',
            'input[id*="account"]',
            'input[type="text"]',
            'input:not([type])',
        ],
        username,
    )
    pass_ok = fill_first(
        page,
        [
            'input[name="password"]',
            'input[id*="password"]',
            'input[type="password"]',
        ],
        password,
    )
    if not (user_ok and pass_ok):
        return False

    clicked = click_first(
        page,
        [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Log In")',
            'button:has-text("Sign In")',
            'button:has-text("Login")',
            'button:has-text("登录")',
            'a:has-text("Log In")',
            'a:has-text("Sign In")',
        ],
    )
    if not clicked:
        page.keyboard.press("Enter")
    page.wait_for_timeout(8000)
    return True


def save_state(context: BrowserContext, output: Path, profile_dir: Path, page: Page) -> list[dict[str, Any]]:
    state = context.storage_state(path=str(output))
    cookies = state.get("cookies", [])
    huawei = huawei_cookies_from_state(state)
    summary = {
        "saved_to": str(output),
        "profile_dir": str(profile_dir),
        "current_url": page.url,
        "total_cookies": len(cookies),
        "huaweicloud_cookies": len(huawei),
        "has_huaweicloud_cookie": bool(huawei),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return huawei


def wait_for_auth_ready(
    context: BrowserContext,
    page: Page,
    urls: dict[str, Any],
    wait_seconds: int,
    output: Path | None = None,
    profile_dir: Path | None = None,
    refresh_seconds: int = 0,
) -> bool:
    deadline = time.time() + wait_seconds
    next_save = time.time() + max(1, refresh_seconds) if refresh_seconds > 0 else float("inf")
    print(
        "Waiting for login, MFA, and risk verification to finish. "
        "This step completes when the opened tab reaches an authenticated Huawei Cloud console page."
    )
    while time.time() < deadline:
        if output and profile_dir and time.time() >= next_save:
            save_state(context, output, profile_dir, page)
            next_save = time.time() + max(1, refresh_seconds)
        if is_authenticated_console(page):
            print(f"Login verified by authenticated console page. Current page: {page.url}")
            return True
        if is_login_page(page) or page_has_visible_login_prompt(page):
            time.sleep(2)
            continue

        print("Login not fully verified yet. Navigate the opened browser to the Huawei Cloud console after completing CAPTCHA, MFA, SMS/email code, or risk verification.")
        time.sleep(5)
    return False


def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://www.huaweicloud.com/intl/en-us/")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--output", default="../../output/web/_runtime/auth_cookie.json")
    parser.add_argument("--profile-dir", default="../../output/web/_runtime/huaweicloud_login_profile")
    parser.add_argument("--wait-seconds", type=int, default=180)
    parser.add_argument("--username", default=os.environ.get("HUAWEICLOUD_USERNAME"))
    parser.add_argument("--password-env", default="HUAWEICLOUD_PASSWORD")
    parser.add_argument("--force-login", action="store_true")
    parser.add_argument("--headed", action="store_true", default=True)
    parser.add_argument("--anti-detection", default="skill/cloud-customer-journey/scripts/anti_detection.js")
    parser.add_argument("--site", choices=sorted(SITE_URLS), default="intl")
    parser.add_argument("--block-risk-script", action="store_true", help="Block accountguard.js. Off by default because it can blank the login page.")
    parser.add_argument("--skip-cookie-validation", action="store_true")
    parser.add_argument("--keep-open", action="store_true", help="Keep the login browser open after saving the output storage state.")
    parser.add_argument(
        "--refresh-seconds",
        type=int,
        default=0,
        help="Optional storage-state refresh interval when --keep-open is set. Defaults to 0 to avoid background browser activity.",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    profile_dir = Path(args.profile_dir)
    if not profile_dir.is_absolute():
        profile_dir = root / profile_dir
    anti_detection = Path(args.anti_detection) if args.anti_detection else None
    if anti_detection and not anti_detection.is_absolute():
        anti_detection = root / anti_detection

    output.parent.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    urls = SITE_URLS[args.site]

    with sync_playwright() as p:
        if not args.force_login and not args.skip_cookie_validation and validate_cookie_state(p, output, anti_detection, urls):
            print("Existing cookie state is valid; no manual login needed.")
            return 0

        context = p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
            args=["--disable-blink-features=AutomationControlled"],
        )
        install_anti_detection(context, anti_detection)
        if args.block_risk_script:
            install_risk_interception(context)
        page = context.pages[0] if context.pages else context.new_page()
        page.on("console", lambda msg: print(f"Browser console [{msg.type}]: {msg.text[:300]}"))
        page.on("pageerror", lambda exc: print(f"Browser pageerror: {str(exc)[:500]}"))

        print("Cookie state is invalid or force login was requested.")
        print("Opening Huawei Cloud auth page for manual login.")
        goto_best_effort(page, login_url(args.site, urls["console"]), wait_ms=3000)

        if args.force_login or is_login_page(page) or not is_probably_logged_in(page):
            password = os.environ.get(args.password_env)
            if args.username and password:
                print("No existing login detected; attempting password login.")
                if not attempt_password_login(page, args.site, args.url, args.username, password):
                    print("Automatic form fill did not complete. Finish login manually in the opened browser.")
            else:
                print(f"No existing login detected. Set HUAWEICLOUD_USERNAME and {args.password_env} for automatic login.")
                print("Finish login manually in the opened browser before the wait ends.")
        print("If CAPTCHA, MFA, or risk verification appears, complete it manually before the wait ends.")
        try:
            logged_in = wait_for_auth_ready(
                context,
                page,
                urls,
                args.wait_seconds,
                output=output,
                profile_dir=profile_dir,
                refresh_seconds=args.refresh_seconds,
            )
        except KeyboardInterrupt:
            print("Interrupted during login wait; saving current browser state before exit.")
            save_state(context, output, profile_dir, page)
            raise
        if logged_in:
            warmup_cookies(page, urls)
        else:
            print("Warning: login page did not exit before the wait ended.")

        huawei_cookies = save_state(context, output, profile_dir, page)
        if args.keep_open:
            print(
                "Keeping login browser open. "
                "The persistent profile is locked while this process runs; run step3 without --use-login-profile "
                "so it imports ../../output/web/_runtime/auth_cookie.json. Press Ctrl+C to stop."
            )
            try:
                while True:
                    time.sleep(max(1, args.refresh_seconds) if args.refresh_seconds > 0 else 3600)
                    if args.refresh_seconds > 0:
                        huawei_cookies = save_state(context, output, profile_dir, page)
            except KeyboardInterrupt:
                print("Stopping login browser and saving final state.")
                huawei_cookies = save_state(context, output, profile_dir, page)
        context.close()

    if not huawei_cookies:
        print("Warning: no huaweicloud.com cookies were captured. The browser may not be logged in.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
