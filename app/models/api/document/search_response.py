from pydantic import BaseModel


class SearchResponse(BaseModel):
    id: str
    content: str
    score: float
