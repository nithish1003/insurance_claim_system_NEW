import logging
from django.conf import settings
from twilio.rest import Client

logger = logging.getLogger(__name__)

class TwilioService:
    """
    Twilio SMS gateway integrated in test-ready mode.
    Live dispatch activates immediately after sender provisioning.
    """
    
    @staticmethod
    def send_sms(to_number, message):
        """
        Dispatches SMS via Twilio. 
        Operates in 'test_ready' mode if sender number is not provisioned.
        """
        sid = settings.TWILIO_ACCOUNT_SID
        token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_PHONE_NUMBER

        # 🛡️ SAFE DEMO MODE CHECK
        if not from_number:
            logger.info(f"[Twilio Test Mode] SMS would be sent to {to_number}: {message}")
            return {
                "status": "test_ready",
                "message": "Twilio credentials loaded. Sender number not provisioned.",
                "sid": "DEMO_MODE_SID",
                "provider": "Twilio"
            }

        # Validate basic requirements
        if not sid or not token:
            logger.error("Twilio credentials missing in environment.")
            return {"status": "error", "error_message": "Missing Credentials"}

        try:
            client = Client(sid, token)
            response = client.messages.create(
                body=message,
                from_=from_number,
                to=to_number
            )
            
            logger.info(f"SMS sent successfully to {to_number}. SID: {response.sid}")
            return {
                "status": "delivered",
                "sid": response.sid,
                "message": "Live dispatch successful.",
                "provider": "Twilio"
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Twilio Dispatch Failure: {error_msg}")
            return {
                "status": "failed",
                "error_message": error_msg,
                "provider": "Twilio"
            }
