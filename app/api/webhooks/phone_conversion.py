from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.webhooks._handler import handle_conversion
from app.integrations.google_ads import GoogleAdsClient
from app.core.config import get_settings

router = APIRouter()


class CallConversionPayload(BaseModel):
    caller_id: str
    call_start_datetime: str
    conversion_datetime: str
    customer_id: str | None = None
    conversion_action: str | None = None


@router.post("/webhooks/phone-conversion", summary="Upload a call conversion to Google Ads")
async def phone_conversion(payload: CallConversionPayload) -> JSONResponse:
    cfg = get_settings()
    client = GoogleAdsClient()

    async def send(p: CallConversionPayload) -> dict:
        return await client.upload_call_conversion(
            customer_id=p.customer_id or cfg.google_ads_mcc_id,
            conversion_action=p.conversion_action or cfg.google_ads_conversion_action_call,
            caller_id=p.caller_id,
            call_start_datetime=p.call_start_datetime,
            conversion_datetime=p.conversion_datetime,
        )

    return await handle_conversion(
        workflow_name="phone_conversion",
        payload=payload,
        send=send,
    )
