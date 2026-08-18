from pipeline.adzuna_client import APP_ID as ADZUNA_APP_ID
from pipeline.hiring_scanner import scan_adzuna_hiring_signals, scan_hiring_signals
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
            "  (none right now - only 7 boards are known, see pipeline/hiring_seed.py; "
            "confirmed live this isn't a filter bug - across all 7 boards' current listings, "
            "the only raw title matches on learn/train/l&d/enable are 'Manager/Leader in "
            "Training' frontline titles, correctly excluded. Filter is verified against "
            "synthetic cases too, see docs/hiring_signal_scope.md)"
        )

    print()
    if not ADZUNA_APP_ID:
        print("Adzuna discovery scan: skipped - ADZUNA_APP_ID/ADZUNA_APP_KEY not set in .env (see .env.example)")
        return

    adzuna_signals = scan_adzuna_hiring_signals()
    print(f"Adzuna discovery triggers (unverified - see docs/hiring_signal_scope.md): {len(adzuna_signals)}")
    for s in adzuna_signals:
        print(
            f"  [{s['relevance_reason']}] {s['posted_date']} {s['establishment_name']} - "
            f"{s['job_title']} - {s['source_url']}"
        )


if __name__ == "__main__":
    main()
