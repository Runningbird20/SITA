import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import UserRole
from app.schemas.base import ORMBase


class UserRead(ORMBase):
    id: uuid.UUID
    username: str
    role: UserRole
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserRead
    expires_at: datetime
