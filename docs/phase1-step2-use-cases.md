# Phase-I Report — Section 2: Use Cases

**Dataset:** Chicago Food Inspection (CFI)  
**Profiled on:** July 3, 2026

This section defines three use cases that illustrate when data cleaning matters — and when it does not.

| Use case | Label | Cleaning needed? |
|---|---|---|
| **U1** | Target (main) | **Yes** — necessary and sufficient |
| **U0** | Zero cleaning | **No** — D is good enough |
| **U2** | Never enough | **No** — cleaning cannot make D suitable |

---

## 2a. Target Use Case U1 — Cleaning Is Necessary and Sufficient (20 pts)

### Scenario

A Chicago public-health analyst wants to identify **ZIP codes with the highest restaurant inspection failure rates** and the **most common sanitation violations** among high-risk dining establishments, so CDPH can prioritize outreach and education in those areas.

### U1 (precise statement)

> For **Risk 1 restaurants** inspected between **January 1, 2023 and December 31, 2025**, compute:
>
> 1. **Q1:** The inspection **failure rate** (`Fail` / total operational inspections) for each ZIP code.
> 2. **Q2:** The **top 10 most frequently cited violation codes** citywide.
>
> Exclude establishments that are not operational at the time of inspection (`Out of Business`, `Not Ready`, `No Entry`, `Business Not Located`).

### Queries

```sql
-- Q1: Failure rate by ZIP (requires cleaned D′)
SELECT e.zip,
       COUNT(*)                                              AS total_inspections,
       SUM(CASE WHEN i.results = 'Fail' THEN 1 ELSE 0 END)  AS failures,
       ROUND(100.0 * SUM(CASE WHEN i.results = 'Fail' THEN 1 ELSE 0 END)
             / COUNT(*), 2)                                    AS fail_pct
FROM   inspection i
JOIN   establishment e ON i.license_num = e.license_num
WHERE  e.risk_level    = 1
  AND  e.facility_type = 'Restaurant'
  AND  i.inspection_date BETWEEN '2023-01-01' AND '2025-12-31'
  AND  i.is_operational = TRUE
GROUP  BY e.zip
ORDER  BY fail_pct DESC;

-- Q2: Top 10 violation codes (requires parsed violation table)
SELECT v.violation_code,
       COUNT(*) AS citation_count
FROM   violation v
JOIN   inspection i    ON v.inspection_id = i.inspection_id
JOIN   establishment e ON i.license_num   = e.license_num
WHERE  e.risk_level    = 1
  AND  e.facility_type = 'Restaurant'
  AND  i.inspection_date BETWEEN '2023-01-01' AND '2025-12-31'
  AND  i.is_operational = TRUE
GROUP  BY v.violation_code
ORDER  BY citation_count DESC
LIMIT  10;
```

### Why cleaning is **necessary**

Running Q1/Q2 on raw **D** produces **incorrect or misleading** answers because:

| Issue on raw D | Effect |
|---|---|
| P1: Non-operational `Results` included | Failure denominators are inflated (44,235 bad rows) |
| P3: `Violations` is unparsed text | Q2 cannot count violation codes at all |
| P6: Duplicate inspection rows | ZIP failure rates are skewed (up to 57× duplication) |
| P4/P5: Missing `Facility Type` / malformed `Risk` | Restaurant + Risk 1 filter silently drops or misclassifies rows |

**Example:** A naive failure-rate query on raw D for ZIP 60620 counts `Out of Business` rows in the denominator, lowering the apparent failure rate. Duplicate Pass rows for license 1354323 on 2010-06-07 (57 copies) would wildly distort any ZIP-level count if not deduplicated.

### Why cleaning is **sufficient**

All blockers are fixable from fields already in D:

- Classify operational vs non-operational results (P1)
- Parse `Violations` into one row per code (P3)
- Deduplicate on inspection key (P6)
- Normalize `Risk` and impute/drop null `Facility Type` (P4, P5)

No external data (health outcomes, revenue, real-time status) is required. After cleaning → **D′**, Q1 and Q2 return correct, fit-for-purpose answers.

### Expected deliverable after Phase-II

A table ranking ZIP codes by failure rate and a bar chart of the top 10 violation codes — both derived from **D′**.

---

## 2b. Zero-Cleaning Use Case U0 — D Is Good Enough (5 pts)

### Scenario

A journalist writing a short data brief wants a **high-level snapshot** of how many food inspections Chicago conducts each year and what share result in Pass vs Fail. No neighborhood drill-down, no violation-code parsing, and no entity resolution is needed.

### U0 (precise statement)

> **Q0:** For each calendar year from 2010 to 2025, report the **total number of inspections** and the **count of Pass vs Fail results** (ignoring all other result types).

### Query (works directly on raw D)

