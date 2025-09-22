# New Address Collection System

## Overview

This document describes the new address collection system implemented to replace the old manual address entry process. The new system follows the modern approach used by companies like JioMart, Blinkit, and Domino's, providing a better user experience with template-based interactions and multiple address collection methods.

## Key Features

### 1. **Template-Based Address Collection**
- Order confirmation templates with "Add Delivery Address" buttons
- Interactive address selection options
- Location sharing integration
- Saved address management

### 2. **Multiple Collection Methods**
- **Current Location**: GPS-based address collection
- **Manual Entry**: Simplified text-based entry
- **Saved Addresses**: Quick selection from previously saved addresses

### 3. **Smart Address Management**
- Address validation and verification
- Default address selection
- Address history and reuse
- Session-based collection tracking

## System Architecture

### Database Models

#### CustomerAddress
```python
class CustomerAddress(Base):
    id: UUID
    customer_id: UUID
    full_name: str
    house_street: str
    locality: str
    city: str
    state: str
    pincode: str
    landmark: Optional[str]
    phone: str
    latitude: Optional[float]
    longitude: Optional[float]
    address_type: str  # home, office, other
    is_default: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
```

#### AddressCollectionSession
```python
class AddressCollectionSession(Base):
    id: UUID
    customer_id: UUID
    order_id: Optional[UUID]
    status: str  # pending, collecting, completed, cancelled
    collection_method: str  # location, manual, saved
    session_data: JSONB
    created_at: datetime
    expires_at: datetime
    completed_at: Optional[datetime]
```

### Services

#### AddressCollectionService
Main service handling the address collection flow:
- `start_address_collection_after_order()`: Initiates address collection after order placement
- `handle_address_button_click()`: Processes button interactions
- `handle_location_message()`: Processes location sharing
- `handle_manual_address_text()`: Processes manual address entry

#### AddressService
Core address management operations:
- `create_customer_address()`: Creates new addresses
- `get_customer_addresses()`: Retrieves customer addresses
- `update_customer_address()`: Updates existing addresses
- `validate_address_data()`: Validates address information

### WhatsApp Templates

#### Order Confirmation Template
```json
{
  "name": "order_confirmation_address",
  "components": [
    {
      "type": "header",
      "parameters": [{"type": "text", "text": "🛍️ Order Confirmed!"}]
    },
    {
      "type": "body",
      "parameters": [
        {"type": "text", "text": "{{customer_name}}"},
        {"type": "text", "text": "₹{{order_total}}"},
        {"type": "text", "text": "{{item_count}} items"}
      ]
    },
    {
      "type": "button",
      "sub_type": "quick_reply",
      "parameters": [{"type": "payload", "payload": "ADD_DELIVERY_ADDRESS"}]
    }
  ]
}
```

#### Address Collection Options Template
```json
{
  "name": "address_collection_options",
  "components": [
    {
      "type": "header",
      "parameters": [{"type": "text", "text": "📍 Delivery Address"}]
    },
    {
      "type": "body",
      "parameters": [{"type": "text", "text": "Choose how you'd like to add your address"}]
    },
    {
      "type": "button",
      "sub_type": "quick_reply",
      "parameters": [{"type": "payload", "payload": "USE_CURRENT_LOCATION"}]
    },
    {
      "type": "button",
      "sub_type": "quick_reply",
      "parameters": [{"type": "payload", "payload": "ENTER_NEW_ADDRESS"}]
    }
  ]
}
```

## User Flow

### 1. Order Placement
1. Customer places order via WhatsApp catalog
2. System creates order in database
3. **NEW**: Order confirmation template sent with "Add Delivery Address" button

### 2. Address Collection Options
When customer clicks "Add Delivery Address":
1. System shows address collection options:
   - "Use Current Location" (if GPS available)
   - "Enter New Address" (manual entry)
   - "Use Saved Address" (if addresses exist)

### 3. Address Collection Methods

#### Current Location Method
1. Customer clicks "Use Current Location"
2. System requests location sharing
3. Customer shares location via WhatsApp
4. System processes location and creates address
5. Address confirmation template sent

#### Manual Entry Method
1. Customer clicks "Enter New Address"
2. System sends simplified address format template
3. Customer enters address in text format
4. System validates and processes address
5. Address confirmation template sent

