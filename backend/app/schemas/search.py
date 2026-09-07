import uuid

from pydantic import BaseModel, ConfigDict


class SearchResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    id: uuid.UUID
    title: str
    subtitle: str
    url: str
