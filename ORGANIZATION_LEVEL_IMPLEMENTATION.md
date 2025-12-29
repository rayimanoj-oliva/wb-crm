# WhatsApp Project - Organization Level Implementation Guide

## Overview

This document explains how the WhatsApp Business API system is implemented at an organization level, allowing multiple organizations to use the same platform while keeping their data completely isolated.

## Architecture Overview

### 1. Multi-Tenancy Model

```
┌─────────────────────────────────────────────────────────────┐
│                    Super Admin Portal                        │
│  • Manages Organizations                                    │
│  • Manages Users & Roles                                    │
│  • Views All Data (Optional)                                │
└─────────────────────────────────────────────────────────────┘
                            │
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
┌───────▼──────────┐                  ┌─────────▼──────────┐
│  Organization 1  │                  │  Organization 2    │
│  (Oliva)         │                  │  (Test Org)        │
│                  │                  │                    │
│  • WhatsApp #1   │                  │  • WhatsApp #4     │
│  • WhatsApp #2   │                  │  • WhatsApp #5     │
│  • WhatsApp #3   │                  │                    │
│                  │                  │                    │
│  • Users         │                  │  • Users           │
│  • Customers     │                  │  • Customers       │
│  • Campaigns     │                  │  • Campaigns       │
│  • Messages      │                  │  • Messages        │
└──────────────────┘                  └────────────────────┘
```

## Core Components

### 1. Organization Structure

**Database Model: Organization**
- `id` (UUID) - Primary key
- `name` - Organization name (e.g., "Oliva Skin Hair Body Clinic")
- `code` - Unique code (e.g., "OLIVA001")
- `slug` - URL-friendly identifier (e.g., "oliva")
- `is_active` - Enable/disable organization

**Key Relationships:**
- Organization → Users (1-to-many)
- Organization → WhatsApp Numbers (1-to-many)
- Organization → Customers (1-to-many, through `organization_id`)

### 2. WhatsApp Number Mapping

**How it works:**
- Each WhatsApp Business phone number is mapped to one organization
- When a message comes in via webhook, the system:
  1. Extracts `phone_number_id` from webhook payload
  2. Looks up which organization owns this phone number
  3. Automatically assigns the customer to that organization

**Database Model: WhatsAppNumber**
```
phone_number_id (Meta's ID) → organization_id
Example:
  "367633743092037" → Oliva Organization ID
  "848542381673826" → Oliva Organization ID
  "859830643878412" → Oliva Organization ID
```

### 3. User Roles & Access Control

**Three-Tier Role System:**

1. **SUPER_ADMIN**
   - Can see ALL organizations
   - Can create/manage organizations
   - Can create/manage users across all organizations
   - Full system access

2. **ORG_ADMIN**
   - Can only see their own organization
   - Can manage users within their organization
   - Can manage campaigns, templates, etc. for their org
   - Cannot see other organizations' data

3. **AGENT**
   - Can only see customers assigned to them
   - Can send messages to customers in their organization
   - Limited access, primarily customer conversations

### 4. Data Isolation

**How data is filtered by organization:**

#### Customers
```python
# All customers have organization_id
Customer.organization_id = organization.id

# Filtering customers
customers = db.query(Customer).filter(
    Customer.organization_id == org_id
).all()
```

#### Messages
```python
# Messages are linked to customers, which are linked to organizations
messages = db.query(Message).join(Customer).filter(
    Customer.organization_id == org_id
).all()
```

#### Campaigns
```python
# Campaigns are created by users, who belong to organizations
campaigns = db.query(Campaign).join(User).filter(
    User.organization_id == org_id
).all()
```

## Implementation Flow

### Step 1: Setup Organization

1. **Create Organization** (Super Admin)
   ```bash
   POST /organizations/
   {
     "name": "Oliva Skin Hair Body Clinic",
     "code": "OLIVA001",
     "slug": "oliva",
     "description": "Main Oliva clinic",
     "is_active": true
   }
   ```

2. **Create Org Admin User** (Super Admin)
   ```bash
   POST /users/
   {
     "username": "oliva_admin",
     "email": "admin@oliva.com",
     "organization_id": "<oliva_org_id>",
     "role_id": "<org_admin_role_id>",
     ...
   }
   ```

