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
    records = []

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

        # go directly to TCAF page -- no homepage first
        print("Opening TCAF page...", file=sys.stderr)
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(8000)

        # dismiss any popup using Playwright locators (pierces shadow DOM)
        print("Checking for popups...", file=sys.stderr)
        for text in ["Accept", "I Agree", "Close", "Financial Advisor", "Continue"]:
            try:
                btn = page.get_by_role("button", name=text).first
                if btn.is_visible(timeout=1500):
                    print("  Clicking: {}".format(text), file=sys.stderr)
                    btn.click()
                    page.wait_for_timeout(2000)
            except Exception:
                pass

        # click Holdings tab
        print("Clicking Holdings tab...", file=sys.stderr)
        try:
            page.click("a[href='#holdings']", timeout=10000)
            page.wait_for_timeout(8000)
        except Exception as e:
            print("  Holdings tab error: {}".format(e), file=sys.stderr)

        # wait for rows
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(3000)

        # use locator to check pagination -- this pierces shadow DOM
        next_loc = page.locator("div.next beacon-icon-button")
        prev_loc = page.locator("div.prev beacon-icon-button")

        next_count = next_loc.count()
        prev_count = prev_loc.count()
        next_state = next_loc.get_attribute("motion-state") if next_count > 0 else "not found"
        prev_state = prev_loc.get_attribute("motion-state") if prev_count > 0 else "not found"

        print("Pagination -- next: {} state={}, prev: {} state={}".format(
            next_count, next_state, prev_count, prev_state), file=sys.stderr)

        # also print first 5 rows to understand what data we're getting
        rows = page.query_selector_all("table tbody tr")
        print("Total rows: {}".format(len(rows)), file=sys.stderr)
        for i, row in enumerate(rows[:5]):
            cells = row.query_selector_all("td")
            texts = [c.inner_text().strip()[:30] for c in cells]
            print("  Row {}: {}".format(i, texts), file=sys.stderr)

        # check if there's a page size selector using locator
        print("Looking for page size controls...", file=sys.stderr)
        selects = page.locator("select").all()
        print("  Found {} select elements".format(len(selects)), file=sys.stderr)
        for sel in selects:
            try:
                opts = sel.locator("option").all_text_contents()
                print("  Select options: {}".format(opts), file=sys.stderr)
            except Exception:
                pass

        # scrape pages
        page_num = 1
        prev_first_row = None

        while True:
            print("Scraping page {}...".format(page_num), file=sys.stderr)
            rows = page.query_selector_all("table tbody tr")

            first_row_text = rows[0].inner_text().strip() if rows else ""
            if first_row_text == prev_first_row and page_num > 1:
                print("  Unchanged -- done.", file=sys.stderr)
                break
            prev_first_row = first_row_text

            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < 3:
                    continue
                texts = [c.inner_text().strip() for c in cells]
                record = {
                    "name":           texts[0] if len(texts) > 0 else "",
                    "pct_of_fund":    texts[1] if len(texts) > 1 else "",
                    "ticker":         texts[2] if len(texts) > 2 else "",
                    "identifier":     texts[3] if len(texts) > 3 else "",
                    "investments":    texts[4] if len(texts) > 4 else "",
                    "options_strike": texts[5] if len(texts) > 5 else "",
                    "quantity":       texts[6] if len(texts) > 6 else "",
                    "market_value":   texts[7] if len(texts) > 7 else "",
                }
                if record["name"] or record["ticker"]:
                    records.append(record)

            # check next button via locator
            next_loc = page.locator("div.next beacon-icon-button")
            n = next_loc.count()
            state = next_loc.get_attribute("motion-state") if n > 0 else "not found"
            print("  Next button: count={} state={}".format(n, state), file=sys.stderr)

            if n > 0 and state != "disabled":
                print("  Clicking next...", file=sys.stderr)
                next_loc.click()
                page.wait_for_timeout(3000)
                page_num += 1
            else:
                print("  No next page -- done.", file=sys.stderr)
                break

            if page_num > 20:
                break

        browser.close()

    return records


def safe_float(s):
    try:
        return round(float(str(s).replace(",", "").replace("%", "").replace("$", "").strip()), 6)
    except (ValueError, TypeError):
        return None


def normalize(records):
    out = []
    for r in records:
        out.append({
            "name":           r.get("name", ""),
            "ticker":         r.get("ticker", ""),
            "identifier":     r.get("identifier", ""),
            "pct_of_fund":    safe_float(r.get("pct_of_fund")),
            "quantity":       safe_float(r.get("quantity")),
            "market_value":   safe_float(r.get("market_value")),
            "investments":    r.get("investments", ""),
            "options_strike": r.get("options_strike", ""),
        })
    return out


