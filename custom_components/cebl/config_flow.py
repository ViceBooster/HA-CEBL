"""Config flow for CEBL integration."""
from homeassistant import config_entries
import voluptuous as vol
import aiohttp
import async_timeout
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class CEBLConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CEBL."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            team_name = user_input["team"]
            team_id = self.team_options_reverse[team_name]  # Get team ID from name
            return self.async_create_entry(title="CEBL", data={"teams": [team_id]})

        # Fetch teams dynamically
        teams = await self._fetch_teams()
        if teams is None:
            errors["base"] = "cannot_connect"
            teams = []

        self.team_options = {str(team["id"]): team["name"] for team in teams}  # Ensure team IDs are strings
        self.team_options_reverse = {v: k for k, v in self.team_options.items()}  # Reverse map for lookups

        schema = vol.Schema({
            vol.Required("team"): vol.In(list(self.team_options.values())),  # Correctly handle team options
        })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def _fetch_teams(self):
        """Fetch the list of teams from the API."""
        url = "https://api.streamplay.streamamg.com/fixtures/basketball/p/3001497?q=(type:fixture)&offset=0&limit=25"
        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            _LOGGER.error("Failed to fetch teams: %s", response.status)
                            return None
                        data = await response.json()
                        teams = []
                        for fixture in data["fixtures"]:
                            home_team = fixture["homeTeam"]
                            away_team = fixture["awayTeam"]
                            if home_team not in teams:
                                teams.append(home_team)
                            if away_team not in teams:
                                teams.append(away_team)
                        return teams
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP error fetching teams: %s", err)
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout error fetching teams")
        except Exception as err:
            _LOGGER.error("Unexpected error fetching teams: %s", err)
        return None

    async def async_step_import(self, user_input=None):
        """Handle import from configuration.yaml."""
        return await self.async_step_user(user_input)
