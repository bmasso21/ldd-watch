#!/usr/bin/env python3
"""Validate data/ldd.json against schema/ldd.schema.json and enforce review rules.

Rules beyond the schema:
  - ids are unique
  - status 'verified' requires verified_by, verified_date, and at least one 'manufacturer' source
  - distribution_type 'exclusive' requires exactly one pharmacy
  - distribution_type 'open' requires zero pharmacies
Exit code 1 on any failure (so it can gate pull requests).
"""
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("pip install jsonschema", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ldd.json"
SCHEMA = ROOT / "schema" / "ldd.schema.json"


def main() -> int:
    data = json.loads(DATA.read_text())
    schema = json.loads(SCHEMA.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    errors = []

    seen = set()
    for i, drug in enumerate(data.get("drugs", [])):
        label = drug.get("id") or drug.get("brand") or f"#{i}"
        for err in validator.iter_errors(drug):
            path = "/".join(str(p) for p in err.absolute_path) or "(root)"
            errors.append(f"{label}: {path}: {err.message}")

        if drug.get("id") in seen:
            errors.append(f"{label}: duplicate id")
        seen.add(drug.get("id"))

        if drug.get("status") == "verified":
            if not drug.get("verified_by") or not drug.get("verified_date"):
                errors.append(f"{label}: verified requires verified_by and verified_date")
            if not any(s.get("type") == "manufacturer" for s in drug.get("sources", [])):
                errors.append(f"{label}: verified requires a manufacturer-type source")

        dt = drug.get("distribution_type")
        n = len(drug.get("pharmacies", []))
        if dt == "exclusive" and n != 1:
            errors.append(f"{label}: exclusive must list exactly one pharmacy (has {n})")
        if dt == "open" and n != 0:
            errors.append(f"{label}: open must list no pharmacies (has {n})")

    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} error(s)")
        return 1
    print(f"OK: {len(data.get('drugs', []))} record(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
