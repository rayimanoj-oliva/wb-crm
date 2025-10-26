"""
Razorpay Client - Direct API integration with Razorpay
Handles all Razorpay API calls, authentication, and error handling
"""

import hmac
import hashlib
import os
import requests
import base64
from typing import Dict, Any, Optional
from datetime import datetime


class RazorpayError(Exception):
    """Base exception for Razorpay-related errors"""
    pass


class ConfigurationError(RazorpayError):
    """Raised when Razorpay configuration is invalid"""
    pass


class RazorpayClient:
    """Razorpay API client for payment operations"""
    
    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID", "rzp_test_123456789")
        self.secret = os.getenv("RAZORPAY_SECRET", "test_secret_123456789")
        self.base_url = os.getenv("RAZORPAY_BASE_URL", "https://api.razorpay.com/v1")
        
        # Validate configuration
        self._validate_configuration()
    
    def _validate_configuration(self):
        """Validate Razorpay configuration"""
        if not self.key_id or self.key_id == "rzp_test_123456789":
            raise ConfigurationError("RAZORPAY_KEY_ID not configured properly")
        
        if not self.secret or self.secret == "test_secret_123456789":
            raise ConfigurationError("RAZORPAY_SECRET not configured properly")
    
    def _get_auth_header(self) -> str:
        """Generate Razorpay Basic Auth header"""
        credentials = f"{self.key_id}:{self.secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    
    def create_payment_link(
        self, 
        amount: float, 
        currency: str = "INR", 
        description: str = "Payment",
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Razorpay payment link
        
        Args:
            amount: Payment amount in rupees
            currency: Currency code (default: INR)
            description: Payment description
            customer_name: Customer name (optional)
            customer_email: Customer email (optional)
            customer_phone: Customer phone (optional)
            
        Returns:
            Dict containing payment link details
            
        Raises:
            RazorpayError: If payment link creation fails
        """
        try:
            # Validate amount
            if amount <= 0:
                raise RazorpayError(f"Invalid amount: {amount}. Amount must be greater than 0")
            
            # Convert amount to paise (smallest currency unit)
            amount_paise = int(amount * 100)
            
            print(f"[RAZORPAY_CLIENT] Creating payment link - Amount: {amount} INR ({amount_paise} paise)")
            
            url = f"{self.base_url}/payment_links"
            headers = {
                "Authorization": self._get_auth_header(),
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
            
            # Add customer details if provided
            if customer_name or customer_email or customer_phone:
                data["customer"] = {}
                if customer_name:
                    data["customer"]["name"] = customer_name
                if customer_email:
                    data["customer"]["email"] = customer_email
                if customer_phone:
                    data["customer"]["contact"] = customer_phone
            
            print(f"[RAZORPAY_CLIENT] Making API request to: {url}")
            
            response = requests.post(url, json=data, headers=headers, timeout=30)
            
            print(f"[RAZORPAY_CLIENT] Response status: {response.status_code}")
            
            if response.status_code != 200:
                error_msg = f"Razorpay API error: {response.status_code} - {response.text}"
                print(f"[RAZORPAY_CLIENT] {error_msg}")
                raise RazorpayError(error_msg)
            
            response_data = response.json()
            print(f"[RAZORPAY_CLIENT] Payment link created successfully: {response_data.get('id')}")
            
            return response_data
            
        except requests.exceptions.Timeout:
            raise RazorpayError("Razorpay API timeout")
        except requests.exceptions.ConnectionError:
            raise RazorpayError("Razorpay API connection error")
        except requests.exceptions.RequestException as e:
            raise RazorpayError(f"Razorpay API request error: {str(e)}")
        except RazorpayError:
            raise
        except Exception as e:
            raise RazorpayError(f"Unexpected error creating payment link: {str(e)}")
    
    def get_payment_details(self, payment_id: str) -> Dict[str, Any]:
        """
        Get payment details from Razorpay
        
        Args:
            payment_id: Razorpay payment ID
            
        Returns:
            Dict containing payment details
            
        Raises:
            RazorpayError: If payment details retrieval fails
        """
        try:
            url = f"{self.base_url}/payments/{payment_id}"
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise RazorpayError(f"Error fetching payment details: {str(e)}")
        except Exception as e:
            raise RazorpayError(f"Unexpected error fetching payment details: {str(e)}")
    
    def capture_payment(self, payment_id: str, amount: float, currency: str = "INR") -> Dict[str, Any]:
        """
        Capture a Razorpay payment
        
        Args:
            payment_id: Razorpay payment ID
            amount: Amount to capture in rupees
            currency: Currency code (default: INR)
            
        Returns:
            Dict containing capture response
            
        Raises:
            RazorpayError: If payment capture fails
        """
        try:
            # Convert amount to paise
            amount_paise = int(amount * 100)
            
            url = f"{self.base_url}/payments/{payment_id}/capture"
            headers = {
                "Authorization": self._get_auth_header(),
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
            raise RazorpayError(f"Error capturing payment: {str(e)}")
        except Exception as e:
            raise RazorpayError(f"Unexpected error capturing payment: {str(e)}")
    
    def validate_webhook_signature(self, data: bytes, received_signature: str, secret: str) -> bool:
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
            # Validate input parameters
            if not received_signature:
                print(f"[RAZORPAY_CLIENT] Error: received_signature is None or empty")
                return False
            
            if not secret:
                print(f"[RAZORPAY_CLIENT] Error: secret is None or empty")
                return False
            
            if not data:
                print(f"[RAZORPAY_CLIENT] Error: data is None or empty")
                return False
            
            print(f"[RAZORPAY_CLIENT] Validating webhook signature - received: {received_signature[:10]}..., secret: {secret[:10]}...")
            
            generated_signature = hmac.new(
                bytes(secret, 'utf-8'),
                msg=data,
                digestmod=hashlib.sha256
            ).hexdigest()

            print(f"[RAZORPAY_CLIENT] Generated signature: {generated_signature[:10]}...")
            
            is_valid = hmac.compare_digest(received_signature, generated_signature)
            print(f"[RAZORPAY_CLIENT] Signature validation result: {is_valid}")
            
            return is_valid
            
        except TypeError as e:
            print(f"[RAZORPAY_CLIENT] TypeError validating signature: {e}")
            print(f"[RAZORPAY_CLIENT] received_signature type: {type(received_signature)}, value: {received_signature}")
            print(f"[RAZORPAY_CLIENT] secret type: {type(secret)}, value: {secret}")
            print(f"[RAZORPAY_CLIENT] data type: {type(data)}, value: {data}")
            return False
        except Exception as e:
            print(f"[RAZORPAY_CLIENT] Error validating Razorpay signature: {e}")
            return False
    
    def generate_signature(self, data: str, secret: str) -> str:
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
    
    def get_configuration_status(self) -> Dict[str, Any]:
        """
        Get Razorpay configuration status for diagnostics
        
        Returns:
            Dict containing configuration status
        """
        return {
            "key_id_configured": bool(self.key_id and self.key_id != "rzp_test_123456789"),
            "secret_configured": bool(self.secret and self.secret != "test_secret_123456789"),
            "base_url": self.base_url,
            "key_id_prefix": self.key_id[:8] + "..." if self.key_id else "Not configured"
        }
