from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from uuid import UUID
import pandas as pd

from database.db import get_db
from models.models import Category, SubCategory, Product
from schemas.catalog_schema import (
    CategoryCreate, CategoryUpdate, CategoryOut,
    ProductCreate, ProductUpdate, ProductOut
)


router = APIRouter(prefix="/catalog", tags=["catalog"])
# --- Seeding Utilities ---
def seed_categories(db: Session):
    base_categories = [
        {"name": "Skin", "slug": "skin"},
        {"name": "Hair", "slug": "hair"},
        {"name": "Body", "slug": "body"},
        {"name": "Nutraceuticals", "slug": "nutraceuticals"},
    ]
    created = 0
    for c in base_categories:
        if not db.query(Category).filter(Category.name.ilike(c["name"])) .first():
            db.add(Category(name=c["name"], description=None, image_url=None, slug=c["slug"]))
            created += 1
    if created:
        db.commit()


def seed_subcategories(db: Session):
    skin = db.query(Category).filter(Category.name.ilike("Skin")).first()
    if skin:
        existing = {s.name.lower(): s for s in skin.sub_categories}
        desired = ["Moisturizers", "Cleansers"]
        for name in desired:
            if name.lower() not in existing:
                db.add(SubCategory(category_id=skin.id, name=name))
        db.commit()


@router.post("/admin/normalize")
def normalize_categories(confirm: Optional[str] = None, db: Session = Depends(get_db)):
    if (confirm or "").lower() != "yes":
        raise HTTPException(status_code=400, detail="Pass confirm=yes to execute normalization")

    # Ensure base categories exist
    seed_categories(db)

    # Fetch canonical targets
    target_names = {
        "skin": db.query(Category).filter(Category.name.ilike("Skin")).first(),
        "hair": db.query(Category).filter(Category.name.ilike("Hair")).first(),
        "body": db.query(Category).filter(Category.name.ilike("Body")).first(),
        "nutraceuticals": db.query(Category).filter(Category.name.ilike("Nutraceuticals")).first(),
    }

    def pick_target(name: str) -> Category:
        n = (name or "").strip().lower()
        if any(k in n for k in ["skin", "derma", "face"]):
            return target_names["skin"]
        if any(k in n for k in ["hair", "scalp"]):
            return target_names["hair"]
        if any(k in n for k in ["nutra", "supplement", "vitamin", "capsule", "tablet"]):
            return target_names["nutraceuticals"]
        return target_names["body"]

    moved_products = 0
    deleted_subs = 0
    deleted_cats = 0

    all_cats = db.query(Category).all()
    canonical_ids = {c.id for c in target_names.values() if c}
    for c in all_cats:
        if c.id in canonical_ids:
            continue
        target = pick_target(c.name)
        # Reassign products to target category
        prods = db.query(Product).filter(Product.category_id == c.id).all()
        for p in prods:
            p.category_id = target.id
            moved_products += 1
        # Delete subcategories under this category (products already moved by category)
        subs = db.query(SubCategory).filter(SubCategory.category_id == c.id).all()
        for s in subs:
            db.delete(s)
            deleted_subs += 1
        # Delete the category itself
        db.delete(c)
        deleted_cats += 1

    db.commit()
    return {
        "status": "ok",
        "moved_products": moved_products,
        "deleted_subcategories": deleted_subs,
        "deleted_categories": deleted_cats,
        "remaining_categories": db.query(Category).count(),
    }


def _category_to_tree(db: Session, category: Category) -> Dict:
    return {
        "id": str(category.id),
        "name": category.name,
        "description": category.description,
        "image_url": category.image_url,
        "subcategories": [
            _category_to_tree(db, sc.category) if isinstance(sc, Category) else {
                "id": str(sc.id),
                "name": sc.name,
                "description": sc.description,
                "image_url": None,
                "subcategories": []
            }
            for sc in category.sub_categories
        ]
    }


