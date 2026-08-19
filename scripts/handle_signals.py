import sys

from pipeline.signal_handler import handle_signal
from pipeline.signal_scanner import scan_inspections, scan_violations

# A fresh scan_inspections()/scan_violations() run against the full 100-day
# window returns the whole backlog (268 Inspection signals alone, as of
# 2026-08-17) - a real deployment would run this frequently against that same
# trailing window, so each run only ever sees the handful of signals that are
# genuinely new since the last run. There's no "already scanned" checkpoint
# built here (out of scope for Task #6), so running this against the full
# backlog would push that many real Slack messages at once. DEFAULT_LIMIT
# keeps a manual run safe; raise it deliberately once you're ready for a
# larger batch.
DEFAULT_LIMIT = 3


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LIMIT

    signals = scan_inspections() + scan_violations()
    print(f"{len(signals)} signals found this run - handling the first {limit}\n")

    for signal in signals[:limit]:
        label = signal.get("insp_subtype", signal["signal_type"])
        # One signal's failure (a HubSpot/Slack/Claude error - rate limit,
        # network blip, malformed response) must not silently take the
        # whole batch down with it: without this, a single bad signal
        # crashes the script and every signal after it in this run never
        # gets processed, with nothing but a traceback to show for it -
        # the real risk this is guarding against at a live demo or in a
        # real scheduled run.
        try:
            result = handle_signal(signal)
        except Exception as e:
            print(f"[{label}] {signal['establishment_name']} -> FAILED: {e}")
            continue
        print(
            f"[{label}] {signal['establishment_name']} -> company {result['company_id']}, "
            f"{result['tier']}, sequence_eligible={result['sequence_eligible']}, "
            f"sequence_enrollment={result['sequence_enrollment']}, "
            f"tier1_first_touch={result['tier1_first_touch']}"
        )


if __name__ == "__main__":
    main()
