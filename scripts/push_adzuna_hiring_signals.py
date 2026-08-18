"""One-off live push for the Adzuna discovery layer's current clean result
set - pushes every signal scan_adzuna_hiring_signals() returns right now,
no default limit (unlike scripts/handle_hiring_signals.py's DEFAULT_LIMIT
safety cap), per an explicit 2026-08-18 request to push the full clean
list rather than a capped batch. One signal per posting, not deduped per
company - multiple postings from the same company each get their own
qsr_signal/Note/Slack message and converge onto the same Company record
via upsert_signal_company's existing dedup, same behavior the OSHA path
already relies on.
"""
from pipeline.hiring_scanner import scan_adzuna_hiring_signals
from pipeline.signal_handler import handle_hiring_signal


def main():
    signals = scan_adzuna_hiring_signals()
    print(f"Pushing {len(signals)} Adzuna-discovered Hiring signals\n")

    for signal in signals:
        result = handle_hiring_signal(signal)
        print(
            f"[Hiring] {signal['establishment_name']} - {signal['job_title']} -> "
            f"company {result['company_id']}, {result['tier']}"
        )


if __name__ == "__main__":
    main()
