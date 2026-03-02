# Google Drive Setup Guide

This guide walks you through setting up automatic Excel and JSON backups to Google Drive.

---

## 📋 What You'll Need

1. **Google Cloud Account** (free)
2. **Google Drive folder** to store backups
3. **15 minutes** of setup time

---

## 🚀 Step-by-Step Setup

### Step 1: Enable Google Drive API

1. Go to **Google Cloud Console**: https://console.cloud.google.com/
2. Create a new project (or select existing):
   - Click the project dropdown (top left)
   - Click "**New Project**"
   - Name: `Market Tracker` (or your choice)
   - Click "**Create**"
3. Wait for project creation, then select it from the dropdown

### Step 2: Enable the Drive API

1. In the search bar at top, type: **Google Drive API**
2. Click "**Google Drive API**" from results
3. Click "**Enable**" button
4. Wait for activation (10-20 seconds)

### Step 3: Create Service Account

1. In left sidebar, go to: **IAM & Admin** → **Service Accounts**
2. Click "**+ Create Service Account**" (top of page)
3. **Service account details**:
   - Name: `market-tracker-uploader`
   - Description: `Uploads market data to Google Drive`
   - Click "**Create and Continue**"
4. **Grant access** (Step 2):
   - Skip this step (not needed)
   - Click "**Continue**"
5. **Grant users access** (Step 3):
   - Skip this step
   - Click "**Done**"

### Step 4: Generate Service Account Key (JSON)

1. Click on the service account you just created
2. Go to "**Keys**" tab (top menu)
3. Click "**Add Key**" → "**Create new key**"
4. Select key type: **JSON**
5. Click "**Create**"
6. A JSON file will download automatically (e.g., `market-tracker-uploader-abc123.json`)
7. **Save this file securely** - you'll need it later

### Step 5: Create Google Drive Folder

1. Open **Google Drive**: https://drive.google.com/
2. Click "**+ New**" → "**New folder**"
3. Name it: `Market Tracker Backups` (or your choice)
4. Click "**Create**"
5. Right-click the folder → "**Share**"
6. **Important**: Copy the **folder ID** from the URL in your browser:
   ```
   https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0
   ```
   The folder ID is: `1a2b3c4d5e6f7g8h9i0`
   
   **Save this ID** - you'll need it!

### Step 6: Share Folder with Service Account

Still in the Share dialog:

