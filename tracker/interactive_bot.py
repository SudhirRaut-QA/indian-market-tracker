"""
Interactive Telegram Bot - Inline Keyboards & Callbacks
========================================================

Optional long-running bot listener that handles:
- Inline keyboard buttons (Show/Hide gainers, sectors, options)
- Callback queries for interactive data exploration
- On-demand data refresh

This requires a persistent process (VPS or local machine).
GitHub Actions can't keep a listener running.

Usage:
  python -m tracker.interactive_bot
"""

import logging
import os
import signal
import sys
from datetime import datetime
from typing import Dict, Any, Optional

import requests

from . import config
from .nse_scraper import MarketScraper
from .delta_engine import DeltaEngine
from .signal_detector import SignalDetector, format_signals_msg
from .telegram_bot import (
    format_fii_dii_msg,
    format_sector_msg,
    format_options_msg,
    format_commodities_msg,
    format_corporate_msg,
    format_52w_alerts_msg,
)

logger = logging.getLogger(__name__)

# Global state
_shutdown_requested = False
_last_snapshot = None
_last_delta = None


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    logger.info(f"Signal {signum} received, shutting down...")
    _shutdown_requested = True


class InteractiveTelegramBot:
    """Telegram bot with inline keyboards and callback handling."""
    
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.session = requests.Session()
        self.session.trust_env = True
        self.update_offset = 0
        
        # Scrapers
        self.scraper = MarketScraper()
        self.delta_engine = DeltaEngine()
        self.signal_detector = SignalDetector()
    
    def send_message(
        self, 
        text: str, 
        reply_markup: Optional[Dict] = None,
        chat_id: str = None
    ) -> bool:
        """Send a message with optional inline keyboard."""
        if not self.token:
            logger.error("Bot token not set")
            return False
        
        target_chat = chat_id or self.chat_id
        
        try:
            payload = {
                "chat_id": target_chat,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            resp = self.session.post(
                f"{self.api_url}/sendMessage",
                json=payload,
                timeout=60,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False
    
    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        """Answer a callback query (button tap)."""
        try:
            self.session.post(
                f"{self.api_url}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Callback answer error: {e}")
    
    def send_main_menu(self):
        """Send main dashboard with inline buttons."""
        global _last_snapshot, _last_delta
        
        # Get fresh snapshot
        snapshot = self.scraper.get_snapshot(
            include_sectors=True,
            include_options=True,
            include_corporate=False,
        )
        delta, _ = self.delta_engine.process(snapshot)
        
        _last_snapshot = snapshot
        _last_delta = delta
        
        # Quick summary
        fii_dii = snapshot.get("fii_dii", {})
        nifty = snapshot.get("indices", {}).get("NIFTY 50", {})
        
        text = f"<b>📊 Indian Market Tracker</b>\\n"
        text += f"{datetime.now().strftime('%d %b %I:%M%p')}\\n\\n"
        
        if nifty:
            text += f"<b>NIFTY 50</b>: {nifty['last']:,.1f} ({nifty['pct']:+.2f}%)\\n"
        
        if fii_dii:
            text += f"<b>FII Net</b>: ₹{fii_dii['fii']['net']:,.0f} Cr\\n"
            text += f"<b>DII Net</b>: ₹{fii_dii['dii']['net']:,.0f} Cr\\n"
        
        text += "\\nTap buttons below for detailed views:"
        
        # Inline keyboard with buttons
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📊 Market Pulse", "callback_data": "view_pulse"},
                    {"text": "🏭 Sectors", "callback_data": "view_sectors"},
                ],
                [
                    {"text": "📈 Options PCR", "callback_data": "view_options"},
                    {"text": "🏆 Commodities", "callback_data": "view_commodities"},
                ],
                [
                    {"text": "🎯 Buy/Sell Signals", "callback_data": "view_signals"},
                    {"text": "📡 52W Alerts", "callback_data": "view_52w"},
                ],
                [
                    {"text": "🔄 Refresh Data", "callback_data": "refresh"},
                ],
            ]
        }
        
        self.send_message(text, keyboard)
    
    def handle_callback(self, callback_query: Dict):
        """Handle button tap callbacks."""
        global _last_snapshot, _last_delta
        
        callback_id = callback_query.get("id")
        data = callback_query.get("data", "")
        from_user = callback_query.get("from", {})
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        
        logger.info(f"Callback: {data} from {from_user.get('username', '?')}")
        
        # Acknowledge immediately
        self.answer_callback_query(callback_id, "Loading...")
        
        if not _last_snapshot:
            self.send_message("⚠ No data available. Use /start to load.", chat_id=str(chat_id))
            return
        
        # Route to appropriate formatter
        if data == "view_pulse":
            msg = format_fii_dii_msg(_last_snapshot, _last_delta)
            self.send_message(msg, chat_id=str(chat_id))
        
        elif data == "view_sectors":
            msg = format_sector_msg(_last_snapshot, _last_delta)
            self.send_message(msg, chat_id=str(chat_id))
        
        elif data == "view_options":
            msg = format_options_msg(_last_snapshot)
            self.send_message(msg, chat_id=str(chat_id))
        
        elif data == "view_commodities":
            msg = format_commodities_msg(_last_snapshot, _last_delta)
            self.send_message(msg, chat_id=str(chat_id))
        
        elif data == "view_signals":
            if _last_snapshot.get("sectors"):
                signals = self.signal_detector.analyze(_last_snapshot, _last_delta)
                msg = format_signals_msg(signals)
                self.send_message(msg, chat_id=str(chat_id))
            else:
                self.send_message("⚠ Signal data unavailable", chat_id=str(chat_id))
        
        elif data == "view_52w":
            msg = format_52w_alerts_msg(_last_snapshot)
            if msg:
                self.send_message(msg, chat_id=str(chat_id))
            else:
                self.send_message("⚠ No 52W alerts", chat_id=str(chat_id))
        
        elif data == "refresh":
            self.send_message("🔄 Refreshing data...", chat_id=str(chat_id))
            self.send_main_menu()
    
    def get_updates(self) -> list:
        """Long poll for updates (messages, callbacks)."""
        try:
            resp = self.session.get(
                f"{self.api_url}/getUpdates",
                params={"offset": self.update_offset, "timeout": 30},
                timeout=35,
            )
            if resp.status_code == 200:
                return resp.json().get("result", [])
        except Exception as e:
            logger.error(f"Get updates error: {e}")
        return []
    
    def run(self):
        """Run the bot in long-polling mode."""
        global _shutdown_requested
        
        logger.info("Interactive bot started (long-polling mode)")
        logger.info("Send /start to the bot to get the main menu")
        
        while not _shutdown_requested:
            updates = self.get_updates()
            
            for update in updates:
                self.update_offset = update["update_id"] + 1
                
                # Handle callback queries (button taps)
                if "callback_query" in update:
                    self.handle_callback(update["callback_query"])
                
                # Handle text messages
                elif "message" in update:
                    msg = update["message"]
                    text = msg.get("text", "")
                    chat_id = msg["chat"]["id"]
                    
                    if text == "/start" or text.startswith("/menu"):
                        self.send_main_menu()
                    elif text == "/help":
                        help_text = (
                            "<b>📊 Market Tracker Bot</b>\\n\\n"
                            "Commands:\\n"
                            "/start - Show main menu\\n"
                            "/menu - Show main menu\\n"
                            "/help - This help\\n\\n"
                            "Tap buttons to view data!"
                        )
                        self.send_message(help_text, chat_id=str(chat_id))
        
        logger.info("Interactive bot stopped")


def main():
    """Entry point for interactive bot."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    # Check credentials
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        logger.error("TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)
    
    if not os.environ.get("TELEGRAM_CHAT_ID"):
        logger.error("TELEGRAM_CHAT_ID not set in .env")
        sys.exit(1)
    
    # Run bot
    bot = InteractiveTelegramBot()
    try:
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
