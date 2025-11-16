"""
Google Calendar Integration for ego_proxy Personal Assistant

Provides OAuth2 authentication and calendar event creation functionality
for natural language calendar management.
"""

import json
import logging
import os
import subprocess
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Scopes required for calendar access
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def is_wsl() -> bool:
    """
    Detect if running in WSL (Windows Subsystem for Linux).

    Returns:
        True if running in WSL, False otherwise
    """
    try:
        with open("/proc/version", "r") as f:
            version = f.read().lower()
            return "microsoft" in version or "wsl" in version
    except Exception:
        return False


def open_browser_wsl(url: str) -> bool:
    """
    Open a URL in Windows browser from WSL.

    Args:
        url: URL to open

    Returns:
        True if successful, False otherwise
    """
    try:
        # Try using cmd.exe to open the URL in default Windows browser
        subprocess.run(
            ["cmd.exe", "/c", "start", url],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.debug(f"Failed to open browser with cmd.exe: {e}")

    try:
        # Try wslview if available (part of wslu package)
        subprocess.run(
            ["wslview", url],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.debug(f"Failed to open browser with wslview: {e}")

    return False


class GoogleCalendarIntegration:
    """
    Manages Google Calendar API integration with OAuth2 authentication
    and event creation capabilities.
    """

    def __init__(self, database_connection, credentials_path: Optional[str] = None):
        """
        Initialize Google Calendar integration.

        Args:
            database_connection: Database connection for storing encrypted tokens
            credentials_path: Path to Google OAuth2 credentials JSON file
        """
        self.db = database_connection
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH", "credentials.json"
        )
        self.creds: Optional[Credentials] = None
        self.service = None
        self._encryption_key = self._get_or_create_encryption_key()

    def _get_or_create_encryption_key(self) -> bytes:
        """
        Get or create encryption key for token storage.

        Returns:
            Encryption key bytes
        """
        key_path = Path.home() / ".ego_proxy" / "calendar_key.bin"
        key_path.parent.mkdir(parents=True, exist_ok=True)

        if key_path.exists():
            return key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            # Set restrictive permissions
            os.chmod(key_path, 0o600)
            return key

    def _encrypt_token(self, token_data: str) -> str:
        """Encrypt token data for storage."""
        f = Fernet(self._encryption_key)
        return f.encrypt(token_data.encode()).decode()

    def _decrypt_token(self, encrypted_data: str) -> str:
        """Decrypt token data from storage."""
        f = Fernet(self._encryption_key)
        return f.decrypt(encrypted_data.encode()).decode()

    def _load_credentials_from_db(self) -> Optional[Credentials]:
        """
        Load OAuth credentials from database.

        Returns:
            Credentials object or None if not found
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("SELECT token_data FROM calendar_credentials WHERE id = 1")
            row = cursor.fetchone()

            if row:
                encrypted_token = row[0]
                token_json = self._decrypt_token(encrypted_token)
                token_data = json.loads(token_json)

                creds = Credentials(
                    token=token_data.get("token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get("token_uri"),
                    client_id=token_data.get("client_id"),
                    client_secret=token_data.get("client_secret"),
                    scopes=token_data.get("scopes"),
                )
                return creds

            return None

        except Exception as e:
            logger.error(f"Error loading credentials from database: {e}")
            return None

    def _save_credentials_to_db(self, creds: Credentials):
        """
        Save OAuth credentials to database.

        Args:
            creds: Credentials object to save
        """
        try:
            token_data = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes,
            }

            token_json = json.dumps(token_data)
            encrypted_token = self._encrypt_token(token_json)

            cursor = self.db.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO calendar_credentials (id, token_data, updated_at)
                VALUES (1, ?, datetime('now'))
            """,
                (encrypted_token,),
            )
            self.db.commit()

            logger.info("Credentials saved to database successfully")

        except Exception as e:
            logger.error(f"Error saving credentials to database: {e}")
            raise

    def authenticate(self) -> bool:
        """
        Authenticate with Google Calendar API using OAuth2.
        Handles interactive flow on first use and token refresh.

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Try to load existing credentials
            self.creds = self._load_credentials_from_db()

            # If credentials exist but are expired, refresh them
            if self.creds and self.creds.expired and self.creds.refresh_token:
                logger.info("Refreshing expired credentials...")
                self.creds.refresh(Request())
                self._save_credentials_to_db(self.creds)

            # If no valid credentials, run interactive OAuth flow
            if not self.creds or not self.creds.valid:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"Credentials file not found: {self.credentials_path}")
                    logger.error(
                        "Please follow GOOGLE_CALENDAR_SETUP.md to obtain credentials"
                    )
                    return False

                logger.info("Starting OAuth2 authentication flow...")
                print("\n🔐 Google Calendar Authentication Required")
                print("=" * 50)
                print(
                    "A browser window will open for you to authorize calendar access."
                )
                print("Please sign in and grant the requested permissions.\n")

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )

                # For WSL, use manual URL approach since browser detection doesn't work reliably
                if is_wsl():
                    print("WSL environment detected.\n")
                    print("Starting local server to receive OAuth callback...")
                    print(
                        "You'll need to manually open the authorization URL in your browser.\n"
                    )

                    # Start server without auto-opening browser
                    # The library will print the URL automatically when open_browser=False
                    try:
                        self.creds = flow.run_local_server(
                            port=0,
                            open_browser=False,
                            authorization_prompt_message="\nPlease visit this URL to authorize:\n\n{url}\n\nWaiting for authorization...\n",
                        )
                    except Exception as e:
                        logger.error(f"OAuth flow failed: {e}")
                        # Try to get the URL and display it
                        try:
                            auth_url, _ = flow.authorization_url()
                            print(f"\n⚠️  OAuth server failed to start.")
                            print(f"Please visit this URL to authorize:\n{auth_url}\n")
                        except:
                            pass
                        raise
                else:
                    # Standard flow for non-WSL environments
                    self.creds = flow.run_local_server(port=0)

                # Save credentials for future use
                self._save_credentials_to_db(self.creds)
                print("✅ Authentication successful! Token saved.\n")

            # Build the service
            self.service = build("calendar", "v3", credentials=self.creds)
            logger.info("Google Calendar service initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def is_authenticated(self) -> bool:
        """
        Check if currently authenticated with valid credentials.

        Returns:
            True if authenticated, False otherwise
        """
        return self.service is not None

    def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a calendar event.

        Args:
            summary: Event title/summary
            start_time: Event start datetime
            end_time: Event end datetime (defaults to 1 hour after start)
            description: Event description
            location: Event location
            attendees: List of attendee email addresses

        Returns:
            Created event data or None if failed
        """
        if not self.is_authenticated():
            logger.error("Not authenticated. Call authenticate() first.")
            return None

        try:
            # Default end time to 1 hour after start
            if end_time is None:
                end_time = start_time + timedelta(hours=1)

            # Build event object
            event = {
                "summary": summary,
                "start": {
                    "dateTime": start_time.isoformat(),
                    "timeZone": "UTC",  # TODO: Make timezone configurable
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                    "timeZone": "UTC",
                },
            }

            if description:
                event["description"] = description

            if location:
                event["location"] = location

            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]

            # Create the event
            created_event = (
                self.service.events().insert(calendarId="primary", body=event).execute()
            )

            logger.info(f"Event created: {created_event.get('htmlLink')}")
            return created_event

        except HttpError as error:
            logger.error(f"An error occurred creating event: {error}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating event: {e}")
            return None

    def format_event_confirmation(self, event: Dict[str, Any]) -> str:
        """
        Format event data into a user-friendly confirmation message.

        Args:
            event: Event data from Google Calendar API

        Returns:
            Formatted confirmation string
        """
        summary = event.get("summary", "Untitled Event")
        start = event.get("start", {}).get("dateTime", "")
        end = event.get("end", {}).get("dateTime", "")
        link = event.get("htmlLink", "")

        # Parse and format datetime
        if start:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            start_str = start_dt.strftime("%Y-%m-%d at %I:%M %p")
        else:
            start_str = "Unknown time"

        msg = f"✅ Calendar event created:\n"
        msg += f"   📅 {summary}\n"
        msg += f"   🕐 {start_str}\n"

        if link:
            msg += f"   🔗 {link}"

        return msg
