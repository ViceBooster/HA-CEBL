import logging
import aiohttp
import asyncio
import async_timeout
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN, API_URL_FIXTURES, API_URL_LIVE_BASE, API_HEADERS, PLATFORMS, STARTUP_MESSAGE

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

    # Schedule live score updates every minute
    async_track_time_interval(hass, coordinator.async_update_live_scores, timedelta(minutes=1))

    return True

class CEBLDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching CEBL data from the API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize."""
        self.entry = entry
        self.session = async_get_clientsession(hass)
        self.url_fixtures = API_URL_FIXTURES
        self.url_live_base = API_URL_LIVE_BASE
        self.headers = API_HEADERS
        self.teams = entry.data.get("teams", [])
        self.competition_ids = {}  # Store competition IDs for live scores
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
                async with self.session.get(self.url_fixtures, headers=self.headers) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Invalid response from API: {response.status}")
                        raise UpdateFailed(f"Invalid response from API: {response.status}")
                    
                    games = await response.json()
                    _LOGGER.debug(f"Fetched raw games data: {games}")
                    
                    # Filter games for selected teams and convert to expected format
                    fixtures = []
                    for game in games:
                        home_team_id = str(game.get("home_team_id", ""))
                        away_team_id = str(game.get("away_team_id", ""))
                        
                        if home_team_id in self.teams or away_team_id in self.teams:
                            # Convert to expected fixture format
                            fixture = {
                                "id": game.get("id"),
                                "homeTeam": {
                                    "id": home_team_id,
                                    "name": game.get("home_team_name", ""),
                                    "logo": game.get("home_team_logo_url", ""),
                                    "score": game.get("home_team_score", 0)
                                },
                                "awayTeam": {
                                    "id": away_team_id,
                                    "name": game.get("away_team_name", ""),
                                    "logo": game.get("away_team_logo_url", ""),
                                    "score": game.get("away_team_score", 0)
                                },
                                "status": game.get("status", ""),
                                "competition": game.get("competition", ""),
                                "venue_name": game.get("venue_name", ""),
                                "period": game.get("period", 0),
                                "start_time_utc": game.get("start_time_utc", ""),
                                "stats_url": game.get("stats_url_en", ""),
                                "cebl_stats_url": game.get("cebl_stats_url_en", "")
                            }
                            fixtures.append(fixture)
                            
                            # Extract competition ID from stats URL for live scores
                            stats_url = game.get("stats_url_en", "")
                            if "/u/CEBL/" in stats_url:
                                try:
                                    competition_id = stats_url.split("/u/CEBL/")[1].split("/")[0]
                                    self.competition_ids[game.get("id")] = competition_id
                                    _LOGGER.debug(f"Extracted competition ID {competition_id} for game {game.get('id')}")
                                except (IndexError, AttributeError):
                                    _LOGGER.warning(f"Could not extract competition ID from {stats_url}")
                    
                    _LOGGER.info(f"Filtered {len(fixtures)} fixtures for selected teams")
                    return {"fixtures": fixtures}
                    
        except aiohttp.ClientError as err:
            _LOGGER.error(f"HTTP error fetching games: {err}")
            raise UpdateFailed(f"HTTP error fetching games: {err}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout error fetching games")
            raise UpdateFailed("Timeout error fetching games")
        except Exception as err:
            _LOGGER.error(f"Unexpected error fetching games: {err}")
            raise UpdateFailed(f"Unexpected error fetching games: {err}")

    async def async_update_live_scores(self, _):
        """Fetch live score data from the API using competition IDs."""
        _LOGGER.info("Fetching live CEBL scores from API.")
        
        if not self.competition_ids:
            _LOGGER.debug("No competition IDs available for live score updates")
            return
            
        live_scores_data = {}
        
        for game_id, competition_id in self.competition_ids.items():
            try:
                live_url = f"{self.url_live_base}{competition_id}.json"
                async with async_timeout.timeout(10):
                    # Use minimal headers for live scores API
                    live_headers = {
                        'Accept': 'application/json',
                        'User-Agent': self.headers['User-Agent']
                    }
                    async with self.session.get(live_url, headers=live_headers) as response:
                        if response.status != 200:
                            _LOGGER.debug(f"No live data for competition {competition_id}: {response.status}")
                            continue

                        live_data = await response.json()
                        if live_data and len(live_data) > 0:
                            match_data = live_data[0]  # API returns array with single match
                            live_scores_data[game_id] = {
                                "matchStatus": match_data.get("matchStatus", ""),
                                "live": match_data.get("live", 0),
                                "homeScore": match_data.get("homescore", ""),
                                "awayScore": match_data.get("awayscore", ""),
                                "matchId": match_data.get("matchId", ""),
                                "homeName": match_data.get("homename", ""),
                                "awayName": match_data.get("awayname", ""),
                                "homeLogo": match_data.get("homelogo", ""),
                                "awayLogo": match_data.get("awaylogo", "")
                            }
                            _LOGGER.debug(f"Updated live scores for game {game_id}: {live_scores_data[game_id]}")
                        
            except aiohttp.ClientError as err:
                _LOGGER.debug(f"HTTP error fetching live scores for competition {competition_id}: {err}")
            except asyncio.TimeoutError:
                _LOGGER.debug(f"Timeout error fetching live scores for competition {competition_id}")
            except Exception as err:
                _LOGGER.debug(f"Error fetching live scores for competition {competition_id}: {err}")
        
        if live_scores_data:
            # Update the coordinator data with live scores
            current_data = self.data or {}
            current_data["live_scores"] = live_scores_data
            self.async_set_updated_data(current_data)
            _LOGGER.info(f"Updated live scores for {len(live_scores_data)} games")
