"""
Interactive Setup for Indian Market Tracker
============================================
This will create your .env file with Telegram credentials
"""
import os
from pathlib import Path

print("\n" + "="*60)
print("🇮🇳 INDIAN MARKET TRACKER - SETUP")
print("="*60 + "\n")

# Check if .env already exists
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    print("⚠️  .env file already exists!")
    overwrite = input("Do you want to overwrite it? (yes/no): ").strip().lower()
    if overwrite != "yes":
        print("\n❌ Setup cancelled. Edit .env manually if needed.")
        exit(0)

print("📝 Let's set up your Telegram credentials...\n")

# Get bot token
print("STEP 1: Bot Token")
print("  • Go to Telegram and message @BotFather")
print("  • Type /newbot and follow instructions")
print("  • BotFather will give you a token (looks like: 123456789:ABCdef...)\n")

while True:
    token = input("Enter your Bot Token: ").strip()
    if token and ":" in token:
        break
    print("❌ Invalid token format. Should contain ':'")

print("\n✅ Token saved!\n")

# Get chat ID
print("STEP 2: Chat ID")
print("  • Open Telegram and search for your bot (@your_bot_name)")
print("  • Send ANY message to your bot (e.g., 'hello')")
print("  • Run: python get_chat_id.py (if you haven't already)")
print("  • OR use @userinfobot (send /start, it replies with your chat ID)\n")

while True:
    chat_id = input("Enter your Chat ID: ").strip()
    if chat_id and (chat_id.isdigit() or chat_id.lstrip("-").isdigit()):
        break
    print("❌ Invalid Chat ID. Should be a number (can be negative)")

print("\n✅ Chat ID saved!\n")

# Create .env file
env_content = f"""# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN={token}
TELEGRAM_CHAT_ID={chat_id}
"""

with open(env_path, "w", encoding="utf-8") as f:
    f.write(env_content)

print("="*60)
print("✅ Setup Complete!")
print("="*60)
print(f"\n📄 Created: {env_path}")
print("\n🔹 Next steps:")
print("  1. Test your setup:")
print("     python -m tracker --setup")
print("\n  2. Run a quick check:")
print("     python -m tracker --now")
print("\n  3. Full analysis:")
print("     python -m tracker --now --full")
print("\n  4. Start scheduler:")
print("     python -m tracker --schedule")
print("\n" + "="*60 + "\n")
