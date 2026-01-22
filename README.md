# Hugging Face Model Tracker

A Python tool to track Hugging Face models from specific users and get notified via Telegram when new models are added or existing models are updated.

## Features

- 🔍 Monitor multiple Hugging Face users simultaneously
- 📦 Detect new models as they're published
- 🔄 Track updates to existing models (new commits)
- 📱 Telegram notifications for all changes
- 💾 Persistent state tracking (remembers what you've seen)
- ⏰ Configurable check intervals

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Telegram Bot

1. Create a Telegram bot:
   - Open Telegram and search for [@BotFather](https://t.me/botfather)
   - Send `/newbot` and follow the instructions
   - Save the bot token you receive

2. Get your Telegram Channel ID:
   - Create a Telegram channel (or use an existing one)
   - Add your bot as an administrator to the channel
   - For public channels: Use `@channelname` (e.g., `@myhfupdates`)
   - For private channels: Use the numeric ID (e.g., `-1001234567890`)
     - To find the numeric ID, forward a message from your channel to [@userinfobot](https://t.me/userinfobot)

### 3. Configure the Tracker

Edit `config.json`:

```json
{
  "hf_users": [
    "username1",
    "username2"
  ],
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN_HERE",
    "channel_id": "@your_channel_name"
  },
  "check_interval_minutes": 60,
  "state_file": "tracker_state.json"
}
```

**Configuration Options:**
- `hf_users`: List of Hugging Face usernames to track
- `telegram.bot_token`: Your Telegram bot token from BotFather
- `telegram.channel_id`: Your Telegram channel ID or username (with @)
- `check_interval_minutes`: How often to check for updates (in minutes)
- `state_file`: File to store tracking state (default: `tracker_state.json`)

## Usage

### Run Continuously (Recommended)

The tracker will run continuously, checking for updates at the configured interval:

```bash
python hf_tracker.py
```

### Run Once

Run a single check and exit:

```bash
python hf_tracker.py --once
```

### Custom Config File

```bash
python hf_tracker.py --config my_config.json
```

## How It Works

1. **Initial Run**: On first run, the tracker fetches all models from the specified users and saves their current state.

2. **Subsequent Runs**: The tracker compares the current state with the saved state to detect:
   - **New Models**: Models that weren't in the previous state
   - **Updated Models**: Models with changed SHA (new commits) or last_modified timestamp

3. **Notifications**: When changes are detected, notifications are sent to your Telegram channel with:
   - Model name and author
   - Model tags and download count (for new models)
   - Direct link to the model on Hugging Face

4. **State Management**: The tracker saves its state to `tracker_state.json` (or your configured file) after each check, so it remembers what it has already seen.

## Example Notification

```
🆕 New Model Detected!

👤 User: example-user
📦 Model: example-user/my-awesome-model
🏷️ Tags: pytorch, text-generation, transformers
📥 Downloads: 1,234
🔗 View on Hugging Face
```

## Troubleshooting

### Telegram Notifications Not Working

- Verify your bot token is correct
- Ensure the bot is added as an administrator to your channel
- For private channels, use the numeric channel ID (negative number)
- Check the logs for error messages

### No Updates Detected

- The first run will not send notifications (it's establishing the baseline)
- Wait for the next check interval to see if updates are detected
- Check that the usernames in `config.json` are correct

### Rate Limiting

- If you're tracking many users or checking very frequently, you might hit Hugging Face API rate limits
- Increase the `check_interval_minutes` to reduce API calls
- The tracker includes a 1-second delay between Telegram notifications to avoid rate limiting

## License

MIT

