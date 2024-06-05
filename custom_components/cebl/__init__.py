import logging
import aiohttp
import async_timeout
import asyncio
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, PLATFORMS, STARTUP_MESSAGE, API_URL_FIXTURES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CEBL from a config entry."""
    _LOGGER.info(STARTUP_MESSAGE)
    coordinator = CEBLDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    _LOGGER.info("CEBL integration setup complete.")
    return True

class CEBLDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching CEBL data from the API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize."""
        self.entry = entry
        self.session = async_get_clientsession(hass)
        self.url = API_URL_FIXTURES
        self.teams = entry.data.get("teams", [])
        _LOGGER.info(f"Initializing CEBLDataUpdateCoordinator with teams: {self.teams}")
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=10),
        )

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.info("Fetching CEBL data from API.")
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(self.url) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Invalid response from API: {response.status}")
                        raise UpdateFailed(f"Invalid response from API: {response.status}")
                    data = await response.json()
                    _LOGGER.debug(f"Fetched data: {data}")
                    fixtures = [fixture for fixture in data["fixtures"] 
                                if str(fixture["homeTeam"]["id"]) in self.teams or str(fixture["awayTeam"]["id"]) in self.teams]
                    _LOGGER.info(f"Fetched fixtures: {fixtures}")
                    return {"fixtures": fixtures}
        except aiohttp.ClientError as err:
            _LOGGER.error(f"HTTP error fetching teams: {err}")
            raise UpdateFailed(f"HTTP error fetching teams: {err}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout error fetching teams")
            raise UpdateFailed("Timeout error fetching teams")
        except Exception as err:
            _LOGGER.error(f"Unexpected error fetching teams: {err}")
            raise UpdateFailed(f"Unexpected error fetching teams: {err}")
