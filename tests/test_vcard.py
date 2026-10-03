"""Tests for CardDAV vCard parsing."""

from custom_components.carddav_birthdays.vcard import (
    ADDRESSBOOK_QUERY,
    parse_vcards,
)


def _report(vcard: str) -> str:
    """Wrap a vCard in a minimal CardDAV multistatus response."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:response>
    <D:propstat><D:prop><C:address-data>{vcard}</C:address-data></D:prop></D:propstat>
  </D:response>
</D:multistatus>"""


def test_addressbook_query_requests_structured_name() -> None:
    assert '<C:prop name="N"/>' in ADDRESSBOOK_QUERY


def test_parse_vcard_prefers_formatted_name() -> None:
    contacts = parse_vcards(
        _report(
            """BEGIN:VCARD
VERSION:3.0
N:Mustermann;Max;;;
FN:Maxi Mustermann
BDAY:2000-01-02
END:VCARD"""
        )
    )

    assert contacts[0]["name"] == "Maxi Mustermann"


def test_parse_vcard_builds_name_when_formatted_name_is_empty() -> None:
    contacts = parse_vcards(
        _report(
            """BEGIN:VCARD
VERSION:3.0
N:Mustermann;Max;;;
FN:   
BDAY:2000-01-02
END:VCARD"""
        )
    )

    assert contacts[0]["name"] == "Max Mustermann"


def test_parse_vcard_builds_name_when_formatted_name_is_missing() -> None:
    contacts = parse_vcards(
        _report(
            """BEGIN:VCARD
VERSION:3.0
N:Mustermann;Max;Maria;Dr.;Jr.
BDAY:2000-01-02
END:VCARD"""
        )
    )

    assert contacts[0]["name"] == "Dr. Max Maria Mustermann Jr."


def test_parse_vcard_uses_unknown_without_any_name() -> None:
    contacts = parse_vcards(
        _report(
            """BEGIN:VCARD
VERSION:3.0
BDAY:2000-01-02
END:VCARD"""
        )
    )

    assert contacts[0]["name"] == "Unknown"
