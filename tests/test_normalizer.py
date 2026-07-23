from datetime import date, timedelta

from app.extraction.normalizer import normalize


def _base_data(**overrides):
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    data.update(overrides)
    return data


def test_bengali_digits_convert():
    normalized, _ = normalize(_base_data(nidNumber="১২৩৪৫৬৭৮৯০"))
    assert normalized["nidNumber"] == "1234567890"


def test_iso_date_passes_through():
    normalized, _ = normalize(_base_data(dateOfBirth="1998-01-15"))
    assert normalized["dateOfBirth"] == "1998-01-15"


def test_bengali_month_format_normalizes():
    normalized, _ = normalize(_base_data(dateOfBirth="১৫ জানুয়ারি ১৯৯৮"))
    assert normalized["dateOfBirth"] == "1998-01-15"


def test_future_date_becomes_null_with_warning():
    future = (date.today() + timedelta(days=365)).isoformat()
    normalized, warnings = normalize(_base_data(dateOfBirth=future))
    assert normalized["dateOfBirth"] is None
    assert any(w["code"] == "unparseable_dob" for w in warnings)


def test_wrong_length_nid_keeps_value_with_warning():
    normalized, warnings = normalize(_base_data(nidNumber="12345"))
    assert normalized["nidNumber"] == "12345"
    assert any(w["code"] == "unusual_nid_length" for w in warnings)


def test_missing_nid_becomes_null_with_warning():
    normalized, warnings = normalize(_base_data(nidNumber=None))
    assert normalized["nidNumber"] is None
    assert any(w["code"] == "missing_nid" for w in warnings)


def test_duplicate_address_is_flagged():
    normalized, warnings = normalize(_base_data(presentAddress="House 12, Dhaka", permanentAddress="House 12, Dhaka"))
    assert any(w["code"] == "duplicate_address" for w in warnings)


def test_duplicate_address_is_case_and_whitespace_insensitive():
    normalized, warnings = normalize(
        _base_data(presentAddress="  House 12, Dhaka  ", permanentAddress="house 12, dhaka")
    )
    assert any(w["code"] == "duplicate_address" for w in warnings)


def test_different_addresses_are_not_flagged():
    normalized, warnings = normalize(_base_data(presentAddress="Dhaka", permanentAddress="Cumilla"))
    assert not any(w["code"] == "duplicate_address" for w in warnings)


def test_name_and_father_name_collision_is_flagged():
    normalized, warnings = normalize(_base_data(name="Md. Rahim Uddin", fatherName="Md. Rahim Uddin"))
    assert any(w["code"] == "cross_field_collision" for w in warnings)


def test_father_and_mother_name_collision_is_flagged():
    normalized, warnings = normalize(_base_data(fatherName="Amena Begum", motherName="Amena Begum"))
    assert any(w["code"] == "cross_field_collision" for w in warnings)


def test_distinct_names_are_not_flagged():
    normalized, warnings = normalize(_base_data())
    assert not any(w["code"] == "cross_field_collision" for w in warnings)