# Categories
@router.post("/categories/", response_model=CategoryOut)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    if payload.parent_id:
        parent = db.query(Category).filter(Category.id == payload.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent category not found")
        subc = SubCategory(category_id=parent.id, name=payload.name, description=payload.description)
        db.add(subc)
        db.commit()
        db.refresh(subc)
        return CategoryOut(id=subc.id, name=subc.name, description=subc.description, image_url=None, subcategories=[])
    cat = Category(name=payload.name, description=payload.description, image_url=payload.image_url)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return CategoryOut(id=cat.id, name=cat.name, description=cat.description, image_url=cat.image_url, subcategories=[])


@router.get("/categories/", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(Category).all()
    result: List[CategoryOut] = []
    for c in cats:
        result.append(CategoryOut(
            id=c.id,
            name=c.name,
            description=c.description,
            image_url=c.image_url,
            subcategories=[CategoryOut(id=s.id, name=s.name, description=s.description, image_url=None, subcategories=[]) for s in c.sub_categories]
        ))
    return result


@router.get("/subcategories")
def list_subcategories(category_id: UUID, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    subs = db.query(SubCategory).filter(SubCategory.category_id == category_id).all()
    return [{"id": s.id, "name": s.name, "category_id": s.category_id} for s in subs]


@router.get("/categories/{category_id}")
def get_category_with_products(category_id: UUID, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        sub = db.query(SubCategory).filter(SubCategory.id == category_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Category not found")
        products = db.query(Product).filter(Product.sub_category_id == sub.id).all()
        return {
            "category": {"id": str(sub.id), "name": sub.name, "description": sub.description, "image_url": None},
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description,
                    "price": p.price,
                    "stock": p.stock,
                    "image_url": p.image_url,
                } for p in products
            ]
        }
    products = db.query(Product).filter(Product.category_id == cat.id).all()
    return {
        "category": {"id": str(cat.id), "name": cat.name, "description": cat.description, "image_url": cat.image_url},
        "subcategories": [{"id": str(s.id), "name": s.name} for s in cat.sub_categories],
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "stock": p.stock,
                "image_url": p.image_url,
            } for p in products
        ]
    }


# Products
@router.post("/products/", response_model=ProductOut)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    # Deduplicate by (name + category_id + sub_category_id)
    name_norm = (payload.name or "").strip()
    existing = (
        db.query(Product)
        .filter(
            Product.name.ilike(name_norm),
            Product.category_id == payload.category_id,
            Product.sub_category_id == payload.sub_category_id,
        )
        .first()
    )

    if existing:
        # Update existing instead of creating a duplicate
        existing.description = payload.description
        existing.price = payload.price
        existing.stock = payload.stock
        existing.image_url = payload.image_url
        db.commit()
        db.refresh(existing)
        return existing

    prod = Product(
        name=name_norm,
        description=payload.description,
        price=payload.price,
        stock=payload.stock,
        image_url=payload.image_url,
        category_id=payload.category_id,
        sub_category_id=payload.sub_category_id,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod


@router.get("/products/", response_model=List[ProductOut])
def list_products(category_id: Optional[UUID] = None, sub_category_id: Optional[UUID] = None, db: Session = Depends(get_db)):
    q = db.query(Product)
    if sub_category_id:
        q = q.filter(Product.sub_category_id == sub_category_id)
    elif category_id:
        q = q.filter(Product.category_id == category_id)
    return q.all()


@router.get("/categories/{category_id}/products", response_model=List[ProductOut])
def list_products_by_category(category_id: UUID, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.category_id == category_id).all()


@router.get("/subcategories/{sub_category_id}/products", response_model=List[ProductOut])
def list_products_by_subcategory(sub_category_id: UUID, db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.sub_category_id == sub_category_id).all()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, db: Session = Depends(get_db)):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return prod


# Excel Upload
@router.post("/upload-excel")
def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file")
    df = pd.read_excel(file.file)
    # Normalize headers (trim)
    df.columns = [str(c).strip() for c in df.columns]

    def find_existing_col(possible_names):
        lowered = {c.lower(): c for c in df.columns}
        for name in possible_names:
            key = name.lower().strip()
            if key in lowered:
                return lowered[key]
        return None

    # Column name variants
    COL_CATEGORY = find_existing_col(["Category", "Categories", "Category Name"]) 
    COL_SUBCATEGORY = find_existing_col(["Subcategory", "Sub Category", "Sub-Category", "Subcategory Name"]) 
    COL_PNAME = find_existing_col(["Product Name", "Product", "Item", "Name", "Title"]) 
    COL_DESC = find_existing_col(["Description", "Desc"]) 
    COL_PRICE = find_existing_col(["Price", "MRP", "Selling Price"]) 
    COL_STOCK = find_existing_col(["Stock", "Qty", "Quantity", "Inventory"]) 
    COL_PIMG = find_existing_col(["ImageURL", "Image URL", "ProductImage", "Image"])
    COL_CIMG = find_existing_col(["CategoryImageURL", "Category Image", "Category Image URL"]) 
    COL_SCIMG = find_existing_col(["SubcategoryImageURL", "Subcategory Image", "Subcategory Image URL"]) 

    # Minimal required: Category and Product Name must exist
    if not COL_CATEGORY or not COL_PNAME:
        # Fallback A: try substring heuristics on current header row
        def pick_contains(options):
            for c in df.columns:
                cl = str(c).lower()
                if any(opt in cl for opt in options):
                    return c
            return None
        COL_CATEGORY = COL_CATEGORY or pick_contains(["category", "catagory", "cat_"])
        COL_PNAME = COL_PNAME or pick_contains(["product name", "product", "item", "name", "title"]) 

        # Fallback B: sometimes the first row is the header but pandas parsed it as data
        if not COL_CATEGORY or not COL_PNAME:
            df_nohdr = pd.read_excel(file.file, header=None)
            # pick the first non-empty row as header
            header_row_idx = None
            for idx in range(min(5, len(df_nohdr))):
                row_vals = [str(v).strip() for v in df_nohdr.iloc[idx].tolist()]
                if any(v and v.lower() not in {"nan", "none"} for v in row_vals):
                    header_row_idx = idx
                    break
            if header_row_idx is not None:
                new_cols = [str(v).strip() for v in df_nohdr.iloc[header_row_idx].tolist()]
                df = df_nohdr.iloc[header_row_idx + 1 : ].copy()
                df.columns = new_cols
                df.columns = [str(c).strip() for c in df.columns]
                # re-run detection
                def find_existing_col2(possible_names):
                    lowered = {c.lower(): c for c in df.columns}
                    for name in possible_names:
                        key = name.lower().strip()
                        if key in lowered:
                            return lowered[key]
                    return None
                COL_CATEGORY = find_existing_col2(["Category", "Categories", "Category Name"]) or pick_contains(["category", "catagory", "cat_"])
                COL_SUBCATEGORY = find_existing_col2(["Subcategory", "Sub Category", "Sub-Category", "Subcategory Name"]) or find_existing_col2(["Sub category"]) or pick_contains(["subcat", "sub-category", "subcategory"]) 
                COL_PNAME = find_existing_col2(["Product Name", "Product", "Item", "Name", "Title"]) or pick_contains(["product", "item", "title"]) 
                COL_DESC = find_existing_col2(["Description", "Desc"]) or COL_DESC
                COL_PRICE = find_existing_col2(["Price", "MRP", "Selling Price"]) or COL_PRICE
                COL_STOCK = find_existing_col2(["Stock", "Qty", "Quantity", "Inventory"]) or COL_STOCK
                COL_PIMG = find_existing_col2(["ImageURL", "Image URL", "ProductImage", "Image"]) or COL_PIMG
                COL_CIMG = find_existing_col2(["CategoryImageURL", "Category Image", "Category Image URL"]) or COL_CIMG
                COL_SCIMG = find_existing_col2(["SubcategoryImageURL", "Subcategory Image", "Subcategory Image URL"]) or COL_SCIMG

        if not COL_CATEGORY or not COL_PNAME:
            raise HTTPException(status_code=400, detail=f"Missing required columns: need Category and Product Name. Found: {list(df.columns)}")

    # Optional columns for richer JioMart-like catalogue

    created = {"categories": 0, "subcategories": 0, "products": 0}
    stats = {
        "found_distinct_categories": set(),
        "found_distinct_subcategories": {},  # cat_name -> set(sub_names)
        "skipped_rows": 0,
        "total_rows": 0,
    }

    def normalize_cell(val: object) -> str:
        try:
            import pandas as _pd  # lazy import guard
            if _pd.isna(val):
                return ""
        except Exception:
            pass
        s = str(val).strip()
        if s.lower() in {"nan", "none", "null", ""}:
            return ""
        return s

    for _, row in df.iterrows():
        stats["total_rows"] += 1
        cat_name = normalize_cell(row.get(COL_CATEGORY, ""))
        sub_name = normalize_cell(row.get(COL_SUBCATEGORY, "")) if COL_SUBCATEGORY else ""
        p_name = normalize_cell(row.get(COL_PNAME, ""))
        p_desc = normalize_cell(row.get(COL_DESC, "")) if COL_DESC else ""
        try:
            p_price = float(row.get(COL_PRICE, 0) or 0) if COL_PRICE else 0.0
        except Exception:
            p_price = 0.0
        try:
            p_stock = int(row.get(COL_STOCK, 0) or 0) if COL_STOCK else 0
        except Exception:
            p_stock = 0
        p_img_raw = row.get(COL_PIMG, "") if COL_PIMG else ""
        p_img = normalize_cell(p_img_raw) or None

        cat_img_raw = row.get(COL_CIMG, "") if COL_CIMG else ""
        cat_img = normalize_cell(cat_img_raw) or None
        sub_img_raw = row.get(COL_SCIMG, "") if COL_SCIMG else ""
        sub_img = normalize_cell(sub_img_raw) or None

        if not cat_name or not p_name:
            stats["skipped_rows"] += 1
            continue

        # Track distincts for response insight
        stats["found_distinct_categories"].add(cat_name)
        if sub_name:
            stats["found_distinct_subcategories"].setdefault(cat_name, set()).add(sub_name)

        cat = db.query(Category).filter(Category.name.ilike(cat_name)).first()
        if not cat:
            cat = Category(name=cat_name, image_url=cat_img)
            db.add(cat)
            created["categories"] += 1
            db.flush()
        elif cat_img and not cat.image_url:
            cat.image_url = cat_img

        sub_id = None
        if sub_name:
            sub = db.query(SubCategory).filter(SubCategory.category_id == cat.id, SubCategory.name.ilike(sub_name)).first()
            if not sub:
                sub = SubCategory(category_id=cat.id, name=sub_name)
                db.add(sub)
                created["subcategories"] += 1
                db.flush()
            # store sub image in future if model adds image support
            sub_id = sub.id

        # Upsert product by (name + category + sub_category)
        existing_prod = (
            db.query(Product)
            .filter(
                Product.name.ilike(p_name),
                Product.category_id == cat.id,
                Product.sub_category_id == sub_id,
            )
            .first()
        )

        if existing_prod:
            # Update existing
            existing_prod.description = p_desc or existing_prod.description
            existing_prod.price = p_price if p_price else (existing_prod.price or 0.0)
            existing_prod.stock = p_stock if p_stock else (existing_prod.stock or 0)
            if p_img and not existing_prod.image_url:
                existing_prod.image_url = p_img
        else:
            prod = Product(
                name=p_name,
                description=p_desc,
                price=p_price,
                stock=p_stock,
                image_url=p_img,
                category_id=cat.id,
                sub_category_id=sub_id,
            )
            db.add(prod)
            created["products"] += 1

    db.commit()
    return {
        "status": "ok",
        **created,
        "found_distinct_categories": len(stats["found_distinct_categories"]),
        "found_distinct_subcategories": sum(len(s) for s in stats["found_distinct_subcategories"].values()),
        "skipped_rows": stats["skipped_rows"],
        "total_rows": stats["total_rows"],
    }


