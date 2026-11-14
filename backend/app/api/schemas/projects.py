import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    """PATCH body: send only the fields to change. `description: null` clears it."""

    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check_fields(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null.")
        return self


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