### Step 2: Map WhatsApp Numbers

1. **Add WhatsApp Numbers to Organization** (Super Admin or Org Admin)
   ```bash
   POST /whatsapp-numbers/
   {
     "phone_number_id": "367633743092037",
     "display_number": "+91 77299 92376",
     "access_token": "EAAcbHJk...",
     "webhook_path": "/webhook",
     "organization_id": "<oliva_org_id>",
     "is_active": true
   }
   ```

2. **Configure Meta Webhook**
   - Go to Meta Business Manager
   - Set webhook URL: `https://yourdomain.com/webhook`
   - Configure for each phone number

### Step 3: Automatic Customer Assignment

**When a message arrives:**

```python
# 1. Webhook receives message
POST /webhook
{
  "entry": [{
    "changes": [{
      "value": {
        "metadata": {
          "phone_number_id": "367633743092037"  # From Oliva
        },
        "messages": [...],
        "contacts": [...]
      }
    }]
  }]
}

# 2. System looks up organization
organization = get_organization_by_phone_id(db, "367633743092037")
# Returns: Oliva Organization

# 3. Creates/updates customer with organization_id
customer = get_or_create_customer(
    db,
    CustomerCreate(wa_id="918309866859", name="John"),
    organization_id=organization.id  # Automatically set to Oliva
)

# 4. Message is saved with customer reference
message = create_message(db, MessageCreate(
    customer_id=customer.id,  # Customer already has organization_id
    ...
))
```

### Step 4: Organization-Scoped Queries

**Dashboard Filtering:**
```python
# When user selects organization filter
GET /dashboard/summary?organization_id=<oliva_org_id>

# Backend filters:
- Customers: WHERE organization_id = <oliva_org_id>
- Messages: JOIN customers WHERE organization_id = <oliva_org_id>
- Campaigns: JOIN users WHERE organization_id = <oliva_org_id>
```

**Conversations List:**
```python
# Automatically filtered by user's organization
# Org Admin can only see their organization's customers
GET /conversations/
# Backend filters by current_user.organization_id
```

## Data Flow Diagram

```
┌──────────────┐
│   Customer   │
│   Messages   │
│  WhatsApp #1 │
└──────┬───────┘
       │
       │ Webhook POST /webhook
       ▼
┌─────────────────────────────────┐
│  Extract phone_number_id        │
│  "367633743092037"              │
└──────┬──────────────────────────┘
       │
       │ Lookup: WhatsAppNumber table
       ▼
┌─────────────────────────────────┐
│  phone_number_id →              │
│  organization_id = "Oliva"      │
└──────┬──────────────────────────┘
       │
       │ Create/Update Customer
       ▼
┌─────────────────────────────────┐
│  Customer {                     │
│    wa_id: "918309866859",       │
│    organization_id: "Oliva"     │  ← Automatically set
│  }                              │
└──────┬──────────────────────────┘
       │
       │ All future queries filtered by organization_id
       ▼
┌─────────────────────────────────┐
│  Dashboard shows only           │
│  Oliva's customers, messages,   │
│  campaigns, etc.                │
└─────────────────────────────────┘
```

## Key Features

### 1. Automatic Organization Assignment
- Customers are automatically assigned to the correct organization based on which WhatsApp number they message
- No manual assignment needed

### 2. Complete Data Isolation
- Each organization sees only their own data
- No cross-organization data leakage
- Secure and compliant

### 3. Scalable Architecture
- Easy to add new organizations
- Each organization can have multiple WhatsApp numbers
- Supports unlimited organizations

### 4. Role-Based Access Control
- Super Admin: Full access
- Org Admin: Manage their organization
- Agent: Limited to assigned customers

## Best Practices

### 1. Organization Setup

**For New Organizations:**
1. Create organization in database
2. Create at least one Org Admin user
3. Map WhatsApp numbers to organization
4. Configure webhooks in Meta Business Manager
5. Test with a sample message

### 2. WhatsApp Number Management

**Guidelines:**
- One phone number can only belong to one organization
- Multiple phone numbers can belong to the same organization
- Phone numbers can be activated/deactivated per organization
- Keep access tokens secure and rotated regularly

