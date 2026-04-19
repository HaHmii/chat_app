from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models.user import User, UserRole
from models.property import Property, PropertyStatus, PropertyType
from models.district import District # Đảm bảo import để register table
from services.property_service import property_service, PropertyCreate, PropertyReview
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
import os

router = APIRouter(prefix="/properties", tags=["Properties"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin đăng nhập",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

@router.get("/districts", response_model=List[dict])
def get_districts(db: Session = Depends(get_db)):
    """Lấy danh sách quận huyện để hiển thị trong select input"""
    districts = db.query(District).all()
    return [{"id": d.id, "name": d.name} for d in districts]

@router.get("/", response_model=List[dict])
def get_properties(type: Optional[PropertyType] = None, db: Session = Depends(get_db)):
    query = db.query(Property).filter(Property.status == PropertyStatus.approved)
    if type:
        query = query.filter(Property.type == type)
    properties = query.order_by(Property.created_at.desc()).all()
    
    result = []
    for p in properties:
        thumbnail = p.images[0].url if p.images else None
        result.append({
            "id": p.id,
            "title": p.title,
            "price": float(p.price),
            "price_unit": p.price_unit,
            "area": float(p.area),
            "address": p.address,
            "type": p.type,
            "bedrooms": p.bedrooms,
            "bathrooms": p.bathrooms,
            "thumbnail_url": thumbnail,
        })
    return result

@router.get("/pending", response_model=List[dict])
def get_pending_properties(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Chỉ Admin mới có quyền xem tin chờ duyệt")
    properties = property_service.get_pending_properties(db)
    result = []
    for p in properties:
        thumbnail = p.images[0].url if p.images else None
        result.append({
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "price": float(p.price),
            "price_unit": p.price_unit,
            "area": float(p.area),
            "address": p.address,
            "type": p.type,
            "category": p.category,
            "bedrooms": p.bedrooms,
            "bathrooms": p.bathrooms,
            "thumbnail_url": thumbnail,
        })
    return result


@router.patch("/{property_id}/review")
def review_property(
    property_id: int,
    review: PropertyReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_service.review_property(db, property_id, review, current_user)
    action_text = "duyệt" if review.action == "approved" else "từ chối"
    return {"message": f"Đã {action_text} tin đăng thành công"}


@router.post("/create", status_code=status.HTTP_201_CREATED)
def create_property(
    prop_in: PropertyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.owner, UserRole.staff, UserRole.admin]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ tài khoản Chủ nhà mới có quyền thực hiện chức năng này."
        )
    return property_service.create_property(db, prop_in, current_user)
