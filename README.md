 # 🏀 CEBL Home Assistant Integration

<div align="center">

![CEBL Logo](https://upload.wikimedia.org/wikipedia/en/e/ee/Canadian_Elite_Basketball_League_logo.png)

**Transform your Home Assistant into a professional CEBL sports center!**

[![Version](https://img.shields.io/badge/version-1.42-blue.svg)](https://github.com/your-repo/ha-cebl)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

*Bringing ESPN-level sports data to your smart home*

</div>

---

## 🚀 **What's New in v1.48 "Championship Edition"**

This isn't just an update - it's a **complete transformation**! We've rebuilt the entire integration with the official CEBL API to deliver professional-grade sports data.

### ✨ **Professional Sports Dashboard Experience**
- 🎯 **4 Comprehensive Sensors Per Team** (instead of 1 basic sensor)
- 📸 **Professional Player Photos** - High-resolution headshots for every player
- 🏆 **High-Res Team Logos** - Crystal clear 200x200px logos for all teams
- 📊 **Advanced Analytics** - ESPN-level statistics and performance metrics
- ⏰ **Real-time Game Clock** - Live period tracking with overtime detection
- 🏀 **All 10 CEBL Teams** - Complete league coverage with dynamic discovery

---

## 🏀 **Features**

### 🎮 **4 Sensors Per Team**

#### 🏀 **Game Sensor** - `sensor.cebl_[team]_game`
- **Live Scores** with opponent info and team logos
- **Game Clock** with period and overtime tracking
- **Game Status** (Pre-game, Live, Final) with countdown timers
- **Venue Information** and officials details

#### 📊 **Team Stats Sensor** - `sensor.cebl_[team]_team_stats`
- **Shooting Percentages** (Field Goals, 3-Pointers, Free Throws)
- **Performance Metrics** (Rebounds, Assists, Turnovers)
- **Advanced Analytics** (Bench Points, Points in Paint, Fast Break Points)
- **Game Flow Data** (Biggest Lead, Time Leading)

#### ⭐ **Top Scorer Sensor** - `sensor.cebl_[team]_top_scorer`
- **Player Photos** - Professional headshots with stats overlay
- **Live Statistics** (Points, Rebounds, Assists, +/-)
- **Player Details** (Position, Jersey Number, Minutes Played)
- **Performance Tracking** with shooting percentages

#### 🏆 **League Scoreboard Sensor** - `sensor.cebl_[team]_league_scoreboard`
- **All Active Games** with live scores and game periods
- **Team Logos** for visual scoreboard displays
- **Multi-game Tracking** across the entire league

### 🎨 **Rich Visual Assets**
- **Professional Player Photos** for every CEBL player
- **High-Resolution Team Logos** (200x200px) for dashboard cards
- **Multiple Logo Sizes** optimized for different display needs

### ⚡ **Real-time Updates**
- **Live Game Tracking** - Updates every 60 seconds during active games
- **Game Clock Integration** - Real-time period and overtime tracking
- **Score Change Detection** - Perfect for automations and notifications

---

## 🏀 **Supported Teams**

All **10 CEBL teams** with automatic discovery:

| Team | Logo | Sensor Prefix |
|------|------|---------------|
| 🐻 **Brampton Honey Badgers** | High-Res Logo | `cebl_brampton_honey_badgers_*` |
| 🔥 **Calgary Surge** | High-Res Logo | `cebl_calgary_surge_*` |
| ⚡ **Edmonton Stingers** | High-Res Logo | `cebl_edmonton_stingers_*` |
| 🤝 **Montreal Alliance** | High-Res Logo | `cebl_montreal_alliance_*` |
| 🦁 **Niagara River Lions** | High-Res Logo | `cebl_niagara_river_lions_*` |
| ⚫ **Ottawa BlackJacks** | High-Res Logo | `cebl_ottawa_blackjacks_*` |
| 🐍 **Saskatchewan Rattlers** | High-Res Logo | `cebl_saskatchewan_rattlers_*` |
| ⭐ **Scarborough Shooting Stars** | High-Res Logo | `cebl_scarborough_shooting_stars_*` |
| 🏴‍☠️ **Vancouver Bandits** | High-Res Logo | `cebl_vancouver_bandits_*` |
| 🌊 **Winnipeg Sea Bears** | High-Res Logo | `cebl_winnipeg_sea_bears_*` |

---

## 📦 **Installation**

### 🏠 **HACS (Recommended)**

1. **Add Custom Repository:**
   ```
   URL: https://github.com/your-repo/ha-cebl
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
3. **Automatic Discovery** - All sensors created automatically
4. **Start Building** - Use sensors in dashboards and automations

### 📊 **Sensor Entities Created**
For each selected team, you get **4 sensors**:
- `sensor.cebl_[team]_game` - Live game tracking
- `sensor.cebl_[team]_team_stats` - Advanced team statistics  
- `sensor.cebl_[team]_top_scorer` - Star player spotlight
- `sensor.cebl_[team]_league_scoreboard` - League-wide scores

---

## 🎮 **Dashboard Examples**

### 📱 **Game Day Card**
```yaml
type: entities
title: 🏀 Calgary Surge Game
entities:
  - sensor.cebl_calgary_surge_game
  - sensor.cebl_calgary_surge_team_stats
  - sensor.cebl_calgary_surge_top_scorer
show_header_toggle: false
```

### 📊 **Advanced Stats Card**
```yaml  
type: glance
columns: 3
entities:
  - entity: sensor.cebl_calgary_surge_team_stats
    name: "Field Goal %"
    attribute: field_goal_percentage
  - entity: sensor.cebl_calgary_surge_team_stats  
    name: "3-Point %"
    attribute: three_point_percentage
  - entity: sensor.cebl_calgary_surge_team_stats
    name: "Rebounds"
    attribute: total_rebounds
```

### 🏆 **League Scoreboard**
```yaml
type: entities
title: 🏆 CEBL League Scores
entities:
  - sensor.cebl_calgary_surge_league_scoreboard
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
        entity_id: sensor.cebl_calgary_surge_game
        attribute: game_status
        from: "Pre-game"
        to: "Live"
    action:
      - service: notify.mobile_app
        data:
          message: "🏀 Calgary Surge game is starting!"
```

### 🎯 **Close Game Alert**
```yaml
automation:
  - alias: "CEBL Close Game"
    trigger:
      - platform: numeric_state
        entity_id: sensor.cebl_calgary_surge_game
        attribute: score_difference
        below: 5
    condition:
      - condition: state
        entity_id: sensor.cebl_calgary_surge_game
        attribute: game_status
        state: "Live"
    action:
      - service: notify.home_assistant
        data:
          message: "🔥 Nail-biter! Calgary Surge game within 5 points!"
```

---

## 🛠️ **Advanced Features**

### 📈 **Rich Sensor Attributes**

#### Game Sensor Attributes:
```yaml
state: "76-82"
attributes:
  game_status: "Live"
  period: "4th Quarter"
  game_clock: "2:45"
  home_team: "Calgary Surge"
  away_team: "Edmonton Stingers"
  venue: "Calgary Event Centre"
  officials: ["John Smith", "Jane Doe"]
  home_logo: "https://api.data.cebl.ca/logos/calgary_200x200.png"
  away_logo: "https://api.data.cebl.ca/logos/edmonton_200x200.png"
```

#### Top Scorer Attributes:
```yaml
state: "Marcus Johnson"
attributes:
  points: 28
  rebounds: 8
  assists: 6
  player_photo: "https://fibalivestats.../player_photo.jpg"
  position: "Guard"
  jersey_number: 23
  minutes_played: 32
  field_goal_percentage: 64.7
```

---

## 🔧 **Troubleshooting**

### ❓ **Common Issues**

**No Sensors Created:**
- Ensure integration is properly installed
- Check that teams are selected during setup
- Restart Home Assistant after installation

**Live Scores Not Updating:**
- Live scores require active games with valid match IDs
- Check network connectivity to CEBL API
- Updates occur every 60 seconds during games

**Player Photos Not Loading:**
- Photos depend on league data availability
- Some players may not have photos in the system
- Photos load automatically when available

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
- **Update Frequency**: 60 seconds during active games

### 📈 **Data Coverage**
- **120+ Games** - Complete 2025 CEBL season
- **Real-time Updates** - Live scores and statistics
- **Historical Data** - Past games and season stats
- **Professional Assets** - High-resolution images and logos

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

- **CEBL** - For providing putting on a great show
- **Team Tracker** - Original inspiration for this integration
- **Home Assistant Community** - For feedback and support
- **Beta Testers** - For helping perfect the experience

---

<div align="center">

**🏀 Ready to transform your Home Assistant into a CEBL command center? 🏠**

[Install Now](https://github.com/your-repo/ha-cebl) • [Documentation](https://github.com/your-repo/ha-cebl/wiki) • [Support](https://github.com/your-repo/ha-cebl/issues)

*Go team! 🎉*

</div>
