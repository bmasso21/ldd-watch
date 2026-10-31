#!/usr/bin/env python3
"""Apply researcher verification output (agent/verify/outNN.json) and the pharmacy contact
directory (agent/verify/pharmacy_directory.json) to data/ldd.json.

Verification objects: {brand, generic, manufacturer, pharmacies:[{name, source_url, source_type,
exclusive_claimed}], hub_program, rems, buy_and_bill, manufacturer_page_found, conflict_note, notes}

Rules applied:
  - add pharmacies/sources not already on the record (names normalized via merge_raw.canon_pharmacy)
  - manufacturer_page_found -> confidence high (still status draft; a human flips to verified)
  - single pharmacy + exclusive_claimed true from a manufacturer/press source -> distribution_type exclusive
  - buy_and_bill true and no SP named by a manufacturer source -> distribution_type open, note says buy-and-bill
  - conflicts/notes appended to notes, never silently resolved
  - directory: fill phone/fax/enrollment_url on every pharmacy entry whose name matches canonical or alias
Usage: apply_verification.py --today YYYY-MM-DD agent/verify/out*.json [--directory agent/verify/pharmacy_directory.json]
"""
import argparse
import importlib.util
import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ldd.json"
spec = importlib.util.spec_from_file_location("merge_raw", ROOT / "scripts" / "merge_raw.py")
mr = importlib.util.module_from_spec(spec); spec.loader.exec_module(mr)

norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
STYPES = {"manufacturer", "pharmacy", "press_release", "fda", "pbm", "other"}


def apply_record(d, v, today):
    changed = []
    if v.get("generic") and (not d.get("generic") or d["generic"] == d["brand"]):
        d["generic"] = v["generic"]; changed.append("generic")
    if v.get("manufacturer") and d.get("manufacturer") in (None, "", "unknown"):
        d["manufacturer"] = v["manufacturer"]; changed.append("manufacturer")
    have = {p["name"] for p in d["pharmacies"]}
    have_src = {s["url"] for s in d["sources"]}
    mfr_excl = []
    for p in v.get("pharmacies") or []:
        cp = mr.canon_pharmacy(p.get("name"))
        if not cp:
            continue
        label, url = cp
        if label not in have:
            d["pharmacies"].append({"name": label, "phone": None, "fax": None, "enrollment_url": url, "notes": None})
            have.add(label); changed.append(f"+{label}")
        su = p.get("source_url")
        if su and su not in have_src:
            t = p.get("source_type") if p.get("source_type") in STYPES else "other"
            d["sources"].append({"url": su, "type": t, "date_checked": today, "note": f"verification: {label}" + (" (exclusive)" if p.get("exclusive_claimed") else "")})
            have_src.add(su)
        if p.get("exclusive_claimed") is True and p.get("source_type") in ("manufacturer", "press_release", "pbm"):
            mfr_excl.append(label)
    hub = v.get("hub_program")
    if hub and isinstance(hub, dict) and any(hub.get(k) for k in ("name", "phone", "url")) and not d.get("hub_program"):
        d["hub_program"] = {"name": hub.get("name"), "phone": hub.get("phone"), "url": hub.get("url")}; changed.append("hub")
    if v.get("rems") is True and not d.get("rems"):
        d["rems"] = True; changed.append("rems")
    if v.get("manufacturer_page_found"):
        d["confidence"] = "high"; changed.append("conf=high")
    if mfr_excl and len(d["pharmacies"]) == 1 and d["distribution_type"] != "exclusive":
        d["distribution_type"] = "exclusive"; changed.append("type=exclusive")
    elif mfr_excl and len(d["pharmacies"]) > 1 and d["distribution_type"] == "exclusive":
        d["distribution_type"] = "limited_network"; changed.append("type=limited_network")
    if v.get("buy_and_bill") is True and not any(p.get("source_type") == "manufacturer" for p in (v.get("pharmacies") or [])):
        if d["distribution_type"] != "open":
            d["distribution_type"] = "open"; changed.append("type=open(buy-and-bill)")
            d["pharmacies"] = []
    notes = []
    if v.get("conflict_note"):
        notes.append(f"CONFLICT: {v['conflict_note']}")
    if v.get("notes"):
        notes.append(v["notes"])
    if notes:
        d["notes"] = ((d.get("notes") or "").rstrip() + f" Verification {today}: " + " ".join(notes)).strip()
    d["next_review_date"] = (date.fromisoformat(today) + timedelta(days=180 if d["distribution_type"] == "open" else 90)).isoformat()
    return changed


def apply_directory(drugs, directory):
    lookup = {}
    for e in directory:
        if e.get("is_pharmacy") is False:
            continue
        names = [e.get("canonical_name")] + (e.get("aliases") or [])
        for n in names:
            if n:
                lookup[norm(n)] = e
    filled = 0
    for d in drugs:
        for p in d["pharmacies"]:
            e = lookup.get(norm(p["name"]))
            if not e:
                continue
            for k_rec, k_dir in (("phone", "intake_phone"), ("fax", "intake_fax"), ("enrollment_url", "enrollment_url")):
                if not p.get(k_rec) and e.get(k_dir):
                    p[k_rec] = e[k_dir]; filled += 1
            if not p.get("enrollment_url") and e.get("website"):
                p["enrollment_url"] = e["website"]; filled += 1
    return filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outputs", nargs="*")
    ap.add_argument("--directory", default=None)
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()
    data = json.loads(DATA.read_text())
    idx = {norm(d["brand"]): d for d in data["drugs"]}
    applied = unmatched = 0
    log = []
    for f in a.outputs:
        for v in json.loads(Path(f).read_text()):
            d = idx.get(norm(v.get("brand")))
            if not d:
                unmatched += 1; log.append(f"UNMATCHED {v.get('brand')}"); continue
            ch = apply_record(d, v, a.today)
            applied += 1
            if ch:
                log.append(f"{d['brand']}: {', '.join(ch)}")
    filled = 0
    if a.directory:
        filled = apply_directory(data["drugs"], json.loads(Path(a.directory).read_text()))
    data["meta"]["last_updated"] = a.today
    DATA.write_text(json.dumps(data, indent=2) + "\n")
    print("\n".join(log))
    print(f"\napplied={applied} unmatched={unmatched} directory_fields_filled={filled}")


if __name__ == "__main__":
    main()