1. Open your downloaded JSON file from Step 4
2. Find the `"client_email"` field (looks like: `market-tracker-uploader@your-project.iam.gserviceaccount.com`)
3. **Copy this email address**
4. In the Share dialog, paste the email
5. Role: **Editor** (allows upload/update files)
6. **Uncheck** "Notify people" (it's a service account, not a person)
7. Click "**Share**"

✅ Your service account can now upload to this folder!

---

## 💻 Local Configuration

### Option 1: Using JSON File (Recommended for Local Testing)

1. Create a folder for credentials (in project root):
   ```powershell
   mkdir credentials
   ```

2. Move your downloaded JSON file there:
   ```powershell
   Move-Item "Downloads\market-tracker-uploader-*.json" "credentials\service-account.json"
   ```

3. Update your `.env` file:
   ```env
   GOOGLE_DRIVE_FOLDER_ID=1a2b3c4d5e6f7g8h9i0
   GOOGLE_SERVICE_ACCOUNT_JSON=credentials/indian-stock-market-tracker-44b12e07c515.json
   ```

4. Add to `.gitignore` (already there):
   ```
   credentials/
   ```

### Option 2: Using JSON String (For GitHub Actions)

1. Open your `service-account.json` file
2. Copy the **entire contents** (it's a single line of JSON)
3. You'll use this as a GitHub Secret (see below)

---

## ☁️ GitHub Actions Configuration

To enable Google Drive uploads in GitHub Actions:

### 1. Add GitHub Secret: GOOGLE_DRIVE_FOLDER_ID

1. Go to: https://github.com/SudhirRaut-QA/indian-market-tracker/settings/secrets/actions
2. Click "**New repository secret**"
3. Name: `GOOGLE_DRIVE_FOLDER_ID`
4. Secret: `1a2b3c4d5e6f7g8h9i0` (your folder ID from Step 5)
5. Click "**Add secret**"

### 2. Add GitHub Secret: GOOGLE_SERVICE_ACCOUNT_JSON

1. Click "**New repository secret**" again
2. Name: `GOOGLE_SERVICE_ACCOUNT_JSON`
3. Secret: Paste the **entire JSON contents** from your service-account.json file
   - Open the JSON file in Notepad
   - Select All (Ctrl+A)
   - Copy (Ctrl+C)
   - Paste here
4. Click "**Add secret**"

### 3. Update Workflow Files

The workflows are already configured, but verify these sections exist:

**morning_tracker.yml** and **afternoon_tracker.yml** should have:

```yaml
- name: Create .env file
  run: |
    echo "TELEGRAM_BOT_TOKEN=${{ secrets.TELEGRAM_BOT_TOKEN }}" > .env
    echo "TELEGRAM_CHAT_ID=${{ secrets.TELEGRAM_CHAT_ID }}" >> .env
    echo "GOOGLE_DRIVE_FOLDER_ID=${{ secrets.GOOGLE_DRIVE_FOLDER_ID }}" >> .env
    echo "GOOGLE_SERVICE_ACCOUNT_JSON=${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}" >> .env
```

---

## ✅ Testing

### Test Locally

```powershell
# Install Google Drive dependencies
pip install -r requirements.txt

# Run a quick test
python -m tracker --now

# Check your Google Drive folder - should see:
# - Excel files in root
# - JSON snapshots (latest 5)
```

### Test in GitHub Actions

1. Go to: https://github.com/SudhirRaut-QA/indian-market-tracker/actions
2. Select "Market Tracker - Morning Session"
3. Click "Run workflow"
4. Wait for completion
5. Check your Google Drive folder for uploaded files

---

## 📁 What Gets Uploaded?

### Excel Files (All)
- `Market_Summary_YYYYMMDD_HHMMSS.xlsx` (latest)
- Automatically replaces previous version if same name

### JSON Snapshots (Latest 5)
- `snapshot_HHMMSS.json`
- Keeps 5 most recent snapshots
- Prevents unlimited growth

### Folder Structure in Drive

```
Market Tracker Backups/
├── Market_Summary_20260301_091500.xlsx
├── Market_Summary_20260301_153500.xlsx
├── snapshot_091502.json
├── snapshot_093005.json
├── snapshot_110003.json
├── snapshot_153504.json
└── snapshot_180001.json
```

---

## 🔧 Troubleshooting

### "Permission denied" error
- Verify you shared the folder with service account email
- Check the email in JSON matches what you shared with

### "File not found" error
- Verify folder ID in .env is correct
- Check folder is not in Trash

### "API not enabled" error
- Go back to Step 2 and enable Google Drive API
- Wait 5 minutes for propagation

### Files not uploading
- Check GitHub Actions logs for errors
- Verify secrets are set correctly (no extra spaces)
- Test locally first to isolate issue

### "google.auth" import error
- Install dependencies: `pip install -r requirements.txt`
- Verify google-api-python-client is installed

---

## 📊 Benefits

✅ **Automatic Backups**: Every run uploads to Drive  
✅ **Access Anywhere**: View Excel files from phone/tablet  
✅ **Easy Sharing**: Share Drive folder link with others  
✅ **Version History**: Google Drive keeps file versions  
✅ **No Local Storage**: Save space on GitHub Actions  
✅ **Telegram Links**: Messages include Drive folder link  

---

## 🔒 Security Notes

- **Never commit** `service-account.json` to Git
- Keep credentials in `.gitignore`
- Use GitHub Secrets for Actions
- Share Drive folder only with trusted people
- Rotate service account keys every 90 days (best practice)

---

## 🎯 Quick Reference

### Environment Variables
```env
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service-account.json
```

### GitHub Secrets (4 total)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GOOGLE_DRIVE_FOLDER_ID` ← New
- `GOOGLE_SERVICE_ACCOUNT_JSON` ← New

### Files to Update
- `.env` (local)
- GitHub Secrets (Actions)
- `.github/workflows/morning_tracker.yml`
- `.github/workflows/afternoon_tracker.yml`

---

## ❓ FAQ

**Q: Is Google Drive integration required?**  
A: No, it's optional. Tracker works fine without it.

**Q: What if I hit Drive storage limits?**  
A: Free Google accounts get 15GB. Market data uses ~10MB/day.

**Q: Can I use my personal Google account?**  
A: Yes, but service accounts are more secure for automation.

**Q: Can I upload to multiple folders?**  
A: Yes, update `GOOGLE_DRIVE_FOLDER_ID` to different folder.

**Q: Does this cost money?**  
A: No, Google Drive API is free for this usage level.

---

**Need Help?**  
- Google Cloud Console: https://console.cloud.google.com/
- Google Drive API Docs: https://developers.google.com/drive/api/v3/about-sdk
- Service Accounts Guide: https://cloud.google.com/iam/docs/service-accounts

---

✅ **Once configured, your Excel files and snapshots will automatically backup to Google Drive with every run!**
