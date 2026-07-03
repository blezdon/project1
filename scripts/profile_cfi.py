#!/usr/bin/env python3
"""
CS 513 — Chicago Food Inspection profiling and cleaning helpers.
Usage:
  python scripts/profile_cfi.py Food_Inspections.csv
  python scripts/profile_cfi.py Food_Inspections.csv --clean -o cleaned/
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

OPERATIONAL = {"Pass", "Fail", "Pass w/ Conditions"}
NON_OPERATIONAL = {"Out of Business", "No Entry", "Not Ready", "Business Not Located"}
VIOLATION_PATTERN = re.compile(
    r"(\d+)\.\s+([^-|]+?)(?:\s*-\s*Comments:\s*(.+?))?(?=\s*\||\s*$)",
    re.DOTALL,
)
RISK_MAP = {
    "Risk 1 (High)": 1,
    "Risk 2 (Medium)": 2,
    "Risk 3 (Low)": 3,
}


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def profile(df: pd.DataFrame) -> None:
    print(f"Shape: {df.shape[0]:,} rows × {df.shape[1]} columns\n")

    print("--- Null counts ---")
    for col in df.columns:
        n = df[col].isna().sum()
        if n:
            print(f"  {col}: {n:,} ({100 * n / len(df):.2f}%)")

    if "Results" in df.columns:
        print("\n--- Results distribution ---")
        print(df["Results"].value_counts().to_string())

    if "Results" in df.columns and "Violations" in df.columns:
        fail_no_v = ((df["Results"] == "Fail") & df["Violations"].isna()).sum()
        print(f"\n--- IC: Fail without violations: {fail_no_v:,} ---")

    key = [c for c in ["License #", "Inspection Date", "Results"] if c in df.columns]
    if len(key) == 3:
        dup = df.groupby(key).size()
        print(f"\n--- Duplicate groups (license+date+result): {(dup > 1).sum():,} ---")
        print(f"    Max group size: {dup.max()}")

    if "Risk" in df.columns and "Facility Type" in df.columns:
        mask = (
            (df["Risk"] == "Risk 1 (High)")
            & (df["Facility Type"] == "Restaurant")
            & (df["Results"].isin(OPERATIONAL))
        )
        if "Inspection Date" in df.columns:
            dates = pd.to_datetime(df["Inspection Date"], errors="coerce")
            mask &= dates.between("2023-01-01", "2025-12-31")
        print(f"\n--- U1 candidate rows (Risk 1 restaurant, operational, 2023-25): {mask.sum():,} ---")


def parse_violations(text: str) -> list[dict]:
    if pd.isna(text) or not str(text).strip():
        return []
    parts = str(text).split(" | ")
    records = []
    for part in parts:
        m = re.match(r"(\d+)\.\s+(.+)", part.strip(), re.DOTALL)
        if not m:
            continue
        code = int(m.group(1))
        rest = m.group(2)
        if " - Comments: " in rest:
            title, comments = rest.split(" - Comments: ", 1)
        else:
            title, comments = rest, ""
        severity = (
            "Critical" if code <= 14 else "Serious" if code <= 29 else "General"
        )
        records.append(
            {
                "violation_code": code,
                "violation_title": title.strip(),
                "inspector_comments": comments.strip(),
                "severity": severity,
            }
        )
    return records


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = df.copy()
    out.columns = [c.strip().replace(" ", "_").lower() for c in out.columns]
    out = out.rename(columns={"license_#": "license_num", "zip": "zip_code"})

    if "results" in out.columns:
        out["is_operational"] = out["results"].isin(OPERATIONAL)

    if "risk" in out.columns:
        out["risk_level"] = out["risk"].map(RISK_MAP)

    before = len(out)
    if "inspection_id" in out.columns:
        out = out.drop_duplicates(subset=["inspection_id"], keep="first")
    print(f"Deduplicated: {before - len(out):,} rows removed")

    violations = []
    for _, row in out.iterrows():
        iid = row.get("inspection_id")
        for v in parse_violations(row.get("violations")):
            violations.append({"inspection_id": iid, **v})
    vdf = pd.DataFrame(violations)
    return out, vdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile and optionally clean CFI data")
    parser.add_argument("csv", type=Path, help="Path to Food_Inspections.csv")
    parser.add_argument("--clean", action="store_true", help="Run cleaning pipeline")
    parser.add_argument("-o", "--output", type=Path, help="Output directory for cleaned files")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"File not found: {args.csv}", file=sys.stderr)
        return 1

    df = load_csv(args.csv)
    profile(df)

    if args.clean:
        if not args.output:
            print("--output required with --clean", file=sys.stderr)
            return 1
        args.output.mkdir(parents=True, exist_ok=True)
        cleaned, violations = clean(df)
        cleaned.to_csv(args.output / "inspection_cleaned.csv", index=False)
        violations.to_csv(args.output / "violation.csv", index=False)
        print(f"\nWrote {args.output / 'inspection_cleaned.csv'}")
        print(f"Wrote {args.output / 'violation.csv'} ({len(violations):,} violation rows)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
