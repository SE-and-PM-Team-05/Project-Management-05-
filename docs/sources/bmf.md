# Source: BMF list of sham companies (Liste der Scheinunternehmen)

POC note for REQ-POC-001 (SCRUM-18) and integration note required by REQ-INT-016. POC script:
`poc/poc_vies_bmf.py`. Figures below are from a run on 2026-11-04.

| | |
|---|---|
| **Owner** | Austrian Federal Ministry of Finance (BMF), published under § 8 SBBG (SRS reference R6) |
| **Check** | `listedAsFakeCompany` (REQ-FUNC-033) |
| **Access** | `GET https://service.bmf.gv.at/service/allg/lsu/rss_lsu.asp`, free, no account or key |
| **Format** | RSS 2.0 XML, `encoding="iso-8859-1"`, about 1 MB; the whole list in one response |
| **Freshness** | Imported once a day (REQ-FUNC-070), not queried per check |
| **Feed timestamp** | `<lastBuildDate>` in the channel, date only (e.g. `04 Nov 2026`); the HTTP response has no `Last-Modified` or `ETag`. Store `lastBuildDate` as the feed's own timestamp in the sync log (REQ-FUNC-072) |

## Entries

One `<item>` per listed company or person: `title` is the name; `description` is HTML with labelled fields
(`<em>Label:</em> value`); the item also has `link`, `guid`, `pubDate` and two `category` elements.

| Field | Where in `description` | Entries that have it (of 1,703) |
|---|---|---|
| Name | `<title>` | 1,703 |
| Address | `Anschrift:` | 1,703 |
| Published | `Veröffentlichung:` (`DD.MM.YYYY`) | 1,703 |
| Decision final | `Rechtskraft Bescheid:` | 1,703 |
| Sham company since | `Zeitpunkt als Scheinunternehmen:` | 1,082 |
| VAT number (UID) | `UID-NR:` (always `ATU…`, sometimes with a suffix such as `-B`, which is dropped) | 1,420 |
| Firmenbuch number (FN) | `Firmenbuch-Nr:` (digits + check letter, e.g. `123456a`) | 1,081 |
| Date of birth | `Geb.Datum:` – only for **persons** (sole traders) | 598 |

## Matching keys (REQ-FUNC-033)

1. **UID**: 1,420 entries (83 %) have one, so most matches are exact.
2. **FN**: for entries without a UID; 1,511 entries (89 %) have a UID or an FN.
3. **Normalized name**: needed for the remaining **192 entries (11 %) with neither**. A name-only hit is never a
   definite match; it is reported as `UNKNOWN` / `AMBIGUOUS_MATCH` with the candidate entry (open decision OD-01).

This confirms assumption A4 for most entries and answers the BMF part of OD-05: the feed does contain VAT numbers.

## VIES with feed UIDs

The POC queried VIES with the first UID from the feed: VIES answered `valid: false`. Listed sham companies are often
already deregistered, so a partner can fail `vatValid` and be `listedAsFakeCompany` at the same time.

## Data protection (REQ-COMP-001)

598 entries are **persons with their date of birth**. Store only what the check needs (name, address, UID, FN,
dates of listing) and do not store dates of birth unless a requirement needs them, e.g. the person-based risk check
(REQ-FUNC-080).

## Parsing notes

- The `description` is HTML inside XML; fields are read with regular expressions, so a change to BMF's markup can
  break the import. The sync must fail loudly and keep the last good copy (REQ-FUNC-073, REQ-REL-002).
- `requests` is used for both calls: on Windows, Python's built-in `urllib` can't verify the EU VIES server's
  certificate chain.

## Open points

- Rate limits or terms of use for automated download: not documented in the feed; check before production (REQ-COMP-004).
- Whether `lastBuildDate` changes only when the list changes, or daily.
