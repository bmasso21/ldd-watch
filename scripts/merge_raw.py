#!/usr/bin/env python3
"""Merge raw pharmacy/payer LDD list scrapes into draft records for data/ldd.json.

Inputs: one or more JSON files, each an array of rows with at least {brand} and either
{pharmacy} (single) or {pharmacies: [..]}, plus source_url and date_checked.
Rows for the same drug (matched on normalized brand, else generic) are collapsed into one
record listing every pharmacy that carries it. Existing records in data/ldd.json are
updated in place (new pharmacies/sources appended) rather than duplicated.

Usage: merge_raw.py agent/raw_*.json [--today 2026-10-29] [--write]
Without --write it prints a summary only.
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ldd.json"

PHARMACY_SITES = {
    "onco360": "https://onco360.com", "biologics": "https://www.biologicsinc.com",
    "accredo": "https://www.accredo.com", "cvs specialty": "https://www.cvsspecialty.com",
    "optum": "https://specialty.optumrx.com", "walgreens": "https://www.walgreensspecialtyrx.com",
    "alliancerx": "https://www.alliancerxwp.com", "orsini": "https://www.orsinihealthcare.com",
    "pantherx": "https://www.pantherxrare.com", "amber": "https://www.amberpharmacy.com",
    "acaria": "https://www.acariahealth.com", "senderra": "https://www.senderrarx.com",
    "bioplus": "https://www.bioplusrx.com", "soleo": "https://www.soleohealth.com",
    "kroger": "https://www.krogerspecialtypharmacy.com", "ardon": "https://www.ardonhealth.com",
}


# Sources that are general "drugs we carry" catalogs, not LDD assertions. Rows from these
# may add a pharmacy to a drug already established as LDD, but never create a record.
GENERAL_CATALOG_PATTERNS = (
    "cvsspecialty.com/education-center/downloads/SpecialtyDrugs.pdf",
    "amberpharmacy.com/specialties/",
    "orsini.com/medication-search",
    "orsini.com/sitemap",
    "rxalmanac.com",
)


def is_general_catalog(url, row):
    u = (url or "").lower()
    if any(p.lower() in u for p in GENERAL_CATALOG_PATTERNS):
        # an explicit exclusivity/LDN claim on the row still counts as an assertion
        return row.get("exclusive_claimed") is None
    return False


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "unknown"


def canon_pharmacy(name):
    n = (name or "").strip()
    if not n:
        return None
    low = n.lower()
    for key, url in PHARMACY_SITES.items():
        if key in low:
            label = {"onco360": "Onco360", "biologics": "Biologics by McKesson", "accredo": "Accredo",
                     "cvs specialty": "CVS Specialty", "optum": "Optum Specialty Pharmacy",
                     "walgreens": "Walgreens Specialty Pharmacy", "alliancerx": "AllianceRx Walgreens Pharmacy",
                     "orsini": "Orsini Specialty Pharmacy", "pantherx": "PANTHERx Rare",
                     "amber": "Amber Specialty Pharmacy", "acaria": "AcariaHealth", "senderra": "Senderra Rx",
                     "bioplus": "BioPlus Specialty Pharmacy", "soleo": "Soleo Health",
                     "kroger": "Kroger Specialty Pharmacy", "ardon": "Ardon Health"}[key]
            return label, url
    return n, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    today = date.fromisoformat(a.today)

    rows = []
    for f in a.inputs:
        try:
            rows.extend(json.loads(Path(f).read_text()))
        except Exception as e:  # noqa
            print(f"skip {f}: {e}", file=sys.stderr)

    # group: asserting rows first, then general-catalog rows only onto existing groups
    asserting = [r for r in rows if not is_general_catalog(r.get("source_url"), r)]
    catalog = [r for r in rows if is_general_catalog(r.get("source_url"), r)]
    groups = {}
    skipped_catalog = 0
    for r in asserting + catalog:
        brand = (r.get("brand") or "").strip()
        generic = (r.get("generic") or "").strip()
        key = norm(brand) or norm(generic)
        if not key:
            continue
        if r in catalog and key not in groups and not (norm(generic) in groups):
            skipped_catalog += 1
            continue
        if key not in groups and norm(generic) in groups:
            key = norm(generic)
        g = groups.setdefault(key, {"brand": brand, "generic": generic, "manufacturer": r.get("manufacturer"),
                                    "pharmacies": {}, "sources": {}, "exclusive_votes": 0, "rows": 0})
        g["rows"] += 1
        if not g["generic"] and generic:
            g["generic"] = generic
        if not g["manufacturer"] and r.get("manufacturer"):
            g["manufacturer"] = r.get("manufacturer")
        if r.get("exclusive_claimed") is True:
            g["exclusive_votes"] += 1
        phs = r.get("pharmacies") or ([r["pharmacy"]] if r.get("pharmacy") else [])
        for p in phs:
            cp = canon_pharmacy(p)
            if cp:
                g["pharmacies"].setdefault(cp[0], cp[1])
        url = r.get("source_url")
        if url:
            stype = "pharmacy" if r.get("pharmacy") else "pbm"
            g["sources"].setdefault(url, {"url": url, "type": stype,
                                          "date_checked": r.get("date_checked") or a.today,
                                          "note": (r.get("publisher") or r.get("pharmacy") or None)})

    data = json.loads(DATA.read_text())
    existing = {norm(d["brand"]): d for d in data["drugs"]}
    existing.update({norm(d["generic"]): d for d in data["drugs"] if d.get("generic")})

    added = updated = 0
    for key, g in groups.items():
        ph_list = [{"name": n, "phone": None, "fax": None, "enrollment_url": u, "notes": None}
                   for n, u in sorted(g["pharmacies"].items())]
        n_ph = len(ph_list)
        dist = "exclusive" if (n_ph == 1 and g["exclusive_votes"] > 0) else ("limited_network" if n_ph >= 1 else "unknown")
        if key in existing:
            d = existing[key]
            have = {p["name"] for p in d["pharmacies"]}
            new_ph = [p for p in ph_list if p["name"] not in have]
            have_src = {s["url"] for s in d["sources"]}
            new_src = [s for u, s in g["sources"].items() if u not in have_src]
            if new_ph or new_src:
                d["pharmacies"].extend(new_ph)
                d["sources"].extend(new_src)
                if d["distribution_type"] in ("unknown", "open") and d["pharmacies"]:
                    d["distribution_type"] = "limited_network"
                if d["distribution_type"] == "exclusive" and len(d["pharmacies"]) > 1:
                    d["distribution_type"] = "limited_network"
                updated += 1
            continue
        rec = {
            "id": slug(g["generic"] or g["brand"]),
            "brand": g["brand"] or g["generic"],
            "generic": g["generic"] or g["brand"],
            "manufacturer": g["manufacturer"] or "unknown",
            "approval_date": None, "indication": None, "dosage_forms": [], "ndcs": [],
            "distribution_type": dist, "pharmacies": ph_list, "hub_program": None,
            "rems": False, "cold_chain": None, "controlled_substance": False,
            "sources": list(g["sources"].values()) or [{"url": "https://example.invalid", "type": "other", "date_checked": a.today, "note": "no source captured"}],
            "confidence": "medium" if n_ph else "low", "status": "draft",
            "verified_by": None, "verified_date": None,
            "next_review_date": (today + timedelta(days=90)).isoformat(),
            "notes": f"Bulk-loaded from {g['rows']} public LDD list row(s) on {a.today}. Pharmacy list = union of lists that carry it; confirm exclusivity and current network on the manufacturer HCP page.",
        }
        # ensure unique id
        ids = {d["id"] for d in data["drugs"]}
        base, i = rec["id"], 2
        while rec["id"] in ids:
            rec["id"] = f"{base}-{i}"; i += 1
        data["drugs"].append(rec)
        existing[key] = rec
        added += 1

    data["drugs"].sort(key=lambda d: d["brand"].lower())
    data["meta"]["last_updated"] = a.today
    print(f"rows={len(rows)} asserting={len(asserting)} catalog_rows={len(catalog)} catalog_skipped={skipped_catalog} groups={len(groups)} added={added} updated={updated} total={len(data['drugs'])}")
    if a.write:
        DATA.write_text(json.dumps(data, indent=2) + "\n")
        print("written")


if __name__ == "__main__":
    main()
