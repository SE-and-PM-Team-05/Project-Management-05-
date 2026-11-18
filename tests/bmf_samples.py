"""A small BMF feed in the markup the SCRUM-18 POC parsed (docs/sources/bmf.md); names and numbers are made up."""

COMPANY = (
    "<em>Anschrift: <strong>Hauptstraße 1, 1010 Wien</strong></em><br/>"
    "<em>Veröffentlichung:</em> 04.11.2026<br/>"
    "<em>Zeitpunkt als Scheinunternehmen:</em> 01.06.2026<br/>"
    "<em>Rechtskraft Bescheid:</em> 20.10.2026<br/>"
    "<em>Firmenbuch-Nr: 123456a</em><br/>"
    "<em>UID-NR:</em> ATU12345678-B"
)
PERSON = (
    "<em>Anschrift: <strong>Gasse 2/3, 8010 Graz</strong></em><br/>"
    "<em>Veröffentlichung:</em> 15.10.2026<br/>"
    "<em>Rechtskraft Bescheid:</em> 01.10.2026<br/>"
    "<em>Geb.Datum:</em> 01.02.1980"
)


def item(title, description, cdata=False):
    if cdata:
        body = f"<![CDATA[{description}]]>"
    else:
        body = description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<item><title>{title}</title><description>{body}</description></item>"


def feed(*items, build_date="04 Nov 2026"):
    channel = "<title>Liste der Scheinunternehmen</title>"
    if build_date is not None:
        channel += f"<lastBuildDate>{build_date}</lastBuildDate>"
    text = (
        '<?xml version="1.0" encoding="iso-8859-1"?>'
        f'<rss version="2.0"><channel>{channel}{"".join(items)}</channel></rss>'
    )
    return text.encode("iso-8859-1")


SAMPLE = feed(item("Schein Bau &amp; Co GmbH", COMPANY), item("Max Muster", PERSON, cdata=True))
