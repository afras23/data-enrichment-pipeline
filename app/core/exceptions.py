"""
Application exception hierarchy for API and pipeline errors.
"""


class AppError(Exception):
    """Base application error with optional structured details."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, object] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class ValidationAppError(AppError):
    """Input or schema validation failed."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message, error_code="VALIDATION_FAILED", details=details)


class NotFoundError(AppError):
    """Requested resource does not exist."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message, error_code="NOT_FOUND", details=details)


class ScrapeError(AppError):
    """HTTP fetch or HTML processing failed."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message, error_code="SCRAPE_FAILED", details=details)


class EnrichmentAIError(AppError):
    """OpenAI enrichment step failed."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message, error_code="ENRICHMENT_AI_FAILED", details=details)


class CostLimitExceeded(AppError):  # noqa: N818 — portfolio naming matches upstream CostLimitExceeded
    """Run exceeded configured AI cost budget."""

    def __init__(self, current_usd: float, limit_usd: float) -> None:
        super().__init__(
            f"Cost {current_usd:.4f} USD exceeds run limit {limit_usd:.4f} USD",
            error_code="COST_LIMIT_EXCEEDED",
            details={"current_usd": current_usd, "limit_usd": limit_usd},
        )
