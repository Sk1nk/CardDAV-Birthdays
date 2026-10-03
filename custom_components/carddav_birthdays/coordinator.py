"""CardDAV birthday data coordinator."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CARDDAV_REFETCH_INTERVAL,
    CONF_PASSWORD,
    CONF_SERVER_URL,
    CONF_UPCOMING_DAYS,
    CONF_USERNAME,
    DOMAIN,
    SCAN_INTERVAL,
)
from .vcard import ADDRESSBOOK_QUERY, parse_vcards

_LOGGER = logging.getLogger(__name__)

def _days_until_next_birthday(bday: date, today: date) -> int:
    """Return the number of days from today until the next occurrence of this birthday."""
    try:
        next_bd = bday.replace(year=today.year)
    except ValueError:
        # Feb 29 on non-leap year → use Mar 1
        next_bd = date(today.year, 3, 1)
    if next_bd < today:
        try:
            next_bd = bday.replace(year=today.year + 1)
        except ValueError:
            next_bd = date(today.year + 1, 3, 1)
    return (next_bd - today).days


def _age_at_next(bday: date, today: date) -> int | None:
    """Return the age the person will turn on their next birthday. None if year unknown."""
    if bday.year == 1:
        return None
    days = _days_until_next_birthday(bday, today)
    next_year = (today + timedelta(days=days)).year
    return next_year - bday.year


class CardDAVBirthdayCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches contacts from CardDAV and calculates birthday datasets."""

    def __init__(self, hass: HomeAssistant, entry_data: dict) -> None:
        self._server_url = entry_data[CONF_SERVER_URL].rstrip("/")
        self._username = entry_data[CONF_USERNAME]
        self._password = entry_data[CONF_PASSWORD]
        self._upcoming_days = entry_data.get(CONF_UPCOMING_DAYS, 30)
        self._contacts: list[dict[str, Any]] = []
        self._last_fetch: datetime | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _fetch_contacts(self) -> None:
        """Fetch vCards from the CardDAV server and cache parsed contacts."""
        auth = aiohttp.BasicAuth(self._username, self._password)
        headers = {
            "Content-Type": "application/xml; charset=utf-8",
            "Depth": "1",
        }
        timeout = aiohttp.ClientTimeout(total=30)
        session = async_get_clientsession(self.hass)
        try:
            async with session.request(
                "REPORT",
                self._server_url,
                data=ADDRESSBOOK_QUERY,
                headers=headers,
                auth=auth,
                timeout=timeout,
            ) as resp:
                if resp.status not in (207, 200):
                    raise UpdateFailed(
                        f"CardDAV REPORT returned HTTP {resp.status}"
                    )
                body = await resp.text()
        except aiohttp.ClientError as exc:
            raise UpdateFailed(f"Cannot connect to CardDAV server: {exc}") from exc

        self._contacts = parse_vcards(body)
        self._last_fetch = datetime.now()
        _LOGGER.debug("Fetched %d contacts with birthdays", len(self._contacts))

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh from CardDAV if needed, then recalculate sensor datasets."""
        needs_fetch = (
            self._last_fetch is None
            or (datetime.now() - self._last_fetch) >= CARDDAV_REFETCH_INTERVAL
        )
        if needs_fetch:
            await self._fetch_contacts()

        today = date.today()
        week_end = today + timedelta(days=7)
        upcoming_end = today + timedelta(days=self._upcoming_days)

        today_contacts = []
        this_week_contacts = []
        upcoming_contacts = []
        next_birthday_entry: dict | None = None
        min_days: int | None = None

        for contact in self._contacts:
            bday: date = contact["birthday"]
            days = _days_until_next_birthday(bday, today)
            age_next = _age_at_next(bday, today)

            entry = {
                "name": contact["name"],
                "days_until": days,
                "date": bday.replace(year=today.year).isoformat()
                if days < 365
                else bday.isoformat(),
                "age_at_next": age_next,
            }

            if days == 0:
                today_contacts.append(
                    {"name": contact["name"], "age": age_next}
                )
            if 0 <= days < 7:
                this_week_contacts.append(entry)
            if 0 <= days < self._upcoming_days:
                upcoming_contacts.append(entry)
            if min_days is None or days < min_days:
                min_days = days
                next_birthday_entry = entry

        this_week_contacts.sort(key=lambda x: x["days_until"])
        upcoming_contacts.sort(key=lambda x: x["days_until"])

        return {
            "today": today_contacts,
            "this_week": this_week_contacts,
            "next": next_birthday_entry,
            "upcoming": upcoming_contacts,
            "upcoming_days": self._upcoming_days,
        }
