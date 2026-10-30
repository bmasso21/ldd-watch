# Bulk-load sources (checked 2026-10-29)

Lists that assert limited-distribution status. Re-scrape quarterly; the first two are the most
complete machine-readable public lists and should be the standing re-verification inputs.

| Source | Date | Rows | Drug → pharmacy? | URL |
|---|---|---|---|---|
| Express Scripts – TRICARE Specialty Program LDD list | Oct 2026 | 215 | yes (1–8 pharmacies each) | https://www.express-scripts.com/pdf/mrx/TRICARE-Specialty-Program-LDD.pdf |
| Florida Blue – Limited Distribution Drugs | 10/1/2026 | 629 | yes (contracted pharmacy or "Buy and Bill") | https://www.bcbsfl.com/DocumentLibrary/Providers/Content/Rx_LimitedDistributionDrugs.pdf |
| BCBS Michigan – Specialty Drug Program Member Guide (LD section) | Oct 2026 | 210 | yes | https://www.bcbsm.com/amslibs/content/dam/public/consumer/forms-documents/pharmacy/specialty-drug-program-member-guide.pdf |
| Prime Therapeutics – Self-Administered Specialty DML (`*` = Prime LDN) | 10/1/2026 | 387 | no (flag only) | https://www.myprime.com/content/dam/prime/memberportal/WebDocs/Other/SpecialtyDMLs/PrimeTherapeutics_Self_Admin_DML.pdf |
| Onco360 – Limited Distribution Oncology Medications | live page | 157 | pharmacy = Onco360; manufacturer given | https://onco360.com/oncology-medications/limited-distribution-oncology-medications/ |
| Biologics by McKesson – LDN Guide (`+` limited, `•` exclusive) | 7/29/2024 | 105 | pharmacy = Biologics | https://biologics.mckesson.com/wp-content/uploads/2024/07/Biologics-Inventory-LDN-Guide-7.29.24.pdf |
| Optum Specialty – Limited distribution drugs serviced at Optum | Nov 2020 (stale) | 186 | pharmacy = Optum | https://specialty-ctc.optum.com/content/dam/optum3/specialtyrx/images/pharma/opt3586931_201111_b2b_limiteddistributiondrugs_final.pdf |
| Optum – new drug approvals / limited distribution access | 2026 | 16 | pharmacy = Optum / Optum Frontier | https://business.optum.com/en/pharmacy-services/specialty/pharmaceutical-manufacturer-support/new-drug-approvals.html |
| Blue Shield of California – Commercial Specialty Drug List | May 2026 | 4 | yes | https://www.blueshieldca.com/content/dam/bsca/en/member/docs/2026/pharmacy/Commercial-Specialty-Drug-List-STANDARD-EN.pdf |
| Press releases (Orsini, PANTHERx, Walgreens/AllianceRx, Amber, Pfizer LDN) | various | ~70 | yes, with exclusivity wording | see per-record sources |

General catalogs (drugs a pharmacy stocks; NOT LDD assertions). Used only to add a pharmacy to a
drug already established above — see `GENERAL_CATALOG_PATTERNS` in `scripts/merge_raw.py`.

| Source | Date | Rows | URL |
|---|---|---|---|
| CVS Specialty – Specialty Pharmacy Distribution Drug List | v10012026 | 759 | https://www.cvsspecialty.com/education-center/downloads/SpecialtyDrugs.pdf |
| Orsini – medication search / sitemap | live | 96 | https://www.orsini.com/medication-search/ |
| Amber Specialty – oncology / rare disease pages | live | 66 | https://www.amberpharmacy.com/specialties/oncology/ |
| Health Alliance – High Cost Medical Drugs (preferred vendor) | 2022–2025 | 291 | https://healthalliance.org/documents/745 |

## Not retrievable by automation (manual download worth doing)

- Capital Blue Cross – Limited Distribution Drug List, Jan 2026 (full drug → pharmacy table): https://www.capbluecross.com/wps/wcm/connect/prod_nws.capblue.com29556/f9a326a0-16bf-4639-a694-e11fa462c1fb/jan-2026-limited-distribution-drug-list.pdf?MOD=AJPERES&CVID=pHGUjK6
- CVS Specialty rare-disease LDD page (~220 rare LDDs): https://www.cvsspecialty.com/pharma/raredisease.html
- pantherxrare.com (entire site), accredo.com/medications, walgreensspecialtyrx.com, acariahealth.com — all block automated fetch.
- Accredo, PANTHERx and Walgreens publish no public LDD list; the TRICARE list is the proxy for their networks.

## Known gaps in the bulk load

- Generic names and manufacturers are mostly missing (payer lists print brand only). Onco360 and Biologics rows carry them.
- `exclusive` is set only where a source used exclusivity language (Biologics `•`, Optum Ryoncil, press releases). Many single-pharmacy payer rows are probably exclusive but are left `limited_network`.
- Records with `unknown` and no pharmacy come from Prime's LDN flag or payer rows naming only an internal program (Florida Blue "Advocate+ Pharmacy Match").
