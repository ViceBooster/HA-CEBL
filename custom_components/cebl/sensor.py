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
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up CEBL sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = []
    
    # Create sensors for each selected team
    for team_id in coordinator.entry.data["teams"]:
        # Core game sensor
        sensors.append(CEBLGameSensor(hass, coordinator, team_id))
        # Team stats sensor
        sensors.append(CEBLTeamStatsSensor(hass, coordinator, team_id))
        # Top scorer sensor for the team
        sensors.append(CEBLTopScorerSensor(hass, coordinator, team_id))
    
    # League-wide sensors (only create once)
    if len(coordinator.entry.data["teams"]) > 0:
        sensors.append(CEBLLeagueScoreboardSensor(hass, coordinator))

    if not sensors:
        _LOGGER.error("No sensors to add. Check team ID configuration.")
    else:
        _LOGGER.debug(f"Adding {len(sensors)} sensors")

    async_add_entities(sensors, True)

class CEBLBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for CEBL sensors."""
    
    def __init__(self, hass: HomeAssistant, coordinator: DataUpdateCoordinator, team_id=None):
        super().__init__(coordinator)
        self.hass = hass
        self._team_id = str(team_id) if team_id else None
        self._state = None
        self._attributes = {}
        self._time_update_remover = None
        self._live_update_remover = None
        self._is_live_game = False
        
    async def async_added_to_hass(self):
        """Run when entity about to be added to Home Assistant."""
        self.async_on_remove(self.coordinator.async_add_listener(self._update_state))
        self._update_state()
        
        # Set up time-based updates for time-sensitive attributes
        self._setup_time_updates()

    async def async_will_remove_from_hass(self):
        """Clean up when entity is removed."""
        if self._time_update_remover:
            self._time_update_remover()
        if self._live_update_remover:
            self._live_update_remover()

    def _setup_time_updates(self):
        """Set up time-based updates for time-sensitive attributes."""
        # Update time-sensitive attributes every minute
        self._time_update_remover = async_track_time_interval(
            self.hass, self._async_time_update, timedelta(minutes=1)
        )
        
    def _setup_live_updates(self):
        """Set up frequent updates for live games (every 30 seconds)."""
        if self._live_update_remover:
            self._live_update_remover()
            
        self._live_update_remover = async_track_time_interval(
            self.hass, self._async_live_update, timedelta(seconds=30)
        )
        
    def _remove_live_updates(self):
        """Remove frequent live game updates."""
        if self._live_update_remover:
            self._live_update_remover()
            self._live_update_remover = None

    async def _async_time_update(self, _):
        """Update time-sensitive attributes every minute."""
        old_attributes = self._attributes.copy()
        self._update_time_sensitive_attributes()
        
        # Only trigger state update if time-sensitive attributes changed
        if self._attributes != old_attributes:
            self.async_write_ha_state()
            
    async def _async_live_update(self, _):
        """Update live game data every 30 seconds."""
        if self._is_live_game:
            # Force a coordinator refresh for live games
            await self.coordinator.async_request_refresh()

    def _update_time_sensitive_attributes(self):
        """Update only time-sensitive attributes without full state refresh."""
        # This will be overridden by subclasses that have time-sensitive attributes
        pass

    async def async_update(self):
        """Update the sensor state."""
        await self.coordinator.async_request_refresh()
        self._update_state()

    def _update_state(self):
        """Update the sensor state - to be implemented by subclasses."""
        pass
    
    def _safe_score(self, score_value):
        """Safely convert score to integer, handling None values."""
        if score_value is None:
            return 0
        try:
            return int(score_value)
        except (ValueError, TypeError):
            return 0
    
    def _calculate_hours_since_game(self, start_time_utc, game_status):
        """Safely calculate hours since game ended."""
        if not start_time_utc or game_status not in ['COMPLETE', 'COMPLETED', 'FINAL']:
            return None
        try:
            parsed_time = dt.parse_datetime(start_time_utc)
            if parsed_time:
                return (dt.now() - dt.as_local(parsed_time)).total_seconds() / 3600
        except (ValueError, TypeError) as e:
            _LOGGER.debug(f"Could not calculate hours since game: {e}")
        return None
    
    def _calculate_time_until_game(self, start_time_utc):
        """Calculate user-friendly time until game starts."""
        if not start_time_utc:
            _LOGGER.debug("No start_time_utc provided for time_until_game calculation")
            return None
        try:
            parsed_time = dt.parse_datetime(start_time_utc)
            if parsed_time:
                start_time_local = dt.as_local(parsed_time)
                now = dt.now()
                if now < start_time_local:
                    delta = start_time_local - now
                    if delta.days > 0:
                        result = f"In {delta.days} days"
                    elif delta.seconds > 3600:
                        hours = delta.seconds // 3600
                        result = f"In {hours} hours"
                    else:
                        minutes = delta.seconds // 60
                        result = f"In {minutes} minutes"
                    _LOGGER.debug(f"Calculated time_until_game: '{result}' (delta: {delta})")
                    return result
                else:
                    _LOGGER.debug("Game has already started - returning 'Starting soon'")
                    return "Starting soon"
            else:
                _LOGGER.debug(f"Could not parse start_time_utc: {start_time_utc}")
        except (ValueError, TypeError) as e:
            _LOGGER.debug(f"Could not calculate time until game for '{start_time_utc}': {e}")
        return None
    
    def _calculate_kick_off_in_seconds(self, start_time_utc):
        """Calculate seconds until game starts (negative if already started)."""
        if not start_time_utc:
            _LOGGER.debug("No start_time_utc provided for kick_off_in calculation")
            return None
        try:
            parsed_time = dt.parse_datetime(start_time_utc)
            if parsed_time:
                start_time_local = dt.as_local(parsed_time)
                now = dt.now()
                seconds = int((start_time_local - now).total_seconds())
                _LOGGER.debug(f"Calculated kick_off_in: {seconds} seconds (start: {start_time_local}, now: {now})")
                return seconds
            else:
                _LOGGER.debug(f"Could not parse start_time_utc: {start_time_utc}")
        except (ValueError, TypeError) as e:
            _LOGGER.debug(f"Could not calculate kick off seconds for '{start_time_utc}': {e}")
        return None

    def _get_team_fixture(self):
        """Get the most relevant fixture for this team (live > upcoming > recent)."""
        data = self.coordinator.data
        fixtures = data.get('fixtures', [])
        
        # Find all fixtures for this team
        team_fixtures = []
        for fixture in fixtures:
            home_team_id = str(fixture['homeTeam']['id'])
            away_team_id = str(fixture['awayTeam']['id'])
            
            if home_team_id == self._team_id or away_team_id == self._team_id:
                team_fixtures.append(fixture)
        
        if not team_fixtures:
            return None
        
        # Sort fixtures by priority: live > upcoming > recent
        from datetime import datetime
        import pytz
        
        now = datetime.now(pytz.UTC)
        live_games = []
        upcoming_games = []
        completed_games = []
        
        for fixture in team_fixtures:
            status = fixture.get('status', '').upper()
            start_time_str = fixture.get('start_time_utc', '')
            
            # Parse start time
            start_time = None
            if start_time_str:
                try:
                    # Handle different datetime formats
                    if 'T' in start_time_str:
                        if start_time_str.endswith('Z'):
                            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                        else:
                            start_time = datetime.fromisoformat(start_time_str)
                            if start_time.tzinfo is None:
                                start_time = start_time.replace(tzinfo=pytz.UTC)
                except ValueError:
                    _LOGGER.debug(f"Could not parse start time: {start_time_str}")
            
            # Categorize games
            if status in ['LIVE', 'IN_PROGRESS', 'HALFTIME', 'QUARTER_BREAK']:
                live_games.append(fixture)
            elif status in ['COMPLETE', 'COMPLETED', 'FINAL']:
                completed_games.append((fixture, start_time))
            elif start_time and now < start_time:
                upcoming_games.append((fixture, start_time))
            else:
                completed_games.append((fixture, start_time))
        
        # Return highest priority game available with smart transition logic
        if live_games:
            _LOGGER.debug(f"Found {len(live_games)} live games, returning first")
            return live_games[0]
        
        # Smart transition logic between completed and upcoming games
        if upcoming_games and completed_games:
            # Sort both lists
            upcoming_games.sort(key=lambda x: x[1] if x[1] else datetime.max.replace(tzinfo=pytz.UTC))
            completed_games.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=pytz.UTC), reverse=True)
            
            next_game = upcoming_games[0]
            recent_game = completed_games[0]
            
            next_game_time = next_game[1]
            recent_game_time = recent_game[1]
            
            if next_game_time and recent_game_time:
                time_until_next = (next_game_time - now).total_seconds()
                time_since_last = (now - recent_game_time).total_seconds()
                
                # Transition rules:
                # 1. If next game is within 48 hours (172800 seconds), prioritize it
                # 2. If recent game ended more than 12 hours ago (43200 seconds) AND next game is within 7 days, show upcoming
                # 3. Otherwise show recent game for up to 12 hours
                
                if time_until_next <= 172800:  # Next game within 48 hours
                    _LOGGER.debug(f"Next game within 48 hours ({time_until_next/3600:.1f}h), showing upcoming game")
                    return next_game[0]
                elif time_since_last > 43200 and time_until_next <= 604800:  # Recent game >12h old AND next game within 7 days
                    _LOGGER.debug(f"Recent game >12h old ({time_since_last/3600:.1f}h), next game within 7 days ({time_until_next/86400:.1f}d), showing upcoming game")
                    return next_game[0]
                else:
                    _LOGGER.debug(f"Showing recent game (ended {time_since_last/3600:.1f}h ago, next game in {time_until_next/86400:.1f}d)")
                    return recent_game[0]
            else:
                # Fallback to upcoming if times couldn't be parsed
                return next_game[0]
        
        if upcoming_games:
            # Sort upcoming games by start time (earliest first)
            upcoming_games.sort(key=lambda x: x[1] if x[1] else datetime.max.replace(tzinfo=pytz.UTC))
            _LOGGER.debug(f"Found {len(upcoming_games)} upcoming games, returning earliest")
            return upcoming_games[0][0]
        
        if completed_games:
            # Sort completed games by start time (most recent first)
            completed_games.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=pytz.UTC), reverse=True)
            _LOGGER.debug(f"Found {len(completed_games)} completed games, returning most recent")
            return completed_games[0][0]
        
        # Fallback to first game
        _LOGGER.debug("No categorized games found, returning first fixture")
        return team_fixtures[0]

    def _get_team_live_data(self):
        """Get live data for this team."""
        data = self.coordinator.data
        live_scores = data.get('live_scores', {})
        
        for game_id, live_data in live_scores.items():
            # Check if this team is in this game
            fixture = None
            for f in data.get('fixtures', []):
                if f.get('id') == int(game_id):
                    fixture = f
                    break
            
            if fixture:
                home_team_id = str(fixture['homeTeam']['id'])
                away_team_id = str(fixture['awayTeam']['id'])
                
                if home_team_id == self._team_id or away_team_id == self._team_id:
                    return live_data, fixture
        return None, None

class CEBLGameSensor(CEBLBaseSensor):
    """Sensor for game information and scores."""
    
    def __init__(self, hass: HomeAssistant, coordinator: DataUpdateCoordinator, team_id):
        super().__init__(hass, coordinator, team_id)
        self._unique_id = format_mac(f"cebl_game_{self._team_id}")
        self._current_fixture = None

    @property
    def name(self):
        team_name = self._attributes.get('team_name', 'Team')
        return f"CEBL {team_name} Game"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def icon(self):
        return "mdi:basketball"

    def _update_time_sensitive_attributes(self):
        """Update time-sensitive attributes like kick_off_in and kick_off_in_friendly."""
        if self._current_fixture and 'start_time_utc' in self._current_fixture:
            start_time_utc = self._current_fixture.get('start_time_utc')
            
            # Recalculate time-sensitive attributes
            kick_off_seconds = self._calculate_kick_off_in_seconds(start_time_utc)
            kick_off_friendly = self._calculate_time_until_game(start_time_utc)
            
            # Update only if values changed
            if self._attributes.get('kick_off_in') != kick_off_seconds:
                self._attributes['kick_off_in'] = kick_off_seconds
                
            if self._attributes.get('kick_off_in_friendly') != kick_off_friendly:
                self._attributes['kick_off_in_friendly'] = kick_off_friendly
                
            # Update hours since game for completed games
            if self._state == "POST":
                game_status = self._current_fixture.get('status', '').upper()
                hours_since = self._calculate_hours_since_game(start_time_utc, game_status)
                if self._attributes.get('hours_since_game') != hours_since:
                    self._attributes['hours_since_game'] = hours_since

    def _update_state(self):
        live_data, fixture = self._get_team_live_data()
        
        # Store current fixture for time-sensitive updates
        if fixture:
            self._current_fixture = fixture
        else:
            self._current_fixture = self._get_team_fixture()
        
        # Determine if this is a live game and manage update frequency
        was_live = self._is_live_game
        
        if live_data:
            # Live game data available - this is the most reliable indicator
            self._is_live_game = True
            self._update_live_game_state(live_data, fixture or self._current_fixture)
        else:
            # No live data, use fixture data with improved logic
            fixture = self._get_team_fixture()
            if fixture:
                self._update_fixture_state(fixture)
            else:
                self._is_live_game = False
                self._state = "No upcoming game"
                self._attributes = {"team_id": self._team_id}
        
        # Manage live update frequency
        if self._is_live_game and not was_live:
            # Game just went live, start frequent updates
            self._setup_live_updates()
            _LOGGER.debug(f"Started live updates for team {self._team_id}")
        elif not self._is_live_game and was_live:
            # Game is no longer live, stop frequent updates
            self._remove_live_updates()
            _LOGGER.debug(f"Stopped live updates for team {self._team_id}")

    def _update_live_game_state(self, live_data, fixture):
        """Update state with live game data."""
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id
        
        # Determine game status from live data
        clock = live_data.get('clock', '00:00')
        period = live_data.get('period', 0)
        in_ot = live_data.get('inOT', 0)
        
        # Improved game state logic - if we have live data, the game is likely live
        # Only mark as POST if we're absolutely sure the game is over
        is_clock_zero = clock in ['00:00', '0:00', ''] or (isinstance(clock, str) and clock.strip() == '')
        is_game_definitely_over = is_clock_zero and period >= 4 and not in_ot
        
        if is_game_definitely_over:
            # Game is definitely over - clock is 0 and we're past regulation with no OT
            self._state = "POST"
            self._is_live_game = False
            _LOGGER.debug(f"Game {self._team_id}: POST - Clock: {clock}, Period: {period}, OT: {in_ot}")
        elif period > 0:
            # Any period > 0 with live data means the game is in progress
            self._state = "IN"
            self._is_live_game = True
            _LOGGER.debug(f"Game {self._team_id}: IN - Clock: {clock}, Period: {period}, OT: {in_ot}")
        else:
            # Pre-game
            self._state = "PRE"
            self._is_live_game = False
            _LOGGER.debug(f"Game {self._team_id}: PRE - Clock: {clock}, Period: {period}, OT: {in_ot}")
        
        # Extract team data from live_data structure
        tm1 = live_data.get('tm', {}).get('1', {})
        tm2 = live_data.get('tm', {}).get('2', {})
        
        # Determine which team is team1 and team2 based on home/away
        if is_home_team:
            team_data = tm1
            opponent_data = tm2
            team_score = tm1.get('score', 0)
            opponent_score = tm2.get('score', 0)
            team_logo = tm1.get('logoS', {}).get('url', '')
            opponent_logo = tm2.get('logoS', {}).get('url', '')
        else:
            team_data = tm2
            opponent_data = tm1
            team_score = tm2.get('score', 0)
            opponent_score = tm1.get('score', 0)
            team_logo = tm2.get('logoS', {}).get('url', '')
            opponent_logo = tm1.get('logoS', {}).get('url', '')
        
        # Build comprehensive attributes
        self._attributes = {
            "team_id": self._team_id,
            "team_name": home_team['name'] if is_home_team else away_team['name'],
            "team_logo": team_logo,
            "team_score": team_score,
            "opponent_name": away_team['name'] if is_home_team else home_team['name'],
            "opponent_logo": opponent_logo,
            "opponent_score": opponent_score,
            "home_away": "home" if is_home_team else "away",
            "game_clock": clock,
            "period": period,
            "period_type": live_data.get('period_type', ''),
            "overtime": in_ot == 1,
            "venue": fixture.get('venue_name', ''),
            "match_id": live_data.get('match_id', ''),
            "officials": live_data.get('officials', []),
            "start_time": fixture.get('start_time_utc', ''),
            "competition": fixture.get('competition', ''),
            "status": fixture.get('status', ''),
            "stats_url": fixture.get('stats_url', ''),
            "cebl_stats_url": fixture.get('cebl_stats_url', ''),
            # Enhanced status tracking
            "game_status": self._state,
            "is_live": self._is_live_game,
            "is_final": is_game_definitely_over,
            "score_difference": abs(team_score - opponent_score),
            # Detailed score information for POST games
            "final_score": f"{team_score}-{opponent_score}" if self._state == "POST" else None,
            # Kick-off timing (useful for all states)
            "kick_off_in": self._calculate_kick_off_in_seconds(fixture.get('start_time_utc')),
            "kick_off_in_friendly": self._calculate_time_until_game(fixture.get('start_time_utc')),
            # Transition timing info
            "hours_since_game": None,  # Not applicable for live games
            "showing_completed_game": False,
            # Live game indicators
            "last_updated": dt.now().isoformat(),
            "update_frequency": "30 seconds" if self._is_live_game else "1 minute",
            # Debug info
            "data_source": "live_data",
            "raw_clock": clock,
            "raw_period": period,
            "raw_in_ot": in_ot
        }

    def _update_fixture_state(self, fixture):
        """Update state with fixture data only."""
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id
        
        # Parse start time
        start_time_utc = dt.parse_datetime(fixture.get('start_time_utc', ''))
        game_status = fixture.get('status', '').upper()
        
        # Improved state determination - be more conservative about POST state
        # Only trust fixture status for clearly completed games
        if game_status in ['LIVE', 'IN_PROGRESS', 'HALFTIME', 'QUARTER_BREAK']:
            self._state = "IN"  # Live game in progress
            self._is_live_game = True
            _LOGGER.debug(f"Game {self._team_id}: IN (fixture) - Status: {game_status}")
        elif game_status in ['COMPLETE', 'COMPLETED', 'FINAL'] and start_time_utc and dt.now() > dt.as_local(start_time_utc) + timedelta(hours=3):
            # Only mark as POST if the game is definitely over (status says so AND it's been 3+ hours since start)
            self._state = "POST"  # Completed game
            self._is_live_game = False
            _LOGGER.debug(f"Game {self._team_id}: POST (fixture) - Status: {game_status}, Hours since start: {(dt.now() - dt.as_local(start_time_utc)).total_seconds() / 3600:.1f}")
        elif start_time_utc and dt.now() < dt.as_local(start_time_utc):
            # Future game
            self._state = "PRE"  # Scheduled/upcoming game
            self._is_live_game = False
            _LOGGER.debug(f"Game {self._team_id}: PRE (fixture) - Status: {game_status}")
        else:
            # Unknown state - be conservative and assume it could be live
            self._state = "IN"  # Assume live if uncertain
            self._is_live_game = True
            _LOGGER.warning(f"Game {self._team_id}: Uncertain state, assuming IN - Status: {game_status}")
        
        self._attributes = {
            "team_id": self._team_id,
            "team_name": home_team['name'] if is_home_team else away_team['name'],
            "team_logo": home_team.get('logo') or '',
            "team_score": self._safe_score(home_team.get('score')) if is_home_team else self._safe_score(away_team.get('score')),
            "opponent_name": away_team['name'] if is_home_team else home_team['name'],
            "opponent_logo": (away_team.get('logo') or '') if is_home_team else (home_team.get('logo') or ''),
            "opponent_score": self._safe_score(away_team.get('score')) if is_home_team else self._safe_score(home_team.get('score')),
            "home_away": "home" if is_home_team else "away",
            "venue": fixture.get('venue_name', ''),
            "start_time": fixture.get('start_time_utc', ''),
            "competition": fixture.get('competition', ''),
            "status": fixture.get('status', ''),
            "stats_url": fixture.get('stats_url', ''),
            "cebl_stats_url": fixture.get('cebl_stats_url', ''),
            # Enhanced status tracking
            "game_status": self._state,
            "is_live": self._is_live_game,
            "is_final": self._state == "POST",
            "is_upcoming": start_time_utc and dt.now() < dt.as_local(start_time_utc) if start_time_utc else False,
            "score_difference": abs(self._safe_score(home_team.get('score') if is_home_team else away_team.get('score')) - 
                                   self._safe_score(away_team.get('score') if is_home_team else home_team.get('score'))),
            # Detailed score information for POST games
            "final_score": f"{self._safe_score(home_team.get('score')) if is_home_team else self._safe_score(away_team.get('score'))}-{self._safe_score(away_team.get('score')) if is_home_team else self._safe_score(home_team.get('score'))}" if self._state == "POST" else None,
            # Time until game (for PRE state)
            "time_until_game": self._calculate_time_until_game(fixture.get('start_time_utc', '')) if self._state == "PRE" else None,
            # Kick-off timing (useful for all states)
            "kick_off_in": self._calculate_kick_off_in_seconds(fixture.get('start_time_utc', '')),
            "kick_off_in_friendly": self._calculate_time_until_game(fixture.get('start_time_utc', '')),
            # Transition timing info
            "hours_since_game": self._calculate_hours_since_game(fixture.get('start_time_utc', ''), game_status),
            "showing_completed_game": self._state == "POST",
            # Update tracking
            "last_updated": dt.now().isoformat(),
            "update_frequency": "30 seconds" if self._is_live_game else "1 minute",
            # Debug info
            "data_source": "fixture_only",
            "fixture_status": game_status
        }

class CEBLTeamStatsSensor(CEBLBaseSensor):
    """Sensor for team statistics."""
    
    def __init__(self, hass: HomeAssistant, coordinator: DataUpdateCoordinator, team_id):
        super().__init__(hass, coordinator, team_id)
        self._unique_id = format_mac(f"cebl_team_stats_{self._team_id}")

    @property
    def name(self):
        team_name = self._attributes.get('team_name', 'Team')
        return f"CEBL {team_name} Stats"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def icon(self):
        return "mdi:chart-box"

    def _update_state(self):
        live_data, fixture = self._get_team_live_data()
        
        # Determine if this is a live game and manage update frequency
        was_live = self._is_live_game
        
        if live_data and fixture:
            self._is_live_game = True
            home_team = fixture['homeTeam']
            away_team = fixture['awayTeam']
            is_home_team = str(home_team['id']) == self._team_id
            
            # Try to get team stats from processed data first
            team_stats = live_data.get('team1_stats' if is_home_team else 'team2_stats', {})
            
            # If processed stats are empty, extract from raw data
            if not team_stats:
                tm1 = live_data.get('tm', {}).get('1', {})
                tm2 = live_data.get('tm', {}).get('2', {})
                team_data = tm1 if is_home_team else tm2
                
                team_stats = {
                    "field_goal_percentage": team_data.get('tot_sFieldGoalsPercentage', 0),
                    "three_point_percentage": team_data.get('tot_sThreePointersPercentage', 0),
                    "free_throw_percentage": team_data.get('tot_sFreeThrowsPercentage', 0),
                    "rebounds": team_data.get('tot_sReboundsTotal', 0),
                    "assists": team_data.get('tot_sAssists', 0),
                    "turnovers": team_data.get('tot_sTurnovers', 0),
                    "steals": team_data.get('tot_sSteals', 0),
                    "blocks": team_data.get('tot_sBlocks', 0),
                    "bench_points": team_data.get('tot_sBenchPoints', 0),
                    "points_in_paint": team_data.get('tot_sPointsInThePaint', 0),
                    "points_from_turnovers": team_data.get('tot_sPointsFromTurnovers', 0),
                    "fast_break_points": team_data.get('tot_sPointsFastBreak', 0),
                    "biggest_lead": team_data.get('tot_sBiggestLead', 0),
                    "time_leading": team_data.get('tot_sTimeLeading', 0)
                }
            
            # State is field goal percentage
            self._state = team_stats.get('field_goal_percentage', 0)
            
            self._attributes = {
                "team_id": self._team_id,
                "team_name": home_team['name'] if is_home_team else away_team['name'],
                "field_goal_percentage": team_stats.get('field_goal_percentage', 0),
                "three_point_percentage": team_stats.get('three_point_percentage', 0),
                "free_throw_percentage": team_stats.get('free_throw_percentage', 0),
                "rebounds": team_stats.get('rebounds', 0),
                "assists": team_stats.get('assists', 0),
                "turnovers": team_stats.get('turnovers', 0),
                "steals": team_stats.get('steals', 0),
                "blocks": team_stats.get('blocks', 0),
                "bench_points": team_stats.get('bench_points', 0),
                "points_in_paint": team_stats.get('points_in_paint', 0),
                "points_from_turnovers": team_stats.get('points_from_turnovers', 0),
                "fast_break_points": team_stats.get('fast_break_points', 0),
                "biggest_lead": team_stats.get('biggest_lead', 0),
                "time_leading": team_stats.get('time_leading', 0),
                "is_live": True,
                "last_updated": dt.now().isoformat(),
                "update_frequency": "30 seconds",
                "data_source": "raw_tm_data" if not live_data.get('team1_stats') else "processed_data"
            }
        else:
            self._is_live_game = False
            self._state = "No game data"
            fixture = self._get_team_fixture()
            team_name = "Team"
            if fixture:
                home_team = fixture['homeTeam']
                away_team = fixture['awayTeam']
                is_home_team = str(home_team['id']) == self._team_id
                team_name = home_team['name'] if is_home_team else away_team['name']
            
            self._attributes = {
                "team_id": self._team_id,
                "team_name": team_name,
                "is_live": False,
                "last_updated": dt.now().isoformat(),
                "update_frequency": "1 minute",
                "data_source": "fixture_only"
            }
        
        # Manage live update frequency
        if self._is_live_game and not was_live:
            # Game just went live, start frequent updates
            self._setup_live_updates()
            _LOGGER.debug(f"Started live updates for team {self._team_id} stats")
        elif not self._is_live_game and was_live:
            # Game is no longer live, stop frequent updates
            self._remove_live_updates()
            _LOGGER.debug(f"Stopped live updates for team {self._team_id} stats")

class CEBLTopScorerSensor(CEBLBaseSensor):
    """Sensor for team's top scorer in current game."""
    
    def __init__(self, hass: HomeAssistant, coordinator: DataUpdateCoordinator, team_id):
        super().__init__(hass, coordinator, team_id)
        self._unique_id = format_mac(f"cebl_top_scorer_{self._team_id}")

    @property
    def name(self):
        team_name = self._attributes.get('team_name', 'Team')
        return f"CEBL {team_name} Top Scorer"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def icon(self):
        return "mdi:account-star"

    def _update_state(self):
        live_data, fixture = self._get_team_live_data()
        
        # Determine if this is a live game and manage update frequency
        was_live = self._is_live_game
        
        if live_data and fixture:
            self._is_live_game = True
            home_team = fixture['homeTeam']
            away_team = fixture['awayTeam']
            is_home_team = str(home_team['id']) == self._team_id
            
            # Try to get team players from the live data structure
            team_players = live_data.get('team1_players' if is_home_team else 'team2_players', [])
            
            # If the processed team_players list is empty, extract from raw data
            if not team_players:
                tm1 = live_data.get('tm', {}).get('1', {})
                tm2 = live_data.get('tm', {}).get('2', {})
                team_data = tm1 if is_home_team else tm2
                players = team_data.get('pl', {})
                
                team_players = []
                for player_id, player in players.items():
                    if player.get('sMinutes', '0:00') != '0:00':  # Only players who played
                        team_players.append({
                            "name": player.get('name', ''),
                            "jersey": player.get('shirtNumber', ''),
                            "position": player.get('playingPosition', ''),
                            "points": player.get('sPoints', 0),
                            "rebounds": player.get('sReboundsTotal', 0),
                            "assists": player.get('sAssists', 0),
                            "minutes": player.get('sMinutes', '0:00'),
                            "plus_minus": player.get('sPlusMinusPoints', 0),
                            "fg_percentage": player.get('sFieldGoalsPercentage', 0),
                            "three_point_percentage": player.get('sThreePointersPercentage', 0),
                            "photo": player.get('photoS', ''),
                            "starter": player.get('starter', 0),
                            "captain": player.get('captain', 0)
                        })
            
            # Find top scorer on this team
            top_scorer = None
            max_points = 0
            
            for player in team_players:
                if player.get('points', 0) > max_points:
                    max_points = player.get('points', 0)
                    top_scorer = player
            
            if top_scorer:
                self._state = f"{top_scorer.get('name', 'Unknown')} - {max_points} pts"
                self._attributes = {
                    "team_id": self._team_id,
                    "team_name": home_team['name'] if is_home_team else away_team['name'],
                    "player_name": top_scorer.get('name', ''),
                    "player_jersey": top_scorer.get('jersey', ''),
                    "player_position": top_scorer.get('position', ''),
                    "points": top_scorer.get('points', 0),
                    "rebounds": top_scorer.get('rebounds', 0),
                    "assists": top_scorer.get('assists', 0),
                    "minutes": top_scorer.get('minutes', '0:00'),
                    "plus_minus": top_scorer.get('plus_minus', 0),
                    "fg_percentage": top_scorer.get('fg_percentage', 0),
                    "three_point_percentage": top_scorer.get('three_point_percentage', 0),
                    "player_photo": top_scorer.get('photo', ''),
                    "starter": top_scorer.get('starter', 0) == 1,
                    "captain": top_scorer.get('captain', 0) == 1,
                    "is_live": True,
                    "last_updated": dt.now().isoformat(),
                    "update_frequency": "30 seconds",
                    "data_source": "team_players" if not live_data.get('team1_players') else "processed_data"
                }
            else:
                self._state = "No player data"
                self._attributes = {
                    "team_id": self._team_id,
                    "team_name": home_team['name'] if is_home_team else away_team['name'],
                    "is_live": True,
                    "last_updated": dt.now().isoformat(),
                    "update_frequency": "30 seconds",
                    "data_source": "no_data"
                }
        else:
            self._is_live_game = False
            self._state = "No game data"
            fixture = self._get_team_fixture()
            team_name = "Team"
            if fixture:
                home_team = fixture['homeTeam']
                away_team = fixture['awayTeam']
                is_home_team = str(home_team['id']) == self._team_id
                team_name = home_team['name'] if is_home_team else away_team['name']
            
            self._attributes = {
                "team_id": self._team_id,
                "team_name": team_name,
                "is_live": False,
                "last_updated": dt.now().isoformat(),
                "update_frequency": "1 minute",
                "data_source": "fixture_only"
            }
        
        # Manage live update frequency
        if self._is_live_game and not was_live:
            # Game just went live, start frequent updates
            self._setup_live_updates()
            _LOGGER.debug(f"Started live updates for team {self._team_id} top scorer")
        elif not self._is_live_game and was_live:
            # Game is no longer live, stop frequent updates
            self._remove_live_updates()
            _LOGGER.debug(f"Stopped live updates for team {self._team_id} top scorer")

