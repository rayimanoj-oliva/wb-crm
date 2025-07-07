from .zenoti_client import search_guest_by_phone



async def get_guest_details(phone: str):
    full_response = await search_guest_by_phone(phone)
    guests = full_response.get("guests", [])
    
    # Handle the case where no guests are found
    if not guests:
        return {"address_info": None}
    
    # Return only address_info field
    address_info = guests[0].get("address_info", None)
    return {"address_info": address_info}
