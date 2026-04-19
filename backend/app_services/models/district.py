from sqlalchemy import Column, Integer, String, Boolean
from database import Base

class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    short_name = Column(String(50), nullable=False)
    is_urban = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<District(id={self.id}, name='{self.name}', code='{self.code}')>"