from fastapi import FastAPI, HTTPException, Header, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
import hmac
import secrets
import logging

import jwt as pyjwt
from pydantic_settings import BaseSettings, SettingsConfigDict

from db import (
    count_articles,
    count_articles_by_source,
    get_articles,
    get_article_by_id,
    search_articles,
    get_attrition_summary,
    get_attrition_by_department,
    get_attrition_by_overtime,
    get_attrition_by_tenure,
    get_top_earners_by_department,
    get_department_detail,
    get_attrition_risk_profile,
)

log = logging.getLogger(__name__)

class Settings(BaseSettings):
    database_url: str
    student_name: str
    internal_api_key: str
    jwt_secret: str
    jwt_expiry_minutes: int = 30
    client_id: str
    client_secret: str

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

settings = Settings()

app = FastAPI(
    title="News & HR Analytics API",
    description=(
        "Mini Project 2 — End to End Data Pipeline API.\n\n"
        "**Path A (ETL):** Scraped articles (RSS, books, quotes) "
        "cleaned di Pandas, loaded ke PostgreSQL.\n\n"
        "**Path B (ELT):** IBM HR Attrition CSV di-load mentah, "
        "di-transform dengan SQL saat query."
    ),
    version="1.0",
)
security_scheme = HTTPBearer(auto_error=False)

class Article(BaseModel):
    """Model untuk satu artikel dari tabel articles."""
    id: int
    title: str
    url: str
    source: str
    content: Optional[str] = None
    published_at: Optional[datetime] = None
    scraped_at: Optional[datetime] = None


# TODO 26: Lengkapi Pydantic model untuk ArticleStats
#
# Endpoint /articles/stats akan return JSON seperti ini:
# {
#     "total_articles": 512,
#     "by_source": {"bbc": 50, "nytimes": 30, "books.toscrape": 200, ...}
# }
#
# Hint: total_articles bertipe int, by_source bertipe Dict[str, int]
class ArticleStats(BaseModel):
  total_articles: int
  by_source: dict[str,int]

class PaginatedArticleResponse(BaseModel):
    data: List[Article]
    page: int
    per_page: int
    total_items: int
    total_pages: int

class TokenRequest(BaseModel):
    """Request body untuk POST /token."""
    client_id: str
    client_secret: str


class TokenResponse(BaseModel):
    """Response dari POST /token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# TODO 27: Lengkapi Pydantic model untuk AttritionSummary
#
# Endpoint /attrition/summary akan return JSON seperti ini:
# {
#     "total_employees": 1470,
#     "attrition_yes": 237,
#     "attrition_no": 1233,
#     "attrition_rate": 0.1612
# }
#
# Hint: semua int kecuali attrition_rate yang float
class AttritionSummary(BaseModel):
    total_employees:int
    attrition_yes:int
    attrition_no:int
    attrition_rate:float


class DepartmentAttrition(BaseModel):
    """Attrition per department."""
    Department: str
    total: int
    attrition_count: int
    attrition_rate: float
    avg_income: float


class OvertimeAttrition(BaseModel):
    """Attrition per overtime status."""
    OverTime: str
    total: int
    attrition_count: int
    attrition_rate: float


class TenureAttrition(BaseModel):
    """Attrition per tenure bucket."""
    tenure_bucket: str
    total: int
    attrition_count: int
    attrition_rate: float


class TopEarner(BaseModel):
    """Top earner dalam satu department."""
    EmployeeNumber: int
    Department: str
    JobRole: str
    MonthlyIncome: int
    Attrition: str
    income_rank: int

class TopEarnerDept(BaseModel):
    EmployeeNumber: int
    JobRole: str
    MonthlyIncome: int

class DepartmentDetailResponse(BaseModel):
    department: str
    total_employees: int
    attrition_count: int
    attrition_rate: float
    avg_income: float
    min_income: int
    max_income: int
    top_earners: List[TopEarnerDept]

# ==================================================================
# Authentication Helpers
#
# API ini support 2 metode autentikasi:
#   1. API Key — kirim header X-API-Key
#   2. JWT Bearer — POST /token dulu, lalu kirim header Authorization
#
# Keduanya bisa dipakai di endpoint yang sama.
# ==================================================================

def create_access_token(client_id: str) -> str:
    """Buat JWT token dengan expiry."""
    # TODO 28: Buat JWT payload dan encode
    #
    # Hint:
    #   now = datetime.now(timezone.utc)
    #   payload = {
    #       "sub": client_id,                                          # subject = siapa pemilik token
    #       "iat": now,                                                # issued at
    #       "exp": now + timedelta(minutes=settings.jwt_expiry_minutes), # expiry
    #       "jti": secrets.token_hex(16),                              # unique token ID
    #   }
    #   return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": client_id,                                          # subject = siapa pemilik token
        "iat": now,                                                # issued at
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes), # expiry
        "jti": secrets.token_hex(16),                              # unique token ID
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_jwt_token(token: str) -> dict:
    """Decode dan validasi JWT token. Raise HTTPException jika invalid."""
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token sudah expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token tidak valid")


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Cek API key dari header X-API-Key."""
    # TODO 29: Validasi API key
    #
    # Logika:
    #   1. Jika x_api_key is None → return None (tidak ada key, bukan error)
    #   2. Jika key cocok dengan settings.internal_api_key → return {"auth_method": "api_key"}
    #   3. Jika key TIDAK cocok → raise HTTPException(status_code=401)
    #
    # Hint: Gunakan hmac.compare_digest(a, b) untuk perbandingan aman
    #       (mencegah timing attack, lebih secure dari == biasa)
    if x_api_key is None:
      return None
    if hmac.compare_digest(x_api_key, settings.internal_api_key):
      return {"auth_method": "api_key"}

    raise HTTPException(status_code=401, detail="API Key Tidak Valid")


