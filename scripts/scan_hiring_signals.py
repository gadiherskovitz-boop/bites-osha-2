from pipeline.hiring_scanner import scan_hiring_signals
from pipeline.site_count import lookup_site_count
from pipeline.tiering import tier_for_lookup


def _tier_line(company_name: str) -> str:
    lookup = lookup_site_count(company_name)
    tier = tier_for_lookup(lookup)
    if lookup["value"] is None:
        return f"{tier} (unresolved, default)"
    return f"{tier} ({lookup['value']:,} sites, {lookup['confidence']})"


def main():
    signals = scan_hiring_signals()

    print(f"Hiring triggers (live boards, trailing 100 days): {len(signals)}")
    for s in signals:
        print(
            f"  [{s['relevance_reason']}] {s['posted_date']} {s['establishment_name']} - "
            f"{s['job_title']} ({s['ats_source']}) - {_tier_line(s['establishment_name'])} - {s['source_url']}"
        )
    if not signals:
        print(
            "  (none right now - only 4 boards are known, see pipeline/hiring_seed.py, "
            "and leadership L&D/HR reqs don't open often; filter itself is verified "
            "against synthetic cases, see docs/hiring_signal_scope.md)"
        )


if __name__ == "__main__":
    main()
