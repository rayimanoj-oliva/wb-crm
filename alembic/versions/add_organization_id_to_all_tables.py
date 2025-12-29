"""Add organization_id to all necessary tables for multi-tenancy

Revision ID: add_org_id_to_all_tables
Revises: add_whatsapp_numbers
Create Date: 2024-12-29 15:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'add_org_id_to_all_tables'
down_revision: Union[str, None] = 'add_whatsapp_numbers'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    
    # List of tables and how to derive organization_id for existing data
    # Format: (table_name, column_name, nullable, derive_from_table, derive_from_column)
    tables_to_update = [
        # Messages - derive from customers.organization_id
        ('messages', 'organization_id', True, 'customers', 'organization_id'),
        # Campaigns - derive from users.organization_id (via created_by)
        ('campaigns', 'organization_id', True, 'users', 'organization_id'),
        # Jobs - derive from campaigns.organization_id
        ('jobs', 'organization_id', True, 'campaigns', 'organization_id'),
        # JobStatus - derive from customers.organization_id
        ('job_status', 'organization_id', True, 'customers', 'organization_id'),
        # Orders - derive from customers.organization_id
        ('orders', 'organization_id', True, 'customers', 'organization_id'),
        # OrderItems - derive from orders.organization_id
        ('order_items', 'organization_id', True, 'orders', 'organization_id'),
        # Payments - derive from orders.organization_id
        ('payments', 'organization_id', True, 'orders', 'organization_id'),
        # PaymentTransactions - derive from orders.organization_id
        ('payment_transactions', 'organization_id', True, 'orders', 'organization_id'),
        # ReferrerTracking - derive from customers.organization_id
        ('referrer_tracking', 'organization_id', True, 'customers', 'organization_id'),
        # CustomerAddresses - derive from customers.organization_id
        ('customer_addresses', 'organization_id', True, 'customers', 'organization_id'),
        # AddressCollectionSessions - derive from customers.organization_id
        ('address_collection_sessions', 'organization_id', True, 'customers', 'organization_id'),
        # Templates - nullable (no direct link, will be set manually)
        ('templates', 'organization_id', True, None, None),
        # CampaignRecipients - derive from campaigns.organization_id
        ('campaign_recipients', 'organization_id', True, 'campaigns', 'organization_id'),
        # QuickReplies - derive from users.organization_id (via created_by)
        ('quick_replies', 'organization_id', True, 'users', 'organization_id'),
        # Leads - derive from customers.organization_id
        ('leads', 'organization_id', True, 'customers', 'organization_id'),
        # ZohoMappings - nullable (can be org-specific or shared)
        ('zoho_mappings', 'organization_id', True, None, None),
        # FlowLogs - derive from customers.organization_id (via wa_id)
        ('flow_logs', 'organization_id', True, 'customers', 'organization_id'),
        # CampaignLogs - derive from campaigns.organization_id
        ('campaign_logs', 'organization_id', True, 'campaigns', 'organization_id'),
        # WhatsAppAPILog - nullable (derived from campaign/job if available)
        ('whatsapp_api_logs', 'organization_id', True, None, None),
        # ZohoPayloadLog - derive from customers.organization_id (via wa_id)
        ('zoho_payload_logs', 'organization_id', True, 'customers', 'organization_id'),
        # NumberFlowConfigs - nullable (linked via phone_number_id to whatsapp_numbers)
        ('number_flow_configs', 'organization_id', True, None, None),
    ]
    
    for table_name, column_name, nullable, derive_from_table, derive_from_column in tables_to_update:
        try:
            existing_tables = inspector.get_table_names()
            if table_name not in existing_tables:
                print(f"Skipping {table_name} - table does not exist")
                continue
            
            existing_columns = [col["name"] for col in inspector.get_columns(table_name)]
            
            if column_name not in existing_columns:
                # Add the column
                op.add_column(table_name, sa.Column(column_name, UUID(as_uuid=True), nullable=nullable))
                print(f"Added {column_name} to {table_name}")
                
                # Create index
                try:
                    op.create_index(f'ix_{table_name}_{column_name}', table_name, [column_name])
                except Exception as e:
                    print(f"Index might already exist for {table_name}.{column_name}: {e}")
                
                # Create foreign key
                try:
                    op.create_foreign_key(
                        f'fk_{table_name}_{column_name}',
                        table_name,
                        'organizations',
                        [column_name],
                        ['id']
                    )
                except Exception as e:
                    print(f"Foreign key might already exist for {table_name}.{column_name}: {e}")
                
                # Migrate existing data - using proper SQL with joins
                if derive_from_table and derive_from_column:
                    try:
                        # Build migration SQL based on table relationships
                        if table_name == 'messages' and derive_from_table == 'customers':
                            op.execute(f"""
                                UPDATE {table_name} m
                                SET {column_name} = c.{derive_from_column}
                                FROM {derive_from_table} c
                                WHERE m.customer_id = c.id
                            """)
                        elif table_name == 'campaigns' and derive_from_table == 'users':
                            op.execute(f"""
                                UPDATE {table_name} ca
                                SET {column_name} = u.{derive_from_column}
                                FROM {derive_from_table} u
                                WHERE ca.created_by = u.id
                            """)
                        elif table_name == 'jobs' and derive_from_table == 'campaigns':
                            op.execute(f"""
                                UPDATE {table_name} j
                                SET {column_name} = ca.{derive_from_column}
                                FROM {derive_from_table} ca
                                WHERE j.campaign_id = ca.id
                            """)
                        elif table_name == 'job_status' and derive_from_table == 'customers':
                            op.execute(f"""
                                UPDATE {table_name} js
                                SET {column_name} = c.{derive_from_column}
                                FROM {derive_from_table} c
                                WHERE js.customer_id = c.id
                            """)
                        elif table_name == 'orders' and derive_from_table == 'customers':
                            op.execute(f"""
                                UPDATE {table_name} o
                                SET {column_name} = c.{derive_from_column}
                                FROM {derive_from_table} c
                                WHERE o.customer_id = c.id
                            """)
                        elif table_name == 'order_items' and derive_from_table == 'orders':
                            op.execute(f"""
                                UPDATE {table_name} oi
                                SET {column_name} = o.{derive_from_column}
                                FROM {derive_from_table} o
                                WHERE oi.order_id = o.id
                            """)
                        elif table_name == 'payments' and derive_from_table == 'orders':
                            op.execute(f"""
                                UPDATE {table_name} p
                                SET {column_name} = o.{derive_from_column}
                                FROM {derive_from_table} o
                                WHERE p.order_id = o.id
                            """)
                        elif table_name == 'payment_transactions' and derive_from_table == 'orders':
                            op.execute(f"""
                                UPDATE {table_name} pt
                                SET {column_name} = o.{derive_from_column}
                                FROM {derive_from_table} o
                                WHERE pt.order_id = o.id
                            """)
                        elif table_name == 'referrer_tracking' and derive_from_table == 'customers':
                            op.execute(f"""
                                UPDATE {table_name} rt
                                SET {column_name} = c.{derive_from_column}
                                FROM {derive_from_table} c
                                WHERE rt.customer_id = c.id
                            """)
                        elif table_name == 'customer_addresses' and derive_from_table == 'customers':
                            op.execute(f"""
                                UPDATE {table_name} ca
                                SET {column_name} = c.{derive_from_column}
                                FROM {derive_from_table} c
                                WHERE ca.customer_id = c.id
                            """)
                        elif table_name == 'address_collection_sessions' and derive_from_table == 'customers':
                            op.execute(f"""
                                UPDATE {table_name} acs
                                SET {column_name} = c.{derive_from_column}
                                FROM {derive_from_table} c
                                WHERE acs.customer_id = c.id
                            """)
                        elif table_name == 'campaign_recipients' and derive_from_table == 'campaigns':
                            op.execute(f"""
                                UPDATE {table_name} cr
                                SET {column_name} = ca.{derive_from_column}
                                FROM {derive_from_table} ca
                                WHERE cr.campaign_id = ca.id
                            """)
                        elif table_name == 'quick_replies' and derive_from_table == 'users':
                            op.execute(f"""
                                UPDATE {table_name} qr
                                SET {column_name} = u.{derive_from_column}
                                FROM {derive_from_table} u
                                WHERE qr.created_by = u.id
                            """)
                        elif table_name == 'leads' and derive_from_table == 'customers':
                            op.execute(f"""
                                UPDATE {table_name} l
                                SET {column_name} = c.{derive_from_column}
                                FROM {derive_from_table} c
                                WHERE l.customer_id = c.id
                            """)
                        elif table_name == 'flow_logs' and derive_from_table == 'customers':
                            # Pick first matching customer's organization_id (use array_agg with ORDER BY to pick first)
                            op.execute(f"""
                                UPDATE {table_name} fl
                                SET {column_name} = (
                                    SELECT (array_agg({derive_from_column} ORDER BY created_at DESC))[1]
                                    FROM {derive_from_table}
                                    WHERE {derive_from_table}.wa_id = fl.wa_id
                                        AND {derive_from_column} IS NOT NULL
                                )
                            """)
                        elif table_name == 'campaign_logs' and derive_from_table == 'campaigns':
                            op.execute(f"""
                                UPDATE {table_name} cl
                                SET {column_name} = ca.{derive_from_column}
                                FROM {derive_from_table} ca
                                WHERE cl.campaign_id = ca.id
                            """)
                        elif table_name == 'zoho_payload_logs' and derive_from_table == 'customers':
                            # Pick first matching customer's organization_id (use array_agg with ORDER BY to pick first)
                            op.execute(f"""
                                UPDATE {table_name} zpl
                                SET {column_name} = (
                                    SELECT (array_agg({derive_from_column} ORDER BY created_at DESC))[1]
                                    FROM {derive_from_table}
                                    WHERE {derive_from_table}.wa_id = zpl.wa_id
                                        AND {derive_from_column} IS NOT NULL
                                )
                            """)
                        
                        print(f"Migrated existing data for {table_name}.{column_name}")
                    except Exception as e:
                        print(f"Warning: Could not migrate existing data for {table_name}.{column_name}: {e}")
            else:
                print(f"{column_name} already exists in {table_name}")
        except Exception as e:
            print(f"Error processing {table_name}: {e}")


def downgrade() -> None:
    """Remove organization_id from all tables"""
    tables_to_downgrade = [
        'messages', 'campaigns', 'jobs', 'job_status', 'orders', 'order_items',
        'payments', 'payment_transactions', 'referrer_tracking', 'customer_addresses',
        'address_collection_sessions', 'templates', 'campaign_recipients', 'quick_replies',
        'leads', 'zoho_mappings', 'flow_logs', 'campaign_logs', 'whatsapp_api_logs',
        'zoho_payload_logs', 'number_flow_configs'
    ]
    
    bind = op.get_bind()
    inspector = inspect(bind)
    
    for table_name in tables_to_downgrade:
        try:
            existing_tables = inspector.get_table_names()
            if table_name not in existing_tables:
                continue
            
            existing_columns = [col["name"] for col in inspector.get_columns(table_name)]
            
            if 'organization_id' in existing_columns:
                # Drop foreign key
                try:
                    op.drop_constraint(f'fk_{table_name}_organization_id', table_name, type_='foreignkey')
                except Exception:
                    pass
                
                # Drop index
                try:
                    op.drop_index(f'ix_{table_name}_organization_id', table_name=table_name)
                except Exception:
                    pass
                
                # Drop column
                op.drop_column(table_name, 'organization_id')
        except Exception as e:
            print(f"Error removing organization_id from {table_name}: {e}")