#### Saved Address Method
1. Customer clicks "Use Saved Address"
2. System shows interactive list of saved addresses
3. Customer selects preferred address
4. Address confirmation template sent

### 4. Address Confirmation
1. System sends address confirmation template
2. Customer confirms or changes address
3. Address saved to database
4. Order processing continues

## Integration Points

### WebSocket Controller Updates
The `controllers/web_socket.py` has been updated to:
- Integrate new address collection system in order flow
- Handle address collection button clicks
- Process location messages for address collection
- Handle manual address text entry

### API Endpoints
New endpoints available at `/address/`:
- `POST /address/` - Create new address
- `GET /address/customer/{customer_id}` - Get customer addresses
- `PUT /address/{address_id}` - Update address
- `DELETE /address/{address_id}` - Delete address
- `POST /address/collection/session` - Create collection session
- `POST /address/validate` - Validate address data

## Migration from Old System

### Backward Compatibility
The new system maintains backward compatibility:
- Old address collection logic remains as fallback
- Existing customer addresses are preserved
- Gradual migration possible

### Migration Steps
1. **Database Migration**: Run the generated Alembic migration
2. **Template Creation**: Create WhatsApp templates in Meta Business Manager
3. **Testing**: Test the new flow with sample orders
4. **Rollout**: Gradually enable new system for customers
5. **Cleanup**: Remove old address collection logic after successful migration

## Benefits

### For Customers
- **Better UX**: Template-based interactions instead of manual text entry
- **Multiple Options**: Choose preferred address collection method
- **Faster Process**: Quick selection from saved addresses
- **Location Integration**: Easy GPS-based address collection

### For Business
- **Reduced Drop-offs**: Better UX reduces order abandonment
- **Address Quality**: Improved validation and verification
- **Data Management**: Better address storage and management
- **Analytics**: Track address collection success rates

## Configuration

### Environment Variables
No additional environment variables required. The system uses existing:
- Database connection
- WhatsApp API credentials
- OpenAI API for address validation

### Template Setup
Templates need to be created in Meta Business Manager:
1. `order_confirmation_address`
2. `address_collection_options`
3. `location_request`
4. `manual_address_entry`
5. `address_confirmation`
6. `address_saved`
7. `address_error`

## Testing

### Test Scenarios
1. **Order Placement**: Test complete order flow with new address collection
2. **Location Sharing**: Test GPS-based address collection
3. **Manual Entry**: Test text-based address entry
4. **Saved Addresses**: Test address selection from saved addresses
5. **Error Handling**: Test validation errors and retry flows

### Test Data
Use the provided test endpoints to:
- Create test addresses
- Simulate address collection sessions
- Test validation logic

## Monitoring

### Key Metrics
- Address collection completion rate
- Method preference (location vs manual vs saved)
- Validation error rates
- Session timeout rates

### Logging
The system logs:
- Address collection session creation/completion
- Validation errors and suggestions
- Template message sending
- Location processing results

## Future Enhancements

### Planned Features
1. **Address Verification**: Integration with address verification APIs
2. **Delivery Time Estimation**: Based on address location
3. **Address Suggestions**: Auto-complete for manual entry
4. **Multi-language Support**: Templates in multiple languages
5. **Address Analytics**: Detailed address collection analytics

### Integration Opportunities
1. **Maps Integration**: Google Maps/OpenStreetMap integration
2. **Delivery Partners**: Integration with delivery service APIs
3. **Address Validation**: Third-party address validation services
4. **Geocoding**: Reverse geocoding for location addresses

## Troubleshooting

### Common Issues
1. **Template Not Found**: Ensure templates are created in Meta Business Manager
2. **Session Expired**: Address collection sessions expire after 30 minutes
3. **Validation Errors**: Check address format and required fields
4. **Location Processing**: Verify GPS coordinates are valid

### Debug Endpoints
- `GET /address/collection/session/{session_id}` - Check session status
- `POST /address/cleanup` - Clean up expired sessions
- `POST /address/validate` - Test address validation

## Conclusion

The new address collection system provides a modern, user-friendly approach to address collection that matches industry standards. It reduces friction in the ordering process while maintaining data quality and providing better analytics for business optimization.

The system is designed to be:
- **Scalable**: Handles high volume of address collections
- **Reliable**: Fallback mechanisms ensure continuity
- **Maintainable**: Clean separation of concerns and modular design
- **Extensible**: Easy to add new features and integrations
