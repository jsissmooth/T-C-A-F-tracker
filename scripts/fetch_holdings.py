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
    all_trp_calls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))
        page = context.new_page()

        # capture ALL network requests
        def handle_request(request):
            url = request.url
            if "troweprice.com" in url and url != URL:
                all_trp_calls.append({"type": "request", "url": url, "method": request.method})

        def handle_response(response):
            url = response.url
            if "troweprice.com" in url and url != URL:
                content_type = response.headers.get("content-type", "")
                size = response.headers.get("content-length", "?")
                all_trp_calls.append({
                    "type": "response",
                    "url": url,
                    "status": response.status,
                    "content_type": content_type,
                    "size": size
                })
                # try to get body for any response
                try:
                    body = response.text()
                    if len(body) > 100:
                        print("  TRP response: {} ({} bytes)".format(url, len(body)), file=sys.stderr)
                        print("  Preview: {}".format(body[:300]), file=sys.stderr)
                except Exception:
                    pass

        page.on("request", handle_request)
        page.on("response", handle_response)

        print("Opening page...", file=sys.stderr)
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(5000)

        print("Clicking Holdings tab...", file=sys.stderr)
        try:
            page.click("a[href='#holdings']", timeout=10000)
            print("Holdings tab clicked.", file=sys.stderr)
            page.wait_for_timeout(8000)
        except Exception as e:
            print("Holdings tab error: {}".format(e), file=sys.stderr)

        print("Waiting for more API calls...", file=sys.stderr)
        page.wait_for_timeout(5000)

        print("\n--- ALL T. ROWE PRICE NETWORK CALLS ---", file=sys.stderr)
        for call in all_trp_calls:
            print("  [{}] {}".format(call.get("status", call.get("method", "?")), call["url"]), file=sys.stderr)

        browser.close()


def main():
    today_str = date.today().isoformat()
    today = date.today()

    if not is_nyse_trading_day(today):
        print("{} is not a NYSE trading day -- skipping.".format(today_str), file=sys.stderr)
        sys.exit(0)

    print("Debugging TCAF network calls for {}...".format(today_str), file=sys.stderr)
    scrape_holdings()
    print("Debug complete.", file=sys.stderr)


if __name__ == "__main__":
    main()
