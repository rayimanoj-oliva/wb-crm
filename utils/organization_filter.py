"""Utility functions for organization-based filtering."""
from typing import Optional
from uuid import UUID
from models.models import User


def get_user_organization_id(user: User) -> Optional[UUID]:
    """
    Helper function to get organization_id for filtering.
    
    Returns None for SUPER_ADMIN (to show all data), 
    otherwise returns the user's organization_id.
    """
    # Check if user is SUPER_ADMIN
    is_super_admin = False
    
    # Check new role system first
    if hasattr(user, 'role_obj') and user.role_obj:
        if user.role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
    
    # Also check legacy role enum
    if not is_super_admin and hasattr(user, 'role') and user.role:
        role_str = str(user.role).upper()
        if role_str == "SUPER_ADMIN":
            is_super_admin = True
    
    # SUPER_ADMIN can see all data (return None), others see only their organization
    if is_super_admin:
        return None
    
    return user.organization_id

