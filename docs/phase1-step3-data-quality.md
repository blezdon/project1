# Phase-I Report — Section 3: Data Quality Problems

**Dataset:** Chicago Food Inspection (CFI)  
**Profiled on:** July 3, 2026  
**Total rows:** 312,740  
**Main use case (U1):** See below — required to justify why cleaning is necessary

---

## Main Use Case U1 (needed for Section 3b)

> **U1:** For **Risk 1 restaurants** inspected between **2023-01-01 and 2025-12-31**, compute (a) the **failure rate** by ZIP code and (b) the **top 10 most frequent violation codes** citywide. Exclude establishments that are not operational (Out of Business, Not Ready, No Entry, Business Not Located).

### U1 as SQL-style queries

```sql
-- Q1: Failure rate by ZIP for Risk 1 restaurants (2023–2025)
SELECT zip,
       COUNT(*) AS total_inspections,
       SUM(CASE WHEN results = 'Fail' THEN 1 ELSE 0 END) AS failures,
       ROUND(100.0 * SUM(CASE WHEN results = 'Fail' THEN 1 ELSE 0 END) / COUNT(*), 2) AS fail_pct
FROM   inspection_joined_establishment
WHERE  risk_level = 1
  AND  facility_type = 'Restaurant'
  AND  inspection_date BETWEEN '2023-01-01' AND '2025-12-31'
  AND  is_operational = TRUE
GROUP  BY zip
ORDER  BY fail_pct DESC;

-- Q2: Top 10 violation codes citywide (same filters)
SELECT violation_code,
       COUNT(*) AS citation_count
FROM   violation
JOIN   inspection i USING (inspection_id)
JOIN   establishment e USING (license_num)
WHERE  e.risk_level = 1
  AND  e.facility_type = 'Restaurant'
  AND  i.inspection_date BETWEEN '2023-01-01' AND '2025-12-31'
  AND  i.is_operational = TRUE
GROUP  BY violation_code
ORDER  BY citation_count DESC
LIMIT  10;
```

**Why this U1 fits CS 513:** Running Q1/Q2 on raw **D** produces misleading answers (wrong denominators, unparseable violations, miscounted duplicates). After cleaning to **D′**, the same queries yield correct ZIP-level failure rates and violation rankings — so cleaning is both **necessary** and **sufficient**.

---

## 3a. Obvious Data Quality Problems (with evidence)

We identified the following problems through portal sampling, SODA API profiling queries, and manual inspection of extreme values. Each entry includes evidence you can paste or screenshot into the final PDF.

---

### P1. Non-operational results mixed with real inspection outcomes

**Columns:** `Results`  
**Problem:** The `Results` field contains values that are **not inspection pass/fail outcomes** but administrative statuses. These must be excluded from failure-rate calculations.

| Results value | Count | % of all rows |
|---|---|---|
| Pass | 161,822 | 51.7% |
| Fail | 60,224 | 19.3% |
| Pass w/ Conditions | 46,459 | 14.9% |
| **Out of Business** | **25,697** | **8.2%** |
| **No Entry** | **13,956** | **4.5%** |
| **Not Ready** | **4,487** | **1.4%** |
| **Business Not Located** | **95** | **<0.1%** |

**Evidence (live samples):**

| DBA Name | Results |
|---|---|
| TEXICAN CHICAGO | Out of Business |
| KOMODO | Out of Business |
| MAYAS LITTLE SCHOOL | Not Ready |

**Impact on U1:** Including “Out of Business” rows in Q1 inflates denominators and depresses failure rates; “Not Ready” rows are not valid pass/fail outcomes.

---

### P2. Missing `Violations` on failed inspections

**Columns:** `Violations`, `Results`  
**Problem:** A failed inspection should cite at least one violation, but **3,628 Fail rows (6.0% of all Fail rows)** have a null `Violations` field. An additional **930 Pass w/ Conditions rows (2.0%)** also lack violation text.

**Evidence:**

| DBA Name | License # | Inspection Date | Results | Violations |
|---|---|---|---|---|
| UNICO LATIN FUSION CONTEMPORARY CUISINE | 3010969 | 2025-03-06 | Fail | *(null)* |
| THE PROMONTORY | 2269539 | 2014-06-05 | Fail | *(null)* |
| THE PROMONTORY | 2269541 | 2014-06-05 | Fail | *(null)* |

**Impact on U1:** Q2 cannot extract violation codes from null fields; top-10 rankings are undercounted.

---

### P3. `Violations` is semi-structured, multi-valued free text

**Columns:** `Violations`  
**Problem:** Multiple violations are packed into one cell, separated by ` | `. Each block embeds a numeric code, a regulatory title, and inspector comments. This is not queryable without parsing.

**Evidence (abbreviated):**