### 3. User Management

**Recommendations:**
- Assign users to specific organizations
- Use role-based permissions appropriately
- Regularly audit user access
- Implement user activity logging

### 4. Data Migration

**For Existing Data:**
If you have existing customers/messages that need to be assigned to organizations:

```python
# Script to update existing customers
def migrate_existing_customers_to_organization():
    # Find customers without organization_id
    customers = db.query(Customer).filter(
        Customer.organization_id == None
    ).all()
    
    # Assign to default organization (e.g., Oliva)
    oliva_org = get_organization_by_name("Oliva")
    
    for customer in customers:
        # Determine organization based on phone number used
        # or assign to default organization
        customer.organization_id = oliva_org.id
    
    db.commit()
```

## API Endpoints Summary

### Organizations
- `GET /organizations/` - List organizations (filtered by role)
- `POST /organizations/` - Create organization (Super Admin only)
- `GET /organizations/{id}` - Get organization details
- `PATCH /organizations/{id}` - Update organization
- `DELETE /organizations/{id}` - Delete organization (soft delete)

### WhatsApp Numbers
- `GET /whatsapp-numbers/` - List WhatsApp numbers (filtered by organization)
- `POST /whatsapp-numbers/` - Map phone number to organization
- `GET /whatsapp-numbers/{id}` - Get WhatsApp number details
- `PATCH /whatsapp-numbers/{id}` - Update WhatsApp number
- `DELETE /whatsapp-numbers/{id}` - Remove mapping

### Dashboard (Organization-Filtered)
- `GET /dashboard/summary?organization_id={id}` - Get dashboard data for organization
- All metrics automatically filtered by organization_id

## Security Considerations

1. **Authentication & Authorization**
   - JWT tokens with role information
   - Role-based access control on all endpoints
   - Organization-scoped queries enforced at service layer

2. **Data Isolation**
   - Never trust client-provided organization_id
   - Always validate user's organization access
   - Use server-side filtering, not client-side

3. **API Security**
   - Rate limiting per organization
   - Webhook signature verification
   - Secure token storage

## Future Enhancements

1. **Billing & Subscription**
   - Track usage per organization
   - Implement per-organization billing
   - Usage limits per organization

2. **Organization-Level Settings**
   - Custom branding per organization
   - Organization-specific templates
   - Custom workflows per organization

3. **Advanced Analytics**
   - Organization-level reports
   - Cross-organization comparisons (Super Admin only)
   - Export capabilities per organization

4. **Multi-Currency Support**
   - Organization-specific currency settings
   - Localized pricing

## Testing Checklist

- [ ] Create new organization
- [ ] Map WhatsApp numbers to organization
- [ ] Create users in organization
- [ ] Send test message via webhook
- [ ] Verify customer assigned to correct organization
- [ ] Verify dashboard shows only organization's data
- [ ] Test role-based access (Super Admin vs Org Admin)
- [ ] Verify data isolation (Org Admin cannot see other orgs)
- [ ] Test multiple organizations simultaneously
- [ ] Verify webhook routing works correctly

## Troubleshooting

### Issue: Customers not assigned to organization
**Solution:** Check that:
1. WhatsApp numbers are mapped to organization in database
2. Webhook is extracting `phone_number_id` correctly
3. `get_organization_by_phone_id()` is working
4. Customer creation is using the organization_id

### Issue: Dashboard showing all organizations' data
**Solution:** Check that:
1. Dashboard queries are filtering by `organization_id`
2. User's organization_id is correctly set
3. Role-based filtering is working

### Issue: Webhook not routing correctly
**Solution:** Check that:
1. Webhook path is correctly configured
2. Phone numbers are mapped in database
3. Meta webhook configuration is correct

## Conclusion

This organization-level implementation provides:
- ✅ Complete data isolation
- ✅ Scalable multi-tenant architecture
- ✅ Automatic organization assignment
- ✅ Role-based access control
- ✅ Easy to add new organizations
- ✅ Secure and compliant

The system is designed to scale from a single organization (Oliva) to multiple organizations while maintaining data integrity and security.

