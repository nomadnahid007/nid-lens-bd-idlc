import re
from datetime import date

BENGALI_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

BENGALI_MONTHS = {
    "জানুয়ারি": 1, "ফেব্রুয়ারি": 2, "মার্চ": 3, "এপ্রিল": 4,
    "মে": 5, "জুন": 6, "জুলাই": 7, "আগস্ট": 8,
    "সেপ্টেম্বর": 9, "অক্টোবর": 10, "নভেম্বর": 11, "ডিসেম্বর": 12,
    # English fallbacks
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

FIELDS = [
    "name", "fatherName", "motherName", "dateOfBirth",
    "nidNumber", "presentAddress", "permanentAddress",
]
NAME_ADDRESS_FIELDS = ["name", "fatherName", "motherName", "presentAddress", "permanentAddress"]

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLASH_DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")


def _convert_bengali_digits(value):
    if isinstance(value, str):
        return value.translate(BENGALI_TO_ASCII_DIGITS)
    return value


def _normalize_nid(value: str | None, warnings: list[dict]) -> str | None:
    digits = re.sub(r"\D", "", value) if value else ""

    if not digits:
        warnings.append({
            "code": "missing_nid",
            "message": "NID number could not be extracted",
            "field": "nidNumber",
        })
        return None

    if len(digits) not in (10, 13, 17):
        warnings.append({
            "code": "unusual_nid_length",
            "message": f"NID number has {len(digits)} digits; expected 10, 13, or 17",
            "field": "nidNumber",
        })

    return digits


def _parse_month_name_date(text: str) -> date | None:
    lowered = text.lower()
    month_num = None
    for name, num in BENGALI_MONTHS.items():
        if name in text or name in lowered:
            month_num = num
            break

    if month_num is None:
        return None

    numbers = [int(n) for n in re.findall(r"\d+", text)]
    day_candidates = [n for n in numbers if 1 <= n <= 31 and n < 1000]
    year_candidates = [n for n in numbers if n >= 1000]

    if not day_candidates or not year_candidates:
        return None

    try:
        return date(year_candidates[0], month_num, day_candidates[0])
    except ValueError:
        return None


def _normalize_dob(value: str | None, warnings: list[dict]) -> str | None:
    parsed = None

    if value:
        text = value.strip()

        if ISO_DATE_RE.match(text):
            try:
                parsed = date.fromisoformat(text)
            except ValueError:
                parsed = None

        if parsed is None:
            m = SLASH_DATE_RE.match(text)
            if m:
                day, month, year = (int(g) for g in m.groups())
                try:
                    parsed = date(year, month, day)
                except ValueError:
                    parsed = None

        if parsed is None:
            parsed = _parse_month_name_date(text)

    if parsed is not None and parsed <= date.today():
        return parsed.isoformat()

    warnings.append({
        "code": "unparseable_dob",
        "message": "Date of birth could not be normalized",
        "field": "dateOfBirth",
    })
    return None


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().casefold() == b.strip().casefold()


def _cross_field_checks(result: dict) -> list[dict]:
    """Checks across multiple fields rather than within one — these catch a
    class of extraction error a per-field check can't see, e.g. the model
    reading the same text twice into two different fields. Both warning codes
    here are treated as critical by ExtractionService (they force `status`
    to "partial" even if every field technically has a value), because a
    collision like this means at least one of the two fields is very likely
    wrong, not just imprecise."""
    warnings: list[dict] = []

    if _same(result.get("presentAddress"), result.get("permanentAddress")):
        warnings.append({
            "code": "duplicate_address",
            "message": (
                "Present and permanent addresses are identical — verify this wasn't a read "
                "error rather than a genuine match."
            ),
            "field": None,
        })

    name_fields = [
        ("name", "fatherName", "Name and father's name"),
        ("name", "motherName", "Name and mother's name"),
        ("fatherName", "motherName", "Father's name and mother's name"),
    ]
    for field_a, field_b, label in name_fields:
        if _same(result.get(field_a), result.get(field_b)):
            warnings.append({
                "code": "cross_field_collision",
                "message": f"{label} are identical — likely a read error rather than a genuine match.",
                "field": None,
            })

    return warnings


def normalize(data: dict) -> tuple[dict, list[dict]]:
    warnings: list[dict] = []
    result = {}

    for field in FIELDS:
        value = _convert_bengali_digits(data.get(field))
        if isinstance(value, str):
            value = value.strip() or None
        result[field] = value

    result["nidNumber"] = _normalize_nid(result.get("nidNumber"), warnings)
    result["dateOfBirth"] = _normalize_dob(result.get("dateOfBirth"), warnings)

    for field in NAME_ADDRESS_FIELDS:
        value = result.get(field)
        if isinstance(value, str):
            value = re.sub(r"\s+", " ", value).strip() or None
        result[field] = value

    warnings.extend(_cross_field_checks(result))

    return result, warnings