def get_current_client(
    api_key_result=Depends(verify_api_key),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
):
    """
    Dependency utama — terima API Key ATAU Bearer token.
    FastAPI akan inject hasil verify_api_key dan credentials otomatis.
    """
    # TODO 30: Gabungkan kedua metode auth
    #
    # Logika:
    #   1. Jika api_key_result is not None → return api_key_result (sudah valid dari verify_api_key)
    #   2. Jika credentials is not None → decode JWT token, return hasilnya
    #      payload = verify_jwt_token(credentials.credentials)
    #      return {"auth_method": "bearer", "client_id": payload["sub"]}
    #   3. Jika keduanya None → raise HTTPException 401 "Authentication required"
    #
    # Hint: Jangan lupa headers={"WWW-Authenticate": "Bearer"} di HTTPException
    if api_key_result is not None:
      return api_key_result

    if credentials is not None:
      payload = verify_jwt_token(credentials.credentials)
      return {"auth_method": "bearer", "client_id":payload["sub"]}

    raise HTTPException(status_code=401, detail="Authentication Required. Gunakan API key atau JWT")

# ==================================================================
# PUBLIC ENDPOINTS — tanpa auth
# ==================================================================
@app.get("/", tags=["Public"])
def read_root():
    return {
        "message": "News & HR Analytics API — End to End Data Pipeline",
        "student": settings.student_name,
        "paths": {
            "etl_articles": "/articles",
            "elt_attrition": "/attrition",
            "docs": "/docs",
        },
    }

@app.get("/health", tags=["Public"])
def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

# ==================================================================
# AUTH ENDPOINT
# ==================================================================
@app.post("/token", response_model=TokenResponse, tags=["Auth"])
def login_for_token(req: TokenRequest):
    """Exchange client_id + client_secret untuk JWT access token."""
    # TODO 31: Validasi credentials dan return token
    #
    # Langkah:
    #   1. Compare req.client_id dengan settings.client_id (hmac.compare_digest)
    #   2. Compare req.client_secret dengan settings.client_secret
    #   3. Jika SALAH → raise HTTPException(status_code=401, detail="Invalid client credentials")
    #   4. Jika BENAR → buat token dan return TokenResponse
    #
    # Hint:
    #   token = create_access_token(req.client_id)
    #   return TokenResponse(
    #       access_token=token,
    #       token_type="bearer",
    #       expires_in=settings.jwt_expiry_minutes * 60,  # convert menit ke detik
    #   )
    valid_id = hmac.compare_digest(req.client_id, settings.client_id)
    valid_secret = hmac.compare_digest(req.client_secret, settings. client_secret)
    if not(valid_id and valid_secret):
        raise HTTPException(status_code=401, detail="Invalid Client Credentials")
    token = create_access_token(req.client_id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_minutes * 60,  # convert menit ke detik
    )

# ==================================================================
# ETL PATH: Article Endpoints
# ==================================================================
@app.get("/articles", response_model=List[Article], tags=["Articles (ETL)"])
def list_articles(
    source: Optional[str] = Query(None, description="Filter by source (e.g. bbc, nytimes)"),
    title: Optional[str] = Query(None, description="Search title (case-insensitive)"),
    limit: int = Query(20, le=100, ge=1, description="Max results (1-100)"),
    auth=Depends(get_current_client),
):
    """List articles dengan optional filter source dan title."""
    # TODO 32: Panggil get_articles dari db.py dan return hasilnya
    #
    # Hint: return get_articles(source=source, title=title, limit=limit)
    return get_articles(source=source, title=title, limit=limit)

