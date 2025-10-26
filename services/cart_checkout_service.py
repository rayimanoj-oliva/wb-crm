# services/cart_checkout_service.py
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal

from models.models import Order, OrderItem, Customer
from services.order_service import get_order
from services.payment_service import create_payment_link
from schemas.payment_schema import PaymentCreate
from utils.whatsapp import send_message_to_waid
from utils.razorpay_utils import create_razorpay_payment_link


class CartCheckoutService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_order_total(self, order_id: str) -> Dict[str, Any]:
        """Calculate total amount for an order including items and any discounts"""
        try:
            order = get_order(self.db, order_id)
            if not order:
                return {"error": "Order not found", "total": 0.0}
            
            # Group items by product_retailer_id to handle duplicates
            items_dict = {}
            total_amount = 0.0
            
            # Process all items and group by product_retailer_id
            for item in order.items:
                if not item.product_retailer_id:
                    continue
                    
                product_id = item.product_retailer_id
                
                if product_id in items_dict:
                    # Add to existing item
                    items_dict[product_id]["quantity"] += item.quantity
                    items_dict[product_id]["total_price"] += float(item.item_price) * item.quantity
                else:
                    # Create new item entry
                    item_total = float(item.item_price) * item.quantity
                    items_dict[product_id] = {
                        "product_retailer_id": product_id,
                        "quantity": item.quantity,
                        "unit_price": float(item.item_price),
                        "total_price": item_total,
                        "currency": item.currency or "INR"
                    }
                
                total_amount += float(item.item_price) * item.quantity
            
            # Convert grouped items to list
            items_summary = list(items_dict.values())
            
            # Apply any discounts (you can extend this logic)
            discount_amount = 0.0
            if hasattr(order, 'discount_percentage') and order.discount_percentage:
                discount_amount = total_amount * (order.discount_percentage / 100)
            
            final_amount = total_amount - discount_amount
            
            print(f"[CART_CHECKOUT] Order {order_id} calculation:")
            print(f"  - Total items in DB: {len(order.items)}")
            print(f"  - Unique products: {len(items_summary)}")
            print(f"  - Total amount: ₹{final_amount:.2f}")
            
            return {
                "order_id": str(order.id),
                "subtotal": total_amount,
                "discount_amount": discount_amount,
                "total_amount": final_amount,
                "currency": "INR",
                "items_count": len(items_summary),
                "items_summary": items_summary
            }
            
        except Exception as e:
            print(f"[CART_CHECKOUT] Error calculating order total: {e}")
            return {"error": str(e), "total": 0.0}

    def cleanup_duplicate_items(self, order_id: str) -> Dict[str, Any]:
        """Clean up duplicate items in an order by merging them"""
        try:
            order = get_order(self.db, order_id)
            if not order:
                return {"error": "Order not found", "success": False}
            
            # Group items by product_retailer_id
            items_dict = {}
            items_to_delete = []
            
            for item in order.items:
                if not item.product_retailer_id:
                    continue
                    
                product_id = item.product_retailer_id
                
                if product_id in items_dict:
                    # Merge with existing item
                    existing_item = items_dict[product_id]
                    existing_item.quantity += item.quantity
                    existing_item.total_price = float(existing_item.item_price) * existing_item.quantity
                    
                    # Mark this item for deletion
                    items_to_delete.append(item)
                else:
                    # Keep this item
                    items_dict[product_id] = item
            
            # Delete duplicate items
            for item in items_to_delete:
                self.db.delete(item)
            
            if items_to_delete:
                self.db.commit()
                print(f"[CART_CHECKOUT] Cleaned up {len(items_to_delete)} duplicate items from order {order_id}")
                return {
                    "success": True,
                    "duplicates_removed": len(items_to_delete),
                    "remaining_items": len(items_dict)
                }
            else:
                print(f"[CART_CHECKOUT] No duplicates found in order {order_id}")
                return {
                    "success": True,
                    "duplicates_removed": 0,
                    "remaining_items": len(items_dict)
                }
                
        except Exception as e:
            print(f"[CART_CHECKOUT] Error cleaning up duplicates: {e}")
            self.db.rollback()
            return {"error": str(e), "success": False}

    async def generate_payment_link_for_order(
        self, 
        order_id: str, 
        customer_wa_id: str,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate Razorpay payment link for an order and send to customer"""
        try:
            # First, clean up any duplicate items in the order
            cleanup_result = self.cleanup_duplicate_items(order_id)
            if cleanup_result.get("success") and cleanup_result.get("duplicates_removed", 0) > 0:
                print(f"[CART_CHECKOUT] Cleaned up {cleanup_result['duplicates_removed']} duplicate items before payment generation")
            
            # Calculate order total (now with cleaned up items)
            order_calculation = self.calculate_order_total(order_id)
            if "error" in order_calculation:
                return order_calculation
            
            total_amount = order_calculation["total_amount"]
            currency = order_calculation["currency"]
            
            # Create payment link using Razorpay
            payment_data = PaymentCreate(
                order_id=order_id,
                amount=total_amount,
                currency=currency,
                payment_method="upi",
                customer_email=customer_email,
                customer_phone=customer_phone,
                customer_name=customer_name
            )
            
            # Create payment record and link
            payment = create_payment_link(self.db, payment_data, mock=False)
            
            # Send payment link to customer via WhatsApp
            await self._send_payment_message_to_customer(
                customer_wa_id, 
                payment.razorpay_short_url, 
                order_calculation,
                customer_name
            )
            
            return {
                "success": True,
                "payment_id": payment.razorpay_id,
                "payment_url": payment.razorpay_short_url,
                "order_total": total_amount,
                "currency": currency,
                "items_count": order_calculation["items_count"],
                "duplicates_cleaned": cleanup_result.get("duplicates_removed", 0)
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"[CART_CHECKOUT] Payment generation failed: {error_msg}")
            
            # Provide more specific error messages based on error type
            if "configuration" in error_msg.lower():
                return {"error": "Payment system configuration error. Please contact support.", "success": False, "error_type": "configuration"}
            elif "validation" in error_msg.lower():
                return {"error": "Invalid payment data. Please check your order details.", "success": False, "error_type": "validation"}
            elif "api_error" in error_msg.lower():
                return {"error": "Payment service temporarily unavailable. Please try again in a few minutes.", "success": False, "error_type": "api_error"}
            elif "timeout" in error_msg.lower():
                return {"error": "Payment service timeout. Please try again.", "success": False, "error_type": "timeout"}
            elif "connection" in error_msg.lower():
                return {"error": "Unable to connect to payment service. Please check your internet connection and try again.", "success": False, "error_type": "connection"}
            else:
                return {"error": f"Payment generation failed: {error_msg}", "success": False, "error_type": "unknown"}

    async def _send_payment_message_to_customer(
        self, 
        wa_id: str, 
        payment_url: str, 
        order_summary: Dict[str, Any],
        customer_name: Optional[str] = None
    ) -> None:
        """Send cart display with payment link to customer via WhatsApp"""
        try:
            # Send cart display with product list format
            await self._send_cart_display_with_payment(
                wa_id, 
                payment_url, 
                order_summary,
                customer_name
            )
            
        except Exception as e:
            print(f"Error sending cart display: {e}")
            # Fallback to simple message
            fallback_message = f"💳 Payment required: {payment_url}"
            await send_message_to_waid(wa_id, fallback_message, self.db)

    async def _send_cart_display_with_payment(
        self, 
        wa_id: str, 
        payment_url: str, 
        order_summary: Dict[str, Any],
        customer_name: Optional[str] = None
    ) -> None:
        """Send detailed cart items with payment link"""
        try:
            # Create detailed cart items text
            items_text = ""
            for item in order_summary.get("items_summary", []):
                product_name = item.get("product_retailer_id", "Unknown Product")
                quantity = item.get("quantity", 1)
                unit_price = item.get("unit_price", 0)
                total_price = item.get("total_price", 0)
                
                items_text += f"• {product_name}\n"
                items_text += f"  Quantity: {quantity} x ₹{unit_price:.2f} = ₹{total_price:.2f}\n\n"

            # Create cart summary message
            cart_message = f"""🛍️ **Your Cart Summary**

Hello {customer_name or 'Customer'}!

📦 **Your Items:**
{items_text}💰 **Order Summary:**
Subtotal: ₹{order_summary.get('subtotal', 0):.2f}
{f"Discount: -₹{order_summary.get('discount_amount', 0):.2f}" if order_summary.get('discount_amount', 0) > 0 else ""}
**Total: ₹{order_summary.get('total_amount', 0):.2f}**

💳 **Complete Your Payment:**
{payment_url}

**Payment Options Available:**
• UPI (PhonePe, Google Pay, Paytm)
• Credit/Debit Cards
• Net Banking
• Digital Wallets

Click the payment link above to redirect to Razorpay's secure payment page. Thank you! 🙏"""

            # Send the cart summary with payment link
            await send_message_to_waid(wa_id, cart_message, self.db)
            
            # Also send an interactive message for better UX
            await self._send_interactive_payment_buttons(wa_id, payment_url, order_summary)
                
        except Exception as e:
            print(f"Error sending cart display: {e}")
            await send_message_to_waid(wa_id, f"💳 Payment required: {payment_url}", self.db)

    async def _send_interactive_payment_buttons(
        self, 
        wa_id: str, 
        payment_url: str, 
        order_summary: Dict[str, Any]
    ) -> None:
        """Send interactive buttons for payment actions"""
        try:
            from services.whatsapp_service import get_latest_token
            from config.constants import get_messages_url
            import os
            import requests
            
            token_entry = get_latest_token(self.db)
            if not token_entry or not token_entry.token:
                return

            access_token = token_entry.token
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

            # Create interactive message with payment buttons
            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "header": {
                        "type": "text",
                        "text": "💳 Payment Options"
                    },
                    "body": {
                        "text": f"Total Amount: ₹{order_summary.get('total_amount', 0):.2f}\n\nChoose an option below:"
                    },
                    "footer": {
                        "text": "Secure payment powered by Razorpay"
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "redirect_to_payment",
                                    "title": "💳 Pay Now"
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "view_payment_link",
                                    "title": "🔗 View Payment Link"
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "order_details",
                                    "title": "📋 Order Details"
                                }
                            }
                        ]
                    }
                }
            }

            response = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
            
            if response.status_code == 200:
                print(f"[interactive_buttons] Payment buttons sent successfully")
            else:
                print(f"[interactive_buttons] Failed to send buttons: {response.text}")
                
        except Exception as e:
            print(f"Error sending interactive buttons: {e}")

    async def _send_payment_url_separately(
        self, 
        wa_id: str, 
        payment_url: str, 
        order_summary: Dict[str, Any]
    ) -> None:
        """Send payment URL as a separate message"""
        try:
            payment_message = f"""🔗 **Payment Link:**

{payment_url}

**Payment Details:**
• Amount: ₹{order_summary.get('total_amount', 0):.2f}
• Items: {order_summary.get('items_count', 0)}
• Valid for: 30 minutes

Click the link above to complete your payment securely. Thank you! 🙏"""
            
            await send_message_to_waid(wa_id, payment_message, self.db)
            
        except Exception as e:
            print(f"Error sending payment URL: {e}")
            await send_message_to_waid(wa_id, f"💳 Payment link: {payment_url}", self.db)

    async def _send_payment_link_message(
        self, 
        wa_id: str, 
        payment_url: str, 
        order_summary: Dict[str, Any]
    ) -> None:
        """Send payment link message with order details"""
        try:
            from services.whatsapp_service import get_latest_token
            from config.constants import get_messages_url
            import os
            import requests
            
            token_entry = get_latest_token(self.db)
            if not token_entry or not token_entry.token:
                await send_message_to_waid(wa_id, f"💳 Payment link: {payment_url}", self.db)
                return

            access_token = token_entry.token
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

            # Create payment message with button
            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "header": {
                        "type": "text",
                        "text": "💳 Complete Payment"
                    },
                    "body": {
                        "text": f"Order Total: {order_summary.get('formatted_total', 'N/A')}\n\nClick below to complete your payment securely.\n\nThis link is valid for 30 minutes."
                    },
                    "footer": {
                        "text": "Powered by Razorpay"
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "view_payment_link",
                                    "title": "🔗 View Payment Link"
                                }
                            },
                            {
                                "type": "reply", 
                                "reply": {
                                    "id": "order_details",
                                    "title": "📋 Order Details"
                                }
                            }
                        ]
                    }
                }
            }

            response = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
            
            if response.status_code == 200:
                print(f"[payment_link] Payment message sent successfully")
                
                # Send the actual payment URL as a separate message
                payment_message = f"""🔗 **Payment Link:**

{payment_url}

**Order Summary:**
• Items: {order_summary.get('items_count', 0)}
• Total: {order_summary.get('formatted_total', 'N/A')}
• Valid for: 30 minutes

Click the link above to complete your payment securely. Thank you! 🙏"""
                
                await send_message_to_waid(wa_id, payment_message, self.db)
            else:
                print(f"[payment_link] Failed to send payment message: {response.text}")
                await send_message_to_waid(wa_id, f"💳 Payment link: {payment_url}", self.db)
                
        except Exception as e:
            print(f"Error sending payment link: {e}")
            await send_message_to_waid(wa_id, f"💳 Payment link: {payment_url}", self.db)

    def get_order_summary_for_payment(self, order_id: str) -> Dict[str, Any]:
        """Get formatted order summary for payment display"""
        calculation = self.calculate_order_total(order_id)
        if "error" in calculation:
            return calculation
        
        return {
            "order_id": calculation["order_id"],
            "total_amount": calculation["total_amount"],
            "currency": calculation["currency"],
            "items_count": calculation["items_count"],
            "formatted_total": f"₹{calculation['total_amount']:.2f}",
            "items": calculation["items_summary"]
        }
