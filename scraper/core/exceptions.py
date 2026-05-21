"""Scraper-specific exceptions."""


class ScraperBlockedError(RuntimeError):
    """Raised when a target site serves an anti-bot challenge or block page."""


class ScraperClassifiedError(RuntimeError):
    """Raised for classified scraper failures with retry/terminal metadata."""

    def __init__(
        self,
        reason_code: str,
        detail: str,
        *,
        terminal: bool,
        retryable: bool,
    ) -> None:
        self.reason_code = reason_code
        self.detail = detail
        self.terminal = terminal
        self.retryable = retryable
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        return (
            f"reason={self.reason_code}; "
            f"terminal={'true' if self.terminal else 'false'}; "
            f"retryable={'true' if self.retryable else 'false'}; "
            f"detail={self.detail}"
        )
