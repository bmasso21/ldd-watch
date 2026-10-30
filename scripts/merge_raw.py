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

# (label, url, match-substrings). Order matters: first match wins.
PHARMACIES = [
    ("Onco360", "https://onco360.com", ["onco360"]),
    ("Biologics by McKesson", "https://biologics.mckesson.com", ["biologics"]),
    ("Accredo", "https://www.accredo.com", ["accredo"]),
    ("Optum Frontier Therapies", "https://www.optumfrontiertherapies.com", ["frontier"]),
    ("Optum Specialty Pharmacy", "https://specialty.optumrx.com", ["optum"]),
    ("CVS Specialty", "https://www.cvsspecialty.com", ["cvs", "caremark"]),
    ("AllianceRx Walgreens Pharmacy", "https://www.alliancerxwp.com", ["alliancerx", "alliance walgreens"]),
    ("Walgreens Specialty Pharmacy", "https://www.walgreensspecialtyrx.com", ["walgreens", "wal-greens"]),
    ("Orsini Specialty Pharmacy", "https://www.orsini.com", ["orsini", "ornsi"]),
    ("PANTHERx Rare", "https://www.pantherxrare.com", ["pantherx", "pantherx", "panthrx", "pantherrx"]),
    ("Amber Specialty Pharmacy", "https://www.amberpharmacy.com", ["amber"]),
    ("AcariaHealth", "https://www.acariahealth.com", ["acaria", "foundation care"]),
    ("AnovoRx", "https://www.anovorx.com", ["anovo", "annovo"]),
    ("Genoa Healthcare", "https://www.genoahealthcare.com", ["genoa"]),
    ("Maxor Specialty", "https://www.maxor.com", ["maxor"]),
    ("Eversana", "https://www.eversana.com", ["eversana"]),
    ("Optime Care", "https://www.optimecare.com", ["optime"]),
    ("Biomatrix Specialty Pharmacy", "https://www.biomatrixsprx.com", ["biomatrix"]),
    ("US Bioservices", "https://www.usbioservices.com", ["us bioservices", "usbio"]),
    ("Option Care Health", "https://www.optioncarehealth.com", ["option care", "optioncare"]),
    ("Fairview Pharmacy Services", "https://www.fairview.org", ["fairview"]),
    ("Carle Specialty Pharmacy", "https://carle.org", ["carle"]),
    ("Lumicera Health Services", "https://www.lumicera.com", ["lumicera"]),
    ("Hemophilia of Georgia", "https://www.hog.org", ["hemophilia of georgia"]),
    ("LeMed Specialty Pharmacy", None, ["lemed"]),
    ("ESSDS (Express Scripts Specialty Distribution Services)", None, ["essds"]),
    ("Vanscoy Rare Pharmacy", None, ["vanscoy"]),
    ("Curant Health", "https://www.curanthealth.com", ["curant"]),
    ("Soleo Health", "https://www.soleohealth.com", ["soleo"]),
    ("Nufactor", "https://www.nufactor.com", ["nufactor"]),
    ("Alto Pharmacy", "https://alto.com", ["alto"]),
    ("KabaFusion", "https://www.kabafusion.com", ["kabafusion"]),
    ("Advanced Care Scripts (Omnicare)", None, ["advanced care scripts", "acs"]),
    ("KnippeRx", "https://www.knipperx.com", ["knipper"]),
    ("TotalCare Rx", None, ["totalcare"]),
    ("Senderra Rx", "https://www.senderrarx.com", ["senderra"]),
    ("BioPlus Specialty Pharmacy", "https://www.bioplusrx.com", ["bioplus"]),
    ("Kroger Specialty Pharmacy", "https://www.krogerspecialtypharmacy.com", ["kroger"]),
    ("Ardon Health", "https://www.ardonhealth.com", ["ardon"]),
    ("MMS Solutions", None, ["mms"]),
    ("Publix Pharmacy", None, ["publix"]),
    ("Walmart Specialty Pharmacy", None, ["wal-mart", "walmart"]),
    ("AHF Pharmacy", None, ["ahf"]),
    ("Premier Specialty", None, ["premier"]),
]
# Program / payer labels that are not dispensing pharmacies.
NOT_A_PHARMACY = ["advocate+", "pharmacy match", "buy and bill", "buy & bill", "prime", "kaiser", "optumrx", "ldd"]


# Sources that are general "drugs we carry" catalogs, not LDD assertions. Rows from these
# may add a pharmacy to a drug already established as LDD, but never create a record.
GENERAL_CATALOG_PATTERNS = (
    "cvsspecialty.com/education-center/downloads/SpecialtyDrugs.pdf",
    "amberpharmacy.com/specialties/",
    "orsini.com/medication-search",
    "orsini.com/sitemap",
    "rxalmanac.com",
    "healthalliance.org/documents/745",   # medical-benefit preferred-vendor list, not an LDD list
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
    if any(k in low for k in NOT_A_PHARMACY) and not any(k in low for _, _, ks in PHARMACIES for k in ks if k not in ("optum",)):
        return None
    for label, url, keys in PHARMACIES:
        if any(k in low for k in keys):
            return label, url
    return n.title() if n.isupper() else n, None


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
                                    "pharmacies": {}, "sources": {}, "exclusive_votes": 0, "rows": 0, "buy_bill": False})
        g["rows"] += 1
        if not g["generic"] and generic:
            g["generic"] = generic
        if not g["manufacturer"] and r.get("manufacturer"):
            g["manufacturer"] = r.get("manufacturer")
        if r.get("exclusive_claimed") is True:
            g["exclusive_votes"] += 1
        phs = r.get("pharmacies") or ([r["pharmacy"]] if r.get("pharmacy") else [])
        for p in phs:
            if "buy" in (p or "").lower() and "bill" in (p or "").lower():
                g["buy_bill"] = True
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
        if n_ph == 0 and g["buy_bill"]:
            dist = "open"
        if key in existing:
            d = existing[key]
            have = {p["name"] for p in d["pharmacies"]}
            new_ph = [p for p in ph_list if p["name"] not in have]
            have_src = {s["url"] for s in d["sources"]}
            new_src = [s for u, s in g["sources"].items() if u not in have_src]
            if new_ph or new_src:
                d["pharmacies"].extend(new_ph)
                d["sources"].extend(new_src)
                # Never reclassify a researched record from a bulk list; flag it for the reviewer instead.
                if new_ph:
                    names = ", ".join(p["name"] for p in new_ph)
                    d["notes"] = (d.get("notes") or "") + f" Bulk-load {a.today}: also listed by {names}; reviewer to confirm distribution_type."
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
            "confidence": "medium" if (n_ph or g["buy_bill"]) else "low", "status": "draft",
            "verified_by": None, "verified_date": None,
            "next_review_date": (today + timedelta(days=90)).isoformat(),
            "notes": (f"Bulk-loaded from {g['rows']} public LDD list row(s) on {a.today}. "
                      + ("Payer list marks it buy-and-bill (provider-administered), no specialty pharmacy. " if g["buy_bill"] else "")
                      + ("Flagged as limited distribution by a payer/PBM list but no dispensing pharmacy named. " if n_ph == 0 and not g["buy_bill"] else "")
                      + "Pharmacy list = union of lists that carry it; confirm exclusivity and current network on the manufacturer HCP page."),
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