```
3. MANAGEMENT, FOOD EMPLOYEE AND CONDITIONAL EMPLOYEE; KNOWLEDGE,
   RESPONSIBILITIES AND REPORTING - Comments: NO EMPLOYEE HEALTH POLICY...
   | 38. INSECTS, RODENTS, & ANIMALS NOT PRESENT - Comments: REAR EXIT DOOR
   NOT COMPLETELY RODENT PROOFED...
```

(Full example from PATIO, Inspection ID 2639297, 2026-07-02.)

**Impact on U1:** Q2 requires splitting this field into one row per `violation_code`. Without parsing, violation frequency cannot be computed.

---

### P4. Missing `Facility Type` (5,347 rows, 1.7%)

**Columns:** `Facility Type`, `License #`  
**Problem:** 5,347 inspections have a null facility type, making the “Restaurant” filter in U1 unreliable.

**Evidence:**

| DBA Name | Facility Type | Risk | Results |
|---|---|---|---|
| NINO"S PIZZA | *(null)* | Risk 2 (Medium) | Fail |
| KOMODO | *(null)* | Risk 1 (High) | Out of Business |
| YAYA MAS GREEK KUZINA | *(null)* | Risk 1 (High) | Not Ready |

**Impact on U1:** These rows are silently dropped or misclassified when filtering `facility_type = 'Restaurant'`.

---

### P5. `Risk` stored as inconsistent text labels

**Columns:** `Risk`  
**Problem:** Risk is a text label, not an integer. Most values follow the pattern `Risk N (Level)`, but anomalies exist.

| Risk value | Count |
|---|---|
| Risk 1 (High) | 232,553 |
| Risk 2 (Medium) | 55,743 |
| Risk 3 (Low) | 24,269 |
| *(null)* | 89 |
| All | 86 |

**Impact on U1:** Filtering `risk_level = 1` requires parsing. Rows labeled `All` or null would be incorrectly included or excluded.

---

### P6. Duplicate / repeated inspection rows

**Columns:** `License #`, `Inspection Date`, `Results`, `Inspection ID`  
**Problem:** The portal disclaimer warns of possible duplicates. Profiling on (`license_`, `inspection_date`, `results`) shows extreme repetition:

| License # | Inspection Date | Results | Duplicate count |
|---|---|---|---|
| 1354323 | 2010-06-07 | Pass | **57** |
| 1354323 | 2013-11-14 | Out of Business | **47** |
| 1974745 | 2011-02-25 | Pass | **41** |

**Impact on U1:** Duplicates inflate inspection counts and skew failure rates in Q1.

---

### P7. Entity identification ambiguity (DBA vs AKA vs License #)

**Columns:** `DBA Name`, `AKA Name`, `License #`  
**Problem:** The public name (AKA) often differs from the legal name (DBA). One license maps to one establishment, but names vary across rows and time.

**Evidence:**

| DBA Name | AKA Name |
|---|---|
| PEAPOD, LLC. | PEAPOD |
| NEW MYLE ASIAN-CUISINE | JOY YEE |
| ILLINOIS SPORTSERVICE, INC. | GUARANTEED RATE FIELD |

Additionally, **2,423 rows (0.8%)** have a null `AKA Name` (e.g., MAYAS LITTLE SCHOOL).

**Impact on U1:** Less critical for Q1/Q2 (which aggregate by ZIP/code), but important if U1 is extended to establishment-level tracking.

---

### P8. Missing geocoordinates despite valid addresses

**Columns:** `Latitude`, `Longitude`, `Address`  
**Problem:** 1,035 rows (0.33%) lack latitude/longitude.

**Evidence:**

| DBA Name | Address | Latitude |
|---|---|---|
| Carver Military Academy | 13100 S Doty (1030E) | *(null)* |
| Remedy Chicago, Inc. | 970 Criss CIR | *(null)* |

**Impact on U1:** Minor for ZIP-based Q1 (zip is present), but blocks map-based extensions of U1.

---

### P9. Inconsistent address formatting

**Columns:** `Address`  
**Problem:** Addresses use heterogeneous formats: street-number ranges, parenthetical notes, inconsistent capitalization.

**Evidence:**

| DBA Name | Address |
|---|---|
| SALAAM RESTAURANT AND BAKERY | 700-706 W 79TH ST |
| MAPLEWOOD BREWING COMPANY | 2717-2719 N MAPLEWOOD AVE |
| Carver Military Academy | 13100 S Doty (1030E) |

**Impact on U1:** Low for ZIP aggregation; higher if geocoding or address matching is needed in Phase-II.

---

### P10. Pass results with violation text (domain inconsistency)

**Columns:** `Results`, `Violations`  
**Problem:** **121,764 Pass rows (75.2% of all Pass rows)** contain non-null violation text. Per CDPH documentation, “Pass” means no *critical or serious* violations (codes 1–14 and 15–29); general violations (30+) may still appear. This is domain knowledge, not a simple error — but it must be handled explicitly when defining “failure” and counting violations.

**Evidence (CUDDLE CARE — codes 31, 32, 35, 41 cited while Results = Pass):**

