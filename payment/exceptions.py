"""
Payment Exceptions - Custom exceptions for payment operations
Defines specific exception types for different payment-related errors
"""


class PaymentError(Exception):
    """Base exception for payment-related errors"""
    
    def __init__(self, message: str, error_type: str = "unknown", details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details or {}


class RazorpayError(PaymentError):
    """Exception raised for Razorpay API errors"""
    
    def __init__(self, message: str, status_code: int = None, details: dict = None):
        super().__init__(message, "razorpay", details)
        self.status_code = status_code


class ConfigurationError(PaymentError):
    """Exception raised for configuration errors"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "configuration", details)


class ValidationError(PaymentError):
    """Exception raised for validation errors"""
    
    def __init__(self, message: str, field: str = None, details: dict = None):
        super().__init__(message, "validation", details)
        self.field = field


class OrderNotFoundError(PaymentError):
    """Exception raised when order is not found"""
    
    def __init__(self, order_id: str, details: dict = None):
        message = f"Order not found: {order_id}"
        super().__init__(message, "order_not_found", details)
        self.order_id = order_id


class PaymentNotFoundError(PaymentError):
    """Exception raised when payment is not found"""
    
    def __init__(self, payment_id: str, details: dict = None):
        message = f"Payment not found: {payment_id}"
        super().__init__(message, "payment_not_found", details)
        self.payment_id = payment_id


class PaymentExpiredError(PaymentError):
    """Exception raised when payment link has expired"""
    
    def __init__(self, payment_id: str, details: dict = None):
        message = f"Payment link has expired: {payment_id}"
        super().__init__(message, "payment_expired", details)
        self.payment_id = payment_id


class PaymentAlreadyProcessedError(PaymentError):
    """Exception raised when payment is already processed"""
    
    def __init__(self, payment_id: str, current_status: str, details: dict = None):
        message = f"Payment already processed: {payment_id} (status: {current_status})"
        super().__init__(message, "payment_already_processed", details)
        self.payment_id = payment_id
        self.current_status = current_status


class InsufficientFundsError(PaymentError):
    """Exception raised when there are insufficient funds"""
    
    def __init__(self, amount: float, available: float = None, details: dict = None):
        message = f"Insufficient funds for amount: {amount}"
        if available is not None:
            message += f" (available: {available})"
        super().__init__(message, "insufficient_funds", details)
        self.amount = amount
        self.available = available


class PaymentGatewayError(PaymentError):
    """Exception raised for payment gateway errors"""
    
    def __init__(self, message: str, gateway: str = None, details: dict = None):
        super().__init__(message, "gateway_error", details)
        self.gateway = gateway


class NotificationError(PaymentError):
    """Exception raised for notification errors"""
    
    def __init__(self, message: str, notification_type: str = None, details: dict = None):
        super().__init__(message, "notification_error", details)
        self.notification_type = notification_type


class WebhookError(PaymentError):
    """Exception raised for webhook processing errors"""
    
    def __init__(self, message: str, webhook_type: str = None, details: dict = None):
        super().__init__(message, "webhook_error", details)
        self.webhook_type = webhook_type


class SignatureValidationError(WebhookError):
    """Exception raised for webhook signature validation errors"""
    
    def __init__(self, message: str = "Invalid webhook signature", details: dict = None):
        super().__init__(message, "signature_validation", details)


class TimeoutError(PaymentError):
    """Exception raised for timeout errors"""
    
    def __init__(self, message: str, timeout_duration: int = None, details: dict = None):
        super().__init__(message, "timeout", details)
        self.timeout_duration = timeout_duration


class ConnectionError(PaymentError):
    """Exception raised for connection errors"""
    
    def __init__(self, message: str, endpoint: str = None, details: dict = None):
        super().__init__(message, "connection", details)
        self.endpoint = endpoint
