import json
import os
import sys
from datetime import date
from playwright.sync_api import sync_playwright
import pandas_market_calendars as mcal

URL = "https://www.troweprice.com/financial-intermediary/us/en/investments/etfs/capital-appreciation-equity-etf.html"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
GRAPHQL_URL = "https://api.public.troweprice.com/ds-dada/graphql"


def is_nyse_trading_day(d):
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=d.isoformat(), end_date=d.isoformat())
    return not schedule.empty


def scrape_holdings():
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

        captured_requests = []

        def handle_request(request):
            if "ds-dada/graphql" in request.url:
                try:
                    body = request.post_data
                    captured_requests.append({
                        "url": request.url,
                        "method": request.method,
                        "headers": dict(request.headers),
                        "body": body,
                    })
                except Exception:
                    pass

        captured_responses = []

        def handle_response(response):
            if "ds-dada/graphql" in response.url:
                try:
                    data = response.json()
                    captured_responses.append({
                        "url": response.url,
                        "data": data,
                        "headers": dict(response.headers),
                    })
                except Exception:
                    pass

        page.on("request", handle_request)
        page.on("response", handle_response)

        print("Opening TCAF page...", file=sys.stderr)
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(8000)

        try:
            btn = page.get_by_role("button", name="Financial Advisor").first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(3000)
        except Exception:
            pass

        page.click("a[href='#holdings']", timeout=10000)
        page.wait_for_timeout(8000)

        captured_requests.clear()
        captured_responses.clear()

        print("Selecting today's date...", file=sys.stderr)
        try:
            selects = page.locator("select").all()
            if len(selects) >= 3:
                selects[2].select_option(index=0)
                page.wait_for_timeout(12000)
        except Exception as e:
            print("Date select error: {}".format(e), file=sys.stderr)

        print("\n=== GRAPHQL REQUESTS ===", file=sys.stderr)
        for req in captured_requests:
            print("URL: {}".format(req["url"]), file=sys.stderr)
            print("Method: {}".format(req["method"]), file=sys.stderr)
            print("Body: {}".format(req["body"]), file=sys.stderr)
            print("Headers: {}".format(json.dumps(req["headers"], indent=2)), file=sys.stderr)

        print("\n=== GRAPHQL RESPONSES ===", file=sys.stderr)
        for resp in captured_responses:
            print("Data: {}".format(str(resp["data"])[:2000]), file=sys.stderr)

        browser.close()


def main():
    today_str = date.today().isoformat()
    today = date.today()

    if not is_nyse_trading_day(today):
        print("{} is not a NYSE trading day -- skipping.".format(today_str), file=sys.stderr)
        sys.exit(0)

    print("Capturing GraphQL query for {}...".format(today_str), file=sys.stderr)
    scrape_holdings()
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