@app.get(
    "/articles/search",
    response_model=PaginatedArticleResponse,
    tags=["Articles (ETL)"],
)
def search_articles_endpoint(
    source: Optional[str] = Query(None, description="Filter by source (misal: bbc, nytimes)"),
    title: Optional[str] = Query(None, description="Case-insensitive partial match pada judul"),
    date_from: Optional[str] = Query(None, description="Format: YYYY-MM-DD, filter published_at >="),
    date_to: Optional[str] = Query(None, description="Format: YYYY-MM-DD, filter published_at <="),
    page: int = Query(1, ge=1, description="Nomor halaman (mulai dari 1)"),
    per_page: int = Query(10, ge=1, le=50, description="Jumlah artikel per halaman (max 50)"),
    auth=Depends(get_current_client),
):
    """Search artikel dengan filter dan pagination."""
    return search_articles(
        source=source,
        title=title,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )

# TODO 33: Buat endpoint GET /articles/stats
#
# Spesifikasi:
#   - Path: /articles/stats
#   - Response model: ArticleStats
#   - Tag: "Articles (ETL)"
#   - Perlu auth: ya (auth=Depends(get_current_client))
#   - Logic: panggil count_articles() dan count_articles_by_source()
#            lalu return ArticleStats(total_articles=..., by_source=...)
#
# Hint:
#   @app.get("/articles/stats", response_model=ArticleStats, tags=["Articles (ETL)"])
#   def article_stats(auth=Depends(get_current_client)):
#       return ArticleStats(
#           total_articles=count_articles(),
#           by_source=count_articles_by_source(),
#       )
@app.get("/articles/stats", response_model=ArticleStats, tags=["Articles (ETL)"])
def article_stats(auth=Depends(get_current_client)):
    return ArticleStats(
        total_articles=count_articles(),
        by_source=count_articles_by_source(),
    )


@app.get("/articles/{article_id}", response_model=Article, tags=["Articles (ETL)"])
def get_single_article(
    article_id: int,
    auth=Depends(get_current_client),
):
    """Get single article by database ID."""
    article = get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


# ==================================================================
# ELT PATH: Attrition Endpoints
#
# Data attrition di-load MENTAH dari CSV (Session 9).
# Transform terjadi SAAT query — inilah "T" di ELT.
# ==================================================================
@app.get("/attrition/summary", response_model=AttritionSummary, tags=["Attrition (ELT)"])
def attrition_summary(auth=Depends(get_current_client)):
    """Overall attrition stats."""
    # TODO 34: Panggil get_attrition_summary() dan return hasilnya
    return get_attrition_summary()

@app.get(
    "/attrition/department/{dept_name}",
    response_model=DepartmentDetailResponse,
    tags=["Attrition (ELT)"],
)
def department_detail(
    dept_name: str,
    auth=Depends(get_current_client),
):
    """Statistik lengkap untuk satu department (termasuk top 3 earners)."""
    detail = get_department_detail(dept_name)
    if not detail:
        raise HTTPException(
            status_code=404,
            detail=f"Department '{dept_name}' tidak ditemukan"
        )
    return detail

# TODO 35: Buat endpoint GET /attrition/by-department
#
# Spesifikasi:
#   - Path: /attrition/by-department
#   - Response model: List[DepartmentAttrition]
#   - Tag: "Attrition (ELT)"
#   - Perlu auth: ya
#   - Logic: return get_attrition_by_department()
#
# Hint: Polanya sama dengan endpoint /attrition/summary di atas

# Endpoint ini sudah jadi — contoh endpoint attrition yang lengkap
@app.get(
    "/attrition/by-overtime",
    response_model=List[OvertimeAttrition],
    tags=["Attrition (ELT)"],
)
def attrition_by_overtime(auth=Depends(get_current_client)):
    """Attrition by overtime status (SQL cross-tab)."""
    return get_attrition_by_overtime()

@app.get(
    "/attrition/by-tenure",
    response_model=List[TenureAttrition],
    tags=["Attrition (ELT)"],
)
def attrition_by_tenure(auth=Depends(get_current_client)):
    """Attrition by tenure bucket (SQL CASE WHEN)."""
    return get_attrition_by_tenure()

@app.get(
    "/attrition/top-earners",
    response_model=List[TopEarner],
    tags=["Attrition (ELT)"],
)
def top_earners(
    limit_per_dept: int = Query(5, le=20, ge=1, description="Top N per department"),
    auth=Depends(get_current_client),
):
    """Top earners per department (SQL RANK window function)."""
    return get_top_earners_by_department(limit_per_dept=limit_per_dept)

@app.get(
    "/attrition/risk-profile",
    response_model=List[Dict],
    tags=["Attrition (ELT)"],
)
def attrition_risk_profile(
    limit: int = Query(20, ge=1, le=100, description="Jumlah data karyawan high-risk (max 100)"),
    auth=Depends(get_current_client),
):
    """Karyawan dengan indikator risiko attrition tinggi (OverTime, tenure < 3th, gaji < rata-rata dept)."""
    return get_attrition_risk_profile(limit=limit)