def save_snapshot(records, today_str):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "{}.json".format(today_str))
    payload = {"date": today_str, "holdings": records}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    with open(os.path.join(DATA_DIR, "latest.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print("Saved {} holdings".format(len(records)), file=sys.stderr)


def find_prior_snapshot(today_str):
    files = sorted(
        f for f in os.listdir(DATA_DIR)
        if f.endswith(".json") and f not in ("latest.json", "diff.json", "history.json")
    )
    prior = [f for f in files if f.replace(".json", "") < today_str]
    return os.path.join(DATA_DIR, prior[-1]) if prior else None


def compute_diff(today_records, prior_records, today_str, prior_date_str):
    today_map = {r["ticker"] or r["name"]: r for r in today_records}
    prior_map = {r["ticker"] or r["name"]: r for r in prior_records}
    all_keys  = sorted(set(today_map) | set(prior_map))
    rows = []
    for key in all_keys:
        t = today_map.get(key)
        p = prior_map.get(key)
        if t and p:
            q_today   = t["quantity"] or 0
            q_prior   = p["quantity"] or 0
            pct_today = t["pct_of_fund"] or 0
            pct_prior = p["pct_of_fund"] or 0
            qty_chg   = ((q_today - q_prior) / q_prior * 100) if q_prior != 0 else 0
            rows.append({
                "ticker":              t.get("ticker") or p.get("ticker") or "",
                "name":                t.get("name") or p.get("name") or "",
                "identifier":          t.get("identifier") or "",
                "status":              "changed" if qty_chg != 0 else "unchanged",
                "quantity_today":      q_today,
                "quantity_prior":      q_prior,
                "quantity_pct_change": round(qty_chg, 4),
                "pct_of_fund_today":   pct_today,
                "pct_of_fund_prior":   p["pct_of_fund"] or 0,
                "pct_of_fund_change":  round(pct_today - (p["pct_of_fund"] or 0), 4),
                "market_value_today":  t.get("market_value"),
            })
        elif t:
            rows.append({
                "ticker": t.get("ticker") or "", "name": t.get("name") or "",
                "identifier": t.get("identifier") or "", "status": "added",
                "quantity_today": t["quantity"] or 0, "quantity_prior": None,
                "quantity_pct_change": None,
                "pct_of_fund_today": t["pct_of_fund"] or 0, "pct_of_fund_prior": None,
                "pct_of_fund_change": None, "market_value_today": t.get("market_value"),
            })
        else:
            rows.append({
                "ticker": p.get("ticker") or "", "name": p.get("name") or "",
                "identifier": p.get("identifier") or "", "status": "removed",
                "quantity_today": None, "quantity_prior": p["quantity"] or 0,
                "quantity_pct_change": None, "pct_of_fund_today": None,
                "pct_of_fund_prior": p["pct_of_fund"] or 0,
                "pct_of_fund_change": None, "market_value_today": None,
            })
    return {"date": today_str, "prior_date": prior_date_str, "diff": rows}


def append_history(today_str, diff):
    history_path = os.path.join(DATA_DIR, "history.json")
    history = []
    if os.path.exists(history_path):
        with open(history_path) as f:
            history = json.load(f)
    entry = {"date": today_str, "prior_date": diff["prior_date"]}
    if entry not in history:
        history.append(entry)
        history.sort(key=lambda x: x["date"], reverse=True)
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)


def main():
    today_str = date.today().isoformat()
    today = date.today()

    if not is_nyse_trading_day(today):
        print("{} is not a NYSE trading day -- skipping.".format(today_str), file=sys.stderr)
        sys.exit(0)

    print("Scraping TCAF holdings for {}...".format(today_str), file=sys.stderr)
    raw = scrape_holdings()
    records = normalize(raw)
    print("Found {} total holdings.".format(len(records)), file=sys.stderr)

    save_snapshot(records, today_str)

    prior_path = find_prior_snapshot(today_str)
    if not prior_path:
        diff = {"date": today_str, "prior_date": None, "diff": []}
    else:
        with open(prior_path) as f:
            prior_data = json.load(f)
        diff = compute_diff(records, prior_data["holdings"], today_str, prior_data["date"])

    with open(os.path.join(DATA_DIR, "diff.json"), "w") as f:
        json.dump(diff, f, indent=2)

    append_history(today_str, diff)

    changed = sum(1 for r in diff["diff"] if r["status"] == "changed")
    added   = sum(1 for r in diff["diff"] if r["status"] == "added")
    removed = sum(1 for r in diff["diff"] if r["status"] == "removed")
    print("Done -- {} holdings | {} changed | {} added | {} removed".format(
        len(records), changed, added, removed), file=sys.stderr)


if __name__ == "__main__":
    main()
