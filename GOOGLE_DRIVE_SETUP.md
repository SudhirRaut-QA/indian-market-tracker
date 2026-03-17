# ☁️ Google Drive Setup Guide

> Automatically back up your Excel reports and JSON snapshots to Google Drive after every run.
> Setup takes about **15 minutes** with this guide.

---

## 🤔 What Does This Do?

```
  After each run...
                                        ┌──────────────────────┐
  Indian Market Tracker                 │   Your Google Drive  │
  ┌─────────────────────────┐           │  ┌────────────────┐  │
  │  data/excel/            │  ──────►  │  │market_tracker  │  │
  │    market_tracker.xlsx  │  uploads  │  │    .xlsx       │  │
  │  data/snapshots/        │           │  └────────────────┘  │
  │    *.json               │           │  ┌────────────────┐  │
  └─────────────────────────┘           │  │ snapshot_XYZ   │  │
                                        │  │    .json       │  │
                                        │  └────────────────┘  │
                                        └──────────────────────┘
```

**Why bother?**
- Access your market history from any device
- GitHub repo has limited storage — Drive has 15 GB free
- Excel files are not practical to store in git history

---

## 📋 Prerequisites

| Need | Details |
|------|---------|
| Google account | Gmail/Workspace — free |
| Google Cloud Console access | [console.cloud.google.com](https://console.cloud.google.com) |
| ~15 minutes | One-time setup only |

---

## 🚀 Step-by-Step Setup

### Step 1 — Create a Google Cloud Project

1. Open [Google Cloud Console](https://console.cloud.google.com)
2. Click the **project dropdown** at the top left
3. Click **"New Project"**
   - Name: `Market Tracker` (or anything you like)
   - Click **"Create"**
4. Make sure your new project is selected in the dropdown

---

### Step 2 — Enable the Google Drive API

1. In the top search bar, type: `Google Drive API`
2. Click **"Google Drive API"** from results
3. Click the blue **"Enable"** button
4. Wait 10–20 seconds for activation

---

### Step 3 — Create a Service Account

> A **Service Account** is like a robot employee — it has its own email address and can be given permission to access your Drive folder.

1. In the left sidebar → **IAM & Admin** → **Service Accounts**
2. Click **"+ Create Service Account"**
3. Fill in:
   - **Name:** `market-tracker-uploader`
   - **Description:** `Uploads market data to Google Drive`
   - Click **"Create and Continue"**
4. Skip the **Grant access** step → Click **"Continue"**
5. Skip the **Grant users access** step → Click **"Done"**

---

### Step 4 — Download the JSON Key

1. Click on the service account you just created
2. Go to the **"Keys"** tab
3. Click **"Add Key"** → **"Create new key"**
4. Choose **JSON** → Click **"Create"**
5. A JSON file downloads automatically (e.g., `market-tracker-uploader-abc123.json`)

> 🔒 **Keep this file safe!** It is a private key. Never share it or commit it to git.

---

### Step 5 — Create a Google Drive Folder

> ⚠️ **Important:** As of late 2024, Google **does not allow** service accounts to upload to personal "My Drive". You have two options:

#### Option A — Shared Drive (Recommended if you have Google Workspace)

1. Open [Google Drive](https://drive.google.com)
2. In the left panel → **"Shared Drives"**
3. Click **"+ New"** → Name it `Market Tracker Backups`
4. Right-click the drive → **"Manage members"**
5. Add your service account email (from the JSON file, `"client_email"` field)
6. Role: **Content Manager** or **Contributor**

#### Option B — Personal Drive with Folder Sharing

1. Open [Google Drive](https://drive.google.com)
2. Click **"+ New"** → **"New folder"**
3. Name it: `Market Tracker Backups`
4. Right-click the folder → **"Share"**
5. Add your service account email
6. Role: **Editor**
7. Uncheck **"Notify people"** (it's a robot, not a person)
8. Click **"Share"**

---

### Step 6 — Get the Folder ID

The **Folder ID** is in the URL when you open the folder in your browser:

```
https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0jklmnop
                                       └─────── FOLDER ID ──────────────┘
```

**Copy and save this** — you need it in Step 7.

---

### Step 7 — Configure Your .env

Open your `.env` file and add:

```env
GOOGLE_DRIVE_FOLDER_ID=1a2b3c4d5e6f7g8h9i0jklmnop
GOOGLE_SERVICE_ACCOUNT_JSON=credentials/service-account.json
```

Move your downloaded JSON key:
```powershell
# Windows
Move-Item "$env:USERPROFILE\Downloads\market-tracker-*.json" "credentials\service-account.json"
```

```bash
# Mac/Linux
mv ~/Downloads/market-tracker-*.json credentials/service-account.json
```

---

### Step 8 — Test the Connection

```bash
python test_google_drive.py
```

Expected output:
```
✅ Google Drive connection: OK
✅ Folder found: Market Tracker Backups
✅ Upload test: OK (test file uploaded and deleted)
```

---

## 🤖 GitHub Actions Setup

For automated Cloud runs, add secrets instead of files:

**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|-------------|-------|
| `GOOGLE_DRIVE_FOLDER_ID` | Your folder ID from Step 6 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | **Entire contents** of your JSON key file (copy-paste the whole file as one string) |

> 💡 To get the JSON as one string: Open the file in a text editor, select all, copy. GitHub handles multi-line secrets fine.

---

## 🗂️ What Gets Uploaded

After every successful run:

| File | When | Drive Path |
|------|------|-----------|
| `market_tracker.xlsx` | Every run | Overwrites same file (version history kept by Drive) |
| `snapshot_YYYYMMDD_HHMMSS.json` | Every snapshot | New file each time |

---

## ❓ FAQ

**Q: Do I need Google Workspace (paid)?**
No, a free Gmail account works. Use Option B (personal Drive folder sharing).

**Q: Why is "My Drive" not working with service accounts?**
Google restricted service account uploads to personal My Drive in mid-2024 due to spam/abuse. Shared Drives (Google Workspace) still work perfectly. Alternatively, share a specific folder with the service account — this works with free Gmail.

**Q: How do I find my service account email?**
Open the downloaded JSON key file. Look for the `"client_email"` field:
```json
{
  "client_email": "market-tracker-uploader@your-project.iam.gserviceaccount.com"
}
```
This is the email to share the Drive folder with.

**Q: Upload failed with "403 Forbidden"?**
The service account doesn't have access to the folder. Re-do Step 5 and make sure you used the correct email address.

**Q: I get "File quota exceeded"?**
Google Drive free tier has 15 GB. Check your storage at [drive.google.com/settings/storage](https://drive.google.com/settings/storage). The Excel file is usually <5 MB and snapshots are <1 MB each.

**Q: Can I use a different folder for Excel vs JSON?**
Not currently — both go to the same `GOOGLE_DRIVE_FOLDER_ID`. You can organise with subfolders inside it.

**Q: Is this secure? My Drive has private files.**
Yes — the service account only has access to the **specific folder** you shared it with (Role: Editor or Content Manager). It cannot see, read, or touch any other files in your Google Drive.

**Q: How to list what's already in my Drive folder?**
```bash
python list_drive_files.py
```

---

## 🔗 See Also

| Document | Content |
|----------|---------|
| [SECURITY.md](SECURITY.md) | How credentials are protected |
| [QUICKSTART.md](QUICKSTART.md) | Full setup guide |
| [README.md](README.md) | Project overview |