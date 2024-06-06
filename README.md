
![CEBL Home Assistant Integration](https://upload.wikimedia.org/wikipedia/en/e/ee/Canadian_Elite_Basketball_League_logo.png)


# CEBL Home Assistant Integration

Welcome to the [CEBL](https://cebl.ca) Home Assistant Integration! This integration was inspiried by [Team Tracker](https://github.com/vasqued2/ha-teamtracker) and allows you to track upcoming and live fixtures for your favorite Canadian Elite Basketball League (CEBL) teams within your Home Assistant setup.

## Features

- Fetch and display upcoming fixtures for selected CEBL teams.
- Provides details about the fixtures including scores, fixture date, time, venue, opponent, and more.
- Updates every 10 minutes to ensure you have the latest information, and every 1 minute if a game is live.

## Installation

### HACS (Home Assistant Community Store)

1. **Add Custom Repository:**
   - Open HACS in Home Assistant.
   - Go to the "Integrations" section.
   - Click the three dots in the top right corner and select "Custom repositories".
   - Add the URL of this repository and select the category as "Integration".

2. **Install the Integration:**
   - After adding the custom repository, search for "CEBL" in the HACS Integrations section.
   - Click "Install" and follow the prompts.

### Manual Installation

1. **Download:**
   - Clone or download this repository.

2. **Copy Files:**
   - Copy the `custom_components/cebl` directory to the `custom_components` directory in your Home Assistant configuration directory.

3. **Restart Home Assistant:**
   - Restart Home Assistant to recognize the new integration.

## Configuration

1. **Add Integration:**
   - Go to the Home Assistant Configuration page.
   - Select "Integrations".
   - Click the "+" button and search for "CEBL".
   - Follow the prompts to select your favorite team.

2. **Verify Entities:**
   - After setup, navigate to the Entities page in Home Assistant.
   - You should see sensors related to the selected team's fixtures.

## Usage

The integration creates sensors that provide information about the upcoming fixtures for the selected team. The sensors include attributes such as:
- Fixture date and time
- Team and opponent logos
- Score
- Venue
- Opponent details
- Time until kickoff
- Quarter/Period
- Period Time left

You can use these sensors in your Home Assistant dashboard, automations, and scripts to create a fully customized experience.

## Troubleshooting

- **No Devices or Entities Created:**
  - Ensure the integration is correctly set up and the team is selected.
  - Check the Home Assistant logs for any error messages.

- **Data Not Updating:**
  - The data updates every 10 minutes (1 minute if live). Ensure you wait for this interval.
  - Check your internet connection.

## Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue or submit a pull request on GitHub.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Thank you for using the CEBL Home Assistant Integration! Enjoy keeping up with your favorite CEBL teams right from your smart home dashboard. If you have any questions or need further assistance, feel free to open an issue on GitHub.
