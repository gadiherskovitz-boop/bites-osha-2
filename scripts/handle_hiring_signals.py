import sys

from pipeline.hiring_scanner import scan_hiring_signals
from pipeline.signal_handler import handle_hiring_signal

# Same safety pattern as scripts/handle_signals.py - no checkpoint tracking
# of already-handled postings, so a manual run stays capped by default.
DEFAULT_LIMIT = 3


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    signals = scan_hiring_signals()
    print(f"{len(signals)} Hiring signals found this run - handling the first {limit}\n")

    for signal in signals[:limit]:
        # Same isolation as scripts/handle_signals.py - one signal's failure
        # must not silently take the whole batch down with it.
        try:
            result = handle_hiring_signal(signal)
        except Exception as e:
            print(f"[Hiring] {signal['establishment_name']} - {signal['job_title']} -> FAILED: {e}")
            continue
        print(
            f"[Hiring] {signal['establishment_name']} - {signal['job_title']} -> "
            f"company {result['company_id']}, {result['tier']}, "
            f"sequence_enrollment={result['sequence_enrollment']}, "
            f"tier1_first_touch={result['tier1_first_touch']}"
        )


if __name__ == "__main__":
    main()
