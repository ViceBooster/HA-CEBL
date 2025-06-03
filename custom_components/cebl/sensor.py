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
        
    async def async_added_to_hass(self):
        """Run when entity about to be added to Home Assistant."""
        self.async_on_remove(self.coordinator.async_add_listener(self._update_state))
        self._update_state()

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
            return None
        try:
            parsed_time = dt.parse_datetime(start_time_utc)
            if parsed_time:
                start_time_local = dt.as_local(parsed_time)
                now = dt.now()
                if now < start_time_local:
                    delta = start_time_local - now
                    if delta.days > 0:
                        return f"In {delta.days} days"
                    elif delta.seconds > 3600:
                        hours = delta.seconds // 3600
                        return f"In {hours} hours"
                    else:
                        minutes = delta.seconds // 60
                        return f"In {minutes} minutes"
                else:
                    return "Starting soon"
        except (ValueError, TypeError) as e:
            _LOGGER.debug(f"Could not calculate time until game: {e}")
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

    def _update_state(self):
        live_data, fixture = self._get_team_live_data()
        
        if live_data:
            # Live game data available
            self._update_live_game_state(live_data, fixture)
        else:
            # No live data, use fixture data
            fixture = self._get_team_fixture()
            if fixture:
                self._update_fixture_state(fixture)
            else:
                self._state = "No upcoming game"
                self._attributes = {"team_id": self._team_id}

    def _update_live_game_state(self, live_data, fixture):
        """Update state with live game data."""
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id
        
        # Determine game status from live data
        clock = live_data.get('clock', '00:00')
        period = live_data.get('period', 0)
        
        # Enhanced game state logic
        if clock == '00:00' and period >= 4:
            # Game is over
            self._state = "POST"
        elif period > 0 and (clock != '00:00' or period >= 1):
            # Game is in progress
            self._state = "IN"
        else:
            # Pre-game or game about to start
            self._state = "PRE"
        
        # Build comprehensive attributes
        self._attributes = {
            "team_id": self._team_id,
            "team_name": home_team['name'] if is_home_team else away_team['name'],
            "team_logo": live_data.get('team1_logo' if is_home_team else 'team2_logo', ''),
            "team_score": live_data.get('team1_score' if is_home_team else 'team2_score', 0),
            "opponent_name": away_team['name'] if is_home_team else home_team['name'],
            "opponent_logo": live_data.get('team2_logo' if is_home_team else 'team1_logo', ''),
            "opponent_score": live_data.get('team2_score' if is_home_team else 'team1_score', 0),
            "home_away": "home" if is_home_team else "away",
            "game_clock": clock,
            "period": period,
            "period_type": live_data.get('period_type', ''),
            "overtime": live_data.get('in_ot', 0) == 1,
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
            "is_live": period > 0 and clock != '00:00',
            "is_final": clock == '00:00' and period >= 4,
            "score_difference": abs(live_data.get('team1_score', 0) - live_data.get('team2_score', 0)),
            # Detailed score information for POST games
            "final_score": f"{live_data.get('team1_score' if is_home_team else 'team2_score', 0)}-{live_data.get('team2_score' if is_home_team else 'team1_score', 0)}" if self._state == "POST" else None,
            # Transition timing info
            "hours_since_game": None,  # Not applicable for live games
            "showing_completed_game": False
        }

    def _update_fixture_state(self, fixture):
        """Update state with fixture data only."""
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id
        
        # Parse start time
        start_time_utc = dt.parse_datetime(fixture.get('start_time_utc', ''))
        game_status = fixture.get('status', '').upper()
        
        # Determine proper state based on game status and time
        if game_status in ['LIVE', 'IN_PROGRESS', 'HALFTIME', 'QUARTER_BREAK']:
            self._state = "IN"  # Live game in progress
        elif game_status in ['COMPLETE', 'COMPLETED', 'FINAL']:
            self._state = "POST"  # Completed game
        else:
            self._state = "PRE"  # Scheduled/upcoming game
        
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
            "is_live": game_status in ['LIVE', 'IN_PROGRESS', 'HALFTIME', 'QUARTER_BREAK'],
            "is_final": game_status in ['COMPLETE', 'COMPLETED', 'FINAL'],
            "is_upcoming": start_time_utc and dt.now() < dt.as_local(start_time_utc) if start_time_utc else False,
            "score_difference": abs(self._safe_score(home_team.get('score') if is_home_team else away_team.get('score')) - 
                                   self._safe_score(away_team.get('score') if is_home_team else home_team.get('score'))),
            # Detailed score information for POST games
            "final_score": f"{self._safe_score(home_team.get('score')) if is_home_team else self._safe_score(away_team.get('score'))}-{self._safe_score(away_team.get('score')) if is_home_team else self._safe_score(home_team.get('score'))}" if self._state == "POST" else None,
            # Time until game (for PRE state)
            "time_until_game": self._calculate_time_until_game(start_time_utc) if self._state == "PRE" else None,
            # Transition timing info
            "hours_since_game": self._calculate_hours_since_game(start_time_utc, game_status),
            "showing_completed_game": game_status in ['COMPLETE', 'COMPLETED', 'FINAL']
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
        
        if live_data and fixture:
            home_team = fixture['homeTeam']
            away_team = fixture['awayTeam']
            is_home_team = str(home_team['id']) == self._team_id
            
            team_stats = live_data.get('team1_stats' if is_home_team else 'team2_stats', {})
            
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
                "time_leading": team_stats.get('time_leading', 0)
            }
        else:
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
                "team_name": team_name
            }

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
        
        if live_data and fixture:
            home_team = fixture['homeTeam']
            away_team = fixture['awayTeam']
            is_home_team = str(home_team['id']) == self._team_id
            
            team_players = live_data.get('team1_players' if is_home_team else 'team2_players', [])
            
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
                    "captain": top_scorer.get('captain', 0) == 1
                }
            else:
                self._state = "No player data"
                self._attributes = {
                    "team_id": self._team_id,
                    "team_name": home_team['name'] if is_home_team else away_team['name']
                }
        else:
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
                "team_name": team_name
            }

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
            
            # Only need to process one live_data entry for other_games
            break
        
        self._state = f"{active_games} active games"
        self._attributes = {
            "active_games": active_games,
            "total_games": len(all_games),
            "games": all_games[:10]  # Limit to 10 games for attributes
        }
