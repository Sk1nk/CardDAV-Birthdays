"""Parsing helpers for CardDAV vCards."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any

import vobject

_LOGGER = logging.getLogger(__name__)

ADDRESSBOOK_QUERY = """<?xml version="1.0" encoding="utf-8" ?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data>
      <C:prop name="FN"/>
      <C:prop name="N"/>
      <C:prop name="BDAY"/>
    </C:address-data>
  </D:prop>
</C:addressbook-query>"""

NS = {
    "D": "DAV:",
    "C": "urn:ietf:params:xml:ns:carddav",
}


def _parse_bday(bday_str: str) -> date | None:
    """Parse a vCard BDAY value into a date. Returns None if unparseable."""
    value = bday_str.strip()
    # Full date: 19850315 or 1985-03-15
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # Year-less: --0315 or --03-15
    if value.startswith("--"):
        tail = value[2:].replace("-", "")
        try:
            parsed = datetime.strptime(tail, "%m%d")
            return date(1, parsed.month, parsed.day)
        except ValueError:
            pass
    return None


def _name_parts(value: Any) -> list[str]:
    """Return non-empty strings from a structured vCard name component."""
    if isinstance(value, (list, tuple)):
        return [part for item in value for part in _name_parts(item)]
    if value is None:
        return []
    part = str(value).strip()
    return [part] if part else []


def _contact_name(vcard: Any) -> str:
    """Return FN or build a display name from the structured N property."""
    fn = getattr(vcard, "fn", None)
    if fn is not None:
        fn_value = str(fn.value).strip()
        if fn_value:
            return fn_value

    structured_name = getattr(vcard, "n", None)
    if structured_name is None:
        return "Unknown"

    value = structured_name.value
    parts: list[str] = []
    # N is stored as family;given;additional;prefix;suffix, but a display name
    # is conventionally rendered with the prefix and given name first.
    for attribute in ("prefix", "given", "additional", "family", "suffix"):
        parts.extend(_name_parts(getattr(value, attribute, None)))
    return " ".join(parts) or "Unknown"


def parse_vcards(xml_body: str) -> list[dict[str, Any]]:
    """Extract contacts with birthday info from a CardDAV REPORT response."""
    contacts: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_body)
    except ET.ParseError as exc:
        _LOGGER.warning("Failed to parse CardDAV XML response: %s", exc)
        return contacts

    for response in root.findall("D:response", NS):
        for prop_ok in response.findall("D:propstat/D:prop/C:address-data", NS):
            vcard_text = prop_ok.text
            if not vcard_text:
                continue
            try:
                vcard = vobject.readOne(vcard_text)
            except Exception:
                continue
            bday_val = getattr(vcard, "bday", None)
            if bday_val is None:
                continue
            bday = _parse_bday(str(bday_val.value))
            if bday is None:
                continue
            contacts.append({"name": _contact_name(vcard), "birthday": bday})

    return contacts
