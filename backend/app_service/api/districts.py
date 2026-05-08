from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from models.district import District
from services.district_service import DistrictResponse

router = APIRouter(prefix="/districts", tags=["Districts"])

@router.get("", response_model=list[DistrictResponse])
def get_districts(
        is_urban: Optional[bool] = Query(None, description="Lọc theo khu vực nội/ngoại thành"),
        db: Session = Depends(get_db),
):
    query = db.query(District)

    if is_urban is not None:
        query = query.filter(District.is_urban == is_urban)

    return query.order_by(District.name).all()


@router.get("/{district_id}", response_model=DistrictResponse)
def get_district(district_id: int, db: Session = Depends(get_db)):
    district = db.query(District).filter(District.id == district_id).first()

    if not district:
        raise HTTPException(status_code=404, detail="District not found")

    return district