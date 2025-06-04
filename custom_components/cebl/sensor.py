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

    # Add sensors without waiting for coordinator data - they will handle empty data gracefully
    async_add_entities(sensors, update_before_add=False)

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
        if not data:
            _LOGGER.debug("No coordinator data available yet")
            return None
            
        fixtures = data.get('fixtures', [])
        if not fixtures:
            _LOGGER.debug("No fixtures available")
            return None
        
        # Find all fixtures for this team
        team_fixtures = []
        for fixture in fixtures:
            try:
                home_team_id = str(fixture['homeTeam']['id'])
                away_team_id = str(fixture['awayTeam']['id'])
                
                if home_team_id == self._team_id or away_team_id == self._team_id:
                    team_fixtures.append(fixture)
            except (KeyError, TypeError) as e:
                _LOGGER.debug(f"Invalid fixture data: {e}")
                continue
        
        if not team_fixtures:
            _LOGGER.debug(f"No fixtures found for team {self._team_id}")
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
        if not data:
            _LOGGER.debug("No coordinator data available for live data")
            return None, None
            
        live_scores = data.get('live_scores', {})
        if not live_scores:
            _LOGGER.debug("No live scores available")
            return None, None
        
        for game_id, live_data in live_scores.items():
            try:
                # Check if this team is in this game
                fixture = None
                fixtures = data.get('fixtures', [])
                for f in fixtures:
                    if f.get('id') == int(game_id):
                        fixture = f
                        break
                
                if fixture:
                    home_team_id = str(fixture['homeTeam']['id'])
                    away_team_id = str(fixture['awayTeam']['id'])
                    
                    if home_team_id == self._team_id or away_team_id == self._team_id:
                        return live_data, fixture
            except (KeyError, TypeError, ValueError) as e:
                _LOGGER.debug(f"Error processing live data for game {game_id}: {e}")
                continue
        
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
            self._update_live_game_state(live_data)
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

    def _update_live_game_state(self, game_data):
        """Update state with live game data."""
        try:
            # Extract game info from different possible structures
            game_info = {}
            
            # Handle fixture-style live data first (with live field)
            if 'homeTeam' in game_data and 'awayTeam' in game_data:
                home_team = game_data['homeTeam']
                away_team = game_data['awayTeam']
                is_home_team = str(home_team['id']) == self._team_id
                
                # Use API live field as primary indicator
                is_live_from_api = game_data.get('live', 0) == 1
                
                game_info = {
                    'home_score': self._safe_score(home_team.get('score', 0)),
                    'away_score': self._safe_score(away_team.get('score', 0)),
                    'team_score': self._safe_score(home_team.get('score', 0)) if is_home_team else self._safe_score(away_team.get('score', 0)),
                    'opponent_score': self._safe_score(away_team.get('score', 0)) if is_home_team else self._safe_score(home_team.get('score', 0)),
                    'clock': game_data.get('clock', '00:00:00'),
                    'period': int(game_data.get('period', 0)),
                    'period_type': game_data.get('period_type', 'REGULAR'),
                    'is_live_api': is_live_from_api  # Store the API live indicator
                }
                
                # Set game state based on API live field primarily
                if is_live_from_api:
                    self._state = "IN"
                    self._is_live_game = True
                    _LOGGER.debug(f"Game {self._team_id}: Live game detected via API live=1")
                else:
                    # If API says not live, check if it's completed
                    game_status = game_data.get('status', '').upper()
                    if game_status in ['COMPLETE', 'COMPLETED', 'FINAL']:
                        self._state = "POST"
                        self._is_live_game = False
                        _LOGGER.debug(f"Game {self._team_id}: Game completed (API live=0, status={game_status})")
                    else:
                        # Unclear state - use conservative approach
                        self._state = "IN"
                        self._is_live_game = True
                        _LOGGER.debug(f"Game {self._team_id}: Uncertain state, assuming live (status={game_status})")
                
            # Handle old tm.1/tm.2 structure as fallback
            elif 'tm' in game_data and len(game_data['tm']) >= 2:
                # Original tm.1/tm.2 extraction logic
                tm1_data = game_data['tm'][0] if len(game_data['tm']) > 0 else {}
                tm2_data = game_data['tm'][1] if len(game_data['tm']) > 1 else {}
                
                # Determine which team is ours
                is_home_team = str(tm1_data.get('id', '')) == self._team_id
                our_team_data = tm1_data if is_home_team else tm2_data
                opponent_data = tm2_data if is_home_team else tm1_data
                
                game_info = {
                    'home_score': self._safe_score(tm1_data.get('score', 0)),
                    'away_score': self._safe_score(tm2_data.get('score', 0)),
                    'team_score': self._safe_score(our_team_data.get('score', 0)),
                    'opponent_score': self._safe_score(opponent_data.get('score', 0)),
                    'clock': game_data.get('clock', '00:00:00'),
                    'period': int(game_data.get('period', 0)),
                    'period_type': game_data.get('periodType', 'REGULAR'),
                    'is_live_api': None  # No API live field available in this format
                }
                
                # Fall back to clock/period logic for tm structure
                clock_str = game_info['clock']
                period = game_info['period']
                
                # Parse clock time
                is_clock_running = True
                try:
                    if ':' in clock_str:
                        time_parts = clock_str.split(':')
                        if len(time_parts) >= 2:
                            minutes = int(time_parts[0])
                            seconds = int(time_parts[1])
                            is_clock_running = minutes > 0 or seconds > 0
                except (ValueError, IndexError):
                    is_clock_running = True  # Assume running if can't parse
                
                # Determine game state based on period and clock
                if period >= 4 and not is_clock_running and game_info['period_type'] == 'REGULAR':
                    self._state = "POST"
                    self._is_live_game = False
                    _LOGGER.debug(f"Game {self._team_id}: Game completed (period={period}, clock={clock_str})")
                elif period > 0:
                    self._state = "IN"
                    self._is_live_game = True
                    _LOGGER.debug(f"Game {self._team_id}: Game in progress (period={period}, clock={clock_str})")
                else:
                    self._state = "PRE"
                    self._is_live_game = False
                    _LOGGER.debug(f"Game {self._team_id}: Game not started (period={period})")
            
            else:
                _LOGGER.warning(f"Game {self._team_id}: Unrecognized live data structure")
                return
                
            # Update attributes with game info
            self._attributes.update({
                "team_score": game_info['team_score'],
                "opponent_score": game_info['opponent_score'],
                "game_clock": game_info['clock'],
                "period": game_info['period'],
                "period_type": game_info['period_type'],
                "game_status": self._state,
                "is_live": self._is_live_game,
                "score_difference": abs(game_info['team_score'] - game_info['opponent_score']),
                "last_updated": dt.now().isoformat(),
                "update_frequency": "30 seconds",
                "data_source": "live_data",
                # Debug info
                "raw_clock": game_info['clock'],
                "api_live_indicator": game_info.get('is_live_api'),
                "home_score_live": game_info['home_score'],
                "away_score_live": game_info['away_score']
            })
            
            _LOGGER.debug(f"Game {self._team_id}: Live state updated - {self._state}, Score: {game_info['team_score']}-{game_info['opponent_score']}, Period: {game_info['period']}, Clock: {game_info['clock']}")
            
        except Exception as e:
            _LOGGER.error(f"Game {self._team_id}: Error updating live game state: {e}")
            # Don't change state on error

    def _update_fixture_state(self, fixture):
        """Update state with fixture data only."""
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id
        
        # Parse start time
        start_time_utc = dt.parse_datetime(fixture.get('start_time_utc', ''))
        game_status = fixture.get('status', '').upper()
        
        # Use the reliable 'live' field from API as primary indicator
        is_live_from_api = fixture.get('live', 0) == 1
        
        # Simplified state determination using the live field
        if is_live_from_api:
            # API explicitly says the game is live
            self._state = "IN"
            self._is_live_game = True
            _LOGGER.debug(f"Game {self._team_id}: IN (API live=1) - Status: {game_status}")
        elif game_status in ['COMPLETE', 'COMPLETED', 'FINAL'] and start_time_utc and dt.now() > dt.as_local(start_time_utc) + timedelta(hours=1):
            # Game is completed and it's been at least 1 hour since start (more conservative)
            self._state = "POST"
            self._is_live_game = False
            _LOGGER.debug(f"Game {self._team_id}: POST (completed >1h ago) - Status: {game_status}")
        elif start_time_utc and dt.now() < dt.as_local(start_time_utc):
            # Future game
            self._state = "PRE"
            self._is_live_game = False
            _LOGGER.debug(f"Game {self._team_id}: PRE (future game) - Status: {game_status}")
        else:
            # Default to PRE for unknown states
            self._state = "PRE"
            self._is_live_game = False
            _LOGGER.debug(f"Game {self._team_id}: PRE (default) - Status: {game_status}, Live: {is_live_from_api}")
        
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
            # Debug info - now includes API live field
            "data_source": "fixture_only",
            "fixture_status": game_status,
            "api_live_field": is_live_from_api,
            "game_clock": fixture.get('clock', ''),
            "period": fixture.get('period', 0),
            "period_type": fixture.get('period_type', '')
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
        # Make unique ID unique per config entry to avoid conflicts
        self._unique_id = format_mac(f"cebl_league_scoreboard_{coordinator.entry.entry_id}")

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
        fixtures = data.get('fixtures', [])
        
        active_games = 0
        all_games = []
        has_live_games = False
        
        # Process both live data and fixtures to get complete game status
        processed_games = set()
        
        # First, process live data
        for game_id, live_data in live_scores.items():
            other_games = live_data.get('other_games', [])
            
            for game in other_games:
                game_id = str(game.get('id', ''))
                if game_id in processed_games:
                    continue
                processed_games.add(game_id)
                
                # Use API live field if available, otherwise fall back to clock/period logic
                is_live = False
                if 'live' in game:
                    is_live = game.get('live', 0) == 1
                else:
                    # Fallback to clock/period logic
                    clock = game.get('clock', '00:00')
                    period = game.get('period', 0)
                    is_live = clock != '00:00' or period > 0
                
                all_games.append({
                    "id": game_id,
                    "team1_name": game.get('team1_name', ''),
                    "team2_name": game.get('team2_name', ''),
                    "team1_score": game.get('team1_score', 0),
                    "team2_score": game.get('team2_score', 0),
                    "period": game.get('period', 0),
                    "clock": game.get('clock', '00:00'),
                    "team1_logo": game.get('team1_logo', ''),
                    "team2_logo": game.get('team2_logo', ''),
                    "is_live": is_live,
                    "api_live_field": game.get('live', 'N/A')
                })
                
                if is_live:
                    active_games += 1
                    has_live_games = True
        
        # Then process fixtures to catch any games not in live data
        for fixture in fixtures:
            game_id = str(fixture.get('id', ''))
            if game_id in processed_games:
                continue
            processed_games.add(game_id)
            
            # Use API live field if available
            is_live = fixture.get('live', 0) == 1
            
            all_games.append({
                "id": game_id,
                "team1_name": fixture.get('homeTeam', {}).get('name', ''),
                "team2_name": fixture.get('awayTeam', {}).get('name', ''),
                "team1_score": fixture.get('homeTeam', {}).get('score', 0),
                "team2_score": fixture.get('awayTeam', {}).get('score', 0),
                "period": fixture.get('period', 0),
                "clock": fixture.get('clock', '00:00'),
                "team1_logo": fixture.get('homeTeam', {}).get('logo', ''),
                "team2_logo": fixture.get('awayTeam', {}).get('logo', ''),
                "is_live": is_live,
                "api_live_field": fixture.get('live', 'N/A'),
                "status": fixture.get('status', '')
            })
            
            if is_live:
                active_games += 1
                has_live_games = True
        
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
            "update_frequency": "30 seconds" if has_live_games else "1 minute",
            "data_source": "combined_live_and_fixtures"
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
