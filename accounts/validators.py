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
# Format of each member state's VAT number, including the prefix, as published by the European
# Commission for VIES (REQ-FUNC-031). Only the shape is checked here; VIES says whether it exists.
COUNTRY_FORMATS = {
    "AT": r"ATU\d{8}",
    "BE": r"BE[01]\d{9}",
    "BG": r"BG\d{9,10}",
    "CY": r"CY\d{8}[A-Z]",
    "CZ": r"CZ\d{8,10}",
    "DE": r"DE\d{9}",
    "DK": r"DK\d{8}",
    "EE": r"EE\d{9}",
    "EL": r"EL\d{9}",
    "ES": r"ES[0-9A-Z]\d{7}[0-9A-Z]",
    "FI": r"FI\d{8}",
    "FR": r"FR[0-9A-Z]{2}\d{9}",
    "HR": r"HR\d{11}",
    "HU": r"HU\d{8}",
    "IE": r"IE\d[0-9A-Z+*]\d{5}[A-Z]{1,2}",
    "IT": r"IT\d{11}",
    "LT": r"LT(\d{9}|\d{12})",
    "LU": r"LU\d{8}",
    "LV": r"LV\d{11}",
    "MT": r"MT\d{8}",
    "NL": r"NL\d{9}B\d{2}",
    "PL": r"PL\d{10}",
    "PT": r"PT\d{9}",
    "RO": r"RO\d{2,10}",
    "SE": r"SE\d{12}",
    "SI": r"SI\d{8}",
    "SK": r"SK\d{10}",
    "XI": r"XI(\d{9}|\d{12}|GD\d{3}|HA\d{3})",
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
    if not re.fullmatch(COUNTRY_FORMATS[prefix], vat):
        raise ValidationError("This is not a valid %(prefix)s VAT number format.", params={"prefix": prefix})