class CEBLLeagueScoreboardSensor(CEBLBaseSensor):
    """Sensor for league-wide scoreboard."""
    
    def __init__(self, hass: HomeAssistant, coordinator: DataUpdateCoordinator):
        super().__init__(hass, coordinator)
        self._unique_id = format_mac("cebl_league_scoreboard")

    @property
    def name(self):
        return "CEBL League Scoreboard"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def icon(self):
        return "mdi:scoreboard"

    def _update_state(self):
        data = self.coordinator.data
        live_scores = data.get('live_scores', {})
        
        # Count active games
        active_games = 0
        all_games = []
        has_live_games = False
        
        for game_id, live_data in live_scores.items():
            other_games = live_data.get('other_games', [])
            
            for game in other_games:
                all_games.append({
                    "team1_name": game.get('team1_name', ''),
                    "team2_name": game.get('team2_name', ''),
                    "team1_score": game.get('team1_score', 0),
                    "team2_score": game.get('team2_score', 0),
                    "period": game.get('period', 0),
                    "clock": game.get('clock', '00:00'),
                    "team1_logo": game.get('team1_logo', ''),
                    "team2_logo": game.get('team2_logo', '')
                })
                
                # Count as active if not final
                if game.get('clock', '00:00') != '00:00' or game.get('period', 0) < 4:
                    active_games += 1
                    has_live_games = True
            
            # Only need to process one live_data entry for other_games
            break
        
        # Determine if this sensor should use live updates
        was_live = self._is_live_game
        self._is_live_game = has_live_games
        
        self._state = f"{active_games} active games"
        self._attributes = {
            "active_games": active_games,
            "total_games": len(all_games),
            "games": all_games[:10],  # Limit to 10 games for attributes
            "is_live": has_live_games,
            "last_updated": dt.now().isoformat(),
            "update_frequency": "30 seconds" if has_live_games else "1 minute"
        }
        
        # Manage live update frequency
        if self._is_live_game and not was_live:
            # Games are now live, start frequent updates
            self._setup_live_updates()
            _LOGGER.debug("Started live updates for league scoreboard")
        elif not self._is_live_game and was_live:
            # No more live games, stop frequent updates
            self._remove_live_updates()
            _LOGGER.debug("Stopped live updates for league scoreboard")
