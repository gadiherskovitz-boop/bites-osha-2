import requests

from pipeline.config import SLACK_BOT_TOKEN

BASE_URL = "https://slack.com/api"

# Created once via conversations.create; IDs are stable, so hardcoded here
# rather than re-created/looked-up on every run.
CHANNELS = {
    "osha_complaints": "C0BQLSGQMGR",
    "osha_citations": "C0BQJTGQ1CJ",
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
