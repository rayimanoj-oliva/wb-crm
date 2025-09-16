"""
Notification service for sending payment links via email and SMS
"""

import requests
import json
from typing import Optional, Dict, Any
from utils.email_utils import get_access_token, SENDER_EMAIL
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# SMS Configuration (you can add your SMS provider credentials here)
SMS_API_KEY = os.getenv("SMS_API_KEY", "")
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "OLIVA")


def send_payment_link_email(
    recipient_email: str, 
    payment_link: str, 
    amount: float, 
    currency: str = "INR",
    customer_name: Optional[str] = None,
    transaction_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send payment link via email using Microsoft Graph API
    
    Args:
        recipient_email: Customer's email address
        payment_link: Razorpay payment link
        amount: Payment amount
        currency: Currency code
        customer_name: Customer's name
        transaction_id: Transaction ID
        
    Returns:
        Dict with success status and message
    """
    try:
        token = get_access_token()
        url = f'https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail'
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Create email content
        subject = f"Payment Link - ₹{amount} - Oliva Clinic"
        customer_greeting = f"Hello {customer_name}," if customer_name else "Hello,"
        
        email_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Payment Request - Oliva Clinic</h2>
            
            <p>{customer_greeting}</p>
            
            <p>You have a pending payment of <strong>₹{amount} {currency}</strong> for your order.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #28a745; margin-top: 0;">Complete Your Payment</h3>
                <p>Click the button below to complete your payment securely:</p>
                <a href="{payment_link}" 
                   style="background-color: #28a745; color: white; padding: 12px 24px; 
                          text-decoration: none; border-radius: 5px; display: inline-block; 
                          font-weight: bold;">
                    Pay Now - ₹{amount}
                </a>
            </div>
            
            <p><strong>Transaction ID:</strong> {transaction_id or 'N/A'}</p>
            
            <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h4 style="margin-top: 0; color: #495057;">Payment Details:</h4>
                <ul style="margin: 0;">
                    <li>Amount: ₹{amount} {currency}</li>
                    <li>Payment Gateway: Razorpay (Secure)</li>
                    <li>Payment Methods: UPI, Cards, Net Banking, Wallets</li>
                </ul>
            </div>
            
            <p style="color: #6c757d; font-size: 14px;">
                This payment link is secure and powered by Razorpay. 
                If you have any questions, please contact our support team.
            </p>
            
            <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
            <p style="color: #6c757d; font-size: 12px; text-align: center;">
                © 2024 Oliva Clinic. All rights reserved.
            </p>
        </div>
        """
        
        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": email_content
                },
                "toRecipients": [
                    {"emailAddress": {"address": recipient_email}}
                ]
            },
            "saveToSentItems": "true"
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(email_data))
        
        if response.status_code == 202:
            return {
                "success": True,
                "message": "Payment link sent successfully via email",
                "method": "email",
                "recipient": recipient_email
            }
        else:
            return {
                "success": False,
                "message": f"Failed to send email: {response.status_code}",
                "error": response.text,
                "method": "email"
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"Email sending failed: {str(e)}",
            "error": str(e),
            "method": "email"
        }


def send_payment_link_sms(
    phone_number: str,
    payment_link: str,
    amount: float,
    currency: str = "INR",
    customer_name: Optional[str] = None,
    transaction_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send payment link via SMS
    
    Args:
        phone_number: Customer's phone number
        payment_link: Razorpay payment link
        amount: Payment amount
        currency: Currency code
        customer_name: Customer's name
        transaction_id: Transaction ID
        
    Returns:
        Dict with success status and message
    """
    try:
        # Clean phone number (remove spaces, add country code if needed)
        clean_phone = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not clean_phone.startswith("+91") and len(clean_phone) == 10:
            clean_phone = "+91" + clean_phone
        
        # Create SMS message
        customer_greeting = f"Hi {customer_name}," if customer_name else "Hi,"
        message = f"""{customer_greeting} Complete your payment of ₹{amount} for Oliva Clinic. 
        
Payment Link: {payment_link}

Transaction ID: {transaction_id or 'N/A'}

Pay securely via UPI, Cards, Net Banking or Wallets.

- Oliva Clinic Team"""
        
        # For now, we'll use a mock SMS service
        # You can integrate with actual SMS providers like:
        # - Twilio
        # - AWS SNS
        # - TextLocal
        # - MSG91
        
        print(f"SMS would be sent to {clean_phone}: {message[:100]}...")
        
        # Mock SMS sending (replace with actual SMS API call)
        return {
            "success": True,
            "message": "Payment link sent successfully via SMS (mock)",
            "method": "sms",
            "recipient": clean_phone,
            "note": "SMS service not configured - this is a mock response"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"SMS sending failed: {str(e)}",
            "error": str(e),
            "method": "sms"
        }


def send_payment_notifications(
    payment_link: str,
    amount: float,
    currency: str = "INR",
    customer_email: Optional[str] = None,
    customer_phone: Optional[str] = None,
    customer_name: Optional[str] = None,
    transaction_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send payment link via both email and SMS if contact details are provided
    
    Args:
        payment_link: Razorpay payment link
        amount: Payment amount
        currency: Currency code
        customer_email: Customer's email address
        customer_phone: Customer's phone number
        customer_name: Customer's name
        transaction_id: Transaction ID
        
    Returns:
        Dict with results from both email and SMS attempts
    """
    results = {
        "email_result": None,
        "sms_result": None,
        "overall_success": False
    }
    
    # Send email if email is provided
    if customer_email:
        results["email_result"] = send_payment_link_email(
            recipient_email=customer_email,
            payment_link=payment_link,
            amount=amount,
            currency=currency,
            customer_name=customer_name,
            transaction_id=transaction_id
        )
    
    # Send SMS if phone is provided
    if customer_phone:
        results["sms_result"] = send_payment_link_sms(
            phone_number=customer_phone,
            payment_link=payment_link,
            amount=amount,
            currency=currency,
            customer_name=customer_name,
            transaction_id=transaction_id
        )
    
    # Determine overall success
    email_success = results["email_result"]["success"] if results["email_result"] else False
    sms_success = results["sms_result"]["success"] if results["sms_result"] else False
    
    results["overall_success"] = email_success or sms_success
    
    return results
