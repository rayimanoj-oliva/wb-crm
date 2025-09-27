"""
Referrer tracking middleware for enhanced tracking
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import re


class ReferrerTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to extract referrer information from requests"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract referrer information from headers
        referrer = request.headers.get("referer", "")
        user_agent = request.headers.get("user-agent", "")
        
        # Log referrer information for debugging
        if referrer:
            print(f"Referrer detected: {referrer}")
            print(f"User Agent: {user_agent}")
        
        response = await call_next(request)
        return response


def extract_utm_from_referrer(referrer_url: str) -> dict:
    """Extract UTM parameters from referrer URL"""
    import urllib.parse as urlparse
    
    if not referrer_url:
        return {}
    
    try:
        parsed_url = urlparse.urlparse(referrer_url)
        query_params = urlparse.parse_qs(parsed_url.query)
        
        utm_data = {}
        for key, value in query_params.items():
            if key.startswith('utm_'):
                utm_data[key] = value[0] if value else ''
        
        return utm_data
    except Exception:
        return {}


def get_center_from_domain(referrer_url: str) -> dict:
    """Extract center information from domain name"""
    if not referrer_url:
        return {"center_name": "Unknown", "location": "Unknown"}
    
    try:
        import urllib.parse as urlparse
        domain = urlparse.urlparse(referrer_url).netloc.lower()
        
        # Map domains to centers
        domain_mapping = {
            'olivaclinics.com': {"center_name": "Oliva Clinics", "location": "Multiple Locations"},
            'banjara.olivaclinics.com': {"center_name": "Oliva Clinics Banjara Hills", "location": "Hyderabad"},
            'jubilee.olivaclinics.com': {"center_name": "Oliva Clinics Jubilee Hills", "location": "Hyderabad"},
            'gachibowli.olivaclinics.com': {"center_name": "Oliva Clinics Gachibowli", "location": "Hyderabad"},
            'bandra.olivaclinics.com': {"center_name": "Oliva Clinics Bandra", "location": "Mumbai"},
            'gurgaon.olivaclinics.com': {"center_name": "Oliva Clinics Gurgaon", "location": "Delhi NCR"},
        }
        
        for domain_key, center_info in domain_mapping.items():
            if domain_key in domain:
                return center_info
        
        return {"center_name": "Oliva Clinics", "location": "Multiple Locations"}
    except Exception:
        return {"center_name": "Unknown", "location": "Unknown"}