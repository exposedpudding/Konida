"""Drives portal.konicaminolta.co.uk guest "Order consumables".

The guest login form is protected by reCAPTCHA. This tool does NOT bypass it:
it fills in the equipment number + postcode, then waits for a human to complete
any challenge in the visible browser window.

The login page is known. The order pages sit behind the captcha and have not yet
been inspected, so their selectors are in one place (SEL) and `--discover` dumps
HTML + screenshots to tune them on first run.
"""
import re
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

BASE = "https://portal.konicaminolta.co.uk"
ORDER_ENTRY = f"{BASE}/en-gb/guest-login/equipment-selector?action=2"

# Tune these after a --discover run against the real order pages.
SEL = {
    "equipment": "#EquipmentNumber",
    "postcode": "#ZipCode",
    "login_submit": "#guest-login-validate-form button[type=submit], #guest-login-validate-form button",
    "product_row": "tr, li, article, [class*=product], [class*=item]",
    "qty_input": "input[type=number], input[name*=quant i], input[id*=quant i]",
    "add_button": "button:has-text('Add'), input[type=submit][value*=Add i]",
    "checkout": "a:has-text('Checkout'), button:has-text('Checkout'), a:has-text('Basket'), button:has-text('Basket')",
    "submit_order": "button:has-text('Place order'), button:has-text('Submit order'), button:has-text('Confirm order')",
    "reference": "text=/(order|request)\\s*(no|number|ref)[^\\n]*/i",
}


class PortalError(RuntimeError):
    pass


def _dump(page: Page, name: str, enabled: bool):
    if not enabled:
        return
    d = Path("discovery")
    d.mkdir(exist_ok=True)
    (d / f"{name}.html").write_text(page.content())
    page.screenshot(path=str(d / f"{name}.png"), full_page=True)
    print(f"  [discover] saved discovery/{name}.(html|png)  url={page.url}")


def _accept_cookies(page: Page):
    try:
        page.get_by_role("button", name=re.compile("accept all", re.I)).click(timeout=4000)
    except PWTimeout:
        pass


def guest_login(page: Page, machine, discover=False, captcha_timeout_s=300):
    page.goto(ORDER_ENTRY)
    _accept_cookies(page)
    page.fill(SEL["equipment"], machine.equipment_number)
    page.fill(SEL["postcode"], machine.postcode)
    page.click(SEL["login_submit"])
    print(f"  Complete the captcha in the browser window if prompted "
          f"(waiting up to {captcha_timeout_s}s)...")
    try:
        page.wait_for_url(lambda u: "equipment-selector" not in u, timeout=captcha_timeout_s * 1000)
    except PWTimeout:
        _dump(page, "login_failed", discover)
        raise PortalError("Still on the login page: bad equipment number/postcode, or captcha not completed.")
    page.wait_for_load_state("networkidle")
    _dump(page, "after_login", discover)


def add_toner(page: Page, code: str, qty: int, discover=False):
    rows = page.locator(SEL["product_row"]).filter(has_text=code)
    if rows.count() == 0:
        _dump(page, f"missing_{code}", discover)
        raise PortalError(f"No product matching {code!r} on the page. Check the code or run --discover.")
    # innermost match: last in DOM order is the most specific container
    row = rows.last
    row.locator(SEL["qty_input"]).first.fill(str(qty))
    row.locator(SEL["add_button"]).first.click()
    page.wait_for_load_state("networkidle")


def place_order(machine, items: dict[str, int], confirm=False, discover=False, headless=False):
    """Returns (status, reference). status: 'dry-run' | 'submitted'."""
    with sync_playwright() as p:
        try:  # Windows always has Edge; avoids shipping a browser
            browser = p.chromium.launch(channel="msedge", headless=headless)
        except Exception:
            browser = p.chromium.launch(headless=headless)
        page = browser.new_context().new_page()
        try:
            guest_login(page, machine, discover)
            for code, qty in items.items():
                print(f"  adding {qty} x {code}")
                add_toner(page, code, qty, discover)
            page.click(SEL["checkout"])
            page.wait_for_load_state("networkidle")
            _dump(page, "checkout", discover)
            if not confirm:
                print("  DRY RUN: stopped before submitting. Re-run with --confirm to place the order.")
                return "dry-run", None
            page.click(SEL["submit_order"])
            page.wait_for_load_state("networkidle")
            _dump(page, "confirmation", discover)
            ref = None
            try:
                ref = page.locator(SEL["reference"]).first.inner_text(timeout=5000).strip()
            except PWTimeout:
                pass
            return "submitted", ref
        finally:
            browser.close()
