from sqlalchemy.orm import Session
from models.models import Cost
from schemas.cost_schema import CostCreate, CostUpdate


def create_or_update_cost(data: CostCreate, db: Session) -> Cost:
    cost = db.query(Cost).filter(Cost.type == data.type).first()
    if cost:
        cost.price = data.price
    else:
        cost = Cost(type=data.type, price=data.price)
        db.add(cost)
    db.commit()
    db.refresh(cost)
    return cost


def get_all_costs(db: Session) -> list[Cost]:
    return db.query(Cost).all()


def get_cost_by_type(cost_type: str, db: Session) -> Cost | None:
    return db.query(Cost).filter(Cost.type == cost_type).first()


def delete_cost(cost_type: str, db: Session) -> bool:
    cost = db.query(Cost).filter(Cost.type == cost_type).first()
    if not cost:
        return False
    db.delete(cost)
    db.commit()
    return True
