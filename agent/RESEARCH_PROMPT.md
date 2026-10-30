# LDD research agent — weekly instructions

You are researching limited-distribution status for newly approved drugs and producing
draft records for `data/ldd.json` in the `ldd-watch` repository.

## Inputs
1. Open GitHub issues labeled `research` (created by the weekly FDA check). Each lists drugs to research.
2. Existing records in `data/ldd.json` whose `next_review_date` is within the next 14 days (re-verification).

## For each drug, check in this order
1. **Manufacturer product site**, HCP section: pages titled "Access", "How to obtain", "Specialty pharmacy",
   "Distribution", "Ordering", or the patient-support/hub program page. This is the only source that can
   support `confidence: high`.
2. **Press releases**: search `"<brand>" specialty pharmacy partner` and `"<brand>" limited distribution`
   on GlobeNewswire, BusinessWire, PR Newswire. Pharmacy announcements prove inclusion, not exclusivity.
3. **Pharmacy LDD lists** (public pages): Onco360, Biologics by McKesson, Accredo, CVS Specialty,
   Optum Specialty, Walgreens Specialty, Orsini, PANTHERx Rare, AllianceRx, Amber Specialty, Senderra, AcariaHealth.
4. **REMS@FDA** (fda.gov REMS database): if the drug has a REMS with certified-pharmacy requirements, set `rems: true`
   and note the certification requirement.
5. **openFDA NDC directory**: pull NDCs for the brand (`/drug/ndc.json?search=brand_name:"<brand>"`).

## Classification
- `exclusive`: manufacturer or hub page names exactly one pharmacy, or language like "available only through".
- `limited_network`: a named list of two or more pharmacies; or one pharmacy announcement with no exclusivity language.
- `open`: manufacturer says available at any pharmacy / wholesaler; or a non-specialty drug.
- `unknown`: nothing found. Still create the record so the drug is tracked; set `confidence: low`.

## Confidence
- `high`: manufacturer-type source confirms the pharmacy list.
- `medium`: pharmacy or press-release source only.
- `low`: inference or nothing found.

## Rules
- Never set `status: verified`. Drafts only; a human verifies by merging and editing status.
- Never invent phone numbers, fax numbers, or URLs. Leave `null` if not found on the source page.
- Every record needs at least one source with `url`, `type`, `date_checked` (today).
- `next_review_date` = today + 90 days for exclusive/limited; + 180 days for open.
- Non-specialty approvals (ordinary oral generics, OTC switches, cosmetic indications) may be marked `open`
  with `confidence: medium` from the FDA source alone.

## Output
1. Validate the merged JSON locally (`python scripts/validate.py`).
2. Open one pull request per issue, branch `research/<issue-number>`, title `Draft LDD records: <issue title>`.
   The PR body lists each drug, its classification, confidence, and the one source that most justifies it.
3. Comment on the issue with the PR link and close nothing; the reviewer closes the issue on merge.
4. For re-verifications, edit the existing record (update `sources[].date_checked`, `next_review_date`,
   and anything that changed) in a PR titled `Re-verify: <brand>`.

## Example (Rasonque / daraxonrasib)
- Onco360 press release says "selected as a national pharmacy partner" → inclusion, not exclusivity → `limited_network`, `confidence: medium`, source type `press_release`.
- To reach `high`, the rasonque.com (ON)Path / HCP access page must list the network.
