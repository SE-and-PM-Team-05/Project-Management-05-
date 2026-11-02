import re

from django.core.exceptions import ValidationError

# EU member states plus Northern Ireland (XI); VIES uses EL for Greece.
EU_PREFIXES = {
    "AT",
    "BE",
    "BG",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "EL",
    "ES",
    "FI",
    "FR",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SE",
    "SI",
    "SK",
    "XI",
}
# Exact formats for the countries most partners come from; the rest only get the generic check.
COUNTRY_FORMATS = {
    "AT": r"ATU\d{8}",
    "DE": r"DE\d{9}",
}


def normalize_vat_number(value):
    """Uppercase and drop the spaces, dots and dashes people type into VAT numbers."""
    return re.sub(r"[\s.\-]", "", value or "").upper()


def validate_vat_number(value):
    """Reject VAT numbers that cannot be valid; whether they exist is checked with VIES later."""
    vat = normalize_vat_number(value)
    prefix = vat[:2]
    if prefix not in EU_PREFIXES:
        raise ValidationError("Enter an EU VAT number starting with its country code, e.g. ATU12345678.")
    pattern = COUNTRY_FORMATS.get(prefix, r"[A-Z]{2}[0-9A-Z]{2,12}")
    if not re.fullmatch(pattern, vat):
        raise ValidationError("This is not a valid %(prefix)s VAT number format.", params={"prefix": prefix})
