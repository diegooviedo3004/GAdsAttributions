"""
Call conversion retry strategy.

When Google Ads returns CALL_NOT_FOUND, a different combination of
callStartDateTime and conversionDateTime sometimes succeeds for the same
caller ID. This module exhausts those combinations before giving up.

Retry grid
──────────
  For start_offset  in 0 .. search_window_days   (original date first, then backwards)
    For conv_offset in 0 .. 15                    (same day first, then up to +15 days)
      attempt upload

  Stop as soon as any attempt succeeds.
  Maximum attempts = (search_window_days + 1) × 16

All datetimes are normalised to midnight PST ("YYYY-MM-DD 00:00:00-08:00")
because that is what the original Zapier workflow used and matches the format
seen in confirmed successful imports from Google Ads.

Error classification
────────────────────
RETRYABLE – changing dates may help, keep going:
  CALL_NOT_FOUND           – call not matched yet, try next combo
  CONVERSION_PRECEDES_CALL – conversion date is before call date; since our
                             conv_offset only increases from 0, this resolves
                             itself on the next conv_offset iteration.

TERMINAL – no date change will ever fix these, stop immediately:
  UNPARSEABLE_CALLERS_PHONE_NUMBER – bad phone format, a data problem
  TOO_RECENT_CALL                  – call is too new, must wait
  LATER_THAN_MAXIMUM_DATE          – conversion date is beyond Google's limit
  EXPIRED_CALL                     – call is outside the conversion action's
                                     lookback window; going further back in
                                     start_offset only makes it worse, so
                                     continuing would waste all remaining
                                     attempts with guaranteed failure.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.integrations.google_ads import GoogleAdsClient

log = logging.getLogger("services.call_conversion_retry")

_TERMINAL_ERRORS: frozenset[str] = frozenset({
    "UNPARSEABLE_CALLERS_PHONE_NUMBER",
    "TOO_RECENT_CALL",
    "LATER_THAN_MAXIMUM_DATE",
    "EXPIRED_CALL",  # lookback window exceeded – call is simply too old
})

# All other errors (including CALL_NOT_FOUND and CONVERSION_PRECEDES_CALL)
# are treated as retryable – keep iterating combinations.


@dataclass
class RetryResult:
    success: bool
    attempts: int
    final_response: dict[str, Any]
    successful_combination: dict[str, str] | None = None
    terminal_error: str | None = None
    all_attempts: list[dict[str, Any]] = field(default_factory=list)


def _extract_error_codes(response: dict[str, Any]) -> set[str]:
    """Return all Google Ads error code values from a partialFailureError body."""
    codes: set[str] = set()
    partial = response.get("partialFailureError") or {}
    for detail in partial.get("details", []):
        for error in detail.get("errors", []):
            for _, value in error.get("errorCode", {}).items():
                codes.add(value)
    return codes


def _is_success(response: dict[str, Any]) -> bool:
    """
    A successful import has at least one non-empty result entry.

    Google Ads returns results: [{}] (empty object) when the conversion
    was submitted but not matched — that is NOT a success. A real success
    populates the result object with at least callerId or conversionAction.
    """
    results = response.get("results", [])
    return bool(results) and any(bool(r) for r in results)


def _parse_to_date(dt_str: str) -> datetime:
    """
    Extract just the date from any common datetime string and return midnight.

    Accepts:  "2026-05-29 21:50:56"
              "2026-05-29T21:50:56"
              "2026-05-29 21:50:56+00:00"
              "2026-05-29"
    Returns:  datetime(2026, 5, 29, 0, 0, 0)
    """
    date_part = dt_str.strip()[:10]  # always "YYYY-MM-DD"
    return datetime.strptime(date_part, "%Y-%m-%d")


def _fmt(dt: datetime) -> str:
    """Format to the midnight-PST string Google Ads expects."""
    return f"{dt.strftime('%Y-%m-%d')} 00:00:00-08:00"


async def run_with_retry(
    *,
    client: GoogleAdsClient,
    customer_id: str,
    conversion_action: str,
    caller_id: str,
    call_start_datetime: str,
    search_window_days: int,
) -> RetryResult:
    base_start = _parse_to_date(call_start_datetime)
    all_attempts: list[dict[str, Any]] = []
    attempt = 0
    last_response: dict[str, Any] = {}

    for start_offset in range(search_window_days + 1):
        adjusted_start = base_start - timedelta(days=start_offset)

        for conv_offset in range(16):  # 0 through +15 days
            adjusted_conv = adjusted_start + timedelta(days=conv_offset)
            attempt += 1

            start_str = _fmt(adjusted_start)
            conv_str = _fmt(adjusted_conv)

            response = await client.upload_call_conversion(
                customer_id=customer_id,
                conversion_action=conversion_action,
                caller_id=caller_id,
                call_start_datetime=start_str,
                conversion_datetime=conv_str,
            )
            last_response = response

            error_codes = _extract_error_codes(response)
            success = _is_success(response)
            result_label = "success" if success else (next(iter(error_codes), "unknown"))

            attempt_record = {
                "attempt": attempt,
                "caller_id": caller_id,
                "call_start_datetime": start_str,
                "conversion_datetime": conv_str,
                "result": result_label,
                "error_codes": sorted(error_codes),
            }
            all_attempts.append(attempt_record)

            log.info("conversion attempt", extra=attempt_record)

            if success:
                return RetryResult(
                    success=True,
                    attempts=attempt,
                    final_response=response,
                    successful_combination={
                        "call_start_datetime": start_str,
                        "conversion_datetime": conv_str,
                    },
                    all_attempts=all_attempts,
                )

            terminal = error_codes & _TERMINAL_ERRORS
            if terminal:
                terminal_code = next(iter(terminal))
                log.warning(
                    "terminal error — stopping all retries",
                    extra={"error_code": terminal_code, "attempt": attempt},
                )
                return RetryResult(
                    success=False,
                    attempts=attempt,
                    final_response=response,
                    terminal_error=terminal_code,
                    all_attempts=all_attempts,
                )

    log.info(
        "retry exhausted — no successful combination found",
        extra={"total_attempts": attempt, "caller_id": caller_id},
    )
    return RetryResult(
        success=False,
        attempts=attempt,
        final_response=last_response,
        all_attempts=all_attempts,
    )
