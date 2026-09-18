#!/usr/bin/env python3
"""Start the dashboard, click every page, and fail on any Streamlit exception or empty page.

Covers what unit tests cannot: the app actually rendering. A page bound to a stale frame, a
column renamed out from under a chart, or a division by zero on an empty filter all look fine to
`pytest` and break the moment someone opens the browser.

Deliberately cheap — it reads the DOM rather than screenshotting, so it can run on every change.
Screenshots are for judging appearance, not for catching exceptions.

Usage:
    smoke_app.py [--port 8599] [--keep]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AUDIT_DIR = Path(__file__).resolve().parent.parent
APP = AUDIT_DIR / "app.py"

PAGES = [
    "Reduction funnel", "Analyst workload", "Deduplication", "Event vs Non-Event",
    "Impactful vs Not", "Event type & priority", "Review queues", "Rules & evidence",
    "Methodology",
]

ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "streamlit.errors",
    "StreamlitAPIException",
    "KeyError",
    "ValueError:",
    "AttributeError",
    "ZeroDivisionError",
)


def wait_for(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.6)
    return False


def click_every_page(base: str) -> list[str]:
    """Drive a real browser through all nine pages.

    Streamlit renders over a websocket, so fetching the HTML shell proves almost nothing — the
    page that blows up on a missing column looks identical to one that works until the script
    actually runs. Clicking each radio option is the only way to exercise them.
    """
    from playwright.sync_api import sync_playwright

    # The environment ships a pinned Chromium that may not match the pip-installed Playwright's
    # expected build, so point at the real binary rather than letting it download one.
    candidates = sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
    launch_kwargs = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if candidates:
        launch_kwargs["executable_path"] = str(candidates[-1])

    problems: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.goto(base, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(2500)

        for label in PAGES:
            try:
                page.get_by_text(label, exact=False).first.click(timeout=15_000)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{label}: could not click ({type(exc).__name__})")
                continue
            page.wait_for_timeout(1800)
            body = page.inner_text("body")

            if "Traceback" in body or "StreamlitAPIException" in body:
                snippet = body[body.find("Traceback"):][:400] if "Traceback" in body else body[:400]
                problems.append(f"{label}: exception on page — {snippet}")
            # An empty page is a silent failure: no exception, nothing rendered.
            if len(body.strip()) < 400:
                problems.append(f"{label}: rendered almost nothing ({len(body)} chars)")
            headings = page.locator("h1").count()
            if headings == 0:
                problems.append(f"{label}: no heading rendered")
        browser.close()
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8599)
    ap.add_argument("--keep", action="store_true", help="leave the server running")
    args = ap.parse_args()

    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(APP),
         "--server.port", str(args.port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://localhost:{args.port}"
    try:
        if not wait_for(f"{base}/_stcore/health"):
            out = proc.stdout.read() if proc.stdout else ""
            print("FAIL: server never became healthy\n" + out[-3000:])
            return 1
        print(f"server up on {base}")

        # Streamlit renders over a websocket, so the HTML shell alone proves little. What the
        # server log shows is every exception raised while rendering any page — which is the
        # failure this guards against.
        with urllib.request.urlopen(base, timeout=10) as r:
            shell = r.read().decode("utf-8", "replace")
        if "<title>" not in shell:
            print("FAIL: no HTML shell served")
            return 1

        failures = click_every_page(base)
        time.sleep(1)
        proc.terminate()
        try:
            log = proc.communicate(timeout=15)[0] or ""
        except subprocess.TimeoutExpired:
            proc.kill()
            log = proc.communicate()[0] or ""

        hits = [m for m in ERROR_MARKERS if m in log]
        if hits:
            print(f"FAIL: server log contains {hits}")
            print(log[-4000:])
            return 1
        if failures:
            for f in failures:
                print(f"FAIL: {f}")
            return 1

        print(f"OK: all {len(PAGES)} pages rendered with no exception and no empty page")
        return 0
    finally:
        if proc.poll() is None:
            if args.keep:
                print(f"left running on {base} (pid {proc.pid})")
            else:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
