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
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))
        page = context.new_page()

        # intercept all responses and look for holdings data
        def handle_response(response):
            url = response.url
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            # look for API calls that might contain holdings
            keywords = ["holding", "portfolio", "position", "fund", "etf", "security", "asset"]
            if any(kw in url.lower() for kw in keywords):
                try:
                    body = response.json()
                    print("  Captured JSON from: {}".format(url), file=sys.stderr)
                    print("  Keys: {}".format(list(body.keys()) if isinstance(body, dict) else type(body).__name__), file=sys.stderr)
                    captured.append({"url": url, "data": body})
                except Exception:
                    pass

        page.on("response", handle_response)

        print("Opening page...", file=sys.stderr)
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(5000)

        # click Holdings tab
        print("Clicking Holdings tab...", file=sys.stderr)
        try:
            page.click("a[href='#holdings']", timeout=10000)
            page.wait_for_timeout(8000)
        except Exception as e:
            print("Holdings tab click error: {}".format(e), file=sys.stderr)

        # wait more for API calls
        page.wait_for_timeout(5000)

        print("Total API responses captured: {}".format(len(captured)), file=sys.stderr)
        for c in captured:
            print("  URL: {}".format(c["url"]), file=sys.stderr)

        browser.close()

    return captured


def main():
    today_str = date.today().isoformat()
    today = date.today()

    if not is_nyse_trading_day(today):
        print("{} is not a NYSE trading day -- skipping.".format(today_str), file=sys.stderr)
        sys.exit(0)

    print("Intercepting TCAF API calls for {}...".format(today_str), file=sys.stderr)
    captured = scrape_holdings()

    if not captured:
        print("No API calls captured -- need different approach.", file=sys.stderr)
    else:
        print("SUCCESS -- captured {} API responses".format(len(captured)), file=sys.stderr)
        for c in captured:
            print("URL: {}".format(c["url"]), file=sys.stderr)
            print("Data preview: {}".format(str(c["data"])[:500]), file=sys.stderr)


if __name__ == "__main__":
    main()
