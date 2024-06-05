import logging
from datetime import datetime, timedelta
import pytz
import aiohttp
import json
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, API_URL_LIVE, API_URL_FIXTURES

_LOGGER = logging.getLogger(__name__)

EST = pytz.timezone("America/New_York")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up CEBL sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = [
        CEBLSensor(coordinator, team_id)
        for team_id in coordinator.entry.data["teams"]
    ]

    if not sensors:
        _LOGGER.error("No sensors to add. Check team ID configuration.")
    else:
        _LOGGER.debug(f"Adding sensors: {sensors}")

    async_add_entities(sensors, True)

class CEBLSensor(CoordinatorEntity, Entity):
    def __init__(self, coordinator: DataUpdateCoordinator, team_id):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._team_id = str(team_id)  # Ensure team_id is a string
        self._state = None
        self._attributes = {}
        self._unique_id = format_mac(f"cebl_{self._team_id}")
        self._update()

    @property
    def name(self):
        return f"CEBL {self._attributes.get('team_name', 'Team')}"

    @property
    def state(self):
        return self._state

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        """Update the sensor state."""
        await self.coordinator.async_request_refresh()
        self._update()

    def _update(self):
        data = self.coordinator.data
        _LOGGER.debug(f"Updating sensor for team ID {self._team_id} with data: {data}")

        # Fetch and update upcoming fixtures data
        for fixture in data.get('fixtures', []):
            home_team_id = str(fixture['homeTeam']['id'])
            away_team_id = str(fixture['awayTeam']['id'])
            _LOGGER.debug(f"Checking fixture: {fixture['id']}, Home Team ID: {home_team_id}, Away Team ID: {away_team_id}")

            if home_team_id == self._team_id or away_team_id == self._team_id:
                _LOGGER.debug(f"Match found for team ID {self._team_id} in fixture {fixture['id']}")
                self._attributes.update(self._parse_fixture(fixture))
                self._state = self._determine_state(fixture)
                break
        else:
            _LOGGER.debug(f"No match found for team ID {self._team_id}")
            if not self._state or self._state != 'IN':
                self._state = 'No upcoming fixture'

        # Fetch and update live score data
        hass = self.coordinator.hass
        hass.async_create_task(self._update_live_score())

    def _parse_fixture(self, fixture):
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id

        start_date_utc = datetime.fromisoformat(fixture['startDate'].replace('Z', '+00:00'))
        start_date_est = start_date_utc.astimezone(EST)

        return {
            'date': start_date_est.isoformat(),
            'kickoff_in': self._get_kickoff_in(start_date_est),
            'venue': fixture.get('stadium', {}).get('name'),
            'team_name': home_team['name'] if is_home_team else away_team['name'],
            'team_logo': home_team['logo'] if is_home_team else away_team['logo'],
            'opponent_abbr': away_team['name'] if is_home_team else home_team['name'],
            'opponent_id': away_team['id'] if is_home_team else home_team['id'],
            'opponent_name': away_team['name'] if is_home_team else home_team['name'],
            'opponent_homeaway': 'away' if is_home_team else 'home',
            'opponent_logo': away_team['logo'] if is_home_team else home_team['logo'],
            'last_update': fixture['updatedAt'],
        }

    def _determine_state(self, fixture):
        now = datetime.now(EST)
        start_date = datetime.fromisoformat(fixture['startDate'].replace('Z', '+00:00')).astimezone(EST)
        if now < start_date:
            return 'PRE'
        elif now > start_date + timedelta(hours=4):
            return 'POST'
        else:
            return 'IN'

    def _get_kickoff_in(self, start_date):
        now = datetime.now(EST)
        delta = start_date - now
        days, seconds = delta.days, delta.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if days > 0:
            return f"in {days} days"
        elif hours > 0:
            return f"in {hours} hours"
        else:
            return f"in {minutes} minutes"

    async def _update_live_score(self):
        """Fetch and update live score data."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL_LIVE) as response:
                    if response.content_type == "application/javascript":
                        text = await response.text()
                        live_data = json.loads(text)
                    else:
                        live_data = await response.json()

                    for match in live_data:
                        if str(match['hometeamId']) == self._team_id or str(match['awayteamId']) == self._team_id:
                            self._attributes.update(self._parse_live_data(match))
                            self._state = self._determine_live_state(match)
                            break
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Error fetching live score data: {e}")

    def _parse_live_data(self, match):
        return {
            'match_status': match['matchStatus'],
            'home_team_name': match['homename'],
            'home_team_score': match['homescore'],
            'away_team_name': match['awayname'],
            'away_team_score': match['awayscore'],
            'match_period': match['period'],
            'match_clock': match['clock'],
        }

    def _determine_live_state(self, match):
        if match['matchStatus'] == 'IN_PROGRESS':
            return 'IN'
        elif match['matchStatus'] == 'COMPLETE':
            return 'POST'
        else:
            return 'PRE'
