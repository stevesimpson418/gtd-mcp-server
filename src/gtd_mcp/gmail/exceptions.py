"""Gmail module exceptions."""


class GmailAPIError(Exception):
    """Raised when a Gmail API call fails."""

    def __init__(self, message: str):
        super().__init__(message)
