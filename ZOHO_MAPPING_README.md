# Zoho Mapping System

## Overview

The Zoho Mapping System allows you to map treatment concerns selected by users in the WhatsApp treatment flow to corresponding Zoho CRM names. When a lead is created after an appointment is captured, the system automatically maps the selected concern to its Zoho name and saves it in the lead.

## Database Schema

### ZohoMapping Table

The system uses a `zoho_mappings` table with the following fields:

- `id` (UUID): Primary key
- `treatment_name` (String): The treatment/concern name as displayed in the WhatsApp flow (unique, indexed)
- `zoho_name` (String): The corresponding Zoho CRM name
- `zoho_sub_concern` (String, optional): The Zoho sub-concern name
- `created_at` (DateTime): Timestamp when the mapping was created
- `updated_at` (DateTime): Timestamp when the mapping was last updated

## How It Works

### 1. Treatment Selection Flow

When a user selects a concern from the treatment list (e.g., "Acne / Acne Scars", "Pigmentation & Uneven Skin Tone"), the system:

1. Stores the selected concern in `appointment_state` for the user's WhatsApp ID
2. Displays the booking options (Book an Appointment or Request a Call Back)

### 2. Lead Creation with Mapping

When creating a lead in Zoho CRM after the appointment is captured:

1. Retrieves the selected concern from `appointment_state`
2. Looks up the Zoho mapping in the `zoho_mappings` table
3. Uses the mapped Zoho name in the lead description
4. If no mapping exists, falls back to the original treatment name

### 3. Lead Description Format

The lead description includes:
- City, Clinic, Appointment details
- **Treatment/Zoho Concern**: The mapped Zoho name (if mapping exists)
- **Treatment**: The original treatment name (if no mapping exists)
- Additional preferences and status

## Managing Zoho Mappings

### View All Mappings

Use the API endpoint to list all mappings:

```bash
GET /zoho-mappings
```

### Create a New Mapping

```bash
POST /zoho-mappings
{
    "treatment_name": "Your Treatment Name",
    "zoho_name": "Corresponding Zoho Name",
    "zoho_sub_concern": "Optional Sub-Concern"
}
```

### Update an Existing Mapping

```bash
PUT /zoho-mappings/{treatment_name}
{
    "zoho_name": "Updated Zoho Name",
    "zoho_sub_concern": "Updated Sub-Concern"
}
```

### Lookup Zoho Name

```bash
GET /zoho-mappings/lookup/{treatment_name}
```

## Seeding Initial Data

To populate the initial Zoho mappings, run:

```bash
python seed_zoho_mappings.py
```

This script creates mappings based on the provided Zoho mapping tables, including:

- **Skin Concerns**: Acne, Pigmentation, Anti-Aging, Laser Hair Removal, etc.
- **Hair Concerns**: Hair Loss, Hair Transplant, Dandruff, etc.
- **Body Concerns**: Weight Management, Body Contouring, etc.
- **Additional Treatments**: Botox, Fillers, Skin Tightening, etc.

## Files Modified

1. **models/models.py**: Added `ZohoMapping` model
2. **controllers/web_socket.py**: Added logic to store selected concern
3. **controllers/components/lead_appointment_flow/zoho_lead_service.py**: Added Zoho mapping lookup during lead creation
4. **services/zoho_mapping_service.py**: Service for Zoho mapping operations
5. **controllers/components/zoho_mapping_controller.py**: API endpoints for managing mappings

## Migration

The database migration was created and applied:

```bash
alembic revision --autogenerate -m "add_zoho_mapping_table"
alembic upgrade head
```

## Example Flow

1. User receives treatment options: Skin, Hair, Body
2. User selects "Skin" → receives list of skin concerns
3. User selects "Acne / Acne Scars"
4. System stores "Acne / Acne Scars" in `appointment_state`
5. User proceeds with appointment booking
6. Lead is created with:
   - **Treatment/Zoho Concern**: "Acne" (mapped from "Acne / Acne Scars")
   - Original treatment name is also stored for reference

## Configuration

The mapping is case-insensitive and supports variations in treatment names. If an exact match is not found, the system falls back to the original treatment name.

## Testing

To test the mapping system:

1. Select a treatment concern in the WhatsApp flow
2. Complete the appointment booking process
3. Check the Zoho CRM lead to verify the mapped concern name is included in the description

