import json
import os
import sys
from datetime import date
from playwright.sync_api import sync_playwright
import pandas_market_calendars as mcal

URL = "https://www.troweprice.com/financial-intermediary/us/en/investments/etfs/capital-appreciation-equity-etf.html"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def is_nyse_trading_day(d):
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=d.isoformat(), end_date=d.isoformat())
    return not schedule.empty


def scrape_holdings():
    holdings_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # intercept ALL responses after date selection
        captured = []

        def handle_response(response):
            try:
                url = response.url
                ct = response.headers.get("content-type", "")
                size = int(response.headers.get("content-length", "0") or "0")
                # capture anything from troweprice that returns json or is large
                if "troweprice.com" in url and ("json" in ct or size > 5000):
                    try:
                        body = response.json()
                        captured.append({"url": url, "data": body, "size": size})
                    except Exception:
                        try:
                            text = response.text()
                            if len(text) > 500:
                                captured.append({"url": url, "text": text[:300], "size": len(text)})
                        except Exception:
                            pass
            except Exception:
                pass

        page.on("response", handle_response)

        print("Opening TCAF page...", file=sys.stderr)
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(8000)

        # click Financial Advisor
        try:
            btn = page.get_by_role("button", name="Financial Advisor").first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(3000)
        except Exception:
            pass

        # click Holdings tab
        page.click("a[href='#holdings']", timeout=10000)
        page.wait_for_timeout(8000)

        # clear captured so far, then select date to trigger fresh API call
        captured.clear()
        print("Selecting today's date -- watching for API calls...", file=sys.stderr)
        try:
            selects = page.locator("select").all()
            if len(selects) >= 3:
                selects[2].select_option(index=0)
                page.wait_for_timeout(12000)
        except Exception as e:
            print("Date select error: {}".format(e), file=sys.stderr)

        print("Captured {} responses after date selection:".format(len(captured)), file=sys.stderr)
        for c in captured:
            url = c["url"]
            size = c.get("size", "?")
            print("  [{}B] {}".format(size, url), file=sys.stderr)
            if "data" in c:
                preview = str(c["data"])[:400]
                print("  JSON preview: {}".format(preview), file=sys.stderr)
            elif "text" in c:
                print("  Text preview: {}".format(c["text"][:200]), file=sys.stderr)

        # try to find holdings data in captured responses
        for c in captured:
            if "data" not in c:
                continue
            data = c["data"]
            # look for a list with stock-like objects
            items = None
            if isinstance(data, list) and len(data) > 5:
                items = data
            elif isinstance(data, dict):
                for key in ["holdings", "positions", "portfolio", "data", "items",
                            "securities", "components", "rows", "results"]:
                    if key in data and isinstance(data[key], list) and len(data[key]) > 5:
                        items = data[key]
                        break

            if items and len(items) > 5:
                print("Found {} items in API response from: {}".format(
                    len(items), c["url"]), file=sys.stderr)
                print("First item keys: {}".format(
                    list(items[0].keys()) if isinstance(items[0], dict) else items[0]),
                    file=sys.stderr)
                holdings_data = items
                break

        browser.close()

    return holdings_data


def main():
    today_str = date.today().isoformat()
    today = date.today()

    if not is_nyse_trading_day(today):
        print("{} is not a NYSE trading day -- skipping.".format(today_str), file=sys.stderr)
        sys.exit(0)

    print("Intercepting TCAF holdings API for {}...".format(today_str), file=sys.stderr)
    items = scrape_holdings()
    print("Found {} items from API.".format(len(items)), file=sys.stderr)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
