"""
Quick test to list all files the service account can access
"""
import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

# Load credentials
credentials = service_account.Credentials.from_service_account_file(
    'credentials/service-account.json',
    scopes=['https://www.googleapis.com/auth/drive']
)

# Build service
service = build('drive', 'v3', credentials=credentials)

print("Listing all files the service account can access:\n")

# List all files accessible to service account
results = service.files().list(
    pageSize=50,
    fields='files(id, name, mimeType, owners, shared, parents)'
).execute()

files = results.get('files', [])

if not files:
    print("❌ No files found. The service account has no access to any files.")
    print("\nThis means the folder was not shared correctly.")
    print("\nPlease:")
    print("1. Open the folder in Google Drive")
    print("2. Right-click → Share")
    print("3. Add: market-tracker-uploader@indian-stock-market-tracker.iam.gserviceaccount.com")
    print("4. Set role: Editor")
    print("5. Make sure to CLICK 'Share' or 'Send' button")
else:
    print(f"✅ Found {len(files)} file(s)/folder(s):\n")
    for file in files:
        print(f"Name: {file['name']}")
        print(f"ID: {file['id']}")
        print(f"Type: {file['mimeType']}")
        if file.get('shared'):
            print(f"Shared: Yes")
        print("-" * 60)

print("\nIf you see your folder above, copy its ID and update .env file")
