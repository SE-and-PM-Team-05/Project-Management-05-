"""Company-name matching for nameMatchesVat (REQ-FUNC-032).

SRS 3.6 requires matching to be deterministic and documented, so all rules live in this one module:

1. Compare case-insensitively (str.casefold, so "ß" equals "SS").
2. Drop dots ("G.m.b.H." becomes "gmbh", "e.U." becomes "eu") and treat every other character that is
   not a letter or digit as a space ("Muster-Bau" equals "Muster Bau", "&" disappears).
3. Remove one legal-form suffix from the end of the name, taken from LEGAL_FORMS below.
4. Collapse repeated spaces.

Two names match when the results are identical. Nothing else is guessed: no fuzzy matching, no
umlaut transliteration ("Müller" does not equal "Mueller"), no abbreviations.
"""

import re

# Legal-form suffixes, written as they are usually spelled. Longer forms come first so that
# "GmbH & Co KG" is removed as a whole and not only its "KG" part. To add a form, add it here.
LEGAL_FORMS = [
    # Austria and Germany
    "GmbH & Co KG",
    "GmbH & Co. KG",
    "GmbH & Co OG",
    "GmbH & Co. OG",
    "Gesellschaft mit beschränkter Haftung",
    "Ges.m.b.H.",
    "GesmbH",
    "GmbH",
    "mbH",
    "UG (haftungsbeschränkt)",
    "AG",
    "KG",
    "OG",
    "OHG",
    "e.U.",
    "e.K.",
    "eGen",
    "eG",
    # Other EU and English forms
    "SE",
    "Ltd",
    "Limited",
    "Sp. z o.o.",
    "s.r.o.",
    "spol. s r.o.",
    "d.o.o.",
    "Kft",
    "S.à r.l.",
    "SARL",
    "SAS",
    "S.A.",
    "SpA",
    "S.r.l.",
    "B.V.",
    "N.V.",
]


def _tokens(text):
    return re.sub(r"[^\w]|_", " ", text.casefold().replace(".", "")).split()


# Each legal form as a token tuple, longest first, e.g. "GmbH & Co. KG" -> ("gmbh", "co", "kg").
_SUFFIXES = sorted({tuple(_tokens(form)) for form in LEGAL_FORMS}, key=len, reverse=True)


def normalize_company_name(name):
    """Return the comparable form of a company name, e.g. "Muster-Bau GmbH" -> "muster bau"."""
    tokens = _tokens(name or "")
    for suffix in _SUFFIXES:
        # Keep the name if it consists of nothing but the legal form.
        if len(tokens) > len(suffix) and tuple(tokens[-len(suffix) :]) == suffix:
            tokens = tokens[: -len(suffix)]
            break
    return " ".join(tokens)


def names_match(given, registered):
    return normalize_company_name(given) == normalize_company_name(registered)
