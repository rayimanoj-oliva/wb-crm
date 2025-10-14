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
        # Try to get from referrer URL if available
        if referrer_url:
            center_info = ReferrerService.get_center_info_from_website(referrer_url)
            if center_info['center_name'] != 'Oliva Clinics' or center_info['location'] != 'Multiple Locations':
                return center_info
        
        # Enhanced center detection from message body
        message_lower = message_body.lower()
        
        # Pattern for "services in [Center], [City] clinic" format
        import re
        center_location_pattern = r'services\s+in\s+([^,]+),\s*([^,\s]+)\s+clinic'
        match = re.search(center_location_pattern, message_lower)
        if match:
            center_part = match.group(1).strip()
            city_part = match.group(2).strip()
            
            # Map center names and cities
            center_mapping = {
                'banjara hills': {'center_name': 'Oliva Clinics Banjara Hills', 'location': 'Hyderabad'},
                'jubilee hills': {'center_name': 'Oliva Clinics Jubilee Hills', 'location': 'Hyderabad'},
                'gachibowli': {'center_name': 'Oliva Clinics Gachibowli', 'location': 'Hyderabad'},
                'bandra': {'center_name': 'Oliva Clinics Bandra', 'location': 'Mumbai'},
                'mumbai': {'center_name': 'Oliva Clinics Mumbai', 'location': 'Mumbai'},
                'gurgaon': {'center_name': 'Oliva Clinics Gurgaon', 'location': 'Delhi NCR'},
                'delhi': {'center_name': 'Oliva Clinics Delhi', 'location': 'Delhi NCR'},
                'bangalore': {'center_name': 'Oliva Clinics Bangalore', 'location': 'Bangalore'},
                'pune': {'center_name': 'Oliva Clinics Pune', 'location': 'Pune'},
                'chennai': {'center_name': 'Oliva Clinics Chennai', 'location': 'Chennai'},
                'kolkata': {'center_name': 'Oliva Clinics Kolkata', 'location': 'Kolkata'},
            }
            
            # Check if center part matches any known center
            for center_key, center_info in center_mapping.items():
                if center_key in center_part:
                    return center_info
            
            # If center not found but city is known, use city-based mapping
            city_mapping = {
                'hyderabad': {'center_name': 'Oliva Clinics Hyderabad', 'location': 'Hyderabad'},
                'mumbai': {'center_name': 'Oliva Clinics Mumbai', 'location': 'Mumbai'},
                'delhi': {'center_name': 'Oliva Clinics Delhi', 'location': 'Delhi NCR'},
                'bangalore': {'center_name': 'Oliva Clinics Bangalore', 'location': 'Bangalore'},
                'pune': {'center_name': 'Oliva Clinics Pune', 'location': 'Pune'},
                'chennai': {'center_name': 'Oliva Clinics Chennai', 'location': 'Chennai'},
                'kolkata': {'center_name': 'Oliva Clinics Kolkata', 'location': 'Kolkata'},
            }
            
            if city_part in city_mapping:
                return city_mapping[city_part]
        
        # Fallback to keyword-based detection
        center_keywords = {
            'banjara': {'center_name': 'Oliva Clinics Banjara Hills', 'location': 'Hyderabad'},
            'jubilee': {'center_name': 'Oliva Clinics Jubilee Hills', 'location': 'Hyderabad'},
            'gachibowli': {'center_name': 'Oliva Clinics Gachibowli', 'location': 'Hyderabad'},
            'bandra': {'center_name': 'Oliva Clinics Bandra', 'location': 'Mumbai'},
            'mumbai': {'center_name': 'Oliva Clinics Mumbai', 'location': 'Mumbai'},
            'gurgaon': {'center_name': 'Oliva Clinics Gurgaon', 'location': 'Delhi NCR'},
            'delhi': {'center_name': 'Oliva Clinics Delhi', 'location': 'Delhi NCR'},
            'bangalore': {'center_name': 'Oliva Clinics Bangalore', 'location': 'Bangalore'},
            'pune': {'center_name': 'Oliva Clinics Pune', 'location': 'Pune'},
            'chennai': {'center_name': 'Oliva Clinics Chennai', 'location': 'Chennai'},
            'kolkata': {'center_name': 'Oliva Clinics Kolkata', 'location': 'Kolkata'},
        }
        
        for keyword, center_info in center_keywords.items():
            if keyword in message_lower:
                return center_info
        
        # Default fallback
        return {"center_name": "Oliva Clinics", "location": "Multiple Locations"}
    
    
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
        
        # Idempotency: if the same slot is already booked, return existing without rewriting
        try:
            from datetime import datetime as _dt
            if (
                referrer.is_appointment_booked and
                isinstance(referrer.appointment_date, _dt) and
                referrer.appointment_time and
                referrer.appointment_date.date() == parsed_date.date() and
                str(referrer.appointment_time).strip().lower() == str(appointment_time).strip().lower()
            ):
                return referrer
        except Exception:
            pass

        # Update the referrer record
        referrer.appointment_date = parsed_date
        referrer.appointment_time = appointment_time
        referrer.treatment_type = treatment_type
        referrer.is_appointment_booked = True
        
        db.commit()
        db.refresh(referrer)
        return referrer

    @staticmethod
    def create_appointment_booking(db: Session, wa_id: str, appointment_date: str, appointment_time: str, treatment_type: str) -> Optional[ReferrerTracking]:
        """Create a NEW appointment row for this wa_id, allowing multiple bookings per wa_id.
        Copies customer and center/location from the earliest referrer record if available.
        """
        from datetime import datetime as dt
        try:
            # Parse date with the same formats as update
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

            # Find earliest referrer to copy context from
            oldest = (
                db.query(ReferrerTracking)
                .filter(ReferrerTracking.wa_id == wa_id)
                .order_by(ReferrerTracking.created_at.asc())
                .first()
            )

            center_name = getattr(oldest, "center_name", None) or "Oliva Clinics"
            location = getattr(oldest, "location", None) or "Multiple Locations"
            customer_id = getattr(oldest, "customer_id", None)

            if not customer_id:
                try:
                    from services.customer_service import get_or_create_customer
                    from schemas.customer_schema import CustomerCreate
                    customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name="Unknown"))
                    customer_id = customer.id
                except Exception:
                    customer_id = None

            # Create a brand-new row
            new_row = ReferrerTracking(
                wa_id=wa_id,
                center_name=center_name,
                location=location,
                customer_id=customer_id,
                appointment_date=parsed_date,
                appointment_time=appointment_time,
                treatment_type=treatment_type,
                is_appointment_booked=True,
            )
            db.add(new_row)
            db.commit()
            db.refresh(new_row)
            return new_row
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"create_appointment_booking error: {str(e)}")
            return None
    
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
        
        message_lower = message_body.lower()
        
        # Enhanced treatment type detection - categorize by skin, hair, body
        treatment_categories = {
            'hair': [
                'hair transplant', 'prp', 'fue', 'fut', 'dhi', 'beard transplant',
                'eyebrow transplant', 'body hair transplant', 'hair restoration',
                'scalp micropigmentation', 'smp', 'hairline design', 'crown restoration',
                'hair loss', 'baldness', 'hair growth', 'hair treatment', 'hair'
            ],
            'skin': [
                'skin treatment', 'acne', 'pigmentation', 'melasma', 'vitiligo',
                'skin whitening', 'anti aging', 'wrinkles', 'dark spots',
                'skin rejuvenation', 'chemical peel', 'microdermabrasion',
                'laser treatment', 'skin care', 'facial', 'skin consultation', 'skin'
            ],
            'body': [
                'body contouring', 'liposuction', 'tummy tuck', 'breast augmentation',
                'body sculpting', 'weight loss', 'body treatment', 'body consultation',
                'cosmetic surgery', 'plastic surgery', 'body enhancement', 'body'
            ],
            'general': [
                'consultation', 'follow up', 'check up', 'services', 'treatment',
                'procedure', 'therapy', 'medical', 'clinic visit'
            ]
        }
        
        # Extract treatment type by category
        detected_treatments = []
        # First pass: exact matches
        for category, treatments in treatment_categories.items():
            for treatment in treatments:
                if treatment in message_lower:
                    if treatment in {'skin', 'hair', 'body'}:
                        # Category-only selection; store category for potential combination later
                        detected_treatments.append(f"{category.title()}")
                    else:
                        detected_treatments.append(f"{category.title()}: {treatment.title()}")
        
        if detected_treatments:
            # If the user first chose category (e.g., Skin) then chose a specific (e.g., Pigmentation),
            # combine as "Skin: Pigmentation"
            if len(detected_treatments) == 1 and detected_treatments[0] in {"Skin", "Hair", "Body"}:
                appointment_info['treatment_type'] = detected_treatments[0]
            else:
                # Normalize cases where category and specific occur separately
                try:
                    if 'Skin' in detected_treatments and any(dt.startswith('Skin:') for dt in detected_treatments):
                        specific = [dt for dt in detected_treatments if dt.startswith('Skin:')][0]
                        appointment_info['treatment_type'] = specific
                    elif 'Hair' in detected_treatments and any(dt.startswith('Hair:') for dt in detected_treatments):
                        specific = [dt for dt in detected_treatments if dt.startswith('Hair:')][0]
                        appointment_info['treatment_type'] = specific
                    elif 'Body' in detected_treatments and any(dt.startswith('Body:') for dt in detected_treatments):
                        specific = [dt for dt in detected_treatments if dt.startswith('Body:')][0]
                        appointment_info['treatment_type'] = specific
                    else:
                        appointment_info['treatment_type'] = ', '.join(detected_treatments[:3])
                except Exception:
                    appointment_info['treatment_type'] = ', '.join(detected_treatments[:3])
        
        # Extract date patterns (explicit formats and interactive IDs)
        date_patterns = [
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',  # DD-MM-YYYY or DD/MM/YYYY
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',  # YYYY-MM-DD or YYYY/MM/DD
            r'(\d{1,2}\s+\w+\s+\d{4})',        # DD Month YYYY
            r'(\w+\s+\d{1,2},?\s+\d{4})',      # Month DD, YYYY
            r'(\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4})',  # 15th January 2025
            r'(tomorrow|today|yesterday)',      # Relative dates
            r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})',  # 15 Jan 2025
            r'(?:^|\s)date_(\d{4}-\d{2}-\d{2})(?:\s|$)',  # interactive id: date_2025-10-01
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, message_body, re.IGNORECASE)
            if match:
                date_text = match.group(1).lower()
                
                # Handle relative dates
                if date_text in ['tomorrow', 'today', 'yesterday']:
                    from datetime import datetime, timedelta
                    today = datetime.now().date()
                    if date_text == 'tomorrow':
                        appointment_info['appointment_date'] = (today + timedelta(days=1)).strftime('%Y-%m-%d')
                    elif date_text == 'today':
                        appointment_info['appointment_date'] = today.strftime('%Y-%m-%d')
                    elif date_text == 'yesterday':
                        appointment_info['appointment_date'] = (today - timedelta(days=1)).strftime('%Y-%m-%d')
                else:
                    # Prefer normalized subgroup if present (e.g., date_YYYY-MM-DD)
                    if match.lastindex and match.groups():
                        # Choose the last non-None capturing group
                        for g in match.groups()[::-1]:
                            if g:
                                appointment_info['appointment_date'] = g
                                break
                    if not appointment_info['appointment_date']:
                        appointment_info['appointment_date'] = match.group(1)
                break
        
        # Extract time patterns (explicit formats and interactive IDs)
        time_patterns = [
            r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))',  # 10:30 AM
            r'(\d{1,2}\s*(?:AM|PM|am|pm))',        # 10 AM
            r'(\d{1,2}:\d{2})',                     # 10:30
            r'(?:^|\s)time_(\d{1,2})_(\d{2})(?:\s|$)',  # interactive id: time_10_00
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, message_body, re.IGNORECASE)
            if match:
                if match.lastindex and match.lastindex >= 2 and match.groups():
                    hh, mm = match.group(1), match.group(2)
                    try:
                        # Default to 12-hour if later suffixed, else keep HH:MM
                        appointment_info['appointment_time'] = f"{int(hh):02d}:{int(mm):02d}"
                    except Exception:
                        appointment_info['appointment_time'] = f"{hh}:{mm}"
                else:
                    appointment_info['appointment_time'] = match.group(1)
                break
        
        # Check if appointment is being booked or inquiry about services
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
        """Track message interaction for service inquiries and appointment booking.
        One-row-per-wa_id policy:
        - On first message: create a single referrer row (center/location if found)
        - On later messages: update the same row with appointment date/time/treatment and flag
        - Avoid creating duplicate rows for the same wa_id
        """
        try:
            # Check if this message contains service-related information
            appointment_info = ReferrerService.extract_appointment_info_from_message(message_body)
            message_lower = message_body.lower()
            
            # Service inquiry keywords that should trigger tracking
            service_keywords = [
                'services', 'treatment', 'consultation', 'clinic', 'oliva',
                'want to know', 'more about', 'appointment', 'book', 'visit',
                'hair', 'skin', 'body', 'transplant', 'prp', 'fue', 'fut'
            ]
            
            # Check if message contains service-related content
            has_service_content = any(keyword in message_lower for keyword in service_keywords)
            
            # If we have an existing record and the user selected just a date/time via interactive UI,
            # proceed to update without requiring service keywords
            # Compute simple flags
            has_any_apt_field = bool(
                appointment_info.get('appointment_date') or appointment_info.get('appointment_time')
            )

            if has_service_content or appointment_info['is_appointment_booked'] or appointment_info['treatment_type'] or has_any_apt_field or message_lower:
                from schemas.referrer_schema import ReferrerTrackingCreate
                from services.customer_service import get_or_create_customer
                from schemas.customer_schema import CustomerCreate

                customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name="Unknown"))

                # Get (or infer) center/location for this message
                center_info = ReferrerService.detect_center_from_message(message_body, referrer_url)

                # Strict single-record policy per wa_id: always use the oldest record if present,
                # never create additional rows once one exists. Only create when none exists.
                oldest: Optional[ReferrerTracking] = (
                    db.query(ReferrerTracking)
                    .filter(ReferrerTracking.wa_id == wa_id)
                    .order_by(ReferrerTracking.created_at.asc())
                    .first()
                )
                should_create_new = oldest is None

                if should_create_new:
                    # Create a seed record for this flow (take center/location from this first message)
                    referrer_data = ReferrerTrackingCreate(
                        wa_id=wa_id,
                        center_name=center_info['center_name'],
                        location=center_info['location'],
                        customer_id=customer.id,
                        appointment_date=appointment_info['appointment_date'],
                        appointment_time=appointment_info['appointment_time'],
                        treatment_type=appointment_info['treatment_type'],
                        is_appointment_booked=appointment_info['is_appointment_booked']
                    )
                    new_referrer = ReferrerService.create_referrer_tracking(db, referrer_data)
                    print(
                        f"Created referrer record for {wa_id} - Center: {new_referrer.center_name}, "
                        f"Location: {new_referrer.location}, Treatment: {new_referrer.treatment_type}"
                    )
                    return new_referrer
                else:
                    # Subsequent messages: update missing or new info only
                    updated = False
                    # Only improve center/location; never downgrade to generic
                    def _is_generic(ci: dict) -> bool:
                        return (ci.get('center_name') == 'Oliva Clinics' and ci.get('location') == 'Multiple Locations')

                    # If record has generic center, and we detect specific center in this message, upgrade it
                    if (oldest.center_name in (None, "", 'Oliva Clinics')) and center_info.get('center_name') and not _is_generic(center_info):
                        oldest.center_name = center_info['center_name']
                        updated = True
                    if (oldest.location in (None, "", 'Multiple Locations')) and center_info.get('location') and not _is_generic(center_info):
                        oldest.location = center_info['location']
                        updated = True
                    # Update treatment immediately when detected (not only on finalization)
                    def _is_generic_treatment(txt: Optional[str]) -> bool:
                        if not txt:
                            return True
                        try:
                            t = txt.strip().lower()
                            return t.startswith('general') or t in {'services', 'service'}
                        except Exception:
                            return False

                    if appointment_info.get('treatment_type'):
                        if (not oldest.treatment_type) or _is_generic_treatment(oldest.treatment_type) or (oldest.treatment_type != appointment_info['treatment_type']):
                            oldest.treatment_type = appointment_info['treatment_type']
                            updated = True
                    # First, allow interim updates (date-only or time-only) without marking booked
                    # Date-only update
                    if appointment_info.get('appointment_date') and not oldest.appointment_date:
                        try:
                            from datetime import datetime as _dt
                            for _fmt in [
                                "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
                                "%d %B %Y", "%B %d, %Y", "%d %b %Y"
                            ]:
                                try:
                                    oldest.appointment_date = _dt.strptime(appointment_info['appointment_date'], _fmt)
                                    updated = True
                                    break
                                except ValueError:
                                    continue
                            if not oldest.appointment_date:
                                # As a last resort, keep it unset rather than writing a bad value
                                pass
                        except Exception:
                            pass
                    # Time-only update
                    if appointment_info.get('appointment_time') and not oldest.appointment_time:
                        oldest.appointment_time = appointment_info['appointment_time']
                        updated = True

                    # Only persist finalization when booking is confirmed (both date and time present)
                    booking_ready = bool(appointment_info.get('appointment_date') and appointment_info.get('appointment_time'))
                    if appointment_info.get('is_appointment_booked') or booking_ready:
                        # treatment can be optional; we may have set it above; ensure it remains if already set
                        if appointment_info.get('treatment_type'):
                            if (not oldest.treatment_type) or _is_generic_treatment(oldest.treatment_type) or (oldest.treatment_type != appointment_info['treatment_type']):
                                oldest.treatment_type = appointment_info['treatment_type']
                                updated = True
                        # Normalize and set date/time via helper (also sets is_appointment_booked True)
                        if booking_ready and (not oldest.appointment_date or not oldest.appointment_time):
                            try:
                                _ = ReferrerService.update_appointment_booking(
                                    db,
                                    wa_id,
                                    appointment_info['appointment_date'],
                                    appointment_info.get('appointment_time') or '',
                                    appointment_info.get('treatment_type') or oldest.treatment_type or ''
                                )
                                updated = True
                            except Exception:
                                pass
                        if not oldest.is_appointment_booked:
                            oldest.is_appointment_booked = True
                            updated = True

                    if updated:
                        try:
                            db.commit()
                            db.refresh(oldest)
                        except Exception:
                            db.rollback()
                        print(
                            f"Updated referrer record for {wa_id} - Center: {oldest.center_name}, "
                            f"Location: {oldest.location}, Treatment: {oldest.treatment_type}"
                        )
                    return oldest

            # Otherwise, skip creating a row for this message
            print(f"No service-related content found for wa_id={wa_id}; skipping create for this message")
            return None
                
        except Exception as e:
            print(f"Error tracking message interaction: {e}")
            import traceback
            traceback.print_exc()
            return None


referrer_service = ReferrerService()
