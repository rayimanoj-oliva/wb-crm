# services/dummy_payment_service.py
import os
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from uuid import uuid4

from models.models import Payment, Order
from schemas.payment_schema import PaymentCreate
from utils.whatsapp import send_message_to_waid


class DummyPaymentService:
    def __init__(self, db: Session):
        self.db = db

    async def create_dummy_payment_link(
        self,
        wa_id: str,
        order_id: Optional[str] = None,
        amount: float = 1.0,
        customer_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a dummy payment link for testing with ₹1 amount"""
        try:
            # Generate dummy payment data
            dummy_payment_id = f"dummy_rzp_{uuid4().hex[:12]}"
            dummy_payment_url = f"https://rzp.io/l/dummy_{uuid4().hex[:8]}"
            
            # Create payment record in database
            payment_data = PaymentCreate(
                order_id=order_id,
                amount=amount,
                currency="INR",
                payment_method="upi",
                customer_name=customer_name,
                customer_phone=wa_id
            )
            
            payment = Payment(
                order_id=payment_data.order_id,
                amount=payment_data.amount,
                currency=payment_data.currency,
                razorpay_id=dummy_payment_id,
                razorpay_short_url=dummy_payment_url,
                status="created",
                created_at=datetime.utcnow(),
            )
            
            self.db.add(payment)
            self.db.commit()
            self.db.refresh(payment)
            
            # Send dummy payment message
            await self._send_dummy_payment_message(wa_id, dummy_payment_url, amount, customer_name)
            
            return {
                "success": True,
                "payment_id": dummy_payment_id,
                "payment_url": dummy_payment_url,
                "amount": amount,
                "currency": "INR",
                "is_dummy": True
            }
            
        except Exception as e:
            return {"error": str(e), "success": False}

    async def _send_dummy_payment_message(
        self,
        wa_id: str,
        payment_url: str,
        amount: float,
        customer_name: Optional[str] = None
    ) -> None:
        """Send dummy payment message to customer"""
        try:
            from services.whatsapp_service import get_latest_token
            from config.constants import get_messages_url
            import requests
            
            token_entry = get_latest_token(self.db)
            if not token_entry or not token_entry.token:
                await send_message_to_waid(wa_id, f"💳 Dummy Payment Link (₹{amount}): {payment_url}", self.db)
                return

            access_token = token_entry.token
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

            # Create dummy payment message with button
            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "header": {
                        "type": "text",
                        "text": "🧪 Test Payment (Dummy)"
                    },
                    "body": {
                        "text": f"Hello {customer_name or 'Customer'}!\n\nThis is a TEST payment link for ₹{amount}.\n\nClick below to test the payment flow.\n\n⚠️ This is a dummy link for testing purposes."
                    },
                    "footer": {
                        "text": "Test Mode - No real money will be charged"
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "test_payment_link",
                                    "title": f"🧪 Test Pay ₹{amount}"
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "dummy_payment_info",
                                    "title": "ℹ️ Test Info"
                                }
                            }
                        ]
                    }
                }
            }

            response = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
            
            if response.status_code == 200:
                print(f"[dummy_payment] Test payment message sent successfully")
                
                # Send the actual dummy payment URL
                dummy_message = f"""🧪 **TEST PAYMENT LINK**

{payment_url}

**Test Details:**
• Amount: ₹{amount}
• Currency: INR
• Type: Dummy/Test Payment
• Status: No real money charged

⚠️ **This is for testing only!**

Click the link above to test the payment flow. This will not charge any real money.

Thank you for testing! 🚀"""
                
                await send_message_to_waid(wa_id, dummy_message, self.db)
            else:
                print(f"[dummy_payment] Failed to send test payment message: {response.text}")
                await send_message_to_waid(wa_id, f"🧪 Test Payment Link (₹{amount}): {payment_url}", self.db)
                
        except Exception as e:
            print(f"Error sending dummy payment message: {e}")
            await send_message_to_waid(wa_id, f"🧪 Test Payment Link (₹{amount}): {payment_url}", self.db)

    async def handle_dummy_payment_response(
        self,
        wa_id: str,
        reply_id: str,
        customer: Any
    ) -> Dict[str, Any]:
        """Handle responses from dummy payment buttons"""
        try:
            if reply_id == "test_payment_link":
                await send_message_to_waid(
                    wa_id, 
                    "🧪 Test payment link sent above! Click it to test the payment flow.", 
                    self.db
                )
                return {"status": "test_payment_info_sent"}
            
            elif reply_id == "dummy_payment_info":
                info_message = """ℹ️ **Test Payment Information**

This is a dummy payment system for testing:

✅ **What it does:**
• Generates test payment links
• Simulates payment flow
• No real money charged
• Tests cart checkout process

✅ **How to use:**
• Click the test payment link
• Complete the test payment flow
• Verify order processing works

✅ **Benefits:**
• Safe testing environment
• No financial risk
• Full flow testing
• Development friendly

Happy testing! 🚀"""
                
                await send_message_to_waid(wa_id, info_message, self.db)
                return {"status": "dummy_info_sent"}
            
            return {"status": "unknown_action", "action_id": reply_id}
            
        except Exception as e:
            return {"status": "failed", "error": str(e)}
