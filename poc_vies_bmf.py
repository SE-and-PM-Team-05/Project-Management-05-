#!/usr/bin/env python3
"""POC for REQ-POC-001: live VIES query + BMF RSS (Liste der Scheinunternehmen) parse.
Standard library only. Run: python poc_vies_bmf.py
"""
import json, re, sys, urllib.request
import xml.etree.ElementTree as ET

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
BMF_URL = "https://service.bmf.gv.at/service/allg/lsu/rss_lsu.asp"


def vies_check(country, number):
    """Live VIES query. Returns the JSON response as a dict."""
    body = json.dumps({"countryCode": country, "vatNumber": number}).encode()
    req = urllib.request.Request(VIES_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


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
        items.append({
            "name": (it.findtext("title") or "").strip(),
            "address": (re.search(r"Anschrift:\s*<strong>(.*?)</strong>", d) or [None, None])[1],
            "published": field(d, "Veröffentlichung"),
            "shell_since": field(d, "Zeitpunkt als Scheinunternehmen"),
            "legally_binding": field(d, "Rechtskraft Bescheid"),
            "birth_date": field(d, "Geb.Datum"),   # persons only
            "firmenbuch_nr": fb.group(1) if fb else None,  # companies only
            "uid": uid.group(1) if uid else None,
        })
    return items


if __name__ == "__main__":
    # 1) VIES: test with a UID from the BMF feed
    print("== BMF feed ==")
    with urllib.request.urlopen(BMF_URL, timeout=20) as r:
        items = parse_bmf(r.read())
    with_uid = [i for i in items if i["uid"]]
    print(f"{len(items)} items, {len(with_uid)} with UID, "
          f"{len(items) - len(with_uid)} without")
    print(json.dumps(items[:2], indent=2, ensure_ascii=False))

    print("\n== VIES live query ==")
    if with_uid:
        cc, num = split_uid(with_uid[0]["uid"])
        print(f"Querying {cc} {num} ({with_uid[0]['name']})")
        print(json.dumps(vies_check(cc, num), indent=2, ensure_ascii=False))
