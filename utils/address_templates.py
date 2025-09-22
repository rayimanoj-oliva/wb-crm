"""
WhatsApp Templates for Address Collection System
Similar to JioMart, Blinkit, Domino's approach
"""

from typing import Dict, Any, Optional
from datetime import datetime


def get_order_confirmation_template(customer_name: str, order_total: float, order_items: list) -> Dict[str, Any]:
    """
    Template sent after order placement - includes 'Add Delivery Address' button
    Similar to JioMart's order confirmation with address button
    """
    return {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": {
            "name": "order_confirmation_address",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "🛍️ Order Confirmed!"
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": customer_name
                        },
                        {
                            "type": "text",
                            "text": f"₹{order_total}"
                        },
                        {
                            "type": "text",
                            "text": f"{len(order_items)} items"
                        }
                    ]
                },
                {
                    "type": "footer",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Please add your delivery address to proceed"
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 0,
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": "ADD_DELIVERY_ADDRESS"
                        }
                    ]
                }
            ]
        }
    }


def get_address_collection_options_template(customer_name: str, has_saved_addresses: bool) -> Dict[str, Any]:
    """
    Template showing address collection options
    Similar to Blinkit's address selection screen
    """
    components = [
        {
            "type": "header",
            "parameters": [
                {
                    "type": "text",
                    "text": "📍 Delivery Address"
                }
            ]
        },
        {
            "type": "body",
            "parameters": [
                {
                    "type": "text",
                    "text": customer_name
                }
            ]
        },
        {
            "type": "footer",
            "parameters": [
                {
                    "type": "text",
                    "text": "Choose how you'd like to add your address"
                }
            ]
        }
    ]
    
    # Add buttons based on available options
    buttons = [
        {
            "type": "button",
            "sub_type": "quick_reply",
            "index": 0,
            "parameters": [
                {
                    "type": "payload",
                    "payload": "USE_CURRENT_LOCATION"
                }
            ]
        },
        {
            "type": "button",
            "sub_type": "quick_reply",
            "index": 1,
            "parameters": [
                {
                    "type": "payload",
                    "payload": "ENTER_NEW_ADDRESS"
                }
            ]
        }
    ]
    
    if has_saved_addresses:
        buttons.append({
            "type": "button",
            "sub_type": "quick_reply",
            "index": 2,
            "parameters": [
                {
                    "type": "payload",
                    "payload": "USE_SAVED_ADDRESS"
                }
            ]
        })
    
    components.extend(buttons)
    
    return {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": {
            "name": "address_collection_options",
            "language": {"code": "en_US"},
            "components": components
        }
    }


def get_location_request_template() -> Dict[str, Any]:
    """
    Template requesting location sharing
    Similar to Domino's location request
    """
    return {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": {
            "name": "location_request",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "📍 Share Your Location"
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Please share your current location for accurate delivery"
                        }
                    ]
                },
                {
                    "type": "footer",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Tap the location icon below to share"
                        }
                    ]
                }
            ]
        }
    }


def get_manual_address_template() -> Dict[str, Any]:
    """
    Template for manual address entry with simplified format
    """
    return {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": {
            "name": "manual_address_entry",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "📝 Enter Your Address"
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Please enter your address in this format:"
                        }
                    ]
                },
                {
                    "type": "footer",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Name, House No, Area, City, State, Pincode"
                        }
                    ]
                }
            ]
        }
    }


def get_saved_addresses_template(addresses: list) -> Dict[str, Any]:
    """
    Template showing saved addresses for selection
    """
    if not addresses:
        return get_manual_address_template()
    
    # Create interactive message for address selection
    sections = []
    for i, address in enumerate(addresses[:3]):  # Limit to 3 addresses
        address_text = f"{address['house_street']}, {address['locality']}, {address['city']} - {address['pincode']}"
        sections.append({
            "title": f"Address {i+1}",
            "description": address_text,
            "product_items": [
                {
                    "product_retailer_id": f"address_{address['id']}"
                }
            ]
        })
    
    return {
        "messaging_product": "whatsapp",
        "type": "interactive",
        "interactive": {
            "type": "product_list",
            "header": {
                "type": "text",
                "text": "📍 Select Address"
            },
            "body": {
                "text": "Choose from your saved addresses"
            },
            "footer": {
                "text": "Tap to select an address"
            },
            "action": {
                "catalog_id": "address_selection",
                "sections": sections
            }
        }
    }


def get_address_confirmation_template(address_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Template confirming the selected address
    """
    address_text = f"{address_data['house_street']}, {address_data['locality']}, {address_data['city']}, {address_data['state']} - {address_data['pincode']}"
    
    return {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": {
            "name": "address_confirmation",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "✅ Address Confirmed"
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": address_text
                        }
                    ]
                },
                {
                    "type": "footer",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Is this address correct?"
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 0,
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": "CONFIRM_ADDRESS"
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 1,
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": "CHANGE_ADDRESS"
                        }
                    ]
                }
            ]
        }
    }


def get_address_saved_template() -> Dict[str, Any]:
    """
    Template confirming address has been saved
    """
    return {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": {
            "name": "address_saved",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "💾 Address Saved"
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Your address has been saved for future orders"
                        }
                    ]
                },
                {
                    "type": "footer",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Proceeding with your order..."
                        }
                    ]
                }
            ]
        }
    }


def get_address_error_template(error_message: str) -> Dict[str, Any]:
    """
    Template for address validation errors
    """
    return {
        "messaging_product": "whatsapp",
        "type": "template",
        "template": {
            "name": "address_error",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "❌ Address Error"
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": error_message
                        }
                    ]
                },
                {
                    "type": "footer",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Please try again"
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": 0,
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": "RETRY_ADDRESS"
                        }
                    ]
                }
            ]
        }
    }
