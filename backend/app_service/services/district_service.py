from pydantic import BaseModel

class DistrictResponse(BaseModel):
    id: int
    code: str
    name: str
    short_name: str
    is_urban: bool

    class Config:
        from_attributes = True