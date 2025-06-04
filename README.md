# 🏀 CEBL Home Assistant Integration

<div align="center">

![CEBL Logo](https://upload.wikimedia.org/wikipedia/en/e/ee/Canadian_Elite_Basketball_League_logo.png)

**Transform your Home Assistant into a professional CEBL sports center!**

[![Version](https://img.shields.io/badge/version-2.0-blue.svg)](https://github.com/ViceBooster/ha-cebl)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

*Bringing ESPN-level sports data to your smart home*

</div>

---

## 🚀 **What's New in v1.61 "Simplified Excellence"**

A **complete reimagining** of the CEBL integration! We've consolidated multiple sensors into one powerful, comprehensive sensor per team for the ultimate user experience.

### ✨ **Revolutionary Sensor Design**
- 🎯 **ONE Comprehensive Sensor Per Team** - Everything in one place!
- 🏷️ **Intuitive Naming** - `sensor.cebl_niagara_river_lions` (not cryptic IDs)
- 📊 **40+ Attributes** - Game state, stats, top scorer, timing - all included
- ⚡ **Smart Live Updates** - 30-second updates during games, 1-minute otherwise
- 🎮 **Intelligent State Management** - PRE/IN/POST with proper timing validation
- 🏀 **All 10 CEBL Teams** - Complete league coverage

---

## 🏀 **Features**

### 🎮 **One Powerful Sensor Per Team**

Each team gets **ONE comprehensive sensor** that contains everything:

#### 📍 **Entity Name**: `sensor.cebl_[team_name]`
**Examples:**
- `sensor.cebl_niagara_river_lions`
- `sensor.cebl_brampton_honey_badgers` 
- `sensor.cebl_edmonton_stingers`

#### 🎯 **What's Included:**

##### 🏀 **Game Data**
- **Live Scores** with opponent info and team logos
- **Game Clock** with period and overtime tracking  
- **Game Status** (PRE/IN/POST) with countdown timers
- **Venue Information** and start times

##### 📊 **Team Statistics** 
- **Shooting Percentages** (Field Goals, 3-Pointers, Free Throws)
- **Performance Metrics** (Rebounds, Assists, Turnovers, Steals, Blocks)
- **Advanced Analytics** (Bench Points, Points in Paint, Fast Break Points)
- **Game Flow Data** (Biggest Lead, Time Leading)

##### ⭐ **Top Scorer Information**
- **Player Details** (Name, Position, Jersey Number)
- **Live Statistics** (Points, Rebounds, Assists, +/-, Minutes)
- **Shooting Performance** (FG%, 3P%, Photo URL)
- **Player Status** (Starter, Captain flags)

##### ⏰ **Smart Timing**
- **Time Until Game** (friendly format: "In 2 days")
- **Kick-off Countdown** (seconds until start)
- **Hours Since Game** (for completed games)
- **Live Update Management** (automatic frequency adjustment)

### 🎨 **Rich Visual Assets**
- **Professional Player Photos** for top scorers
- **High-Resolution Team Logos** for dashboard displays
- **Real-time Clock Display** for live games

### ⚡ **Intelligent Updates**
- **Live Games** - Updates every 30 seconds with real-time data
- **Upcoming Games** - Updates every 1 minute with timing info
- **Smart Data Validation** - Prevents showing old game data for future games
- **Automatic State Transitions** - PRE → IN → POST with proper timing

---

## 🏀 **Supported Teams**

All **10 CEBL teams** with beautiful, readable entity names:

| Team | Entity Name | Display Name |
|------|-------------|--------------|
| 🐻 **Brampton Honey Badgers** | `sensor.cebl_brampton_honey_badgers` | `CEBL Brampton Honey Badgers` |
| 🔥 **Calgary Surge** | `sensor.cebl_calgary_surge` | `CEBL Calgary Surge` |
| ⚡ **Edmonton Stingers** | `sensor.cebl_edmonton_stingers` | `CEBL Edmonton Stingers` |
| 🤝 **Montreal Alliance** | `sensor.cebl_montreal_alliance` | `CEBL Montreal Alliance` |
| 🦁 **Niagara River Lions** | `sensor.cebl_niagara_river_lions` | `CEBL Niagara River Lions` |
| ⚫ **Ottawa BlackJacks** | `sensor.cebl_ottawa_blackjacks` | `CEBL Ottawa BlackJacks` |
| 🐍 **Saskatchewan Rattlers** | `sensor.cebl_saskatchewan_rattlers` | `CEBL Saskatchewan Rattlers` |
| ⭐ **Scarborough Shooting Stars** | `sensor.cebl_scarborough_shooting_stars` | `CEBL Scarborough Shooting Stars` |
| 🏴‍☠️ **Vancouver Bandits** | `sensor.cebl_vancouver_bandits` | `CEBL Vancouver Bandits` |
| 🌊 **Winnipeg Sea Bears** | `sensor.cebl_winnipeg_sea_bears` | `CEBL Winnipeg Sea Bears` |

---

## 📦 **Installation**

### 🏠 **HACS (Recommended)**

1. **Add Custom Repository:**
   ```
   URL: https://github.com/ViceBooster/ha-cebl
   Category: Integration
   ```

2. **Install:**
   - Search for "CEBL" in HACS Integrations
   - Click "Install" and restart Home Assistant

3. **Add Integration:**
   - Go to Settings → Devices & Services
   - Click "Add Integration" and search for "CEBL"
   - Select your favorite teams

### 🔧 **Manual Installation**

1. **Download and Copy:**
   ```bash
   # Copy the cebl folder to your custom_components directory
   /config/custom_components/cebl/
   ```

2. **Restart Home Assistant**

3. **Add Integration via UI**

---

## ⚙️ **Configuration**

### 🎯 **Easy Setup**
1. **Add Integration** via Settings → Devices & Services
2. **Select Teams** - Choose your favorite CEBL teams
3. **Automatic Discovery** - One comprehensive sensor per team created
4. **Start Building** - Use sensors in dashboards and automations

### 📊 **Sensor Entity Created**
For each selected team, you get **ONE comprehensive sensor**:
- `sensor.cebl_[team_name]` - Everything you need in one place!

---

## 🎮 **Dashboard Examples**

### 📱 **Comprehensive Team Card**
```yaml
type: entities
title: 🏀 Niagara River Lions
entities:
  - sensor.cebl_niagara_river_lions
show_header_toggle: false
```

### 📊 **Game Stats Display**
```yaml  
type: glance
columns: 4
title: 🦁 Niagara River Lions Stats
entities:
  - entity: sensor.cebl_niagara_river_lions
    name: "Score"
    attribute: team_score
  - entity: sensor.cebl_niagara_river_lions  
    name: "FG%"
    attribute: stats_field_goal_percentage
  - entity: sensor.cebl_niagara_river_lions
    name: "Rebounds"
    attribute: stats_rebounds
  - entity: sensor.cebl_niagara_river_lions
    name: "Assists"
    attribute: stats_assists
```

### ⭐ **Top Scorer Spotlight**
```yaml
type: glance
columns: 3
title: 🌟 Top Scorer
entities:
  - entity: sensor.cebl_niagara_river_lions
    name: "Player"
    attribute: top_scorer_name
  - entity: sensor.cebl_niagara_river_lions
    name: "Points"
    attribute: top_scorer_points
  - entity: sensor.cebl_niagara_river_lions
    name: "Position"
    attribute: top_scorer_position
```

### 🏆 **Multi-Team Dashboard**
```yaml
type: entities
title: 🏆 My CEBL Teams
entities:
  - sensor.cebl_niagara_river_lions
  - sensor.cebl_brampton_honey_badgers
  - sensor.cebl_edmonton_stingers
show_header_toggle: false
```

---

## 🤖 **Automation Examples**

### 🚨 **Game Start Notification**
```yaml
automation:
  - alias: "CEBL Game Starting"
    trigger:
      - platform: state
        entity_id: sensor.cebl_niagara_river_lions
        from: "PRE"
        to: "IN"
    action:
      - service: notify.mobile_app
        data:
          message: "🏀 Niagara River Lions game is starting!"
```

### 🎯 **Close Game Alert**
```yaml
automation:
  - alias: "CEBL Close Game"
    trigger:
      - platform: numeric_state
        entity_id: sensor.cebl_niagara_river_lions
        attribute: score_difference
        below: 5
    condition:
      - condition: state
        entity_id: sensor.cebl_niagara_river_lions
        state: "IN"
    action:
      - service: notify.home_assistant
        data:
          message: "🔥 Nail-biter! Lions game within 5 points!"
```

### 🌟 **Top Scorer Achievement**
```yaml
automation:
  - alias: "CEBL Player Hot Streak"
    trigger:
      - platform: numeric_state
        entity_id: sensor.cebl_niagara_river_lions
        attribute: top_scorer_points
        above: 25
    condition:
      - condition: state
        entity_id: sensor.cebl_niagara_river_lions
        state: "IN"
    action:
      - service: notify.home_assistant
        data:
          message: "🔥 {{ state_attr('sensor.cebl_niagara_river_lions', 'top_scorer_name') }} has 25+ points!"
```

---

## 🛠️ **Sensor Attributes Reference**

### 📈 **Complete Attribute List**

#### Core Game Data:
```yaml
state: "IN"  # PRE, IN, or POST
attributes:
  # Team & Opponent Info
  team_name: "Niagara River Lions"
  opponent_name: "Scarborough Shooting Stars"
  team_logo: "https://storage.googleapis.com/cebl-project.appspot.com/logos/niagara.png"
  opponent_logo: "https://storage.googleapis.com/cebl-project.appspot.com/logos/scarborough.png"
  home_away: "home"
  venue: "Meridian Centre"
  
  # Live Game Data
  team_score: 67
  opponent_score: 82
  game_clock: "03:14:00"
  period: 4
  period_type: "REGULAR"
  score_difference: 15
  
  # Timing Information
  start_time: "2025-06-06T23:00:00Z"
  time_until_game: "In 2 days"
  kick_off_in: 190598  # seconds
  kick_off_in_friendly: "In 2 days"
  hours_since_game: 12.5  # for completed games
  
  # Game Status
  status: "SCHEDULED"  # or IN_PROGRESS, COMPLETED
  is_live: false
  is_final: false
  is_upcoming: true
```

#### Team Statistics:
```yaml
  # Shooting Stats
  stats_field_goal_percentage: 48.5
  stats_three_point_percentage: 35.2
  stats_free_throw_percentage: 76.9
  
  # Performance Stats
  stats_rebounds: 42
  stats_assists: 18
  stats_turnovers: 12
  stats_steals: 7
  stats_blocks: 3
  
  # Advanced Stats
  stats_bench_points: 24
  stats_points_in_paint: 38
  stats_points_from_turnovers: 21
  stats_fast_break_points: 18
  stats_biggest_lead: 16
  stats_time_leading: 39.65
```

#### Top Scorer Information:
```yaml
  # Player Identity
  top_scorer_name: "A. Hill"
  top_scorer_jersey: "6"
  top_scorer_position: "G"
  top_scorer_photo: "https://images.statsengine.playbyplay.api.geniussports.com/player.png"
  
  # Player Stats
  top_scorer_points: 20
  top_scorer_rebounds: 5
  top_scorer_assists: 5
  top_scorer_minutes: "26:59"
  top_scorer_plus_minus: 19
  top_scorer_fg_percentage: 53
  
  # Player Status
  top_scorer_is_starter: true
  top_scorer_is_captain: false
```

#### Technical Data:
```yaml
  # Update Management
  last_updated: "2025-06-04T14:06:55.102222-04:00"
  update_frequency: "30 seconds"  # or "1 minute"
  data_source: "live_data"  # or "fixture_only"
  
  # API Integration
  api_live_field: true
  raw_clock: "03:14:00"
  home_score_live: 67
  away_score_live: 82
```

---

## 🔧 **Troubleshooting**

### ❓ **Common Issues**

**No Sensors Created:**
- Ensure integration is properly installed
- Check that teams are selected during setup
- Restart Home Assistant after installation

**Wrong Game Data Showing:**
- The integration now validates live data currency
- Old completed game data won't show for upcoming games
- Check logs for "Live data appears to be from previous game" messages

**Live Scores Not Updating:**
- Live scores require active games with valid match IDs
- Check network connectivity to CEBL API
- Updates occur every 30 seconds during live games

**Entity Names Changed:**
- v2.0 uses team names instead of IDs
- Old: `sensor.cebl_25_game` → New: `sensor.cebl_niagara_river_lions`
- Update your dashboards and automations accordingly

### 📋 **Getting Help**
- Check Home Assistant logs for error messages
- Verify internet connectivity to `api.data.cebl.ca`
- Open GitHub issue with logs and configuration details

---

## 📊 **API Information**

### 🔗 **Data Sources**
- **Games API**: `https://api.data.cebl.ca/games/2025/`
- **Live Scores**: `https://fibalivestats.dcd.shared.geniussports.com/`
- **Authentication**: X-Api-Key header (handled automatically)
- **Update Frequency**: 30 seconds during live games, 1 minute otherwise

### 📈 **Data Coverage**
- **120+ Games** - Complete 2025 CEBL season
- **Real-time Updates** - Live scores and statistics
- **Historical Data** - Past games and season stats
- **Professional Assets** - High-resolution images and logos

---

## 🆕 **Migration from v1.x**

### 🔄 **What Changed**
- **4 sensors per team** → **1 comprehensive sensor per team**
- **Numeric entity IDs** → **Team name entity IDs**
- **Separate league scoreboard** → **Removed (use individual team sensors)**

### 📝 **Update Your Dashboards**
**Old v1.x entities:**
```yaml
- sensor.cebl_niagara_river_lions_game
- sensor.cebl_niagara_river_lions_team_stats  
- sensor.cebl_niagara_river_lions_top_scorer
- sensor.cebl_niagara_river_lions_league_scoreboard
```

**New v2.0 entity:**
```yaml
- sensor.cebl_niagara_river_lions  # Everything in one sensor!
```

### 🎯 **Attribute Access**
**Old way (multiple sensors):**
```yaml
# Had to reference different sensors
field_goal_percentage: "{{ states('sensor.cebl_team_stats') }}"
top_scorer: "{{ states('sensor.cebl_top_scorer') }}"
```

**New way (single sensor with attributes):**
```yaml
# Everything from one sensor
field_goal_percentage: "{{ state_attr('sensor.cebl_niagara_river_lions', 'stats_field_goal_percentage') }}"
top_scorer: "{{ state_attr('sensor.cebl_niagara_river_lions', 'top_scorer_name') }}"
```

---

## 🤝 **Contributing**

We welcome contributions! Here's how you can help:

- 🐛 **Report Bugs** - Open issues with detailed logs
- 💡 **Request Features** - Share your dashboard ideas
- 🔧 **Submit PRs** - Code improvements and enhancements
- 📖 **Improve Docs** - Help others with better documentation

---

## 📄 **License**

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🙏 **Acknowledgments**

- **CEBL** - For providing an exciting basketball league
- **Team Tracker** - Original inspiration for this integration
- **Home Assistant Community** - For feedback and support
- **Beta Testers** - For helping perfect the simplified experience

---

<div align="center">

**🏀 Ready to experience the ultimate CEBL integration? 🏠**

[Install Now](https://github.com/ViceBooster/ha-cebl) • [Documentation](https://github.com/ViceBooster/ha-cebl/wiki) • [Support](https://github.com/ViceBooster/ha-cebl/issues)

*Go team! 🎉*

</div>
