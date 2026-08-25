from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Base for schemas that read directly from SQLAlchemy model instances."""

    model_config = ConfigDict(from_attributes=True)
