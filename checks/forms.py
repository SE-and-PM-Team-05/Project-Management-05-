"""Validation and normalization of check input (REQ-FUNC-030, REQ-SEC-005)."""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from accounts.validators import normalize_vat_number, validate_vat_number

from .results import Partner

# Austrian company register number: up to 6 digits plus a check letter, e.g. 123456a (SRS 1.3).
FN_PATTERN = r"\d{1,6}[a-z]"
MAX_NAME_LENGTH = 200
MAX_TEXT_LENGTH = 500


def parse_check_input(data):
    """Return (Partner, reference) or raise ValidationError with a dict of field errors.

    Field names are the API's camelCase names; error messages follow the user's language.
    """
    if not isinstance(data, dict):
        raise ValidationError({"__all__": [_("Send a JSON object.")]})
    errors = {}

    def text(name, required=False, max_length=MAX_TEXT_LENGTH):
        value = data.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                errors[name] = [_("This field is required.")]
            return ""
        if not isinstance(value, str):
            errors[name] = [_("Enter text.")]
            return ""
        value = " ".join(value.split())
        if len(value) > max_length:
            errors[name] = [_("Enter at most %(max)s characters.") % {"max": max_length}]
        return value

    vat_number = text("vatNumber", required=True, max_length=30)
    if vat_number:
        vat_number = normalize_vat_number(vat_number)
        try:
            validate_vat_number(vat_number)
        except ValidationError as error:
            errors["vatNumber"] = error.messages

    company_name = text("companyName", required=True, max_length=MAX_NAME_LENGTH)
    if company_name and not re.search(r"\w", company_name):
        errors["companyName"] = [_("Enter a company name.")]

    register_number = text("companyRegisterNumber", max_length=20).replace(" ", "").lower()
    register_number = register_number.removeprefix("fn")
    if register_number and not re.fullmatch(FN_PATTERN, register_number):
        errors["companyRegisterNumber"] = [_("Enter up to 6 digits and a check letter, e.g. 123456a.")]

    address = text("address")
    reference = text("reference", max_length=MAX_NAME_LENGTH)

    codes = data.get("requiredLicenseCodes") or []
    if not isinstance(codes, list) or not all(isinstance(c, str) and c.strip() for c in codes):
        errors["requiredLicenseCodes"] = [_("Enter a list of license codes.")]
        codes = []

    if errors:
        raise ValidationError(errors)
    partner = Partner(
        vat_number=vat_number,
        company_name=company_name,
        company_register_number=register_number,
        address=address,
        required_license_codes=tuple(c.strip() for c in codes),
    )
    return partner, reference
