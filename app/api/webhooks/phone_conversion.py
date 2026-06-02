from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from app.api.webhooks._handler import handle_conversion
from app.integrations.google_ads import GoogleAdsClient
from app.services.call_conversion_retry import run_with_retry
from app.core.config import get_settings

router = APIRouter()


class CallConversionPayload(BaseModel):
    caller_id: str
    call_start_datetime: str
    # Required when search_window_days == 0; optional when retry strategy is active
    conversion_datetime: str | None = None
    customer_id: str | None = None
    conversion_action: str | None = None
    search_window_days: int = Field(
        default=0,
        ge=0,
        le=90,
        description=(
            "When > 0, activates the retry strategy. The endpoint will try up to "
            "(search_window_days + 1) × 16 date combinations before giving up. "
            "conversion_datetime is ignored and derived automatically."
        ),
    )

    @model_validator(mode="after")
    def require_conversion_datetime_without_retry(self) -> "CallConversionPayload":
        if self.search_window_days == 0 and self.conversion_datetime is None:
            raise ValueError("conversion_datetime is required when search_window_days is 0")
        return self


@router.post("/webhooks/phone-conversion", summary="Upload a call conversion to Google Ads")
async def phone_conversion(payload: CallConversionPayload) -> JSONResponse:
    cfg = get_settings()
    client = GoogleAdsClient()
    customer_id = payload.customer_id or cfg.google_ads_mcc_id
    conversion_action = payload.conversion_action or cfg.google_ads_conversion_action_call

    if payload.search_window_days > 0:
        async def send(p: CallConversionPayload) -> dict:
            result = await run_with_retry(
                client=client,
                customer_id=customer_id,
                conversion_action=conversion_action,
                caller_id=p.caller_id,
                call_start_datetime=p.call_start_datetime,
                search_window_days=p.search_window_days,
            )
            return {
                "success": result.success,
                "attempts": result.attempts,
                "successful_combination": result.successful_combination,
                "terminal_error": result.terminal_error,
                **result.final_response,
            }
    else:
        async def send(p: CallConversionPayload) -> dict:
            return await client.upload_call_conversion(
                customer_id=customer_id,
                conversion_action=conversion_action,
                caller_id=p.caller_id,
                call_start_datetime=p.call_start_datetime,
                conversion_datetime=p.conversion_datetime,
            )

    return await handle_conversion(
        workflow_name="phone_conversion",
        payload=payload,
        send=send,
    )
