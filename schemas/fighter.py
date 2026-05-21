from pydantic import BaseModel
from datetime import date

class Fighter(BaseModel):
    url: str
    name: str
    nickname: str | None
    height: str
    weight: str
    reach: str
    stance: str
    dob: date
    SLpM: float
    StrAcc: float
    SApM: float
    StrDef: float
    TDAvg: float
    TDAcc: float
    TDDef: float
    SubAvg: float