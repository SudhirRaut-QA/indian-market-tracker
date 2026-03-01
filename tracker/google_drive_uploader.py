"""
Google Drive Uploader for Market Tracker
=========================================

Uploads Excel files and JSON snapshots to Google Drive.
Supports both Service Account (for GitHub Actions) and OAuth2 (for local use).

Setup:
1. Enable Google Drive API in Google Cloud Console
2. Create Service Account and download credentials JSON
3. Share target Google Drive folder with service account email
4. Set GOOGLE_DRIVE_FOLDER_ID and GOOGLE_SERVICE_ACCOUNT_JSON in env
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GoogleDriveUploader:
    """Upload files to Google Drive using Service Account."""
    
    def __init__(self, folder_id: Optional[str] = None, credentials_json: Optional[str] = None):
        """
        Initialize Google Drive uploader.
        
        Args:
            folder_id: Google Drive folder ID (from URL)
            credentials_json: Path to service account JSON or JSON string
        """
        self.folder_id = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        self.credentials_json = credentials_json or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        self.service = None
        self.enabled = False
        
        if self.folder_id and self.credentials_json:
            try:
                self._initialize_service()
                self.enabled = True
                logger.info(f"Google Drive enabled - Folder ID: {self.folder_id[:20]}...")
            except Exception as e:
                logger.warning(f"Google Drive initialization failed: {e}")
                logger.warning("Continuing without Google Drive upload")
        else:
            logger.info("Google Drive not configured (optional)")
    
    def _initialize_service(self):
        """Initialize Google Drive API service."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google Drive dependencies not installed. Install with:\n"
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        
        # Parse credentials (could be file path or JSON string)
        if self.credentials_json.startswith('{'):
            # It's a JSON string (from GitHub secret)
            credentials_info = json.loads(self.credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
        else:
            # It's a file path
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_json,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
        
        self.service = build('drive', 'v3', credentials=credentials)
        logger.info("Google Drive API initialized")
    
    def upload_file(self, file_path: str, folder_id: Optional[str] = None, 
                   mime_type: Optional[str] = None) -> Optional[str]:
        """
        Upload a single file to Google Drive.
        
        Args:
            file_path: Path to file to upload
            folder_id: Override default folder ID
            mime_type: MIME type (auto-detected if not provided)
        
        Returns:
            File ID on success, None on failure
        """
        if not self.enabled:
            return None
        
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            logger.error("googleapiclient not installed")
            return None
        
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        target_folder = folder_id or self.folder_id
        file_name = file_path.name
        
        # Auto-detect MIME type
        if mime_type is None:
            if file_path.suffix == '.xlsx':
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif file_path.suffix == '.json':
                mime_type = 'application/json'
            elif file_path.suffix == '.zip':
                mime_type = 'application/zip'
            else:
                mime_type = 'application/octet-stream'
        
        try:
            # Check if file already exists (by name in folder)
            existing_file_id = self._find_file_by_name(file_name, target_folder)
            
            file_metadata = {
                'name': file_name,
                'parents': [target_folder]
            }
            
            media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
            
            if existing_file_id:
                # Update existing file
                file = self.service.files().update(
                    fileId=existing_file_id,
                    media_body=media
                ).execute()
                logger.info(f"Updated: {file_name} (ID: {file['id']})")
            else:
                # Create new file
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink'
                ).execute()
                logger.info(f"Uploaded: {file_name} (ID: {file['id']})")
            
            return file['id']
            
        except Exception as e:
            logger.error(f"Failed to upload {file_name}: {e}")
            return None
    
    def _find_file_by_name(self, file_name: str, folder_id: str) -> Optional[str]:
        """Find file by name in specific folder."""
        try:
            query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                spaces='drive'
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            return None
            
        except Exception as e:
            logger.warning(f"Error searching for file: {e}")
            return None
    
    def upload_excel_files(self, excel_dir: str) -> int:
        """
        Upload all Excel files from directory.
        
        Args:
            excel_dir: Path to directory containing Excel files
        
        Returns:
            Number of files successfully uploaded
        """
        if not self.enabled:
            return 0
        
        excel_dir = Path(excel_dir)
        if not excel_dir.exists():
            logger.warning(f"Excel directory not found: {excel_dir}")
            return 0
        
        uploaded = 0
        for xlsx_file in excel_dir.glob("*.xlsx"):
            if self.upload_file(str(xlsx_file)):
                uploaded += 1
        
        return uploaded
    
    def upload_snapshots(self, snapshots_dir: str, max_files: int = 10) -> int:
        """
        Upload recent JSON snapshots.
        
        Args:
            snapshots_dir: Path to snapshots directory
            max_files: Maximum number of recent files to upload
        
        Returns:
            Number of files successfully uploaded
        """
        if not self.enabled:
            return 0
        
        snapshots_dir = Path(snapshots_dir)
        if not snapshots_dir.exists():
            logger.warning(f"Snapshots directory not found: {snapshots_dir}")
            return 0
        
        # Get all JSON files recursively
        json_files = list(snapshots_dir.rglob("*.json"))
        
        # Sort by modification time (newest first)
        json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Upload most recent files
        uploaded = 0
        for json_file in json_files[:max_files]:
            if self.upload_file(str(json_file)):
                uploaded += 1
        
        return uploaded
    
    def create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> Optional[str]:
        """
        Create a new folder in Google Drive.
        
        Args:
            folder_name: Name of folder to create
            parent_folder_id: Parent folder ID (None for root)
        
        Returns:
            Folder ID on success, None on failure
        """
        if not self.enabled:
            return None
        
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id, name, webViewLink'
            ).execute()
            
            logger.info(f"Created folder: {folder_name} (ID: {folder['id']})")
            return folder['id']
            
        except Exception as e:
            logger.error(f"Failed to create folder {folder_name}: {e}")
            return None
    
    def get_folder_link(self, folder_id: Optional[str] = None) -> str:
        """Get shareable link for folder."""
        fid = folder_id or self.folder_id
        return f"https://drive.google.com/drive/folders/{fid}"
    
    def list_files(self, folder_id: Optional[str] = None, max_results: int = 20) -> list:
        """
        List files in folder.
        
        Args:
            folder_id: Folder ID (uses default if not provided)
            max_results: Maximum number of files to return
        
        Returns:
            List of file dictionaries with id, name, size, modifiedTime
        """
        if not self.enabled:
            return []
        
        target_folder = folder_id or self.folder_id
        
        try:
            query = f"'{target_folder}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields='files(id, name, size, modifiedTime, webViewLink)',
                orderBy='modifiedTime desc'
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []


def format_drive_summary(uploader: GoogleDriveUploader, excel_count: int, 
                         snapshot_count: int) -> str:
    """
    Format Google Drive upload summary for Telegram.
    
    Args:
        uploader: GoogleDriveUploader instance
        excel_count: Number of Excel files uploaded
        snapshot_count: Number of snapshots uploaded
    
    Returns:
        Formatted HTML message
    """
    if not uploader.enabled or (excel_count == 0 and snapshot_count == 0):
        return ""
    
    folder_link = uploader.get_folder_link()
    
    msg = "\n\n<b>📂 Google Drive Backup</b>\n"
    
    if excel_count > 0:
        msg += f"• {excel_count} Excel file(s) uploaded\n"
    
    if snapshot_count > 0:
        msg += f"• {snapshot_count} JSON snapshot(s) uploaded\n"
    
    msg += f"\n🔗 <a href='{folder_link}'>View Files</a>"
    
    return msg