```
31. CLEAN MULTI-USE UTENSILS... | 32. FOOD AND NON-FOOD CONTACT SURFACES...
| 35. WALLS, CEILINGS... | 41. PREMISES MAINTAINED FREE OF LITTER...
```

**Impact on U1:** Q2 must count violation codes from Pass rows too (they are real citations), but Q1 must not treat Pass as Fail. Cleaning should normalize severity, not delete these rows.

---

## 3b. Why Data Cleaning Is Necessary to Support U1

### Claim

Data cleaning is **necessary** because executing U1 queries on raw **D** yields **incorrect and/or misleading** answers. Data cleaning is **sufficient** because the problems above are addressable without acquiring new data sources.

### Necessity argument (before vs after)

| Step | Problem | What goes wrong on raw D | Cleaning action for D′ |
|---|---|---|---|
| Filter | P1 | 44,235 non-operational rows pollute denominators | Add `is_operational` flag; exclude Out of Business, Not Ready, No Entry, Business Not Located |
| Filter | P4, P5 | Null/malformed Facility Type and Risk break restaurant/Risk-1 filters | Impute or drop null facility types; parse Risk to integer; quarantine `All`/null |
| Dedup | P6 | Up to 57× repeated rows per license+date | Deduplicate on (`inspection_id`) or (`license_`, `inspection_date`, `dba_name`, `results`) |
| Parse | P3 | Violations not countable | Split on `\|`, extract code with regex `^(\d+)\.` |
| Repair | P2 | 3,628 Fail rows contribute nothing to Q2 | Flag as incomplete; exclude from violation ranking or impute from related re-inspections |
| Normalize | P10 | Pass+violation rows misinterpreted as failures | Parse severity from code ranges (1–14 critical, 15–29 serious, 30+ general) |

### Concrete “before” example

Suppose we naively run on raw **D**:

```sql
-- NAIVE (wrong): counts all rows including Out of Business
SELECT zip, COUNT(*) AS n, AVG(results = 'Fail') AS fail_rate
FROM   raw_inspections
WHERE  risk = 'Risk 1 (High)' AND facility_type = 'Restaurant'
GROUP  BY zip;
```

Problems:
1. Rows with `Results = 'Out of Business'` are included → **denominator too large**
2. Duplicate Pass rows on 2010-06-07 for license 1354323 counted 57 times → **rates distorted**
3. `Violations` not parsed → **Q2 returns nothing**

### Concrete “after” example

On cleaned **D′**:

```sql
SELECT z.zip, COUNT(*) AS n,
       ROUND(100.0 * SUM(i.results = 'Fail') / COUNT(*), 2) AS fail_pct
FROM   inspection i
JOIN   establishment e ON i.license_num = e.license_num
JOIN   zip_lookup z ON e.zip = z.zip
WHERE  e.risk_level = 1
  AND  e.facility_type = 'Restaurant'
  AND  i.is_operational = TRUE
  AND  i.inspection_date BETWEEN '2023-01-01' AND '2025-12-31'
GROUP  BY z.zip;
```

Plus Q2 on normalized `violation` table → correct top-10 codes.

### Sufficiency argument

All blockers for U1 are present **in the data itself** (formatting, duplicates, missing parses) — not missing external facts. No additional dataset is needed to:
- classify operational vs non-operational results,
- parse violation codes from existing text,
- deduplicate repeated rows,
- normalize risk and facility type.

Therefore, a well-defined cleaning workflow (Phase-II S2–S5) can produce **D′** on which U1 is **fit-for-purpose**.

---

## Summary table for the report

| ID | Problem | Severity for U1 | Rows affected |
|---|---|---|---|
| P1 | Non-operational Results values | **High** | 44,235 |
| P2 | Fail without Violations | **High** | 3,628 |
| P3 | Unparsed Violations text | **Critical** | ~224,784 non-null cells |
| P4 | Missing Facility Type | **Medium** | 5,347 |
| P5 | Risk as text + anomalies | **Medium** | 175 anomalous |
| P6 | Duplicate inspections | **High** | Unknown (57 max per group) |
| P7 | DBA/AKA ambiguity | Low | 2,423 null AKA |
| P8 | Missing geocoordinates | Low | 1,035 |
| P9 | Address format inconsistency | Low | Qualitative |
| P10 | Pass rows with violation text | **Medium** | 121,764 |

---

## Screenshots / snippets checklist for PDF

- [ ] P1: Facet on `Results` in OpenRefine showing non-operational values
- [ ] P2: Filter `Results = Fail` AND `Violations` is blank — paste 3 rows
- [ ] P3: One full `Violations` cell with pipe separators highlighted
- [ ] P4: Blank `Facility Type` facet count (5,347)
- [ ] P6: Duplicate group for license 1354323 on 2010-06-07
- [ ] P10: CUDDLE CARE Pass row with violation codes 31–41
