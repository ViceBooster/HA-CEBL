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

    def _get_team_fixture(self):
        """Get the fixture for this team."""
        data = self.coordinator.data
        for fixture in data.get('fixtures', []):
            home_team_id = str(fixture['homeTeam']['id'])
            away_team_id = str(fixture['awayTeam']['id'])
            
            if home_team_id == self._team_id or away_team_id == self._team_id:
                return fixture
        return None

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
        
        # Determine game status
        clock = live_data.get('clock', '00:00')
        period = live_data.get('period', 0)
        
        if clock == '00:00' and period >= 4:
            self._state = "Final"
        elif clock != '00:00' or period > 0:
            self._state = f"Period {period} - {clock}"
        else:
            self._state = "Pre-Game"
        
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
            "cebl_stats_url": fixture.get('cebl_stats_url', '')
        }

    def _update_fixture_state(self, fixture):
        """Update state with fixture data only."""
        home_team = fixture['homeTeam']
        away_team = fixture['awayTeam']
        is_home_team = str(home_team['id']) == self._team_id
        
        # Parse start time
        start_time_utc = dt.parse_datetime(fixture.get('start_time_utc', ''))
        if start_time_utc:
            start_time_local = dt.as_local(start_time_utc)
            now = dt.now()
            
            if now < start_time_local:
                delta = start_time_local - now
                if delta.days > 0:
                    self._state = f"In {delta.days} days"
                elif delta.seconds > 3600:
                    hours = delta.seconds // 3600
                    self._state = f"In {hours} hours"
                else:
                    minutes = delta.seconds // 60
                    self._state = f"In {minutes} minutes"
            else:
                self._state = fixture.get('status', 'Scheduled')
        else:
            self._state = fixture.get('status', 'Scheduled')
        
        self._attributes = {
            "team_id": self._team_id,
            "team_name": home_team['name'] if is_home_team else away_team['name'],
            "team_logo": home_team.get('logo', ''),
            "team_score": home_team.get('score', 0) if is_home_team else away_team.get('score', 0),
            "opponent_name": away_team['name'] if is_home_team else home_team['name'],
            "opponent_logo": away_team.get('logo', '') if is_home_team else home_team.get('logo', ''),
            "opponent_score": away_team.get('score', 0) if is_home_team else home_team.get('score', 0),
            "home_away": "home" if is_home_team else "away",
            "venue": fixture.get('venue_name', ''),
            "start_time": fixture.get('start_time_utc', ''),
            "competition": fixture.get('competition', ''),
            "status": fixture.get('status', ''),
            "stats_url": fixture.get('stats_url', ''),
            "cebl_stats_url": fixture.get('cebl_stats_url', '')
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
