"""Tests for Gmail OAuth2 authentication."""

from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

import pytest

from gtd_mcp.gmail.auth import SCOPES, GmailAuth


class TestGetCredentials:
    def test_loads_valid_token(self, tmp_path):
        auth = GmailAuth(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
        )
        mock_creds = MagicMock()
        mock_creds.valid = True

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "gtd_mcp.gmail.auth.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ) as mock_load,
        ):
            result = auth.get_credentials()

        assert result is mock_creds
        mock_load.assert_called_once_with(str(tmp_path / "token.json"), SCOPES)

    def test_refreshes_expired_token(self, tmp_path):
        auth = GmailAuth(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
        )
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_tok"
        mock_creds.to_json.return_value = '{"token": "new"}'

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "gtd_mcp.gmail.auth.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ),
            patch("builtins.open", mock_open()),
            patch("os.makedirs"),
        ):
            result = auth.get_credentials()

        mock_creds.refresh.assert_called_once()
        assert result is mock_creds

    def test_runs_consent_flow_when_no_token(self, tmp_path):
        creds_path = str(tmp_path / "creds.json")
        token_path = str(tmp_path / "token.json")
        auth = GmailAuth(credentials_path=creds_path, token_path=token_path)

        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "new"}'
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        def exists_side_effect(path):
            if path == token_path:
                return False
            if path == creds_path:
                return True
            return False

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch(
                "gtd_mcp.gmail.auth.InstalledAppFlow.from_client_secrets_file",
                return_value=mock_flow,
            ) as mock_from_file,
            patch("builtins.open", mock_open()),
            patch("os.makedirs"),
        ):
            result = auth.get_credentials()

        mock_from_file.assert_called_once_with(creds_path, SCOPES)
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert result is mock_creds

    def test_raises_when_credentials_file_missing(self, tmp_path):
        auth = GmailAuth(
            credentials_path=str(tmp_path / "missing_creds.json"),
            token_path=str(tmp_path / "token.json"),
        )

        with (
            patch("os.path.exists", return_value=False),
            pytest.raises(FileNotFoundError, match="Gmail credentials file not found"),
        ):
            auth.get_credentials()


class TestGetService:
    def test_builds_and_caches_service(self, tmp_path):
        auth = GmailAuth(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
        )
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_service = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch(
                "gtd_mcp.gmail.auth.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ),
            patch("gtd_mcp.gmail.auth.build", return_value=mock_service) as mock_build,
        ):
            service1 = auth.get_service()
            service2 = auth.get_service()

        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)
        assert service1 is service2
