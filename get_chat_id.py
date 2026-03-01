"""
Quick script to get your Telegram Chat ID
Run after creating bot and messaging it once
"""
import requests
import sys

print("\n=== Telegram Chat ID Finder ===\n")
print("STEP 1: Enter your bot token (from BotFather)")
token = input("Bot Token: ").strip()

if not token:
    print("❌ No token provided")
    sys.exit(1)

print("\nSTEP 2: Open Telegram and send ANY message to your bot")
print("        (Search for your bot username and say 'hello')")
input("\nPress ENTER after you've sent a message to your bot...")

print("\nFetching your Chat ID...")
try:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    resp = requests.get(url, timeout=10)
    
    if resp.status_code != 200:
        print(f"❌ Error: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    
    if not data.get("result"):
        print("❌ No messages found. Make sure you sent a message to your bot first!")
        sys.exit(1)
    
    chat_id = data["result"][0]["message"]["chat"]["id"]
    username = data["result"][0]["message"]["chat"].get("username", "N/A")
    first_name = data["result"][0]["message"]["chat"].get("first_name", "N/A")
    
    print("\n✅ Found your details:")
    print(f"   Chat ID: {chat_id}")
    print(f"   Username: @{username}")
    print(f"   Name: {first_name}")
    print(f"\nYour Chat ID is: {chat_id}")
    print("\nCopy this number for the next step!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
