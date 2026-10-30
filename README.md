# LDD Watch

A free, open directory of **limited-distribution drugs (LDDs)** and the specialty pharmacies that can dispense them,
plus a local tool that flags LDDs in your own prior-auth or claims exports.

Everything runs on free tiers: GitHub (repo, Actions, Pages), openFDA (public API), and a weekly research pass.
No member or claims data ever leaves your machine.

## Layout

| Path | What |
|---|---|
| `data/ldd.json` | The directory. One record per drug. Public information only. |
| `schema/ldd.schema.json` | JSON Schema every record must satisfy. |
| `scripts/validate.py` | Schema + review-rule check. Runs on every PR. |
| `scripts/check_fda_approvals.py` | Weekly openFDA pull for new approvals → opens a `research` issue. |
| `scripts/match_claims.py` | **Local only.** Joins your CSV export against the directory. |
| `agent/RESEARCH_PROMPT.md` | Instructions the weekly research agent follows to draft records. |
| `docs/index.html` | Static search site (GitHub Pages). |
| `.github/workflows/` | `weekly-fda-check`, `validate`, `pages`. |

## Workflow

1. **Monday**: Actions queries openFDA for original approvals in the last 21 days, drops anything already tracked,
   opens an issue labeled `research`.
2. **Research agent** (scheduled Claude task) reads the issue, researches each drug per `agent/RESEARCH_PROMPT.md`,
   opens a PR with `status: draft` records.
3. **You**: review the PR. If a manufacturer source confirms the pharmacy list, set `status: verified`,
   `verified_by`, `verified_date`. Merge. `validate.py` blocks merges that break the rules.
4. **Pages** redeploys on merge. Search at `https://<you>.github.io/ldd-watch/`.
5. **Matching**: export PA requests / rejected claims to CSV and run
   `python scripts/match_claims.py export.csv` on your machine. Output `hits.csv` lists the member rows that
   hit an LDD with the pharmacy contact.

## Setup (one time, ~10 minutes)

```bash
# 1. create an empty PUBLIC repo on GitHub named ldd-watch, then:
cd ldd-watch
git init -b main
git add .
git commit -m "LDD Watch v1"
git remote add origin https://github.com/<you>/ldd-watch.git
git push -u origin main

# 2. GitHub → repo Settings → Pages → Source: "GitHub Actions"
# 3. GitHub → repo → Issues → Labels → create label "research"
# 4. GitHub → Actions → "Weekly FDA approval check" → Run workflow   (first run seeds .fda_seen.json)
```

Optional: an openFDA API key (free, instant) raises rate limits. Add it as repo secret `OPENFDA_API_KEY`.

## Local matching

```bash
pip install jsonschema          # only needed for validate.py
python scripts/match_claims.py my_pa_export.csv
python scripts/match_claims.py my_pa_export.csv --remote https://raw.githubusercontent.com/<you>/ldd-watch/main/data/ldd.json
```

Accepted columns (case-insensitive): `ndc`, and/or `drug_name` / `drug` / `medication` / `product`.
All other columns pass through to `hits.csv`.

## Record rules

- `status: verified` requires a reviewer, a date, and a `manufacturer`-type source.
- `exclusive` means exactly one pharmacy; `open` means none listed.
- No phone, fax, or URL is ever entered unless it appears on a cited source.
- Records re-verify every 90 days (exclusive/limited) or 180 days (open).

## Disclaimer

Compiled from public manufacturer, pharmacy, and FDA sources. Confirm with the manufacturer or pharmacy before
acting on it for a patient. Not affiliated with any manufacturer, pharmacy, or PBM.
