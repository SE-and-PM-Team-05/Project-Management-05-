#!/usr/bin/env python3
"""POC for REQ-POC-001 (SCRUM-18): live VIES query + parse of the BMF RSS feed (Liste der Scheinunternehmen).

Standalone spike, not part of the Django app. Findings are written up in docs/sources/bmf.md.
Run from the repository root with the project's virtual environment active: python poc/poc_vies_bmf.py
"""

import json
import re
import xml.etree.ElementTree as ET

import requests

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
BMF_URL = "https://service.bmf.gv.at/service/allg/lsu/rss_lsu.asp"


def vies_check(country, number):
    """Live VIES query. Returns the JSON response as a dict."""
    # requests ships its own CA bundle; urllib on Windows can't verify the EU server's certificate chain.
    response = requests.post(VIES_URL, json={"countryCode": country, "vatNumber": number}, timeout=20)
    response.raise_for_status()
    return response.json()


def split_uid(uid):
    """'ATU81508469' -> ('AT', 'U81508469'); drops suffixes like '-B'."""
    uid = uid.strip().split("-")[0]
    return uid[:2], uid[2:]


def field(desc, label):
    m = re.search(re.escape(label) + r":\s*(?:<[^>]+>)?\s*([^<,]*?)\s*(?:</[^>]+>)?\s*(?:,|<|$)", desc)
    return m.group(1).strip() if m else None


def parse_bmf(xml_bytes):
    root = ET.fromstring(xml_bytes)  # encoding is declared in the XML header (iso-8859-1)
    items = []
    for it in root.iter("item"):
        d = it.findtext("description") or ""
        uid = re.search(r"UID-NR:</em>\s*(ATU[0-9A-Z\-]+)", d)
        fb = re.search(r"Firmenbuch-Nr:\s*([0-9]+[a-z])", d)
        address = re.search(r"Anschrift:\s*<strong>(.*?)</strong>", d)
        items.append(
            {
                "name": (it.findtext("title") or "").strip(),
                "address": address.group(1) if address else None,
                "published": field(d, "Veröffentlichung"),
                "shell_since": field(d, "Zeitpunkt als Scheinunternehmen"),
                "legally_binding": field(d, "Rechtskraft Bescheid"),
                "birth_date": field(d, "Geb.Datum"),  # persons only
                "firmenbuch_nr": fb.group(1) if fb else None,  # companies only
                "uid": uid.group(1) if uid else None,
            }
        )
    return items


if __name__ == "__main__":
    print("== BMF feed ==")
    response = requests.get(BMF_URL, timeout=20)
    response.raise_for_status()
    items = parse_bmf(response.content)
    with_uid = [i for i in items if i["uid"]]
    print(f"{len(items)} items, {len(with_uid)} with UID, {len(items) - len(with_uid)} without")
    print(json.dumps(items[:2], indent=2, ensure_ascii=False))

    # VIES: test with a UID from the BMF feed
    print("\n== VIES live query ==")
    if with_uid:
        cc, num = split_uid(with_uid[0]["uid"])
        print(f"Querying {cc} {num} ({with_uid[0]['name']})")
        print(json.dumps(vies_check(cc, num), indent=2, ensure_ascii=False))
