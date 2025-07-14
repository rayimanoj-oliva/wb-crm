from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.db import get_db
from schemas.cost_schema import CostCreate, CostOut
from services import cost_service

router = APIRouter(prefix="/costs", tags=["Costs"])

@router.post("/", response_model=CostOut)
def create_or_update(data: CostCreate, db: Session = Depends(get_db)):
    return cost_service.create_or_update_cost(data, db)

@router.get("/", response_model=list[CostOut])
def get_all(db: Session = Depends(get_db)):
    return cost_service.get_all_costs(db)

@router.get("/{cost_type}", response_model=CostOut)
def get_by_type(cost_type: str, db: Session = Depends(get_db)):
    cost = cost_service.get_cost_by_type(cost_type, db)
    if not cost:
        raise HTTPException(status_code=404, detail="Cost type not found")
    return cost

@router.delete("/{cost_type}")
def delete(cost_type: str, db: Session = Depends(get_db)):
    success = cost_service.delete_cost(cost_type, db)
    if not success:
        raise HTTPException(status_code=404, detail="Cost type not found")
    return {"detail": "Deleted successfully"}
