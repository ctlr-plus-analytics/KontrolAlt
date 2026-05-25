"""Scraper-specific exceptions."""


class ScraperBlockedError(RuntimeError):
    """Raised when a target site serves an anti-bot challenge or block page."""


class CloudflareBlockError(ScraperBlockedError):
    """Raised when a Cloudflare block/challenge is classified."""

    def __init__(
        self,
        *,
        error_name: str,
        block_type: str,
        rotation_helps: bool,
        error_code: int | None = None,
        detail: str = "",
    ) -> None:
        self.error_name = error_name
        self.block_type = block_type
        self.rotation_helps = rotation_helps
        self.error_code = error_code
        message = (
            f"cloudflare_error={error_name}; block_type={block_type}; "
            f"rotation_helps={'true' if rotation_helps else 'false'}; "
            f"error_code={error_code if error_code is not None else 'none'}; detail={detail}"
        )
        super().__init__(message)


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