```sql
SELECT EXTRACT(YEAR FROM inspection_date) AS yr,
       COUNT(*)                            AS total_inspections,
       SUM(CASE WHEN results = 'Pass' THEN 1 ELSE 0 END) AS passes,
       SUM(CASE WHEN results = 'Fail' THEN 1 ELSE 0 END) AS fails
FROM   inspections
WHERE  results IN ('Pass', 'Fail')
GROUP  BY yr
ORDER  BY yr;
```

Equivalent SODA API call (no cleaning):

```
https://data.cityofchicago.org/resource/4ijn-s7e5.json
  ?$select=date_trunc_y(inspection_date,'year') as yr, results, count(*) as cnt
  &$where=results in ('Pass','Fail')
  &$group=yr,results
  &$order=yr DESC
```

### Why cleaning is **not necessary**

| Property | Why U0 is unaffected |
|---|---|
| `Results` values Pass/Fail are clean strings | No parsing needed; we explicitly ignore other values |
| Duplicates | At worst, year-level totals are slightly inflated — acceptable for a rough trend story |
| `Violations` text | Not used |
| `Facility Type` / `Risk` | Not used |
| Geocoding gaps | Not used |

The answer A = Q0(D) is **directionally correct**: Chicago conducts tens of thousands of inspections per year; Pass outnumbers Fail. A reader learns the right story without any wrangling.

### Sample output (live portal, recent years)

| Year | Pass | Fail |
|---|---|---|
| 2025 | ~tens of thousands | ~thousands |
| 2024 | similar order of magnitude | similar |

*(Exact counts available by running Q0 on download date.)*

### Takeaway

U0 reinforces that **cleaning should be purpose-driven**. For coarse annual aggregates on well-labeled categorical fields, raw D is fit-for-purpose.

---

## 2c. “Never Enough” Use Case U2 — Cleaning Cannot Make D Suitable (5 pts)

### Scenario

A food-delivery startup wants to build a **real-time “Is this restaurant safe to order from right now?”** feature that shows each establishment’s **current operating license status**, **most recent inspection outcome**, and **probability of causing foodborne illness** on any given day.

### U2 (precise statement)

> For every licensed restaurant in Chicago, provide:
>
> 1. **Q2a:** Whether the establishment is **currently open and licensed** (as of today).
> 2. **Q2b:** The **probability that a customer will contract a foodborne illness** if they eat there tomorrow.
> 3. **Q2c:** A **live risk score** updated within 24 hours of any inspection event.

### Why cleaning is **not sufficient** (even if it looks fixable at first)

At first glance, one might think: “Just clean the data, deduplicate rows, parse violations, and build the app.” But U2 requires information that **does not exist in D**, regardless of cleaning quality:

| Requirement | Available in D? | Gap |
|---|---|---|
| Current license status (today) | **No** | D records inspection events, not live licensing state. An establishment marked `Out of Business` in 2019 may have reopened under a new license. |
| Foodborne illness probability | **No** | D has inspector citations, not patient diagnoses or outbreak linkage. No health-outcome data. |
| Real-time status (< 24 h) | **No** | Portal updates daily; inspections occur on a schedule (weeks/months between visits). |
| Causal link violation → illness | **No** | Violation codes describe facility conditions, not downstream health effects. |

### What cleaning *could* do (and why it still fails U2)

Even a perfect **D′** with parsed violations, deduplicated rows, and normalized entities only gives:

- Historical inspection outcomes (days to months stale)
- Sanitation citation codes (not illness rates)
- A snapshot of past compliance (not current license validity)

**A = Q2(D′) would still be misleading** if presented as a real-time safety guarantee.

### What would actually be needed (outside scope of cleaning D)

| Additional data source | Purpose |
|---|---|
| Chicago BACP live license API/registry | Current license status |
| IL Dept. of Public Health outbreak reports | Illness case linkage |
| Real-time inspection feed or CDPH partnership | Sub-daily updates |
| Epidemiological model + labeled outcome data | Illness probability |

### Takeaway

U2 reinforces that **data cleaning is not a substitute for having the right data**. No amount of OpenRefine, SQL, or Python on the CFI inspection log can invent illness outcomes or real-time licensing state.

---

## Use case comparison (summary table for report)

| | U0 | U1 | U2 |
|---|---|---|---|
| **Question** | Annual Pass/Fail counts | ZIP failure rates + top violations | Real-time safety / illness risk |
| **Granularity** | Year × result | ZIP × violation code | Establishment × day |
| **Columns used** | `inspection_date`, `results` | Most columns + parsed violations | Columns not in D |
| **Cleaning needed?** | No | Yes | Insufficient even after cleaning |
| **Answer on raw D** | Correct enough | Incorrect / misleading | Impossible |

---

## Alignment with Section 3 (DQ problems)

Only **U1** depends on fixing problems P1, P3, P4, P5, and P6 documented in Section 3. U0 is unaffected by those problems at the chosen granularity. U2 fails for reasons beyond any problem listed in Section 3.
