import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.util import dt

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up CEBL sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = [
        CEBLSensor(hass, coordinator, team_id)
        for team_id in coordinator.entry.data["teams"]
    ]

    if not sensors:
        _LOGGER.error("No sensors to add. Check team ID configuration.")
    else:
        _LOGGER.debug(f"Adding sensors: {sensors}")

    async_add_entities(sensors, True)

class CEBLSensor(CoordinatorEntity, Entity):
    def __init__(self, hass: HomeAssistant, coordinator: DataUpdateCoordinator, team_id):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self._team_id = str(team_id)
        self._state = None
        self._attributes = {}
        self._unique_id = format_mac(f"cebl_{self._team_id}")

        async_track_time_interval(self.hass, self._update_live_score, timedelta(seconds=30))
        async_track_time_change(self.hass, self._update_daily_fixtures, hour=0, minute=0, second=0)

    @property
    def name(self):
        return f"CEBL - {self._attributes.get('team_name', 'Team')}"

    @property
    def state(self):
        return self._state

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_added_to_hass(self):
        """Run when entity about to be added to Home Assistant."""
        self.async_on_remove(self.coordinator.async_add_listener(self._update_state))
        self._update_state()

    async def async_update(self):
        """Update the sensor state."""
        _LOGGER.debug(f"async_update called for team ID {self._team_id}")
        await self.coordinator.async_request_refresh()
        self._update_state()

    def _update_state(self):
        data = self.coordinator.data
        _LOGGER.debug(f"Updating sensor for team ID {self._team_id} with data: {data}")

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

        if self.entity_id:
            self.async_write_ha_state()

    async def _update_live_score(self, _):
        """Fetch and update live score data."""
        _LOGGER.debug(f"Updating live score for team ID {self._team_id}")
        if self._is_match_live():
            await self.coordinator.async_update_live_scores(None)
            self._update_live_data()

    def _is_match_live(self):
        live_data = self.coordinator.data.get('live_scores', [])
        for match in live_data:
            if match['homename'] == self._attributes.get('team_name') or match['awayname'] == self._attributes.get('team_name'):
                if match['matchStatus'] == 'IN_PROGRESS':
                    return True
        return False

    def _update_live_data(self):
        live_data = self.coordinator.data.get('live_scores', [])
        for match in live_data:
            if match['homename'] == self._attributes.get('team_name') or match['awayname'] == self._attributes.get('team_name'):
                _LOGGER.debug(f"Live match found for team: {self._attributes.get('team_name')}")
                self._attributes.update(self._parse_live_data(match))
                self._state = self._determine_live_state(match)
                if self.entity_id:
                    self.async_write_ha_state()
                break

    def _parse_live_data(self, match):
        return {
            'match_status': match['matchStatus'],
            'home_team_score': match['homescore'],
            'away_team_score': match['awayscore'],
            'match_period': match.get('period', 'Unknown'),
            'match_clock': match.get('clock', 'Unknown'),
        }

    def _determine_live_state(self, match):
        if match['matchStatus'] == 'IN_PROGRESS':
            return 'IN'
        elif match['matchStatus'] == 'COMPLETE':
            return 'POST'
        else:
            return 'PRE'

    async def _update_daily_fixtures(self, _):
        """Check daily for upcoming fixtures and update the entity."""
        _LOGGER.debug(f"Checking for upcoming fixtures daily for team ID {self._team_id}")
        await self.coordinator.async_request_refresh()
        self._update_state()

    def _parse_fixture(self, fixture):
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id

        # Parse the UTC date using Home Assistant's utility
        start_date_utc = dt.parse_datetime(fixture['startDate'])
        if not start_date_utc:
            start_date_utc = datetime.fromisoformat(fixture['startDate'].replace('Z', '+00:00'))
        
        # Convert to local time using Home Assistant's time zone
        start_date_local = dt.as_local(start_date_utc)

        return {
            'date': start_date_local.isoformat(),
            'kickoff_in': self._get_kickoff_in(start_date_local),
            'venue': fixture.get('stadium', {}).get('name'),
            'team_name': home_team['name'] if is_home_team else away_team['name'],
            'team_logo': home_team['logo'] if is_home_team else away_team['logo'],
            'opponent_name': away_team['name'] if is_home_team else home_team['name'],
            'opponent_homeaway': 'away' if is_home_team else 'home',
            'opponent_logo': away_team['logo'] if is_home_team else home_team['logo'],
        }

    def _determine_state(self, fixture):
        start_date_utc = dt.parse_datetime(fixture['startDate'])
        if not start_date_utc:
            start_date_utc = datetime.fromisoformat(fixture['startDate'].replace('Z', '+00:00'))
        
        start_date_local = dt.as_local(start_date_utc)
        now = dt.now()

        if now < start_date_local:
            return 'PRE'
        elif now > start_date_local + timedelta(hours=4):
            return 'POST'
        else:
            return 'IN'

    def _get_kickoff_in(self, start_date):
        now = dt.now()
        delta = start_date - now
        days, seconds = delta.days, delta.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if delta.total_seconds() > 0:
            if days > 0:
                return f"in {days} days"
            elif hours > 0:
                return f"in {hours} hours"
            elif minutes > 0:
                return f"in {minutes} minutes"
            else:
                return "now"
        else:
            delta = now - start_date
            days, seconds = delta.days, delta.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if days > 0:
                return f"{days} days ago"
            elif hours > 0:
                return f"{hours} hours ago"
            else:
                return f"{minutes} minutes ago"
