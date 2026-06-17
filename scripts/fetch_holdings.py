import json
import os
import sys
from datetime import date
from playwright.sync_api import sync_playwright
import pandas_market_calendars as mcal

# Try the personal investing URL - it's a different app and may use a simpler API
URL = "https://www.troweprice.com/personal-investing/tools/fund-research/etf/TCAF"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def is_nyse_trading_day(d):
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=d.isoformat(), end_date=d.isoformat())
    return not schedule.empty


def scrape_holdings():
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))
        page = context.new_page()

        def handle_response(response):
            try:
                url = response.url
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type:
                    return
                body = response.json()
                captured.append({"url": url, "data": body})
            except Exception:
                pass

        page.on("response", handle_response)

        print("Opening personal investing TCAF page...", file=sys.stderr)
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(10000)

        print("Captured {} JSON responses so far".format(len(captured)), file=sys.stderr)

        # print all JSON URLs
        for c in captured:
            print("  {}".format(c["url"]), file=sys.stderr)
            preview = str(c["data"])[:300]
            print("  Preview: {}".format(preview), file=sys.stderr)
            print("", file=sys.stderr)

        browser.close()


def main():
    today_str = date.today().isoformat()
    today = date.today()

    if not is_nyse_trading_day(today):
        print("{} is not a NYSE trading day -- skipping.".format(today_str), file=sys.stderr)
        sys.exit(0)

    print("Checking personal investing API for {}...".format(today_str), file=sys.stderr)
    scrape_holdings()
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
