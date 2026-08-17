import requests

from pipeline.config import SLACK_BOT_TOKEN

BASE_URL = "https://slack.com/api"

# Created once via conversations.create; IDs are stable, so hardcoded here
# rather than re-created/looked-up on every run.
# Inspection = any early-stage trigger (Complaint, Accident, Fat/Cat - no
# outcome known yet). Violation = a citation was actually issued, regardless
# of what inspection type led to it.
CHANNELS = {
    "osha_inspections": "C0BQLSGQMGR",
    "osha_violations": "C0BQJTGQ1CJ",
    "hiring_signals": "C0BQJTH9F26",
}


def _headers():
    return {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }


def post_message(channel: str, text: str):
    resp = requests.post(
        f"{BASE_URL}/chat.postMessage",
        headers=_headers(),
        json={"channel": channel, "text": text},
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack error: {data}")
    return data
