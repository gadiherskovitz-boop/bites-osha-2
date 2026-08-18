"""Exports the unique companies behind the current Adzuna discovery scan to
a CSV for manual Clay enrichment - matches the company_name,company_domain
header convention already established in output/clay_test_companies.csv.

Domain is blank for every row here: unlike the 7 ATS-native boards
(pipeline/hiring_seed.py), Adzuna doesn't carry a company domain, so
that's exactly the gap Clay's manual enrichment step fills.
"""
import csv

from pipeline.hiring_scanner import scan_adzuna_hiring_signals

OUTPUT_PATH = "output/hiring_companies_for_clay.csv"


def main():
    signals = scan_adzuna_hiring_signals()
    companies = sorted({s["establishment_name"] for s in signals})

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["company_name", "company_domain"])
        for name in companies:
            writer.writerow([name, ""])

    print(f"{len(companies)} unique companies written to {OUTPUT_PATH}")
    for name in companies:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
