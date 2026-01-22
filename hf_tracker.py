"""
Hugging Face Model Tracker
Tracks models from specific HF users and notifies via Telegram on updates.
"""

import json
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path

from huggingface_hub import HfApi, ModelInfo
from telegram import Bot
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HFTracker:
    """Main tracker class for monitoring Hugging Face models."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the tracker with configuration."""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.hf_users = self.config.get("hf_users", [])
        self.telegram_config = self.config.get("telegram", {})
        self.check_interval = self.config.get("check_interval_minutes", 60) * 60  # Convert to seconds
        self.state_file = Path(self.config.get("state_file", "tracker_state.json"))
        
        # Initialize APIs
        self.hf_api = HfApi()
        self.telegram_bot = None
        
        # Initialize Telegram bot if credentials are provided
        bot_token = self.telegram_config.get("bot_token")
        if bot_token and bot_token != "YOUR_TELEGRAM_BOT_TOKEN":
            try:
                self.telegram_bot = Bot(token=bot_token)
                logger.info("Telegram bot initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
        else:
            logger.warning("Telegram bot token not configured. Notifications will be disabled.")
        
        # Load or initialize state
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load previous tracking state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                logger.info(f"Loaded state from {self.state_file}")
                return state
            except Exception as e:
                logger.error(f"Error loading state: {e}")
                return {}
        else:
            logger.info("No existing state file found. Starting fresh.")
            return {}
    
    def _save_state(self):
        """Save current tracking state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def _get_user_models(self, username: str) -> List[ModelInfo]:
        """Fetch all models for a given user."""
        try:
            models = list(self.hf_api.list_models(author=username))
            # Sort by last_modified (most recent first) if available
            def get_sort_key(m):
                if hasattr(m, 'last_modified') and m.last_modified:
                    return m.last_modified
                elif hasattr(m, 'updated_at') and m.updated_at:
                    return m.updated_at
                elif hasattr(m, 'created_at') and m.created_at:
                    return m.created_at
                else:
                    return datetime.min.replace(tzinfo=timezone.utc)
            models.sort(key=get_sort_key, reverse=True)
            return models
        except Exception as e:
            logger.error(f"Error fetching models for user {username}: {e}")
            return []
    
    def _get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get detailed information about a specific model."""
        try:
            return self.hf_api.model_info(model_id)
        except Exception as e:
            logger.error(f"Error fetching model info for {model_id}: {e}")
            return None
    
    def _format_model_info(self, model: ModelInfo) -> Dict:
        """Extract relevant information from a model."""
        return {
            "id": model.id,
            "author": getattr(model, 'author', None),
            "created_at": model.created_at.isoformat() if hasattr(model, 'created_at') and model.created_at else None,
            "updated_at": model.updated_at.isoformat() if hasattr(model, 'updated_at') and model.updated_at else None,
            "last_modified": model.last_modified.isoformat() if hasattr(model, 'last_modified') and model.last_modified else None,
            "sha": getattr(model, 'sha', None),
            "tags": getattr(model, 'tags', []) or [],
            "downloads": getattr(model, 'downloads', 0),
        }
    
    def _check_user_updates(self, username: str) -> List[Dict]:
        """Check for updates in a user's models and return list of changes."""
        updates = []
        logger.info(f"Checking updates for user: {username}")
        
        # Get current models (basic list)
        current_models = self._get_user_models(username)
        current_model_ids = {model.id for model in current_models}
        
        # Get previous state for this user
        previous_state = self.state.get(username, {})
        previous_models = previous_state.get("models", {})
        previous_model_ids = set(previous_models.keys())
        
        # Fetch detailed info for all current models to get SHA and track commits
        current_model_dict = {}
        for model in current_models:
            model_id = model.id
            # Fetch detailed model info to get SHA for commit tracking
            detailed_info = self._get_model_info(model_id)
            if detailed_info:
                current_model_dict[model_id] = self._format_model_info(detailed_info)
            else:
                # Fallback to basic info if detailed fetch fails
                current_model_dict[model_id] = self._format_model_info(model)
        
        # Check for new models
        new_model_ids = current_model_ids - previous_model_ids
        for model_id in new_model_ids:
            updates.append({
                "type": "new_model",
                "user": username,
                "model_id": model_id,
                "model_info": current_model_dict.get(model_id, {})
            })
            logger.info(f"New model detected: {model_id}")
        
        # Check for updates in existing models (SHA changes indicate new commits)
        existing_model_ids = current_model_ids & previous_model_ids
        for model_id in existing_model_ids:
            current_info = current_model_dict.get(model_id, {})
            previous_info = previous_models.get(model_id, {})
            
            # Check if SHA changed (indicates new commit)
            current_sha = current_info.get("sha")
            previous_sha = previous_info.get("sha")
            
            if current_sha and previous_sha and current_sha != previous_sha:
                updates.append({
                    "type": "model_updated",
                    "user": username,
                    "model_id": model_id,
                    "previous_sha": previous_sha,
                    "current_sha": current_sha,
                    "model_info": current_info
                })
                logger.info(f"Model updated: {model_id} (SHA changed: {previous_sha[:8]} -> {current_sha[:8]})")
            
            # Also check if last_modified changed (fallback if SHA not available)
            elif current_info.get("last_modified") != previous_info.get("last_modified"):
                updates.append({
                    "type": "model_updated",
                    "user": username,
                    "model_id": model_id,
                    "previous_modified": previous_info.get("last_modified"),
                    "current_modified": current_info.get("last_modified"),
                    "model_info": current_info
                })
                logger.info(f"Model updated: {model_id} (last_modified changed)")
        
        # Update state for this user
        self.state[username] = {
            "models": current_model_dict,
            "last_checked": datetime.now().isoformat(),
            "model_count": len(current_model_dict)
        }
        
        return updates
    
    def _send_telegram_notification(self, message: str):
        """Send a notification to Telegram channel."""
        if not self.telegram_bot:
            logger.warning("Telegram bot not initialized. Skipping notification.")
            return
        
        channel_id = self.telegram_config.get("channel_id")
        if not channel_id or channel_id == "YOUR_TELEGRAM_CHANNEL_ID":
            logger.warning("Telegram channel ID not configured. Skipping notification.")
            return
        
        try:
            # Ensure channel_id is a string (Telegram API expects @channelname or -1001234567890 format)
            if isinstance(channel_id, int) or (isinstance(channel_id, str) and channel_id.lstrip('-').isdigit()):
                channel_id = int(channel_id)
            
            # Run async send_message in a new event loop
            # Since we're in a synchronous context, asyncio.run() should work fine
            asyncio.run(self._async_send_message(channel_id, message))
        except RuntimeError as e:
            # If there's already an event loop running, use a different approach
            logger.warning(f"Event loop issue: {e}. Trying alternative method...")
            import threading
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    new_loop.run_until_complete(self._async_send_message(channel_id, message))
                finally:
                    new_loop.close()
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()
        except TelegramError as e:
            logger.error(f"Failed to send Telegram notification: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram notification: {e}")
    
    async def _async_send_message(self, channel_id: int, message: str):
        """Async helper to send Telegram message."""
        try:
            await self.telegram_bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info("Telegram notification sent successfully")
        except Exception as e:
            logger.error(f"Error in async send_message: {e}")
            raise
    
    def _format_update_message(self, update: Dict) -> str:
        """Format an update into a readable message."""
        update_type = update.get("type")
        username = update.get("user")
        model_id = update.get("model_id")
        model_info = update.get("model_info", {})
        
        model_url = f"https://huggingface.co/{model_id}"
        
        if update_type == "new_model":
            tags = model_info.get("tags", [])
            tags_str = ", ".join(tags[:5]) if tags else "No tags"
            
            message = (
                f"🆕 <b>New Model Detected!</b>\n\n"
                f"👤 User: <b>{username}</b>\n"
                f"📦 Model: <b>{model_id}</b>\n"
                f"🏷️ Tags: {tags_str}\n"
                f"📥 Downloads: {model_info.get('downloads', 0):,}\n"
                f"🔗 <a href='{model_url}'>View on Hugging Face</a>"
            )
        elif update_type == "model_updated":
            message = (
                f"🔄 <b>Model Updated!</b>\n\n"
                f"👤 User: <b>{username}</b>\n"
                f"📦 Model: <b>{model_id}</b>\n"
                f"📅 Last Modified: {model_info.get('last_modified', 'Unknown')}\n"
                f"🔗 <a href='{model_url}'>View on Hugging Face</a>"
            )
        else:
            message = f"Update detected for {model_id} by {username}"
        
        return message
    
    def check_all_users(self):
        """Check all configured users for updates."""
        logger.info(f"Starting check for {len(self.hf_users)} users...")
        all_updates = []
        
        for username in self.hf_users:
            try:
                updates = self._check_user_updates(username)
                all_updates.extend(updates)
            except Exception as e:
                logger.error(f"Error checking user {username}: {e}")
        
        # Save state after checking all users
        self._save_state()
        
        # Send notifications for all updates
        if all_updates:
            logger.info(f"Found {len(all_updates)} updates. Sending notifications...")
            for update in all_updates:
                message = self._format_update_message(update)
                self._send_telegram_notification(message)
                # Small delay between notifications to avoid rate limiting
                time.sleep(1)
        else:
            logger.info("No updates detected.")
        
        return all_updates
    
    def run_continuous(self):
        """Run the tracker continuously with the configured interval."""
        logger.info(f"Starting continuous tracking (interval: {self.check_interval/60:.1f} minutes)")
        
        # Initial check
        self.check_all_users()
        
        # Continuous loop
        while True:
            try:
                logger.info(f"Waiting {self.check_interval/60:.1f} minutes until next check...")
                time.sleep(self.check_interval)
                self.check_all_users()
            except KeyboardInterrupt:
                logger.info("Tracker stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in continuous loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying on error


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Hugging Face Model Tracker")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to configuration file (default: config.json)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run check once and exit (don't run continuously)"
    )
    
    args = parser.parse_args()
    
    tracker = HFTracker(config_path=args.config)
    
    if args.once:
        tracker.check_all_users()
    else:
        tracker.run_continuous()


if __name__ == "__main__":
    main()

