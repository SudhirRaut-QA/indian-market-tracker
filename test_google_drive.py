"""
Google Drive Setup Verification & Test
=======================================

Quick test to verify Google Drive configuration before running the full tracker.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

def test_google_drive_setup():
    """Test Google Drive configuration."""
    print("\n" + "="*60)
    print("Google Drive Configuration Check")
    print("="*60 + "\n")
    
    # 1. Check environment variables
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    credentials_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    
    print("1. Environment Variables:")
    print(f"   Folder ID: {'✅ ' + folder_id if folder_id else '❌ Not set'}")
    print(f"   Credentials: {'✅ ' + credentials_path if credentials_path else '❌ Not set'}")
    
    if not folder_id or not credentials_path:
        print("\n❌ Missing environment variables in .env file")
        return False
    
    # 2. Check credentials file exists
    print(f"\n2. Credentials File:")
    cred_path = Path(credentials_path)
    if cred_path.exists():
        print(f"   ✅ File exists: {cred_path}")
        print(f"   Size: {cred_path.stat().st_size} bytes")
    else:
        print(f"   ❌ File not found: {cred_path}")
        return False
    
    # 3. Parse credentials
    print(f"\n3. Service Account Details:")
    try:
        import json
        with open(cred_path) as f:
            creds = json.load(f)
        
        client_email = creds.get("client_email", "")
        project_id = creds.get("project_id", "")
        
        print(f"   Email: {client_email}")
        print(f"   Project: {project_id}")
        
        if not client_email or not project_id:
            print("   ❌ Invalid credentials JSON")
            return False
        
        print(f"   ✅ Credentials valid")
        
    except Exception as e:
        print(f"   ❌ Error parsing credentials: {e}")
        return False
    
    # 4. Check Google API libraries
    print(f"\n4. Google API Libraries:")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        print("   ✅ google-api-python-client installed")
    except ImportError as e:
        print(f"   ❌ Missing library: {e}")
        print("   Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        return False
    
    # 5. Test connection to Google Drive
    print(f"\n5. Testing Google Drive Connection:")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        # Load credentials
        credentials = service_account.Credentials.from_service_account_file(
            str(cred_path),
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        # Build service
        service = build('drive', 'v3', credentials=credentials)
        
        print("   ✅ Service initialized")
        
        # Try to access the folder
        print(f"\n6. Testing Folder Access:")
        folder = service.files().get(
            fileId=folder_id,
            fields='id, name, capabilities'
        ).execute()
        
        print(f"   ✅ Folder found: {folder['name']}")
        print(f"   Folder ID: {folder['id']}")
        
        # Check permissions
        capabilities = folder.get('capabilities', {})
        can_edit = capabilities.get('canEdit', False)
        
        if can_edit:
            print(f"   ✅ Service account has EDIT permission")
        else:
            print(f"   ⚠️ Service account may not have edit permission")
            print(f"   Make sure you shared the folder with: {client_email}")
        
        # Try to list files in folder
        print(f"\n7. Listing Files in Folder:")
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=10,
            fields='files(id, name, size, modifiedTime)'
        ).execute()
        
        files = results.get('files', [])
        if files:
            print(f"   Found {len(files)} file(s):")
            for file in files:
                size = int(file.get('size', 0))
                size_kb = size / 1024
                print(f"   - {file['name']} ({size_kb:.1f} KB)")
        else:
            print(f"   📁 Folder is empty (ready for uploads)")
        
        print("\n" + "="*60)
        print("✅ ALL CHECKS PASSED - Google Drive is ready!")
        print("="*60)
        print(f"\nFolder link: https://drive.google.com/drive/folders/{folder_id}")
        print(f"\nYou can now run: python -m tracker --now")
        print("Excel files will automatically upload to this folder.")
        print("="*60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        print(f"\n   Troubleshooting:")
        print(f"   1. Verify Google Drive API is enabled in Cloud Console")
        print(f"   2. Verify folder is shared with: {client_email}")
        print(f"   3. Check folder ID is correct: {folder_id}")
        return False

if __name__ == "__main__":
    success = test_google_drive_setup()
    sys.exit(0 if success else 1)
