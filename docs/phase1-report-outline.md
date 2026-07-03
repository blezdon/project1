# CS 513 Phase-I Report — Chicago Food Inspection (CFI)

**Team-ID:** *[fill in]*  
**Team name:** *[fill in]*  

| Member | Illinois Email | Primary role |
|---|---|---|
| *[Name A]* | *[email@illinois.edu]* | Dataset description, S1/S4 testing |
| *[Name B]* | *[email@illinois.edu]* | SQL profiling, Python cleaning |
| *[Name C]* | *[email@illinois.edu]* | OpenRefine, screenshots |
| *[Name D]* | *[email@illinois.edu]* | Report assembly, S5 quantification |

**Dataset:** [Chicago Food Inspections](https://data.cityofchicago.org/Health-Human-Services/Food-Inspections/4ijn-s7e5)  
**Profiled:** July 3, 2026 | **Rows:** 312,740 | **Date range:** 2010-01-04 → 2026-07-02

---

## Report structure

Copy each section below into your final PDF. Files live in `docs/`.

| Section | Points | File |
|---|---|---|
| 1. Dataset description | 25 | [phase1-step1-dataset-description.md](phase1-step1-dataset-description.md) |
| 2. Use cases (U0, U1, U2) | 30 | [phase1-step2-use-cases.md](phase1-step2-use-cases.md) |
| 3. Data quality problems | 30 | [phase1-step3-data-quality.md](phase1-step3-data-quality.md) |
| 4. Phase-II plan (S1–S5) | 15 | [phase1-step4-phase2-plan.md](phase1-step4-phase2-plan.md) |

**Supporting materials:** [queries/profiling-queries.txt](../queries/profiling-queries.txt)

---

## Quick reference

### Main use case U1
Risk 1 restaurants, 2023–2025: failure rate by ZIP + top 10 violation codes.

### Zero-cleaning use case U0
Annual Pass vs Fail inspection counts — works on raw D.

### Never-enough use case U2
Real-time foodborne-illness risk per restaurant — impossible with D alone.

### Top data quality problems for U1
P1 non-operational results | P3 unparsed violations | P6 duplicates | P4/P5 missing type/risk

### Phase-II tools
OpenRefine + Python + SQL + YesWorkflow

---

## Submission checklist

- [ ] Header with Team-ID and all member emails
- [ ] Section 1: ER diagram figure + schema table + narrative
- [ ] Section 2: U0, U1, U2 each with paragraph + why cleaning does/doesn't apply
- [ ] Section 3: ≥6 DQ problems with evidence snippets/screenshots
- [ ] Section 3b: Necessity argument linking P1–P6 to U1
- [ ] Section 4: S1–S5 with owners and timeline
- [ ] Export single PDF; submit once on Coursera
