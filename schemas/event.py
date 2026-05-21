from pydantic import BaseModel
from datetime import datetime

class Event(BaseModel):
    url: str
    title: str
    date: datetime
    location: str
    organizer: str