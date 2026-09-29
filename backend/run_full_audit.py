import os
import sys
import asyncio

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.audit_historical_telegram import (
    get_telegram_client, verify_code, scan_and_audit_channel,
    ONLINE_CHAT_ID, KKC_CHAT_ID
)
from backend.database import get_settings

async def execute_full_audit(otp_code: str, password: str = ""):
    settings = get_settings()
    phone_hash = settings.get("PENDING_PHONE_CODE_HASH", "")
    phone = settings.get("PENDING_PHONE_NUMBER", "+66830789329")

    client = get_telegram_client()
    print(f"Verifying OTP code: {otp_code} for phone {phone}...")
    await verify_code(client, phone, otp_code, phone_hash, password)
    print("Telethon authorized successfully! Permanent StringSession saved.")

    # 1. Audit Online Group across 9 months: 2026-01-01 to 2026-09-22
    print("\n" + "="*70)
    print("STEP 1: AUDITING ONLINE GROUP (2026-01-01 to 2026-09-22)")
    print("="*70)
    online_res = await scan_and_audit_channel(
        client=client,
        chat_id=ONLINE_CHAT_ID,
        channel_name="online",
        since_date="2026-01-01"
    )

    # 2. Audit KKC Storefront Group across 2 months: 2026-08-01 to 2026-09-22
    print("\n" + "="*70)
    print("STEP 2: AUDITING KKC STOREFRONT GROUP (2026-08-01 to 2026-09-22)")
    print("="*70)
    kkc_res = await scan_and_audit_channel(
        client=client,
        chat_id=KKC_CHAT_ID,
        channel_name="kkc",
        since_date="2026-08-01"
    )

    print("\n" + "="*70)
    print("ALL AUDITS COMPLETED SUCCESSFULLY!")
    print("="*70)
    return online_res, kkc_res

if __name__ == "__main__":
    if len(sys.argv) > 1:
        code = sys.argv[1]
        pwd = sys.argv[2] if len(sys.argv) > 2 else ""
        asyncio.run(execute_full_audit(code, pwd))
    else:
        print("Usage: python run_full_audit.py <OTP_CODE> [2FA_PASSWORD]")
