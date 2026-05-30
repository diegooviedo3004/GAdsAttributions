from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.webhooks._handler import handle_conversion
from app.integrations.google_ads import GoogleAdsClient
from app.core.config import get_settings

router = APIRouter()


class ClickConversionPayload(BaseModel):
    gclid: str
    conversion_datetime: str
    customer_id: str | None = None
    conversion_action: str | None = None


@router.post("/webhooks/callrail-attribution", summary="Upload a GCLID click conversion to Google Ads")
async def callrail_attribution(payload: ClickConversionPayload) -> JSONResponse:
    cfg = get_settings()
    client = GoogleAdsClient()

    async def send(p: ClickConversionPayload) -> dict:
        return await client.upload_click_conversion(
            customer_id=p.customer_id or cfg.google_ads_customer_id,
            conversion_action=p.conversion_action or cfg.google_ads_conversion_action_callrail,
            gclid=p.gclid,
            conversion_datetime=p.conversion_datetime,
        )

    return await handle_conversion(
        workflow_name="callrail_attribution",
        payload=payload,
        send=send,
    )
