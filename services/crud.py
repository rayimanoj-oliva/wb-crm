from sqlalchemy.orm import Session
from models.models import User
from schemas.user_schema import UserCreate, UserUpdate
import uuid

from utils.utils import get_password_hash


def get_user(db: Session, user_id: uuid.UUID):
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def get_users(db: Session, skip: int = 0, limit: int = 50, search: str = None):
    """Get all users with pagination and optional search."""
    query = db.query(User)

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (User.username.ilike(search_term)) |
            (User.email.ilike(search_term)) |
            (User.first_name.ilike(search_term)) |
            (User.last_name.ilike(search_term))
        )

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    users = query.offset(skip).limit(limit).all()

    return {"items": users, "total": total, "skip": skip, "limit": limit}


def create_user(db: Session, user: UserCreate):
    """
    Create a new user with organization and role assignment.
    
    Rules:
    - SUPER_ADMIN must have organization_id = None
    - ORG_ADMIN and AGENT must have organization_id set
    - If role_id is provided, use it; otherwise use legacy role enum
    """
    from models.models import Role, Organization
    from schemas.user_schema import UserRole
    
    # Determine if this is a SUPER_ADMIN
    is_super_admin = False
    
    # Check new role system first (role_id)
    if user.role_id:
        role_obj = db.query(Role).filter(Role.id == user.role_id).first()
        if role_obj and role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
            # SUPER_ADMIN cannot have organization_id
            organization_id = None
        elif role_obj:
            # For ORG_ADMIN and AGENT, organization_id is required
            if not user.organization_id:
                raise ValueError(f"organization_id is required for role '{role_obj.name}'")
            organization_id = user.organization_id
        else:
            raise ValueError(f"Role with id '{user.role_id}' not found")
    elif user.role == UserRole.SUPER_ADMIN:
        # Legacy role enum - SUPER_ADMIN
        is_super_admin = True
        organization_id = None
    else:
        # Legacy role enum - ORG_ADMIN or AGENT
        if not user.organization_id:
            raise ValueError(f"organization_id is required for role '{user.role.value}'")
        organization_id = user.organization_id
    
    # Verify organization exists if organization_id is provided
    if organization_id:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise ValueError(f"Organization with id '{organization_id}' not found")
    
    db_user = User(
        username=user.username,
        password=get_password_hash(user.password),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone_number=user.phone_number,
        role=user.role,  # Legacy role enum (for backward compatibility)
        organization_id=organization_id,
        role_id=user.role_id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user



def update_user(db: Session, user_id: uuid.UUID, user: UserUpdate):
    """
    Update a user with organization and role assignment.
    
    Rules:
    - SUPER_ADMIN must have organization_id = None
    - ORG_ADMIN and AGENT must have organization_id set
    - If role_id is provided, use it; otherwise use legacy role enum
    """
    from models.models import Role, Organization
    from schemas.user_schema import UserRole
    
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        return None
    
    # Get update data (only fields that are being updated)
    update_data = user.model_dump(exclude_unset=True)
    
    # Handle password separately (if provided)
    if "password" in update_data:
        password = update_data.pop("password")
        db_user.password = get_password_hash(password)
    
    # Handle organization_id and role_id validation
    if "role_id" in update_data or "organization_id" in update_data or "role" in update_data:
        # Determine the target role (from role_id or legacy role enum)
        target_role_id = update_data.get("role_id", db_user.role_id)
        target_role_enum = update_data.get("role", db_user.role)
        
        is_super_admin = False
        
        # Check new role system first (role_id)
        if target_role_id:
            role_obj = db.query(Role).filter(Role.id == target_role_id).first()
            if not role_obj:
                raise ValueError(f"Role with id '{target_role_id}' not found")
            
            if role_obj.name == "SUPER_ADMIN":
                is_super_admin = True
                # SUPER_ADMIN cannot have organization_id
                if "organization_id" in update_data and update_data["organization_id"] is not None:
                    raise ValueError("SUPER_ADMIN cannot have an organization_id")
                update_data["organization_id"] = None
            else:
                # For ORG_ADMIN and AGENT, organization_id is required
                target_org_id = update_data.get("organization_id", db_user.organization_id)
                if not target_org_id:
                    raise ValueError(f"organization_id is required for role '{role_obj.name}'")
                
                # Verify organization exists
                org = db.query(Organization).filter(Organization.id == target_org_id).first()
                if not org:
                    raise ValueError(f"Organization with id '{target_org_id}' not found")
        elif target_role_enum == UserRole.SUPER_ADMIN:
            # Legacy role enum - SUPER_ADMIN
            is_super_admin = True
            if "organization_id" in update_data and update_data["organization_id"] is not None:
                raise ValueError("SUPER_ADMIN cannot have an organization_id")
            update_data["organization_id"] = None
        elif target_role_enum:
            # Legacy role enum - ORG_ADMIN or AGENT
            target_org_id = update_data.get("organization_id", db_user.organization_id)
            if not target_org_id:
                raise ValueError(f"organization_id is required for role '{target_role_enum.value}'")
            
            # Verify organization exists
            org = db.query(Organization).filter(Organization.id == target_org_id).first()
            if not org:
                raise ValueError(f"Organization with id '{target_org_id}' not found")
    
    # Apply all other updates
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: uuid.UUID):
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user
