from pipeline.signal_scanner import scan_inspections, scan_violations


def main():
    inspections = scan_inspections()
    violations = scan_violations()

    print(f"Inspection triggers (trailing 100 days): {len(inspections)}")
    for s in inspections[:10]:
        print(
            f"  [{s['insp_subtype']:9s}] {s['open_date']} {s['establishment_name']} "
            f"({s['state']}, NAICS {s['naics']}) - {s['activity_nr']}"
            f"{' [open]' if s['is_open'] else ''}"
        )

    print(f"\nViolation triggers (trailing 100 days): {len(violations)}")
    for s in violations[:10]:
        print(
            f"  [{s['citation_type']:8s}] {s['issuance_date']} {s['establishment_name']} "
            f"({s['state']}) - {s['standard_cited']} - ${s['current_penalty']:,.0f} "
            f"- relevant: {s['relevance_reason']}"
        )


if __name__ == "__main__":
    main()
