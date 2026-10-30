#!/usr/bin/env python3
"""Weekly openFDA check for newly approved drugs not yet in data/ldd.json.

Queries the Drugs@FDA endpoint for original approvals (NDA/BLA, submission_type ORIG,
status AP) in the last N days, drops anything already tracked, and writes a Markdown
report to stdout (the GitHub Action turns it into an issue).

No API key is required for ~240 req/min / 1,000 req/day; set OPENFDA_API_KEY to raise limits.
Usage: check_fda_approvals.py [--days 14] [--state .fda_seen.json]
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ldd.json"
API = "https://api.fda.gov/drug/drugsfda.json"


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ldd-watch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def query_new_approvals(days: int) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    rng = f"[{start:%Y%m%d}+TO+{end:%Y%m%d}]"
    search = (
        f"submissions.submission_type:ORIG+AND+submissions.submission_status:AP"
        f"+AND+submissions.submission_status_date:{rng}"
    )
    params = {"search": search, "limit": 100}
    key = os.environ.get("OPENFDA_API_KEY")
    if key:
        params["api_key"] = key
    # openFDA wants '+' as the space/AND separator; don't percent-encode it.
    qs = "&".join(f"{k}={v}" if k == "search" else f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        payload = fetch(f"{API}?{qs}")
    except urllib.error.HTTPError as e:
        if e.code == 404:  # openFDA returns 404 for "no matches"
            return []
        raise
    out = []
    for r in payload.get("results", []):
        orig = [s for s in r.get("submissions", []) if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"]
        if not orig:
            continue
        prods = r.get("products", []) or []
        brand = (prods[0].get("brand_name") if prods else None) or "(unknown)"
        generic = (prods[0].get("active_ingredients", [{}])[0].get("name") if prods else None) or "(unknown)"
        out.append({
            "application_number": r.get("application_number"),
            "sponsor": r.get("sponsor_name"),
            "brand": brand,
            "generic": generic,
            "approval_date": max(s.get("submission_status_date", "") for s in orig),
            "dosage_forms": sorted({p.get("dosage_form", "") for p in prods if p.get("dosage_form")}),
            "routes": sorted({p.get("route", "") for p in prods if p.get("route")}),
        })
    return out


def tracked_names() -> set[str]:
    data = json.loads(DATA.read_text())
    names = set()
    for d in data.get("drugs", []):
        for k in ("brand", "generic", "id"):
            if d.get(k):
                names.add(d[k].lower())
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--state", default=str(ROOT / ".fda_seen.json"))
    args = ap.parse_args()

    state_path = Path(args.state)
    seen = set(json.loads(state_path.read_text())) if state_path.exists() else set()
    known = tracked_names()

    approvals = query_new_approvals(args.days)
    new = [a for a in approvals
           if a["application_number"] not in seen
           and a["brand"].lower() not in known
           and a["generic"].lower() not in known]

    if not new:
        print("NO_NEW_APPROVALS")
        return 0

    today = date.today().isoformat()
    lines = [f"## New FDA original approvals to research ({today})", "",
             "Research each for limited-distribution status. See agent/RESEARCH_PROMPT.md.", "",
             "| Brand | Generic | Sponsor | Approved | Form / Route | App # |",
             "|---|---|---|---|---|---|"]
    for a in sorted(new, key=lambda x: x["approval_date"], reverse=True):
        fr = ", ".join(a["dosage_forms"]) + (" / " + ", ".join(a["routes"]) if a["routes"] else "")
        d = a["approval_date"]
        d = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d
        lines.append(f"| {a['brand']} | {a['generic']} | {a['sponsor']} | {d} | {fr} | {a['application_number']} |")
    lines += ["", "- [ ] Draft entries opened as a PR", "- [ ] Reviewed and merged"]
    print("\n".join(lines))

    seen.update(a["application_number"] for a in new)
    state_path.write_text(json.dumps(sorted(seen), indent=0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
