# Organization ID Migration Summary

## Overview
This migration adds `organization_id` column to all necessary tables in the database to enable complete multi-tenancy support.

## Migration File
`alembic/versions/add_organization_id_to_all_tables.py`

## Tables Updated

### Tables with organization_id added:

1. **messages** - Derives from `customers.organization_id`
2. **campaigns** - Derives from `users.organization_id` (via `created_by`)
3. **jobs** - Derives from `campaigns.organization_id`
4. **job_status** - Derives from `customers.organization_id`
5. **orders** - Derives from `customers.organization_id`
6. **order_items** - Derives from `orders.organization_id`
7. **payments** - Derives from `orders.organization_id`
8. **payment_transactions** - Derives from `orders.organization_id`
9. **referrer_tracking** - Derives from `customers.organization_id`
10. **customer_addresses** - Derives from `customers.organization_id`
11. **address_collection_sessions** - Derives from `customers.organization_id`
12. **templates** - Nullable (to be set manually)
13. **campaign_recipients** - Derives from `campaigns.organization_id`
14. **quick_replies** - Derives from `users.organization_id` (via `created_by`)
15. **leads** - Derives from `customers.organization_id`
16. **zoho_mappings** - Nullable (can be org-specific or shared)
17. **flow_logs** - Derives from `customers.organization_id` (via `wa_id`)
18. **campaign_logs** - Derives from `campaigns.organization_id`
19. **whatsapp_api_logs** - Nullable (derived from campaign/job if available)
20. **zoho_payload_logs** - Derives from `customers.organization_id` (via `wa_id`)
21. **number_flow_configs** - Nullable (linked via `phone_number_id` to `whatsapp_numbers`)

### Tables that already have organization_id:
- **users** ✓
- **customers** ✓
- **whatsapp_numbers** ✓

### Tables that don't need organization_id:
- **organizations** (this is the parent table)
- **roles** (system-wide, not org-specific)
- **categories/sub_categories** (can be shared or org-specific - TBD)
- **products** (can be shared or org-specific - TBD)
- **costs** (can be shared or org-specific - TBD)
- **files** (shared media files)

## Migration Features

1. **Idempotent**: Checks if column exists before adding
2. **Indexes**: Creates indexes on all `organization_id` columns for fast filtering
3. **Foreign Keys**: Creates foreign key constraints to `organizations.id`
4. **Data Migration**: Automatically migrates existing data by deriving `organization_id` from related tables
5. **Nullable**: All columns are nullable initially to handle existing data

## Running the Migration

```bash
cd wb-crm
alembic upgrade head
```

## Next Steps

1. **Update Models**: Add `organization_id` column definitions to SQLAlchemy models
2. **Update Services**: Modify service functions to filter by `organization_id`
3. **Update Controllers**: Add organization filtering to API endpoints
4. **Frontend**: Ensure frontend passes organization context to API calls

## Notes

- For tables with direct relationships (messages → customers, orders → customers), organization_id is derived directly
- For tables with indirect relationships (jobs → campaigns → users), organization_id is derived through the chain
- Some tables like `templates` and `zoho_mappings` are left nullable for manual assignment or shared use
- The migration handles existing data gracefully by deriving organization_id from related records

