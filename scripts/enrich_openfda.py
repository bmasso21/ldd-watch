#!/usr/bin/env python3
"""Fill structured fields on every record from openFDA (runs in GitHub Actions; api.fda.gov is
blocked from some environments).

For each drug, queries:
  /drug/drugsfda.json  search=openfda.brand_name:"BRAND"   -> sponsor, generic, original approval date, dosage forms
  /drug/ndc.json       search=brand_name:"BRAND"           -> NDCs (product_ndc + package NDCs), labeler, DEA schedule
  /drug/label.json     search=openfda.brand_name:"BRAND"   -> indications_and_usage (first sentence), boxed warning, REMS mention

Only fills fields that are empty/null/"unknown". Never overwrites a human- or researcher-supplied value.
Writes an enrichment log to stdout. Usage: enrich_openfda.py [--limit N] [--only brand,brand]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ldd.json"
API = "https://api.fda.gov/drug"
KEY = os.environ.get("OPENFDA_API_KEY")


def get(endpoint, search, limit=5):
    qs = {"search": search, "limit": limit}
    if KEY:
        qs["api_key"] = KEY
    url = f"{API}/{endpoint}.json?" + urllib.parse.urlencode(qs, quote_via=urllib.parse.quote)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ldd-watch/1.0"}), timeout=60) as r:
                return json.load(r).get("results", [])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if e.code == 429:
                time.sleep(2 + attempt * 3)
                continue
            raise
    return []


def clean_brand(b):
    # strip pack/kit suffixes that openFDA won't match
    b = re.sub(r"\s*\((.*?)\)", "", b)
    b = re.sub(r"\b(co-pack|copack|kit|pen|flextouch|autoinjector|iqlik)\b", "", b, flags=re.I)
    return b.strip()


def fmt_date(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and len(d) == 8 and d.isdigit() else None


def first_sentence(text):
    if not text:
        return None
    t = re.sub(r"^\s*(1\s+)?INDICATIONS AND USAGE\s*", "", text.strip(), flags=re.I)
    t = re.sub(r"\s+", " ", t)
    m = re.match(r"(.{20,400}?\.)(\s|$)", t)
    return (m.group(1) if m else t[:400]).strip()


def enrich(d, log):
    brand = clean_brand(d["brand"])
    if not brand or len(brand) < 3:
        return False
    changed = False
    q = brand.replace('"', "")

    # --- Drugs@FDA
    res = get("drugsfda", f'openfda.brand_name:"{q}"')
    if not res and d.get("generic") and d["generic"] != d["brand"]:
        res = get("drugsfda", f'openfda.generic_name:"{d["generic"].replace(chr(34), "")}"')
    if res:
        r = res[0]
        prods = r.get("products") or []
        subs = r.get("submissions") or []
        orig = [s for s in subs if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"]
        if d.get("manufacturer") in (None, "", "unknown") and r.get("sponsor_name"):
            d["manufacturer"] = r["sponsor_name"].title() if r["sponsor_name"].isupper() else r["sponsor_name"]; changed = True
        if (not d.get("generic") or d["generic"] == d["brand"]) and prods and prods[0].get("active_ingredients"):
            d["generic"] = ", ".join(a["name"].lower() for a in prods[0]["active_ingredients"]); changed = True
        if not d.get("approval_date") and orig:
            d["approval_date"] = fmt_date(min(s.get("submission_status_date", "") for s in orig)); changed = True
        if not d.get("dosage_forms") and prods:
            forms = sorted({f"{p.get('dosage_form','').lower()} {p.get('route','').lower()}".strip() for p in prods if p.get("dosage_form")})
            if forms:
                d["dosage_forms"] = forms; changed = True
        app = r.get("application_number", "")
        if app and not any("accessdata.fda.gov" in s["url"] or "Drugs@FDA" in (s.get("note") or "") for s in d["sources"]):
            d["sources"].append({"url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={re.sub(r'[^0-9]', '', app)}",
                                 "type": "fda", "date_checked": TODAY, "note": f"Drugs@FDA {app}"}); changed = True
        log.append(f"{d['brand']}: drugsfda ok ({app})")
    else:
        log.append(f"{d['brand']}: drugsfda no match")

    # --- NDC directory
    if not d.get("ndcs"):
        res = get("ndc", f'brand_name:"{q}"', limit=20)
        ndcs = set()
        for r in res:
            if r.get("product_ndc"):
                ndcs.add(r["product_ndc"])
            for p in r.get("packaging") or []:
                if p.get("package_ndc"):
                    ndcs.add(p["package_ndc"])
            if r.get("dea_schedule") and not d.get("controlled_substance"):
                d["controlled_substance"] = True; changed = True
            if d.get("manufacturer") in (None, "", "unknown") and r.get("labeler_name"):
                d["manufacturer"] = r["labeler_name"]; changed = True
        valid = sorted(n for n in ndcs if re.match(r"^\d{4,5}-\d{3,4}(-\d{1,2})?$", n))
        # schema requires labeler-product-package form; keep package NDCs, else product NDCs padded as -XX is invalid, so keep only 3-part
        three = [n for n in valid if n.count("-") == 2]
        if three:
            d["ndcs"] = three[:30]; changed = True
            log.append(f"{d['brand']}: {len(three)} NDC(s)")

    # --- Label (indication, REMS, boxed warning)
    if not d.get("indication") or d.get("rems") is False:
        res = get("label", f'openfda.brand_name:"{q}"', limit=1)
        if res:
            r = res[0]
            if not d.get("indication"):
                ind = first_sentence(" ".join(r.get("indications_and_usage") or []))
                if ind:
                    d["indication"] = ind; changed = True
            full = json.dumps(r).lower()
            if "risk evaluation and mitigation strategy" in full or '"rems"' in full or " rems " in full:
                if not d.get("rems"):
                    d["rems"] = True; changed = True
                    log.append(f"{d['brand']}: REMS mentioned in label")
            # storage: refrigerate -> cold chain
            if d.get("cold_chain") is None:
                stor = " ".join(r.get("storage_and_handling") or r.get("how_supplied") or []).lower()
                if stor:
                    d["cold_chain"] = ("refrigerat" in stor or "2°c" in stor or "2 °c" in stor or "36°f" in stor); changed = True
    return changed


TODAY = None


def main():
    global TODAY
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--today", default=None)
    a = ap.parse_args()
    from datetime import date
    TODAY = a.today or date.today().isoformat()

    data = json.loads(DATA.read_text())
    only = {x.strip().lower() for x in a.only.split(",") if x.strip()}
    log, n_changed, n = [], 0, 0
    for d in data["drugs"]:
        if only and d["brand"].lower() not in only:
            continue
        if a.limit and n >= a.limit:
            break
        n += 1
        try:
            if enrich(d, log):
                n_changed += 1
        except Exception as e:  # noqa
            log.append(f"{d['brand']}: ERROR {e}")
        time.sleep(0.25 if KEY else 0.3)
    data["meta"]["last_updated"] = TODAY
    DATA.write_text(json.dumps(data, indent=2) + "\n")
    print("\n".join(log))
    print(f"\nprocessed={n} changed={n_changed}")


if __name__ == "__main__":
    main()
