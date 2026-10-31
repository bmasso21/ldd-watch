#!/usr/bin/env python3
"""Match a local claims / prior-auth export against the LDD directory.

Runs entirely on your machine. PHI never leaves it; only the public ldd.json is read
(from the local repo copy or, with --remote, from GitHub).

Input: a CSV with at least one of these columns (case-insensitive, flexible names):
    ndc            -> matched exactly after stripping dashes (11-digit or 10-digit)
    drug_name / drug / medication / product -> matched on brand or generic, substring, case-insensitive
Any other columns (member id, PA number, date) are carried through to the output.

Output: hits.csv with one row per matching claim row, plus pharmacy contact info.

Usage:
    python match_claims.py claims.csv
    python match_claims.py claims.csv --out hits.csv
    python match_claims.py claims.csv --remote https://raw.githubusercontent.com/<you>/ldd-watch/main/data/ldd.json
"""
import argparse
import csv
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ldd.json"

NDC_COLS = {"ndc", "ndc11", "ndc_code", "product_ndc"}
NAME_COLS = {"drug_name", "drug", "medication", "product", "product_name", "label_name", "drugname"}


def norm_ndc(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def load_ldd(remote: str | None) -> list[dict]:
    if remote:
        with urllib.request.urlopen(remote, timeout=60) as r:
            return json.load(r)["drugs"]
    return json.loads(DATA.read_text())["drugs"]


def build_index(drugs: list[dict]):
    by_ndc = {}
    by_name = []
    for d in drugs:
        for n in d.get("ndcs", []):
            k = norm_ndc(n)
            by_ndc[k] = d
            # also index the 9-digit product prefix (labeler+product) for 10/11 digit variants
            by_ndc.setdefault(k[:9], d)
        for name in (d.get("brand"), d.get("generic")):
            if name:
                by_name.append((name.lower(), d))
    return by_ndc, by_name


def match_row(row: dict, by_ndc, by_name):
    lower = {k.lower().strip(): v for k, v in row.items()}
    for c in NDC_COLS & lower.keys():
        n = norm_ndc(lower[c])
        if n and (n in by_ndc or n[:9] in by_ndc):
            return by_ndc.get(n) or by_ndc.get(n[:9]), "ndc"
    for c in NAME_COLS & lower.keys():
        v = (lower[c] or "").lower()
        if not v:
            continue
        for name, d in by_name:
            if name in v or v in name:
                return d, "name"
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("claims_csv")
    ap.add_argument("--out", default="hits.csv")
    ap.add_argument("--remote", default=None, help="URL of ldd.json (raw GitHub) instead of local copy")
    ap.add_argument("--include-open", action="store_true", help="also report drugs with distribution_type=open")
    args = ap.parse_args()

    drugs = load_ldd(args.remote)
    by_ndc, by_name = build_index(drugs)

    hits = []
    with open(args.claims_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d, how = match_row(row, by_ndc, by_name)
            if not d:
                continue
            if d["distribution_type"] == "open" and not args.include_open:
                continue
            pharm = "; ".join(
                " | ".join(x for x in [p.get("name"), p.get("phone"), p.get("fax"), p.get("enrollment_url")] if x)
                for p in d.get("pharmacies", [])
            )
            hub = d.get("hub_program") or {}
            hits.append({
                **row,
                "ldd_brand": d["brand"],
                "ldd_generic": d["generic"],
                "ldd_distribution": d["distribution_type"],
                "ldd_pharmacies": pharm,
                "ldd_hub": " | ".join(x for x in [hub.get("name"), hub.get("phone"), hub.get("url")] if x),
                "ldd_rems": d.get("rems"),
                "ldd_inactive": d.get("inactive", False),
                "ldd_status": d["status"],
                "ldd_confidence": d["confidence"],
                "matched_on": how,
            })

    if not hits:
        print("No LDD matches.")
        return 0
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(hits[0].keys()))
        w.writeheader()
        w.writerows(hits)
    print(f"{len(hits)} matching row(s) -> {args.out}")
    for h in hits:
        print(f"  {h['ldd_brand']} ({h['ldd_distribution']}, {h['ldd_status']}): {h['ldd_pharmacies'] or 'no pharmacy on file'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
