"""
Referrer tracking service for WhatsApp link clicks
"""
from sqlalchemy.orm import Session
from models.models import ReferrerTracking
from schemas.referrer_schema import ReferrerTrackingCreate, ReferrerTrackingResponse
from typing import Optional, Dict, Any
import re


class ReferrerService:
    
    @staticmethod
    def create_referrer_tracking(db: Session, referrer_data: ReferrerTrackingCreate) -> ReferrerTracking:
        """Create a new referrer tracking record"""
        db_referrer = ReferrerTracking(
            wa_id=referrer_data.wa_id,
            utm_source=referrer_data.utm_source,
            utm_medium=referrer_data.utm_medium,
            utm_campaign=referrer_data.utm_campaign,
            utm_content=referrer_data.utm_content,
            referrer_url=referrer_data.referrer_url,
            center_name=referrer_data.center_name,
            location=referrer_data.location,
            customer_id=referrer_data.customer_id
        )
        db.add(db_referrer)
        db.commit()
        db.refresh(db_referrer)
        return db_referrer
    
    @staticmethod
    def get_referrer_by_wa_id(db: Session, wa_id: str) -> Optional[ReferrerTracking]:
        """Get referrer tracking by WhatsApp ID"""
        return db.query(ReferrerTracking).filter(ReferrerTracking.wa_id == wa_id).first()
    
    @staticmethod
    def parse_utm_parameters(url_or_string: str) -> Dict[str, str]:
        """Parse UTM parameters from URL or string"""
        import urllib.parse as urlparse
        
        utm_data = {}
        
        try:
            # If it looks like a URL, parse it
            if url_or_string.startswith(('http://', 'https://')):
                parsed_url = urlparse.urlparse(url_or_string)
                query_params = urlparse.parse_qs(parsed_url.query)
                
                for key, value in query_params.items():
                    if key.startswith('utm_'):
                        utm_data[key] = value[0] if value else ''
            else:
                # If it's just a query string, parse it directly
                query_params = urlparse.parse_qs(url_or_string)
                
                for key, value in query_params.items():
                    if key.startswith('utm_'):
                        utm_data[key] = value[0] if value else ''
                        
        except Exception as e:
            print(f"Error parsing UTM parameters: {e}")
        
        return utm_data
    
    @staticmethod
    def get_center_info_from_utm(utm_data: Dict[str, str]) -> Dict[str, str]:
        """Map UTM parameters to center information"""
        center_mapping = {
            'banjara_hills': {
                'center_name': 'Oliva Clinics Banjara Hills',
                'location': 'Hyderabad'
            },
            'jubilee_hills': {
                'center_name': 'Oliva Clinics Jubilee Hills',
                'location': 'Hyderabad'
            },
            'gachibowli': {
                'center_name': 'Oliva Clinics Gachibowli',
                'location': 'Hyderabad'
            },
            'mumbai_bandra': {
                'center_name': 'Oliva Clinics Bandra',
                'location': 'Mumbai'
            },
            'delhi_gurgaon': {
                'center_name': 'Oliva Clinics Gurgaon',
                'location': 'Delhi NCR'
            }
        }
        
        campaign = utm_data.get('utm_campaign', '').lower()
        center_info = center_mapping.get(campaign, {
            'center_name': 'Oliva Clinics',
            'location': 'Multiple Locations'
        })
        
        return center_info
    
    @staticmethod
    def get_center_info_from_website(referrer_url: str) -> Dict[str, str]:
        """Extract center information from website URL"""
        if not referrer_url:
            return {"center_name": "Oliva Clinics", "location": "Multiple Locations"}
        
        try:
            import urllib.parse as urlparse
            domain = urlparse.urlparse(referrer_url).netloc.lower()
            
            # Map domains to centers
            website_mapping = {
                'olivaclinics.com': {"center_name": "Oliva Clinics", "location": "Multiple Locations"},
                'www.olivaclinics.com': {"center_name": "Oliva Clinics", "location": "Multiple Locations"},
                'banjara.olivaclinics.com': {"center_name": "Oliva Clinics Banjara Hills", "location": "Hyderabad"},
                'www.banjara.olivaclinics.com': {"center_name": "Oliva Clinics Banjara Hills", "location": "Hyderabad"},
                'jubilee.olivaclinics.com': {"center_name": "Oliva Clinics Jubilee Hills", "location": "Hyderabad"},
                'www.jubilee.olivaclinics.com': {"center_name": "Oliva Clinics Jubilee Hills", "location": "Hyderabad"},
                'gachibowli.olivaclinics.com': {"center_name": "Oliva Clinics Gachibowli", "location": "Hyderabad"},
                'www.gachibowli.olivaclinics.com': {"center_name": "Oliva Clinics Gachibowli", "location": "Hyderabad"},
                'bandra.olivaclinics.com': {"center_name": "Oliva Clinics Bandra", "location": "Mumbai"},
                'www.bandra.olivaclinics.com': {"center_name": "Oliva Clinics Bandra", "location": "Mumbai"},
                'gurgaon.olivaclinics.com': {"center_name": "Oliva Clinics Gurgaon", "location": "Delhi NCR"},
                'www.gurgaon.olivaclinics.com': {"center_name": "Oliva Clinics Gurgaon", "location": "Delhi NCR"},
                'mumbai.olivaclinics.com': {"center_name": "Oliva Clinics Mumbai", "location": "Mumbai"},
                'www.mumbai.olivaclinics.com': {"center_name": "Oliva Clinics Mumbai", "location": "Mumbai"},
                'delhi.olivaclinics.com': {"center_name": "Oliva Clinics Delhi", "location": "Delhi NCR"},
                'www.delhi.olivaclinics.com': {"center_name": "Oliva Clinics Delhi", "location": "Delhi NCR"},
                'bangalore.olivaclinics.com': {"center_name": "Oliva Clinics Bangalore", "location": "Bangalore"},
                'www.bangalore.olivaclinics.com': {"center_name": "Oliva Clinics Bangalore", "location": "Bangalore"},
                'pune.olivaclinics.com': {"center_name": "Oliva Clinics Pune", "location": "Pune"},
                'www.pune.olivaclinics.com': {"center_name": "Oliva Clinics Pune", "location": "Pune"},
                'chennai.olivaclinics.com': {"center_name": "Oliva Clinics Chennai", "location": "Chennai"},
                'www.chennai.olivaclinics.com': {"center_name": "Oliva Clinics Chennai", "location": "Chennai"},
                'kolkata.olivaclinics.com': {"center_name": "Oliva Clinics Kolkata", "location": "Kolkata"},
                'www.kolkata.olivaclinics.com': {"center_name": "Oliva Clinics Kolkata", "location": "Kolkata"},
            }
            
            # Check for exact domain match
            for domain_key, center_info in website_mapping.items():
                if domain == domain_key:
                    return center_info
            
            # Check for partial domain match (subdomain detection)
            for domain_key, center_info in website_mapping.items():
                if domain_key in domain:
                    return center_info
            
            # If no specific match, return default
            return {"center_name": "Oliva Clinics", "location": "Multiple Locations"}
            
        except Exception as e:
            print(f"Error parsing website URL: {e}")
            return {"center_name": "Oliva Clinics", "location": "Multiple Locations"}
    
    @staticmethod
    def detect_center_from_message(message_body: str, referrer_url: str = None) -> Dict[str, str]:
        """Detect center information from message body and referrer URL"""
        # First try to get from UTM parameters in message
        utm_data = ReferrerService.parse_utm_parameters(message_body)
        if utm_data:
            center_info = ReferrerService.get_center_info_from_utm(utm_data)
            if center_info['center_name'] != 'Oliva Clinics' or center_info['location'] != 'Multiple Locations':
                return center_info
        
        # If no UTM data or generic info, try to get from referrer URL
        if referrer_url:
            center_info = ReferrerService.get_center_info_from_website(referrer_url)
            if center_info['center_name'] != 'Oliva Clinics' or center_info['location'] != 'Multiple Locations':
                return center_info
        
        # Default fallback
        return {"center_name": "Oliva Clinics", "location": "Multiple Locations"}
    
    @staticmethod
    def track_referrer_from_message(db: Session, wa_id: str, message_body: str, customer_id: str) -> Optional[ReferrerTracking]:
        """Extract and track referrer information from message body"""
        # Look for UTM parameters in the message
        utm_pattern = r'utm_[a-z_]+=[a-zA-Z0-9_]+'
        utm_matches = re.findall(utm_pattern, message_body)
        
        if not utm_matches:
            return None
        
        # Parse UTM parameters
        utm_data = {}
        for match in utm_matches:
            key, value = match.split('=')
            utm_data[key] = value
        
        # Get center information
        center_info = ReferrerService.get_center_info_from_utm(utm_data)
        
        # Create referrer tracking record
        referrer_data = ReferrerTrackingCreate(
            wa_id=wa_id,
            utm_source=utm_data.get('utm_source', ''),
            utm_medium=utm_data.get('utm_medium', ''),
            utm_campaign=utm_data.get('utm_campaign', ''),
            utm_content=utm_data.get('utm_content', ''),
            referrer_url='',  # Not available from message
            center_name=center_info['center_name'],
            location=center_info['location'],
            customer_id=customer_id
        )
        
        return ReferrerService.create_referrer_tracking(db, referrer_data)


referrer_service = ReferrerService()
