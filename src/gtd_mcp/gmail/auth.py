"""Gmail OAuth2 authentication — token persistence and refresh."""

from __future__ import annotations

import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailAuth:
    """Handles Gmail OAuth2 flow, token storage, and refresh.

    On first run, opens a browser for consent. Subsequent runs use the
    stored token, refreshing automatically when expired.
    """

    def __init__(self, credentials_path: str, token_path: str) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._service = None

    def get_credentials(self) -> Credentials:
        """Load or create OAuth2 credentials.

        Returns valid credentials, handling refresh and first-run consent flow.
        Raises FileNotFoundError if credentials file is missing.
        """
        creds = None

        # Try loading existing token
        if os.path.exists(self._token_path):
            creds = Credentials.from_authorized_user_file(self._token_path, SCOPES)

        # Refresh or run consent flow
        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_token(creds)
            return creds

        # First-run: need credentials file
        if not os.path.exists(self._credentials_path):
            raise FileNotFoundError(
                f"Gmail credentials file not found at '{self._credentials_path}'. "
                "Download it from Google Cloud Console: "
                "https://console.cloud.google.com/apis/credentials"
            )

        flow = InstalledAppFlow.from_client_secrets_file(self._credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
        self._save_token(creds)
        return creds

    def get_service(self):
        """Build and cache a Gmail API service resource."""
        if self._service is None:
            creds = self.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def _save_token(self, creds: Credentials) -> None:
        """Persist token to disk for future runs."""
        os.makedirs(os.path.dirname(self._token_path) or ".", exist_ok=True)
        with open(self._token_path, "w") as f:
            f.write(creds.to_json())
