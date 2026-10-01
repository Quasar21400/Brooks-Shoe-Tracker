"""One check: ask every source, compare with the last run, notify on changes."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import geo
from .http import Http
from .models import Offer, SourceResult, Target
from .notify import Notifier
from .sources import brooks, fleetfeet, shopify

STOCK_ISSUE = "stock"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shoe_tracker", description=__doc__)
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--state", default="state.json")
    ap.add_argument("--dry-run", action="store_true", help="check and print only: no notifications, state untouched")
    ap.add_argument("--test-notification", action="store_true", help="send a test alert through every configured channel first")
    args = ap.parse_args(argv)

    cfg = tomllib.loads(Path(args.config).read_text())
    target = Target(**cfg["shoe"])
    notifier = Notifier(dry_run=args.dry_run)
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    before = json.dumps(state, sort_keys=True)

    print(f"Looking for: {target.label}")
    print(f"Alert channels: {', '.join(notifier.channels()) or 'none configured (results are only printed)'}")
    if args.test_notification:
        send_test(notifier, target, cfg)

    http = Http()
    results = run_sources(target, cfg, http)
    report(results)

    now = datetime.now(timezone.utc)
    handle_stock(results, state, notifier, target)
    handle_health(results, state, notifier, now, float(cfg.get("alerts", {}).get("source_down_hours", 6)))

    if not args.dry_run and json.dumps(state, sort_keys=True) != before:
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        print(f"State saved to {state_path}")
    return 0


def run_sources(target: Target, cfg: dict, http: Http) -> list[SourceResult]:
    jobs = []
    if cfg.get("brooks", {}).get("enabled", True):
        jobs.append((brooks.NAME, lambda: brooks.check(target, cfg["brooks"], http)))
    if cfg.get("fleet_feet", {}).get("enabled", True):
        home = geo.resolve_home(cfg.get("location", {}), http)
        jobs.append((fleetfeet.NAME, lambda: fleetfeet.check(target, cfg["fleet_feet"], http, home)))
    shop_cfg = cfg.get("shopify", {})
    if shop_cfg.get("enabled", True):
        for store in shop_cfg.get("stores", []):
            jobs.append((store["name"], lambda s=store: shopify.check(target, s, shop_cfg.get("search", target.model), http)))

    results = []
    for name, job in jobs:
        print(f"Checking {name} ...")
        try:
            result = job()
        except Exception as exc:
            result = SourceResult(name, status="check failed", error=f"{type(exc).__name__}: {exc}"[:400])
        print(f"  {result.status}" + (f" [{result.error}]" if result.error else ""))
        results.append(result)
    return results


def report(results: list[SourceResult]) -> None:
    rows = ["| Where | Result |", "|---|---|"]
    for r in results:
        text = r.status + (f" ⚠️ `{r.error}`" if r.error else "")
        rows.append(f"| {r.name} | {text.replace('|', '/')} |")
    offers = [o for r in results for o in r.offers]
    header = f"## {'✅ In stock' if offers else '❌ Not available yet'}\n\n"
    summary = header + "\n".join(rows) + "\n"
    if offers:
        summary += "\n" + "\n".join(f"- [{o.retailer} ({o.where})]({o.url}) {o.note}" for o in offers) + "\n"
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(summary)


def handle_stock(results: list[SourceResult], state: dict, notifier: Notifier, target: Target) -> None:
    known: dict = state.setdefault("offers", {})
    issues: dict = state.setdefault("issues", {})
    failed = {r.name for r in results if not r.ok}
    current: dict[str, tuple[str, Offer]] = {o.key: (r.name, o) for r in results for o in r.offers}

    new = [(src, o) for key, (src, o) in current.items() if key not in known]
    if new:
        title = f"IN STOCK: {target.label}"
        lines = [o.line() for _, o in new]
        still = [o.line() for key, (_, o) in current.items() if key in known]
        body = "\n".join(lines) + (("\n\nStill available:\n" + "\n".join(still)) if still else "")
        pushed = notifier.send(title, body, url=new[0][1].url, priority=5, tags=("athletic_shoe", "rotating_light"))
        md = "\n".join(f"- [{o.retailer} ({o.where})]({o.url}) {o.note}" for _, o in new)
        issued = notifier.open_issue(issues, STOCK_ISSUE, title, f"**{target.label}** is available:\n\n{md}")
        if pushed or issued or not notifier.channels():
            stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
            for src, o in new:
                known[o.key] = {"source": src, "since": stamp, "offer": f"{o.retailer} ({o.where})"}
        else:
            print("  no alert channel delivered; will retry next run")

    # Forget offers that are gone, but not ones whose source just failed to load.
    gone = [key for key, info in known.items() if key not in current and info.get("source") not in failed]
    for key in gone:
        del known[key]
    if gone and not known:
        title = f"Sold out again: {target.label}"
        notifier.send(title, "Every place that had it is sold out again. Still watching.", priority=2, tags=("hourglass",))
        notifier.close_issue(issues, STOCK_ISSUE, "Sold out again everywhere. The tracker keeps watching and will open a new issue on the next restock.")


def handle_health(results: list[SourceResult], state: dict, notifier: Notifier, now: datetime, alert_after_hours: float) -> None:
    """Alert once if a source keeps failing, e.g. a site redesign broke parsing."""
    health: dict = state.setdefault("health", {})
    issues: dict = state.setdefault("issues", {})
    for r in results:
        entry = health.get(r.name)
        key = f"health:{r.name}"
        if r.ok:
            if entry and entry.get("alerted"):
                notifier.send(f"Tracker recovered: {r.name}", f"{r.name} is being checked normally again.", priority=2)
                notifier.close_issue(issues, key, "Checks are working again.")
            health.pop(r.name, None)
            continue
        if entry is None:
            entry = health[r.name] = {"failing_since": now.isoformat(timespec="minutes"), "alerted": False, "first_error": r.error}
        since = datetime.fromisoformat(entry["failing_since"])
        if not entry["alerted"] and now - since >= timedelta(hours=alert_after_hours):
            title = f"Shoe tracker can't check {r.name}"
            body = (
                f"Checks of {r.name} have failed since {entry['failing_since']} UTC.\n"
                f"Latest error: {r.error}\n"
                "Stock at this retailer isn't being watched until this is fixed."
            )
            notifier.send(title, body, priority=3, tags=("warning",))
            notifier.open_issue(issues, key, title, body)
            entry["alerted"] = True


def send_test(notifier: Notifier, target: Target, cfg: dict) -> None:
    title = "Test alert from your shoe tracker"
    body = f"Alerts work. You'll get one like this when {target.label} is in stock."
    url = cfg.get("brooks", {}).get("product_url", "")
    notifier.send(title, body, url=url, priority=4, tags=("white_check_mark",))
    scratch: dict = {}
    if notifier.open_issue(scratch, "test", title, body):
        notifier.close_issue(scratch, "test", "Test finished. Closing this automatically.")
