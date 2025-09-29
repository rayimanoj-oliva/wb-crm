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
            customer_id=referrer_data.customer_id,
            appointment_date=referrer_data.appointment_date,
            appointment_time=referrer_data.appointment_time,
            treatment_type=referrer_data.treatment_type,
            is_appointment_booked=referrer_data.is_appointment_booked
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
        import re
        
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
            
            # Also try to extract UTM parameters from message text using regex
            # This handles cases where UTM params are embedded in the message text
            utm_pattern = r'utm_([a-z_]+)=([a-zA-Z0-9_\-\.]+)'
            matches = re.findall(utm_pattern, url_or_string, re.IGNORECASE)
            
            for key, value in matches:
                utm_data[f'utm_{key}'] = value
                        
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
    
    @staticmethod
    def update_appointment_booking(db: Session, wa_id: str, appointment_date: str, appointment_time: str, treatment_type: str) -> Optional[ReferrerTracking]:
        """Update referrer tracking record with appointment booking information"""
        referrer = db.query(ReferrerTracking).filter(ReferrerTracking.wa_id == wa_id).first()
        
        if not referrer:
            return None
        
        # Parse appointment date
        from datetime import datetime as dt
        try:
            # Try different date formats
            date_formats = [
                "%Y-%m-%d",
                "%d-%m-%Y", 
                "%d/%m/%Y",
                "%Y/%m/%d",
                "%d %B %Y",
                "%B %d, %Y"
            ]
            
            parsed_date = None
            for fmt in date_formats:
                try:
                    parsed_date = dt.strptime(appointment_date, fmt)
                    break
                except ValueError:
                    continue
            
            if not parsed_date:
                print(f"Could not parse appointment date: {appointment_date}")
                return None
                
        except Exception as e:
            print(f"Error parsing appointment date: {e}")
            return None
        
        # Update the referrer record
        referrer.appointment_date = parsed_date
        referrer.appointment_time = appointment_time
        referrer.treatment_type = treatment_type
        referrer.is_appointment_booked = True
        
        db.commit()
        db.refresh(referrer)
        return referrer
    
    @staticmethod
    def extract_appointment_info_from_message(message_body: str) -> dict:
        """Extract appointment information from WhatsApp message"""
        import re
        from datetime import datetime as dt
        
        appointment_info = {
            'appointment_date': None,
            'appointment_time': None,
            'treatment_type': None,
            'is_appointment_booked': False
        }
        
        # Common treatment types
        treatment_keywords = [
            'hair transplant', 'prp', 'fue', 'fut', 'dhi', 'beard transplant',
            'eyebrow transplant', 'body hair transplant', 'hair restoration',
            'scalp micropigmentation', 'smp', 'hairline design', 'crown restoration',
            'consultation', 'follow up', 'check up'
        ]
        
        # Extract treatment type
        message_lower = message_body.lower()
        for treatment in treatment_keywords:
            if treatment in message_lower:
                appointment_info['treatment_type'] = treatment.title()
                break
        
        # Extract date patterns
        date_patterns = [
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',  # DD-MM-YYYY or DD/MM/YYYY
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',  # YYYY-MM-DD or YYYY/MM/DD
            r'(\d{1,2}\s+\w+\s+\d{4})',        # DD Month YYYY
            r'(\w+\s+\d{1,2},?\s+\d{4})',      # Month DD, YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, message_body, re.IGNORECASE)
            if match:
                appointment_info['appointment_date'] = match.group(1)
                break
        
        # Extract time patterns
        time_patterns = [
            r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))',  # 10:30 AM
            r'(\d{1,2}\s*(?:AM|PM|am|pm))',        # 10 AM
            r'(\d{1,2}:\d{2})',                     # 10:30
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, message_body, re.IGNORECASE)
            if match:
                appointment_info['appointment_time'] = match.group(1)
                break
        
        # Check if appointment is being booked
        booking_keywords = [
            'book', 'booking', 'appointment', 'schedule', 'confirm', 'confirmed',
            'booked', 'reserve', 'reservation', 'fix', 'arrange'
        ]
        
        for keyword in booking_keywords:
            if keyword in message_lower:
                appointment_info['is_appointment_booked'] = True
                break
        
        return appointment_info
    
    @staticmethod
    def get_appointment_bookings(db: Session, center_name: str = None, from_date: str = None, to_date: str = None) -> list:
        """Get appointment bookings with optional filters"""
        query = db.query(ReferrerTracking).filter(ReferrerTracking.is_appointment_booked == True)
        
        if center_name:
            query = query.filter(ReferrerTracking.center_name.ilike(f"%{center_name}%"))
        
        if from_date:
            from datetime import datetime as dt
            try:
                from_dt = dt.strptime(from_date, "%Y-%m-%d")
                query = query.filter(ReferrerTracking.appointment_date >= from_dt)
            except ValueError:
                print(f"Invalid from_date format: {from_date}")
        
        if to_date:
            from datetime import datetime as dt
            try:
                to_dt = dt.strptime(to_date, "%Y-%m-%d")
                query = query.filter(ReferrerTracking.appointment_date <= to_dt)
            except ValueError:
                print(f"Invalid to_date format: {to_date}")
        
        return query.order_by(ReferrerTracking.appointment_date.desc()).all()
    
    @staticmethod
    def track_message_interaction(db: Session, wa_id: str, message_body: str, referrer_url: str = None) -> Optional[ReferrerTracking]:
        """Track every message interaction and extract UTM parameters"""
        try:
            # Extract UTM parameters from message
            utm_data = ReferrerService.parse_utm_parameters(message_body)
            
            # Also check referrer URL for UTM parameters
            if referrer_url:
                referrer_utm = ReferrerService.parse_utm_parameters(referrer_url)
                # Merge referrer UTM data (prioritize message UTM data)
                for key, value in referrer_utm.items():
                    if key not in utm_data or not utm_data[key]:
                        utm_data[key] = value
            
            # Get center information
            center_info = ReferrerService.detect_center_from_message(message_body, referrer_url)
            
            # Check if referrer record exists
            existing_referrer = ReferrerService.get_referrer_by_wa_id(db, wa_id)
            
            if existing_referrer:
                # Update existing record with new UTM data
                updated = False
                if utm_data.get('utm_source') and utm_data['utm_source'] != existing_referrer.utm_source:
                    existing_referrer.utm_source = utm_data['utm_source']
                    updated = True
                if utm_data.get('utm_medium') and utm_data['utm_medium'] != existing_referrer.utm_medium:
                    existing_referrer.utm_medium = utm_data['utm_medium']
                    updated = True
                if utm_data.get('utm_campaign') and utm_data['utm_campaign'] != existing_referrer.utm_campaign:
                    existing_referrer.utm_campaign = utm_data['utm_campaign']
                    updated = True
                if utm_data.get('utm_content') and utm_data['utm_content'] != existing_referrer.utm_content:
                    existing_referrer.utm_content = utm_data['utm_content']
                    updated = True
                if referrer_url and referrer_url != existing_referrer.referrer_url:
                    existing_referrer.referrer_url = referrer_url
                    updated = True
                if center_info['center_name'] != 'Oliva Clinics' and center_info['center_name'] != existing_referrer.center_name:
                    existing_referrer.center_name = center_info['center_name']
                    updated = True
                if center_info['location'] != 'Multiple Locations' and center_info['location'] != existing_referrer.location:
                    existing_referrer.location = center_info['location']
                    updated = True
                
                if updated:
                    db.commit()
                    db.refresh(existing_referrer)
                    print(f"Updated referrer record for {wa_id} with new UTM data")
                
                return existing_referrer
            else:
                # Create new referrer record
                from schemas.referrer_schema import ReferrerTrackingCreate
                from services.customer_service import CustomerService
                
                # Get or create customer
                from schemas.customer_schema import CustomerCreate
                
                customer_service = CustomerService()
                customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name="Unknown"))
                
                referrer_data = ReferrerTrackingCreate(
                    wa_id=wa_id,
                    utm_source=utm_data.get('utm_source', ''),
                    utm_medium=utm_data.get('utm_medium', ''),
                    utm_campaign=utm_data.get('utm_campaign', ''),
                    utm_content=utm_data.get('utm_content', ''),
                    referrer_url=referrer_url or '',
                    center_name=center_info['center_name'],
                    location=center_info['location'],
                    customer_id=customer.id
                )
                
                new_referrer = ReferrerService.create_referrer_tracking(db, referrer_data)
                print(f"Created new referrer record for {wa_id}")
                return new_referrer
                
        except Exception as e:
            print(f"Error tracking message interaction: {e}")
            import traceback
            traceback.print_exc()
            return None


referrer_service = ReferrerService()
