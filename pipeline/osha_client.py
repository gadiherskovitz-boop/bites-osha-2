from __future__ import annotations

from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.osha.gov/ords/imis"


def _clean(text: str | None) -> str:
    return text.replace("\xa0", "").strip() if text else ""


def _parse_date(text: str | None) -> date | None:
    text = _clean(text)
    if not text:
        return None
    return datetime.strptime(text, "%m/%d/%Y").date()


def _parse_money(text: str | None) -> float:
    text = _clean(text).replace("$", "").replace(",", "")
    return float(text) if text else 0.0


def _parse_int(text: str | None) -> int:
    text = _clean(text)
    return int(text) if text else 0


def industry_search(naics: str, start_date: date, end_date: date, page_size: int = 2000) -> list[dict]:
    """Lists inspections for one NAICS code opened within [start_date, end_date].

    One NAICS per call - the site's form does not accept comma-separated codes
    (confirmed live: returns "did not return any results" instead of an error).

    The site's own form fields are misleadingly named - the field named
    `startyear`/`startmonth`/`startday` is titled "End Year" internally and
    actually takes the LATER date, while `endyear`/`endmonth`/`endday` is
    titled "Start Year" and takes the EARLIER date. Verified by inspecting the
    live form's `title` attributes and by round-tripping a query and reading
    back the "Inspection Date Range" the results page echoes. Get this
    backwards and the query silently returns the wrong (or an empty) range.
    """
    resp = requests.get(
        f"{BASE_URL}/industry.search",
        params={
            "p_logger": 1,
            "sic": "",
            "naics": naics,
            "State": "All",
            "officetype": "All",
            "Office": "All",
            # earlier bound of the window -> the site's "end*" fields
            "endmonth": f"{start_date.month:02d}",
            "endday": f"{start_date.day:02d}",
            "endyear": start_date.year,
            # later bound of the window -> the site's "start*" fields
            "startmonth": f"{end_date.month:02d}",
            "startday": f"{end_date.day:02d}",
            "startyear": end_date.year,
            "owner": "",
            "scope": "",
            "FedAgnCode": "",
            "p_show": page_size,
        },
        timeout=30,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    if "did not return any results" in resp.text:
        return []

    table = next(
        t for t in soup.find_all("table") if "Establishment Name" in t.get_text()
    )
    # No <tbody> in the raw source here (unlike establishment.inspection_detail's
    # tables) - html.parser doesn't synthesize one, so query <tr> directly.
    rows = table.find_all("tr")[1:]  # drop header row

    results = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) != 12:
            continue
        activity_link = cells[2].find("a")
        results.append(
            {
                "activity_nr": _clean(activity_link.get_text()),
                "is_open": activity_link.find("em") is not None,
                "date_opened": _parse_date(cells[3].get_text()),
                "office_rid": _clean(cells[4].get_text()),
                "state": _clean(cells[5].get_text()),
                "insp_type": _clean(cells[6].get_text()),
                "scope": _clean(cells[7].get_text()),
                "sic": _clean(cells[8].get_text()),
                "naics": _clean(cells[9].get_text()),
                "violations_count": _parse_int(cells[10].get_text()),
                "establishment_name": _clean(cells[11].get_text()),
            }
        )
    return results


def _text_after_label(soup: BeautifulSoup, label: str) -> str:
    strong = next(
        (s for s in soup.find_all("strong") if _clean(s.get_text()) == label), None
    )
    if strong is None:
        return ""
    return _clean(strong.next_sibling).lstrip(":").strip() if strong.next_sibling else ""


def _site_address(soup: BeautifulSoup) -> str:
    strong = next(
        (s for s in soup.find_all("strong") if _clean(s.get_text()) == "Site Address"),
        None,
    )
    if strong is None:
        return ""
    lines = [
        line.strip()
        for line in strong.parent.get_text(separator="\n").split("\n")[1:]
        if line.strip()
    ]
    return ", ".join(lines)


def inspection_detail(activity_nr: str) -> dict:
    """Full detail for one inspection, including its Violation Items table."""
    resp = requests.get(
        f"{BASE_URL}/establishment.inspection_detail",
        params={"id": activity_nr},
        timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    case_status_div = soup.find("div", class_="well well-small")
    case_status = _clean(case_status_div.get_text()).replace("Case Status:", "").strip()

    violations = []
    viol_table = next(
        (
            t
            for t in soup.find_all("table")
            if t.find("caption") and "Violation Items" in t.find("caption").get_text()
        ),
        None,
    )
    if viol_table is not None:
        for row in viol_table.find("tbody").find_all("tr")[1:]:  # drop header row
            cells = row.find_all(["td", "th"])
            if len(cells) != 12:
                continue
            citation_link = cells[1].find("a")
            violations.append(
                {
                    "citation_id": _clean(citation_link.get_text())
                    if citation_link
                    else _clean(cells[1].get_text()),
                    "citation_type": _clean(cells[2].get_text()),
                    "standard_cited": _clean(cells[3].get_text()),
                    "issuance_date": _parse_date(cells[4].get_text()),
                    "abatement_due_date": _parse_date(cells[5].get_text()),
                    "current_penalty": _parse_money(cells[6].get_text()),
                    "initial_penalty": _parse_money(cells[7].get_text()),
                    "fta_penalty": _parse_money(cells[8].get_text()),
                    "contest": _clean(cells[9].get_text()),
                    "latest_event": _clean(cells[10].get_text()),
                }
            )

    return {
        "activity_nr": activity_nr,
        "case_status": case_status,
        "site_address": _site_address(soup),
        "naics": _text_after_label(soup, "NAICS").replace("\xa0", "").strip(),
        "insp_type": _text_after_label(soup, "Inspection Type"),
        "case_closed_date": _parse_date(_text_after_label(soup, "Case Closed")),
        "violations": violations,
    }
