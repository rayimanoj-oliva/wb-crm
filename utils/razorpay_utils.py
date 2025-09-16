import hmac
import hashlib
import os
import requests
import base64
from typing import Dict, Any

# Razorpay Configuration
RAZORPAY_KEY_ID = "rzp_live_uMx1leMLvqdOxv"
RAZORPAY_SECRET = "0TbD6fORvP9sBVte5IJxN6g0"
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"

def validate_razorpay_signature(data: bytes, received_signature: str, secret: str) -> bool:
    """
    Validate Razorpay webhook signature

    Args:
        data: Raw request body as bytes
        received_signature: Signature from X-Razorpay-Signature header
        secret: Webhook secret from Razorpay dashboard

    Returns:
        bool: True if signature is valid, False otherwise
    """
    try:
        generated_signature = hmac.new(
            bytes(secret, 'utf-8'),
            msg=data,
            digestmod=hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(received_signature, generated_signature)
    except Exception as e:
        print(f"Error validating Razorpay signature: {e}")
        return False


def generate_razorpay_signature(data: str, secret: str) -> str:
    """
    Generate Razorpay signature for testing purposes

    Args:
        data: Data to sign
        secret: Secret key

    Returns:
        str: Generated signature
    """
    try:
        signature = hmac.new(
            bytes(secret, 'utf-8'),
            msg=bytes(data, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        return signature
    except Exception as e:
        print(f"Error generating Razorpay signature: {e}")
        return ""


def get_razorpay_auth_header() -> str:
    """
    Generate Razorpay Basic Auth header
    
    Returns:
        str: Base64 encoded auth header
    """
    credentials = f"{RAZORPAY_KEY_ID}:{RAZORPAY_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded_credentials}"


def create_razorpay_payment_link(amount: float, currency: str = "INR", description: str = "Payment") -> Dict[str, Any]:
    """
    Create a Razorpay payment link directly using Razorpay API
    
    Args:
        amount: Payment amount in rupees
        currency: Currency code (default: INR)
        description: Payment description
        
    Returns:
        Dict containing payment link details
    """
    try:
        # Convert amount to paise (smallest currency unit)
        amount_paise = int(amount * 100)
        
        url = f"{RAZORPAY_BASE_URL}/payment_links"
        headers = {
            "Authorization": get_razorpay_auth_header(),
            "Content-Type": "application/json"
        }
        
        data = {
            "amount": amount_paise,
            "currency": currency,
            "description": description,
            "reminder_enable": True,
            "notify": {
                "sms": True,
                "email": True
            }
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"Error creating Razorpay payment link: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"Unexpected error creating payment link: {e}")
        return {"error": str(e)}


def get_razorpay_payment_details(payment_id: str) -> Dict[str, Any]:
    """
    Get payment details from Razorpay
    
    Args:
        payment_id: Razorpay payment ID
        
    Returns:
        Dict containing payment details
    """
    try:
        url = f"{RAZORPAY_BASE_URL}/payments/{payment_id}"
        headers = {
            "Authorization": get_razorpay_auth_header(),
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Razorpay payment details: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"Unexpected error fetching payment details: {e}")
        return {"error": str(e)}


def capture_razorpay_payment(payment_id: str, amount: float, currency: str = "INR") -> Dict[str, Any]:
    """
    Capture a Razorpay payment
    
    Args:
        payment_id: Razorpay payment ID
        amount: Amount to capture in rupees
        currency: Currency code (default: INR)
        
    Returns:
        Dict containing capture response
    """
    try:
        # Convert amount to paise
        amount_paise = int(amount * 100)
        
        url = f"{RAZORPAY_BASE_URL}/payments/{payment_id}/capture"
        headers = {
            "Authorization": get_razorpay_auth_header(),
            "Content-Type": "application/json"
        }
        
        data = {
            "amount": amount_paise,
            "currency": currency
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"Error capturing Razorpay payment: {e}")
        return {"error": str(e)}
    except Exception as e:
        print(f"Unexpected error capturing payment: {e}")
        return {"error": str(e)}