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
    """Set up CEBL sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Get teams from config
    teams = entry.data.get("teams", [])
    
    # Create one comprehensive sensor per team
    for team_id in teams:
        entities.append(CEBLTeamSensor(hass, coordinator, team_id))
    
    async_add_entities(entities, update_before_add=False)

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
                
                _LOGGER.debug(f"time_until_game calc: start={start_time_local}, now={now}")
                
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
                    _LOGGER.debug(f"Calculated time_until_game: '{result}' (delta: {delta}, total_seconds: {delta.total_seconds()})")
                    return result
                else:
                    _LOGGER.debug(f"Game has already started - returning 'Starting soon' (game was {(now - start_time_local).total_seconds()} seconds ago)")
                    return "Starting soon"
            else:
                _LOGGER.warning(f"Could not parse start_time_utc: {start_time_utc}")
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"Could not calculate time until game for '{start_time_utc}': {e}")
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
                _LOGGER.debug(f"kick_off_in calc: start={start_time_local}, now={now}, seconds={seconds}")
                return seconds
            else:
                _LOGGER.warning(f"Could not parse start_time_utc: {start_time_utc}")
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"Could not calculate kick off seconds for '{start_time_utc}': {e}")
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
        
        # Simple transition logic: if completed game is >1 day old, move to next scheduled game
        if upcoming_games and completed_games:
            # Sort both lists
            upcoming_games.sort(key=lambda x: x[1] if x[1] else datetime.max.replace(tzinfo=pytz.UTC))
            completed_games.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=pytz.UTC), reverse=True)
            
            next_game = upcoming_games[0]
            recent_game = completed_games[0]
            
            recent_game_time = recent_game[1]
            
            if recent_game_time:
                time_since_last = (now - recent_game_time).total_seconds()
                
                # Simple rule: If completed game is older than 1 day (86400 seconds), show upcoming game
                if time_since_last > 86400:  # 1 day = 86400 seconds
                    _LOGGER.debug(f"Recent game is {time_since_last/86400:.1f} days old - moving to next scheduled game")
                    return next_game[0]
                else:
                    _LOGGER.debug(f"Recent game ended {time_since_last/3600:.1f} hours ago - still showing completed game")
                    return recent_game[0]
            else:
                # Fallback to upcoming if recent game time couldn't be parsed
                _LOGGER.debug("Could not parse recent game time - showing upcoming game")
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

class CEBLTeamSensor(CEBLBaseSensor):
    """Sensor for team information and statistics."""
    
    def __init__(self, hass: HomeAssistant, coordinator: DataUpdateCoordinator, team_id):
        super().__init__(hass, coordinator, team_id)
        
        # Get team name for proper entity naming
        self._team_name = self._get_team_name_from_data()
        self._team_slug = self._create_team_slug(self._team_name)
        
        # Use team name slug for unique ID instead of team ID number
        self._unique_id = format_mac(f"cebl_{self._team_slug}")
        self._current_fixture = None
    
    def _get_team_name_from_data(self):
        """Get team name from coordinator data."""
        try:
            fixtures = self.coordinator.data.get('fixtures', [])
            for fixture in fixtures:
                home_team = fixture.get('homeTeam', {})
                away_team = fixture.get('awayTeam', {})
                
                if str(home_team.get('id')) == self._team_id:
                    return home_team.get('name', f'Team {self._team_id}')
                elif str(away_team.get('id')) == self._team_id:
                    return away_team.get('name', f'Team {self._team_id}')
            
            # Fallback - try to extract from team ID mapping
            return f'Team {self._team_id}'
        except Exception as e:
            _LOGGER.debug(f"Error getting team name for {self._team_id}: {e}")
            return f'Team {self._team_id}'
    
    def _create_team_slug(self, team_name):
        """Create a valid entity ID slug from team name."""
        import re
        
        # Convert to lowercase and replace spaces/special chars with underscores
        slug = re.sub(r'[^a-z0-9]+', '_', team_name.lower())
        # Remove leading/trailing underscores
        slug = slug.strip('_')
        # Ensure it doesn't start with a number
        if slug and slug[0].isdigit():
            slug = f'team_{slug}'
        
        return slug or f'team_{self._team_id}'

    @property
    def name(self):
        # Use stored team name, fallback to attributes if needed
        team_name = self._team_name or self._attributes.get('team_name', f'Team {self._team_id}')
        return f"CEBL {team_name}"

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
        
        # Get the most current fixture to check game timing
        current_fixture = self._current_fixture
        
        # Check if we have live data AND if it's for the current/upcoming game
        if live_data and current_fixture:
            # Validate that live data matches the current fixture timing
            is_live_data_current = self._is_live_data_current(live_data, current_fixture)
            
            if is_live_data_current:
                # Live data is for current game - use it
                self._is_live_game = True
                self._update_live_game_state(live_data)
            else:
                # Live data is stale/old - use fixture data instead
                _LOGGER.debug(f"Game {self._team_id}: Live data appears to be from previous game, using fixture data")
                self._is_live_game = False
                self._update_fixture_state(current_fixture)
        elif live_data and not current_fixture:
            # Live data available but no fixture - use live data
            self._is_live_game = True
            self._update_live_game_state(live_data)
        else:
            # No live data, use fixture data
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

    def _is_live_data_current(self, live_data, fixture):
        """Check if live data is for the current/upcoming game vs old data."""
        try:
            from datetime import datetime
            import pytz
            
            # Get fixture start time
            fixture_start = fixture.get('start_time_utc', '')
            if not fixture_start:
                # No start time to compare - assume live data is current
                return True
            
            # Parse fixture start time
            try:
                if fixture_start.endswith('Z'):
                    fixture_dt = datetime.fromisoformat(fixture_start[:-1]).replace(tzinfo=pytz.UTC)
                else:
                    fixture_dt = datetime.fromisoformat(fixture_start).replace(tzinfo=pytz.UTC)
            except Exception:
                # Can't parse time - assume live data is current
                return True
            
            # Get current time
            now = datetime.now(pytz.UTC)
            
            # Check game status from fixture
            fixture_status = fixture.get('status', '').upper()
            
            # If fixture says SCHEDULED and start time is in future, live data is probably old
            if fixture_status == 'SCHEDULED' and fixture_dt > now:
                time_until_game = (fixture_dt - now).total_seconds()
                # If game is more than 1 hour in the future, live data is definitely old
                if time_until_game > 3600:  # 1 hour
                    _LOGGER.debug(f"Game {self._team_id}: Game scheduled for {fixture_dt}, {time_until_game/3600:.1f} hours away - live data is old")
                    return False
            
            # Check if live data has 'live' field indicating current status
            if 'live' in live_data:
                is_api_live = live_data.get('live', 0) == 1
                if not is_api_live and fixture_status == 'SCHEDULED':
                    _LOGGER.debug(f"Game {self._team_id}: API live=0 and fixture SCHEDULED - live data is old")
                    return False
            
            # If we get here, assume live data is current
            return True
            
        except Exception as e:
            _LOGGER.debug(f"Game {self._team_id}: Error validating live data currency: {e}")
            # On error, assume live data is current to avoid breaking functionality
            return True

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
                
            # Handle team1_*/team2_* structure (most common live data format)
            elif 'team1_name' in game_data and 'team2_name' in game_data:
                # This is the structured live data format with team1_*/team2_* keys
                _LOGGER.debug(f"Game {self._team_id}: Processing team1_*/team2_* live data structure")
                
                # Determine which team is ours and get home/away context
                # Get the fixture data to understand home/away assignment
                fixture = self._get_team_fixture()
                team1_name = game_data.get('team1_name', '')
                team2_name = game_data.get('team2_name', '')
                
                is_home_team = None
                our_team_name = None
                opponent_name = None
                
                if fixture:
                    home_team_name = fixture.get('homeTeam', {}).get('name', '')
                    away_team_name = fixture.get('awayTeam', {}).get('name', '')
                    home_team_id = str(fixture.get('homeTeam', {}).get('id', ''))
                    away_team_id = str(fixture.get('awayTeam', {}).get('id', ''))
                    
                    # Determine which team we are tracking
                    if self._team_id == home_team_id:
                        our_team_name = home_team_name
                        opponent_name = away_team_name
                        # Now determine if our team is team1 or team2 in the live data
                        if home_team_name == team1_name:
                            is_home_team = True  # We are home team, and we are team1
                        elif home_team_name == team2_name:
                            is_home_team = True  # We are home team, but we are team2 in live data
                        else:
                            is_home_team = True  # Default assumption
                            _LOGGER.debug(f"Game {self._team_id}: Name mismatch - fixture home: {home_team_name}, live teams: {team1_name}, {team2_name}")
                    elif self._team_id == away_team_id:
                        our_team_name = away_team_name
                        opponent_name = home_team_name
                        # Now determine if our team is team1 or team2 in the live data
                        if away_team_name == team1_name:
                            is_home_team = False  # We are away team, and we are team1
                        elif away_team_name == team2_name:
                            is_home_team = False  # We are away team, and we are team2 in live data
                        else:
                            is_home_team = False  # Default assumption
                            _LOGGER.debug(f"Game {self._team_id}: Name mismatch - fixture away: {away_team_name}, live teams: {team1_name}, {team2_name}")
                    else:
                        # Fallback if team ID doesn't match
                        is_home_team = True
                        our_team_name = team1_name
                        opponent_name = team2_name
                        _LOGGER.debug(f"Game {self._team_id}: Team ID not found in fixture, using team1 as default")
                else:
                    # No fixture available, assume team1 is our team
                    is_home_team = True
                    our_team_name = team1_name
                    opponent_name = team2_name
                    _LOGGER.debug(f"Game {self._team_id}: No fixture available, assuming team1")
                
                # Determine if our team is team1 or team2 based on name matching
                our_team_is_team1 = (our_team_name == team1_name)
                
                game_info = {
                    'home_score': self._safe_score(game_data.get('team1_score', 0)),
                    'away_score': self._safe_score(game_data.get('team2_score', 0)),
                    'team_score': self._safe_score(game_data.get('team1_score', 0)) if our_team_is_team1 else self._safe_score(game_data.get('team2_score', 0)),
                    'opponent_score': self._safe_score(game_data.get('team2_score', 0)) if our_team_is_team1 else self._safe_score(game_data.get('team1_score', 0)),
                    'clock': game_data.get('clock', '00:00:00'),
                    'period': int(game_data.get('period', 0)),
                    'period_type': game_data.get('period_type', 'REGULAR'),
                    'is_live_api': None,  # No explicit live field in this format
                    'in_ot': game_data.get('in_ot', 0)
                }
                
                _LOGGER.debug(f"Game {self._team_id}: Team mapping - Our team: {our_team_name} ({'team1' if our_team_is_team1 else 'team2'}), Opponent: {opponent_name}, Home/Away: {'home' if is_home_team else 'away'}")
                
                # Determine game state based on period, clock, and OT status
                clock_str = game_info['clock']
                period = game_info['period']
                in_ot = game_info['in_ot']
                
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
                
                # Determine game state
                if period >= 4 and not is_clock_running and not in_ot:
                    self._state = "POST"
                    self._is_live_game = False
                    _LOGGER.debug(f"Game {self._team_id}: Game completed (period={period}, clock={clock_str}, OT={in_ot})")
                elif period > 0 or in_ot:
                    self._state = "IN"
                    self._is_live_game = True
                    _LOGGER.debug(f"Game {self._team_id}: Game in progress (period={period}, clock={clock_str}, OT={in_ot})")
                else:
                    self._state = "PRE"
                    self._is_live_game = False
                    _LOGGER.debug(f"Game {self._team_id}: Game not started (period={period})")
            
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
                # Log unrecognized structure for future enhancement
                data_keys = list(game_data.keys()) if isinstance(game_data, dict) else str(type(game_data))
                _LOGGER.warning(f"Game {self._team_id}: Truly unrecognized live data structure. Keys: {data_keys}")
                _LOGGER.debug(f"Game {self._team_id}: Full data structure: {game_data}")
                
                # Provide minimal fallback
                game_info = {
                    'home_score': 0,
                    'away_score': 0,
                    'team_score': 0,
                    'opponent_score': 0,
                    'clock': '00:00:00',
                    'period': 0,
                    'period_type': 'UNKNOWN',
                    'is_live_api': None
                }
                
                # Default to live state since we got live data
                self._state = "IN"
                self._is_live_game = True
                _LOGGER.debug(f"Game {self._team_id}: Using minimal fallback for truly unknown structure")
                
            # Extract team stats and top scorer data if available
            # Determine if we're home team based on the data structure
            is_our_team_home = True  # Default assumption
            if 'homeTeam' in game_data and 'awayTeam' in game_data:
                # For fixture-style data
                is_our_team_home = str(game_data['homeTeam']['id']) == self._team_id
            elif 'team1_name' in game_data and 'team2_name' in game_data:
                # For team1_*/team2_* structure, need to check against fixture
                fixture = self._get_team_fixture()
                if fixture:
                    home_team_name = fixture.get('homeTeam', {}).get('name', '')
                    our_team_name = home_team_name if str(fixture.get('homeTeam', {}).get('id', '')) == self._team_id else fixture.get('awayTeam', {}).get('name', '')
                    is_our_team_home = (our_team_name == game_data.get('team1_name', ''))
            
            team_stats = self._extract_team_stats(game_data, is_our_team_home)
            top_scorer = self._extract_top_scorer(game_data, is_our_team_home)
            
            # Update attributes with game info, stats, and top scorer
            self._attributes.update({
                # Core game data
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
                "away_score_live": game_info['away_score'],
                
                # Team stats
                "stats_field_goal_percentage": team_stats.get('field_goal_percentage', 0),
                "stats_three_point_percentage": team_stats.get('three_point_percentage', 0),
                "stats_free_throw_percentage": team_stats.get('free_throw_percentage', 0),
                "stats_rebounds": team_stats.get('rebounds', 0),
                "stats_assists": team_stats.get('assists', 0),
                "stats_turnovers": team_stats.get('turnovers', 0),
                "stats_steals": team_stats.get('steals', 0),
                "stats_blocks": team_stats.get('blocks', 0),
                "stats_bench_points": team_stats.get('bench_points', 0),
                "stats_points_in_paint": team_stats.get('points_in_paint', 0),
                "stats_points_from_turnovers": team_stats.get('points_from_turnovers', 0),
                "stats_fast_break_points": team_stats.get('fast_break_points', 0),
                "stats_biggest_lead": team_stats.get('biggest_lead', 0),
                "stats_time_leading": team_stats.get('time_leading', 0),
                
                # Top scorer info
                "top_scorer_name": top_scorer.get('name', ''),
                "top_scorer_points": top_scorer.get('points', 0),
                "top_scorer_jersey": top_scorer.get('jersey', ''),
                "top_scorer_position": top_scorer.get('position', ''),
                "top_scorer_rebounds": top_scorer.get('rebounds', 0),
                "top_scorer_assists": top_scorer.get('assists', 0),
                "top_scorer_minutes": top_scorer.get('minutes', '0:00'),
                "top_scorer_plus_minus": top_scorer.get('plus_minus', 0),
                "top_scorer_fg_percentage": top_scorer.get('fg_percentage', 0),
                "top_scorer_photo": top_scorer.get('photo', ''),
                "top_scorer_is_starter": top_scorer.get('starter', False),
                "top_scorer_is_captain": top_scorer.get('captain', False)
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
        
        # Get the raw start_time_utc string for debugging
        start_time_utc_str = fixture.get('start_time_utc', '')
        
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
        
        # Calculate all timing attributes consistently
        kick_off_seconds = self._calculate_kick_off_in_seconds(start_time_utc_str)
        kick_off_friendly = self._calculate_time_until_game(start_time_utc_str)
        hours_since = self._calculate_hours_since_game(start_time_utc_str, game_status)
        
        # For PRE games, provide additional time context
        time_until_game = kick_off_friendly if self._state == "PRE" else None
        
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
            "start_time": start_time_utc_str,
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
            # FIXED: All timing calculations now use the same input and consistent logic
            "time_until_game": time_until_game,
            "kick_off_in": kick_off_seconds,
            "kick_off_in_friendly": kick_off_friendly,
            "hours_since_game": hours_since,
            "showing_completed_game": self._state == "POST",
            # Update tracking
            "last_updated": dt.now().isoformat(),
            "update_frequency": "30 seconds" if self._is_live_game else "1 minute",
            # Enhanced debug info to troubleshoot timing issues
            "data_source": "fixture_only",
            "fixture_status": game_status,
            "api_live_field": is_live_from_api,
            "game_clock": fixture.get('clock', ''),
            "period": fixture.get('period', 0),
            "period_type": fixture.get('period_type', ''),
            # Debug timing calculations
            "debug_start_time_utc_raw": start_time_utc_str,
            "debug_start_time_parsed": start_time_utc.isoformat() if start_time_utc else None,
            "debug_now": dt.now().isoformat(),
            "debug_state_logic": f"live_api={is_live_from_api}, status={game_status}, state={self._state}",
            # Consistency check
            "timing_consistency_check": {
                "kick_off_seconds": kick_off_seconds,
                "friendly_matches_seconds": kick_off_friendly == "Starting soon" if kick_off_seconds and kick_off_seconds < 0 else kick_off_friendly,
                "all_use_same_start_time": start_time_utc_str
            }
        }

    def _extract_team_stats(self, game_data, is_home_team):
        """Extract team statistics from live game data."""
        try:
            # Handle team1_*/team2_* structure first
            if 'team1_stats' in game_data and 'team2_stats' in game_data:
                team_stats_key = 'team1_stats' if is_home_team else 'team2_stats'
                return game_data.get(team_stats_key, {})
            
            # Handle tm.1/tm.2 structure
            elif 'tm' in game_data and len(game_data['tm']) >= 2:
                tm1 = game_data.get('tm', {}).get('1', {})
                tm2 = game_data.get('tm', {}).get('2', {})
                team_data = tm1 if is_home_team else tm2
                
                return {
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
            
            return {}
            
        except Exception as e:
            _LOGGER.debug(f"Game {self._team_id}: Error extracting team stats: {e}")
            return {}
    
    def _extract_top_scorer(self, game_data, is_home_team):
        """Extract top scorer information from live game data."""
        try:
            team_players = []
            
            # Handle team1_*/team2_* structure first
            if 'team1_players' in game_data and 'team2_players' in game_data:
                players_key = 'team1_players' if is_home_team else 'team2_players'
                team_players = game_data.get(players_key, [])
            
            # Handle tm.1/tm.2 structure
            elif 'tm' in game_data and len(game_data['tm']) >= 2:
                tm1 = game_data.get('tm', {}).get('1', {})
                tm2 = game_data.get('tm', {}).get('2', {})
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
                            "starter": player.get('starter', 0) == 1,
                            "captain": player.get('captain', 0) == 1
                        })
            
            # Find top scorer
            top_scorer = None
            max_points = 0
            
            for player in team_players:
                if player.get('points', 0) > max_points:
                    max_points = player.get('points', 0)
                    top_scorer = player
            
            return top_scorer if top_scorer else {}
            
        except Exception as e:
            _LOGGER.debug(f"Game {self._team_id}: Error extracting top scorer: {e}")
            return {}


