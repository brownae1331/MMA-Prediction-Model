from pydantic import BaseModel
from datetime import date

class Fighter(BaseModel):
    url: str
    name: str
    nickname: str | None = None
    height: str | None = None
    weight: str | None = None
    reach: str | None = None
    stance: str | None = None
    dob: date | None = None
    SLpM: float | None = None
    StrAcc: float | None = None
    SApM: float | None = None
    StrDef: float | None = None
    TDAvg: float | None = None
    TDAcc: float | None = None
    TDDef: float | None = None
    SubAvg: float | None = None
