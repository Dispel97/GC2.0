from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Response, Query, Header, Request, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import io
import uuid
import logging
import requests
import pdfplumber
import bcrypt
import jwt
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict


mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---------- Auth config ----------
JWT_SECRET = os.environ.get("JWT_SECRET", "insecure-fallback-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or ""


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id, "email": email, "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    if not user.get("is_approved") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Account in attesa di approvazione")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo per amministratori")
    return user


# ---------- Object Storage (Emergent OR Cloudflare R2 / S3-compatible) ----------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "openfiber-notes"
storage_key = None

# --- Cloudflare R2 / S3-compatible config ---
R2_ENDPOINT = (os.environ.get("R2_ENDPOINT") or "").strip()
R2_BUCKET = (os.environ.get("R2_BUCKET") or "").strip()
R2_ACCESS_KEY = (os.environ.get("R2_ACCESS_KEY") or "").strip()
R2_SECRET_KEY = (os.environ.get("R2_SECRET_KEY") or "").strip()
R2_REGION = (os.environ.get("R2_REGION") or "auto").strip()
USE_R2 = bool(R2_ENDPOINT and R2_BUCKET and R2_ACCESS_KEY and R2_SECRET_KEY)
_r2_client = None


def _get_r2_client():
    global _r2_client
    if _r2_client is None:
        import boto3
        from botocore.config import Config
        _r2_client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            region_name=R2_REGION,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
    return _r2_client


def init_storage(force: bool = False):
    global storage_key
    if USE_R2:
        return "r2"
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if USE_R2:
        try:
            _get_r2_client().put_object(
                Bucket=R2_BUCKET, Key=path, Body=data, ContentType=content_type
            )
            return {"path": path, "backend": "r2"}
        except Exception as e:
            logger.exception(f"R2 put failed: {e}")
            raise
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    if resp.status_code == 404:
        init_storage(force=True)
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": storage_key, "Content-Type": content_type},
                            data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    if USE_R2:
        try:
            r = _get_r2_client().get_object(Bucket=R2_BUCKET, Key=path)
            return r["Body"].read(), r.get("ContentType", "application/octet-stream")
        except Exception as e:
            logger.exception(f"R2 get failed: {e}")
            raise
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": storage_key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ---------- PDF Parser ----------
def parse_openfiber_pdf(pdf_bytes: bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_data = []
        for page in pdf.pages:
            w = page.width
            h = page.height
            mid = w / 2
            header_text = page.crop((0, 0, w, 150)).extract_text() or ''
            left_text = page.crop((0, 150, mid + 10, h - 25)).extract_text() or ''
            right_text = page.crop((mid - 10, 150, w, h - 25)).extract_text() or ''
            m = re.search(r'WR:\s*(\S+)', header_text)
            wr = m.group(1) if m else ''
            page_data.append({'wr': wr, 'header': header_text, 'left': left_text, 'right': right_text})

    grouped = defaultdict(lambda: {'header': '', 'left': '', 'right': ''})
    order = []
    for pd in page_data:
        wr = pd['wr']
        if not wr:
            continue
        if wr not in grouped:
            order.append(wr)
        grouped[wr]['header'] += "\n" + pd['header']
        grouped[wr]['left'] += "\n" + pd['left']
        grouped[wr]['right'] += "\n" + pd['right']

    results = []
    for wr in order:
        d = grouped[wr]
        body = d['left'] + "\n" + d['right']

        m = re.search(r'Cliente:\s*(.*?)\s+Indiriz\.', d['header']); cliente = m.group(1).strip() if m else ''
        m = re.search(r'Descrizione OLO:\s*(\S+)', d['header']); olo = m.group(1).strip() if m else ''
        m = re.search(r'PORTA_DI_USCITA_SPLITTER_PFS\s*-\s*(\S+)', body); splitter = m.group(1).strip() if m else ''

        nome_pte = ''
        for src in [d['left'], d['right']]:
            m = re.search(r'NOME_PTE\s*-\s*([^\n]*(?:\n(?![A-Z_]+\s*-|\d+\s*-\s*[A-Z])[^\n]*)*)', src)
            if m:
                nome_pte = re.sub(r'\s+', ' ', m.group(1)).strip()
                break
        if 'A662_' in nome_pte:
            via = nome_pte.split('A662_', 1)[1].strip()
        elif '/' in nome_pte:
            via = nome_pte.rsplit('/', 1)[1].strip()
        else:
            via = nome_pte

        n_pp = ''
        m = re.search(r'N\.\s*PORTA PERM\.\s*-\s*(\S+)', body)
        if m:
            nums = re.findall(r'(\d+)', m.group(1))
            if nums: n_pp = str(int(nums[-1]))

        p_pte = ''
        for src in [d['left'], d['right']]:
            m = re.search(r'PORTA_PTE\s*-\s*([^\n]*(?:\n(?![A-Z_]+\s*-|\d+\s*-\s*[A-Z])[^\n]*)*)', src)
            if m:
                val = re.sub(r'\s+', ' ', m.group(1)).strip()
                mm = re.search(r'-P_?0*(\d+)', val)
                if mm: p_pte = mm.group(1); break

        m = re.search(r'Indiriz\.:\s*(.*?)\s+Comune:', d['header']); indirizzo = m.group(1).strip() if m else ''

        # Dati privati (non vanno nella nota copiata)
        full_text = d['header'] + "\n" + body
        # Telefono cliente: cerca "Telefono", "Tel.", "Cellulare", "Recapito"
        m = re.search(r'(?:Telefono(?:\s+Reclamante)?|Recapito|Cellulare|Tel\.?)\s*[:\-]?\s*(\+?[\d\s\.\-\/]{6,})', full_text, re.IGNORECASE)
        phone_client = re.sub(r'[^\d\+]', '', m.group(1)).strip() if m else ''
        # ID SERVIZIO: pattern AAA + numeri (es. AAA12345)
        m = re.search(r'\b(AAA\d{4,})\b', full_text)
        id_servizio = m.group(1) if m else ''
        # ID RISORSA: cerca "ID Risorsa"/"ID_RISORSA"/"IDRisorsa" seguito da valore alfanumerico
        m = re.search(r'ID[_ ]?RISORSA[:\s\-]*([A-Z0-9_\-]+)', full_text, re.IGNORECASE)
        id_risorsa = m.group(1) if m else ''
        # Password apparato: formati vari (solo numeri, alfanumerico, o due gruppi separati da trattino)
        m = re.search(r'(?:PASSWORD[_\s]+APPARATO|PWD[_\s]+APPARATO|Password[_\s]+apparato)\s*[:\-]?\s*([A-Za-z0-9]+(?:\s*[-_]\s*[A-Za-z0-9]+)*)', full_text, re.IGNORECASE)
        apparato_password = m.group(1) if m else ''

        results.append({
            'wr': wr, 'is_numeric': wr.isdigit(),
            'cliente': cliente, 'olo': olo, 'splitter': splitter, 'via': via,
            'nome_pte_raw': nome_pte, 'n_porta_perm': n_pp, 'porta_pte': p_pte,
            'indirizzo': indirizzo,
            'phone_client': phone_client, 'id_servizio': id_servizio,
            'id_risorsa': id_risorsa, 'apparato_password': apparato_password,
        })
    return results


def compose_note(cliente, olo, splitter, via, n_porta_perm, porta_pte,
                 cpe='', ont_sfp='', wr='',
                 pte_est='PTE-EST', ts='TS', tc='TC', d='D', a='A',
                 mono_type='', mono='MONO', internal='INT',
                 materials=None):
    """Generate note text. Empty fields are skipped. `mono_type` (unified MONO INT / MONO EST / SBR / VRT STR SBR)
    takes precedence over legacy mono+internal pair."""
    parts = []
    def add(v):
        if v is not None and str(v).strip():
            parts.append(str(v).strip())
    add(splitter); add(via); add(pte_est)
    if n_porta_perm: parts.append(f"PFS {n_porta_perm}")
    if porta_pte:    parts.append(f"PTE {porta_pte}")
    add(ts); add(tc); add(d); add(a)
    if mono_type and mono_type.strip():
        parts.append(mono_type.strip())
    else:
        if mono and str(mono).strip(): parts.append(str(mono).strip())
        if internal and str(internal).strip(): parts.append(str(internal).strip())
    tech = " ".join(parts)

    lines = [f"WR: {wr}"]
    if cliente and cliente.strip(): lines.append(cliente.strip().lower())
    if olo and str(olo).strip():    lines.append(str(olo).strip())
    if tech:                        lines.append(tech)
    if cpe and cpe.strip():         lines.append(f"CPE: {cpe.strip()}")
    if ont_sfp and str(ont_sfp).strip(): lines.append(f"(ONT/SFP): {ont_sfp.strip()}")
    # Additional materials (EXT, etc.)
    for m in (materials or []):
        tipo = (m.get('tipo') or '').strip() if isinstance(m, dict) else ''
        ser = (m.get('serial') or '').strip() if isinstance(m, dict) else ''
        if tipo and ser:
            lines.append(f"{tipo}: {ser}")
        elif tipo:
            lines.append(f"{tipo}:")
    return "\n".join(lines)


def regenerate_note_text(doc):
    return compose_note(
        doc.get('cliente', ''), doc.get('olo', ''), doc.get('splitter', ''),
        doc.get('via', ''), doc.get('n_porta_perm', ''), doc.get('porta_pte', ''),
        doc.get('cpe', ''), doc.get('ont_sfp', ''), doc.get('wr', ''),
        doc.get('pte_est', 'PTE-EST'), doc.get('ts', 'TS'), doc.get('tc', 'TC'),
        doc.get('d', 'D'), doc.get('a', 'A'),
        doc.get('mono_type', ''), doc.get('mono', ''), doc.get('internal', ''),
        doc.get('materials', []),
    )


# ---------- Models ----------
class Photo(BaseModel):
    id: str
    storage_path: str
    filename: str
    content_type: str


class Material(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tipo: str = ''
    serial: str = ''


class Note(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ''
    shared_with: List[str] = Field(default_factory=list)  # user_ids of team partners for the day
    wr: str
    cliente: str = ''
    olo: str = ''
    splitter: str = ''
    via: str = ''
    n_porta_perm: str = ''
    porta_pte: str = ''
    cpe: str = ''
    ont_sfp: str = ''
    indirizzo: str = ''
    pte_est: str = 'PTE-EST'
    ts: str = 'TS'; tc: str = 'TC'; d: str = 'D'; a: str = 'A'
    mono: str = 'MONO'; internal: str = 'INT'
    mono_type: str = ''  # "MONO INT" | "MONO EST" | "SBR" | "VRT STR SBR"
    materials: List[Material] = Field(default_factory=list)  # extra materials (EXT etc.)
    # Private work fields — NOT included in note_text
    phone_client: str = ''
    apparato_password: str = ''
    id_servizio: str = ''
    id_risorsa: str = ''
    note_text: str = ''
    note_text_manual: bool = False
    photos: List[Photo] = Field(default_factory=list)
    pdf_filename: str = ''
    pdf_storage_path: str = ''
    # note_type: limbo (nuova, non conteggiata) | espletato | sospeso | guasto | migrazione
    note_type: str = 'limbo'
    status: str = 'limbo'  # legacy alias; kept for backward compat with UI toggles
    suspend_reason: str = ''
    note_date: str = ''  # ISO date (YYYY-MM-DD), user-editable; default = date of creation
    synced: bool = False
    synced_at: str = ''
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NoteUpdate(BaseModel):
    cliente: Optional[str] = None
    olo: Optional[str] = None
    splitter: Optional[str] = None
    via: Optional[str] = None
    n_porta_perm: Optional[str] = None
    porta_pte: Optional[str] = None
    cpe: Optional[str] = None
    ont_sfp: Optional[str] = None
    indirizzo: Optional[str] = None
    pte_est: Optional[str] = None
    ts: Optional[str] = None; tc: Optional[str] = None
    d: Optional[str] = None; a: Optional[str] = None
    mono: Optional[str] = None; internal: Optional[str] = None
    mono_type: Optional[str] = None
    materials: Optional[List[Material]] = None
    phone_client: Optional[str] = None
    apparato_password: Optional[str] = None
    id_servizio: Optional[str] = None
    id_risorsa: Optional[str] = None
    note_text: Optional[str] = None
    note_text_manual: Optional[bool] = None
    status: Optional[str] = None
    note_type: Optional[str] = None
    suspend_reason: Optional[str] = None
    note_date: Optional[str] = None


class BulkDeleteRequest(BaseModel):
    ids: List[str]


class VacationRequestCreate(BaseModel):
    from_date: str  # YYYY-MM-DD
    to_date: str
    reason: Optional[str] = ""


class VacationDecisionRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    admin_note: Optional[str] = ""


class DeleteTagRequest(BaseModel):
    tag: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = ''


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ApproveRequest(BaseModel):
    role: Optional[str] = "user"  # "user" | "magazzino"


class TeamLeaderRequest(BaseModel):
    is_team_leader: bool = True


class ArchivePurgeRequest(BaseModel):
    before: str  # ISO date YYYY-MM-DD; delete docs strictly older than this date
    collections: List[str] = Field(default_factory=lambda: ["notes", "serial_events", "notifications"])


class TeamRequest(BaseModel):
    partner_user_id: Optional[str] = ""  # empty string clears the partnership
    date: Optional[str] = None  # YYYY-MM-DD; default = today


class TagThreshold(BaseModel):
    tag: str
    threshold: int = 0  # 0 = disabled


class SuspendEmailRequest(BaseModel):
    to: EmailStr


async def _get_team_partners(user_id: str, date_iso: str) -> List[str]:
    """Return list of partner user_ids for the given user on the given date (bidirectional)."""
    partners = set()
    async for t in db.teams.find({"date": date_iso}):
        if t.get("primary_user_id") == user_id and t.get("partner_user_id"):
            partners.add(t["partner_user_id"])
        if t.get("partner_user_id") == user_id and t.get("primary_user_id"):
            partners.add(t["primary_user_id"])
    return list(partners)


class SerialItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    serial: str
    tipo: str = ""  # free-form tag (es. "CPE", "ONT", "SFP", "Router", etc.)
    status: str = "in_stock"  # in_stock | assegnato | scaricato
    assigned_to_user_id: str = ""
    assigned_to_name: str = ""
    downloaded_by_user_id: str = ""
    downloaded_by_name: str = ""
    downloaded_at: str = ""
    note: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SerialCreate(BaseModel):
    serial: str
    tipo: str = ""
    note: str = ""
    assigned_to_user_id: Optional[str] = ""


class SerialUpdate(BaseModel):
    serial: Optional[str] = None
    tipo: Optional[str] = None
    status: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    note: Optional[str] = None


class BulkSerialsRequest(BaseModel):
    serials: List[str]
    tipo: str = ""


# ---------- Serial Events / Notifications helpers ----------
async def add_serial_event(serial: str, event_type: str, actor_id: str = "", actor_name: str = "",
                           note_id: str = "", note_wr: str = "", extra: Optional[dict] = None):
    doc = {
        "id": str(uuid.uuid4()),
        "serial": serial,
        "event_type": event_type,  # created | assigned | unassigned | downloaded | manual_update | deleted
        "actor_id": actor_id,
        "actor_name": actor_name,
        "note_id": note_id,
        "note_wr": note_wr,
        "extra": extra or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.serial_events.insert_one(dict(doc))


async def notify_magazzino(kind: str, message: str, from_user_name: str = "", note_id: str = "",
                            note_wr: str = "", serials: Optional[List[str]] = None):
    now_iso = datetime.now(timezone.utc).isoformat()
    recipients = await db.users.find(
        {"is_approved": True, "role": {"$in": ["magazzino", "admin"]}},
        {"_id": 0, "id": 1}
    ).to_list(500)
    for r in recipients:
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": r["id"],
            "kind": kind,
            "message": message,
            "from_user_name": from_user_name,
            "note_id": note_id,
            "note_wr": note_wr,
            "serials": serials or [],
            "read": False,
            "created_at": now_iso,
        })


# ---------- Auth Routes ----------
@api_router.post("/auth/register")
async def register(req: RegisterRequest):
    email = req.email.lower().strip()
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password troppo corta (min 6 caratteri)")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email già registrata")
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id, "email": email, "name": (req.name or '').strip(),
        "password_hash": hash_password(req.password),
        "role": "user", "is_approved": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(dict(doc))
    return {"id": user_id, "email": email, "is_approved": False,
            "message": "Registrazione riuscita. Attendi l'approvazione dell'amministratore."}


@api_router.post("/auth/login")
async def login(req: LoginRequest):
    email = req.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Email o password non corretti")
    if not user.get("is_approved") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Account in attesa di approvazione dell'amministratore")
    token = create_access_token(user["id"], user["email"], user.get("role", "user"))
    is_super_admin = (user["email"].lower() == ADMIN_EMAIL) and user.get("role") == "admin"
    return {
        "access_token": token, "token_type": "bearer",
        "user": {"id": user["id"], "email": user["email"], "name": user.get("name", ""),
                 "role": user.get("role", "user"), "is_approved": user.get("is_approved", False),
                 "is_super_admin": is_super_admin,
                 "is_team_leader": bool(user.get("is_team_leader", False))},
    }


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    is_super_admin = (user.get("email", "").lower() == ADMIN_EMAIL) and user.get("role") == "admin"
    return {"id": user["id"], "email": user["email"], "name": user.get("name", ""),
            "role": user.get("role", "user"), "is_approved": user.get("is_approved", False),
            "is_super_admin": is_super_admin,
            "is_team_leader": bool(user.get("is_team_leader", False))}


@api_router.get("/auth/admin/users")
async def admin_list_users(admin: dict = Depends(get_current_admin)):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api_router.get("/auth/admin/pending")
async def admin_list_pending(admin: dict = Depends(get_current_admin)):
    docs = await db.users.find({"is_approved": False, "role": {"$ne": "admin"}},
                               {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api_router.post("/auth/admin/approve/{user_id}")
async def admin_approve(user_id: str, body: Optional[ApproveRequest] = None,
                        admin: dict = Depends(get_current_admin)):
    role = (body.role if body else "user") or "user"
    if role not in ("user", "magazzino"):
        raise HTTPException(status_code=400, detail="Ruolo non valido")
    res = await db.users.update_one({"id": user_id, "role": {"$ne": "admin"}},
                                    {"$set": {"is_approved": True, "role": role}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return {"approved": True, "id": user_id, "role": role}


@api_router.post("/auth/admin/set-role/{user_id}")
async def admin_set_role(user_id: str, body: ApproveRequest,
                         admin: dict = Depends(get_current_admin)):
    role = body.role or "user"
    if role not in ("user", "magazzino"):
        raise HTTPException(status_code=400, detail="Ruolo non valido")
    res = await db.users.update_one({"id": user_id, "role": {"$ne": "admin"}},
                                    {"$set": {"role": role}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return {"id": user_id, "role": role}


@api_router.post("/auth/admin/revoke/{user_id}")
async def admin_revoke(user_id: str, admin: dict = Depends(get_current_admin)):
    res = await db.users.update_one({"id": user_id, "role": {"$ne": "admin"}},
                                    {"$set": {"is_approved": False}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Utente non trovato o non modificabile")
    return {"revoked": True, "id": user_id}


@api_router.delete("/auth/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(get_current_admin)):
    user = await db.users.find_one({"id": user_id})
    if not user or user.get("role") == "admin":
        raise HTTPException(status_code=404, detail="Utente non eliminabile")
    await db.users.delete_one({"id": user_id})
    # Cascade delete notes owned
    await db.notes.delete_many({"user_id": user_id})
    return {"deleted": True}


@api_router.post("/auth/admin/promote/{user_id}")
async def admin_promote(user_id: str, admin: dict = Depends(get_current_admin)):
    """Promuove un utente a ruolo admin. Chiunque sia admin può farlo."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    if target.get("role") == "admin":
        raise HTTPException(status_code=400, detail="L'utente è già admin")
    await db.users.update_one({"id": user_id}, {"$set": {"role": "admin", "is_approved": True}})
    return {"promoted": True, "id": user_id}


@api_router.post("/auth/admin/demote/{user_id}")
async def admin_demote(user_id: str, body: Optional[ApproveRequest] = None,
                       admin: dict = Depends(get_current_admin)):
    """Declassa un admin. Solo il super-admin (ADMIN_EMAIL) può farlo. Il super-admin stesso non può essere declassato."""
    if admin.get("email", "").lower() != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Solo il super-admin può declassare altri admin")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    if target.get("email", "").lower() == ADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="Il super-admin non può essere declassato")
    if target.get("role") != "admin":
        raise HTTPException(status_code=400, detail="L'utente non è admin")
    new_role = (body.role if body else "user") or "user"
    if new_role not in ("user", "magazzino"):
        raise HTTPException(status_code=400, detail="Ruolo non valido")
    await db.users.update_one({"id": user_id}, {"$set": {"role": new_role}})
    return {"demoted": True, "id": user_id, "role": new_role}


@api_router.post("/auth/admin/set-team-leader/{user_id}")
async def admin_set_team_leader(user_id: str, body: TeamLeaderRequest,
                                 admin: dict = Depends(get_current_admin)):
    """Designa (o rimuove) un utente come caposquadra. Solo i caposquadra possono selezionare il compagno di squadra."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    await db.users.update_one({"id": user_id}, {"$set": {"is_team_leader": bool(body.is_team_leader)}})
    # Se rimosso il flag, azzera anche le sue partnership attive
    if not body.is_team_leader:
        await db.teams.delete_many({"primary_user_id": user_id})
    return {"ok": True, "id": user_id, "is_team_leader": bool(body.is_team_leader)}


# ---------- Archivio DB (admin) ----------
ARCHIVABLE_COLLECTIONS = {
    "notes": "created_at",
    "serial_events": "created_at",
    "notifications": "created_at",
    "vacations": "created_at",
}


@api_router.get("/admin/archive/export")
async def archive_export(before: str = Query(""), admin: dict = Depends(get_current_admin)):
    """Dump JSON di note + eventi seriali + notifiche + ferie (opzionale filtro before=YYYY-MM-DD).
    Ritorna il file per il download; non elimina nulla."""
    q: dict = {}
    if before:
        try:
            datetime.fromisoformat(before)
        except Exception:
            raise HTTPException(status_code=400, detail="Parametro 'before' non valido (usa YYYY-MM-DD)")
        q = {"created_at": {"$lt": before + "T23:59:59"}}
    payload: dict = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": admin.get("email"),
        "before": before or None,
        "collections": {},
    }
    for coll in ARCHIVABLE_COLLECTIONS.keys():
        docs = await db[coll].find(q if before else {}, {"_id": 0}).to_list(100000)
        payload["collections"][coll] = docs
    # Aggiungiamo anche users e serials (senza filtro) per un archivio completo
    payload["collections"]["users"] = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(100000)
    payload["collections"]["serials"] = await db.serials.find({}, {"_id": 0}).to_list(100000)
    return payload


@api_router.post("/admin/archive/purge")
async def archive_purge(req: ArchivePurgeRequest, admin: dict = Depends(get_current_admin)):
    """Elimina i documenti di note/serial_events/notifications/vacations più vecchi di 'before' (YYYY-MM-DD).
    Non tocca users e serials. Usalo DOPO aver scaricato l'export per liberare spazio."""
    try:
        datetime.fromisoformat(req.before)
    except Exception:
        raise HTTPException(status_code=400, detail="Parametro 'before' non valido (usa YYYY-MM-DD)")
    cutoff = req.before + "T23:59:59"
    deleted: dict = {}
    for coll in req.collections:
        if coll not in ARCHIVABLE_COLLECTIONS:
            raise HTTPException(status_code=400, detail=f"Collezione '{coll}' non archiviabile")
        res = await db[coll].delete_many({"created_at": {"$lt": cutoff}})
        deleted[coll] = res.deleted_count
    return {"purged": True, "before": req.before, "deleted": deleted}


# ---------- Note Routes ----------
@api_router.get("/")
async def root():
    return {"message": "OpenFiber Notes API"}


@api_router.post("/pdf/parse")
async def parse_pdf(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Deve essere un file PDF")
    data = await file.read()

    pdf_path = f"{APP_NAME}/pdfs/{uuid.uuid4()}.pdf"
    try:
        put_object(pdf_path, data, "application/pdf")
    except Exception:
        logging.exception("PDF storage failed")
        pdf_path = ''

    try:
        parsed = parse_openfiber_pdf(data)
    except Exception as e:
        logging.exception("PDF parse failed")
        raise HTTPException(status_code=400, detail=f"Impossibile leggere il PDF: {e}")

    created_notes = []
    fault_notes = []
    today_iso = datetime.now(timezone.utc).date().isoformat()
    # Detect team partner for shared_with
    partner_ids = await _get_team_partners(user["id"], today_iso)
    duplicate_wrs = []
    for item in parsed:
        existing = await db.notes.find_one({
            "wr": item['wr'],
            "$or": [{"user_id": user["id"]}, {"shared_with": user["id"]}]
        })
        if existing:
            duplicate_wrs.append(item['wr'])
            continue
        is_fault = not item['is_numeric']
        note = Note(
            user_id=user["id"],
            shared_with=partner_ids,
            wr=item['wr'], cliente=item['cliente'], olo=item['olo'],
            splitter=item['splitter'], via=item['via'],
            n_porta_perm=item['n_porta_perm'], porta_pte=item['porta_pte'],
            indirizzo=item['indirizzo'],
            phone_client=item.get('phone_client', ''),
            apparato_password=item.get('apparato_password', ''),
            id_servizio=item.get('id_servizio', ''),
            id_risorsa=item.get('id_risorsa', ''),
            pdf_filename=file.filename, pdf_storage_path=pdf_path,
            note_date=today_iso,
            note_type=('guasto' if is_fault else 'limbo'),
            status=('guasto' if is_fault else 'limbo'),
        )
        note.note_text = regenerate_note_text(note.model_dump())
        doc = note.model_dump()
        await db.notes.insert_one(dict(doc))
        if is_fault:
            fault_notes.append(doc)
        else:
            created_notes.append(doc)

    return {"created_count": len(created_notes),
            "fault_count": len(fault_notes),
            "duplicate_count": len(duplicate_wrs),
            "duplicate_wrs": duplicate_wrs,
            "skipped_wr": [n['wr'] for n in fault_notes],  # legacy field name
            "notes": created_notes + fault_notes,
            "pdf_storage_path": pdf_path,
            "pdf_filename": file.filename}


@api_router.get("/notes")
async def list_notes(search: str = Query(''), user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        q = {}
    else:
        q = {"$or": [{"user_id": user["id"]}, {"shared_with": user["id"]}]}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q = {"$and": [q, {"$or": [{"wr": rx}, {"cliente": rx}, {"olo": rx}]}]}
    docs = await db.notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    # Legacy migration: fill note_type/note_date defaults
    for d in docs:
        if not d.get('note_type'):
            legacy = d.get('status', 'limbo')
            d['note_type'] = legacy if legacy in ('espletato', 'sospeso', 'guasto', 'migrazione') else 'limbo'
        if not d.get('note_date'):
            d['note_date'] = (d.get('created_at') or '')[:10]
    return docs


async def _get_own_note(note_id: str, user: dict) -> dict:
    if user.get("role") == "admin":
        query = {"id": note_id}
    else:
        query = {"id": note_id, "$or": [{"user_id": user["id"]}, {"shared_with": user["id"]}]}
    doc = await db.notes.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Nota non trovata")
    return doc


# ---------- Notes stats (per data range, esclude sabati) ----------
def _daterange(start_iso: str, end_iso: str):
    from datetime import date, timedelta
    s = date.fromisoformat(start_iso); e = date.fromisoformat(end_iso)
    cur = s
    while cur <= e:
        yield cur
        cur = cur + timedelta(days=1)


@api_router.get("/notes/stats")
async def notes_stats(
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    user: dict = Depends(get_current_user),
):
    from datetime import date, timedelta
    today = datetime.now(timezone.utc).date()
    if not from_date: from_date = today.replace(day=1).isoformat()
    if not to_date: to_date = today.isoformat()
    q = {"$or": [{"user_id": user["id"]}, {"shared_with": user["id"]}]}
    docs = await db.notes.find(q, {"_id": 0, "note_type": 1, "status": 1, "note_date": 1, "created_at": 1}).to_list(20000)

    def _classify(d):
        t = d.get('note_type') or d.get('status') or 'limbo'
        return t if t in ('espletato', 'sospeso', 'guasto', 'migrazione') else 'limbo'

    def _get_date(d):
        return (d.get('note_date') or (d.get('created_at') or '')[:10])

    tot = {"limbo": 0, "espletato": 0, "sospeso": 0, "guasto": 0, "migrazione": 0}
    by_day = {}
    for d in docs:
        dt = _get_date(d)
        if not dt: continue
        if dt < from_date or dt > to_date: continue
        c = _classify(d)
        tot[c] = tot.get(c, 0) + 1
        by_day.setdefault(dt, {"limbo": 0, "espletato": 0, "sospeso": 0, "guasto": 0, "migrazione": 0})
        by_day[dt][c] = by_day[dt].get(c, 0) + 1

    counted_days = [d for d in _daterange(from_date, to_date) if d.weekday() != 5]
    total_completed = tot.get("espletato", 0) + tot.get("migrazione", 0)
    total_faults = tot.get("guasto", 0)
    avg_completed = round(total_completed / max(len(counted_days), 1), 2)
    avg_faults = round(total_faults / max(len(counted_days), 1), 2)

    daily = []
    for d in _daterange(from_date, to_date):
        iso = d.isoformat()
        entry = by_day.get(iso, {"limbo": 0, "espletato": 0, "sospeso": 0, "guasto": 0, "migrazione": 0})
        entry["date"] = iso
        entry["is_saturday"] = d.weekday() == 5
        daily.append(entry)

    return {
        "from": from_date, "to": to_date,
        "totals": tot,
        "avg_completed_per_working_day": avg_completed,
        "avg_faults_per_working_day": avg_faults,
        "working_days_count": len(counted_days),
        "daily": daily,
    }


@api_router.get("/notes/{note_id}")
async def get_note(note_id: str, user: dict = Depends(get_current_user)):
    return await _get_own_note(note_id, user)


@api_router.patch("/notes/{note_id}")
async def update_note(note_id: str, upd: NoteUpdate, user: dict = Depends(get_current_user)):
    doc = await _get_own_note(note_id, user)
    updates = {k: v for k, v in upd.model_dump().items() if v is not None}
    # Convert Material Pydantic objects → dict
    if 'materials' in updates:
        updates['materials'] = [m.model_dump() if hasattr(m, 'model_dump') else m for m in updates['materials']]
    # Sync legacy status <-> note_type
    if 'note_type' in updates and 'status' not in updates:
        updates['status'] = updates['note_type']
    elif 'status' in updates and 'note_type' not in updates:
        updates['note_type'] = updates['status']
    if 'note_text' in updates:
        doc.update(updates)
        doc['note_text_manual'] = updates.get('note_text_manual', True)
    else:
        doc.update(updates)
        if not doc.get('note_text_manual', False):
            doc['note_text'] = regenerate_note_text(doc)
    doc['updated_at'] = datetime.now(timezone.utc).isoformat()
    await db.notes.update_one({"id": note_id}, {"$set": doc})
    return doc


@api_router.post("/notes/{note_id}/regenerate")
async def regenerate_note(note_id: str, user: dict = Depends(get_current_user)):
    doc = await _get_own_note(note_id, user)
    doc['note_text'] = regenerate_note_text(doc)
    doc['note_text_manual'] = False
    doc['updated_at'] = datetime.now(timezone.utc).isoformat()
    await db.notes.update_one({"id": note_id}, {"$set": doc})
    return doc


@api_router.delete("/notes/{note_id}")
async def delete_note(note_id: str, user: dict = Depends(get_current_user)):
    await _get_own_note(note_id, user)
    res = await db.notes.delete_one({"id": note_id, "user_id": user["id"]})
    return {"deleted": res.deleted_count}


@api_router.post("/notes/bulk-delete")
async def bulk_delete_notes(req: BulkDeleteRequest, user: dict = Depends(get_current_user)):
    if not req.ids:
        return {"deleted": 0}
    res = await db.notes.delete_many({"id": {"$in": req.ids}, "user_id": user["id"]})
    return {"deleted": res.deleted_count}


@api_router.post("/notes/{note_id}/photos")
async def upload_photos(note_id: str, files: List[UploadFile] = File(...),
                        user: dict = Depends(get_current_user)):
    doc = await _get_own_note(note_id, user)
    photos = doc.get('photos', [])
    for f in files:
        ext = (f.filename.rsplit('.', 1)[-1] if '.' in f.filename else 'jpg').lower()
        path = f"{APP_NAME}/photos/{note_id}/{uuid.uuid4()}.{ext}"
        data = await f.read()
        put_object(path, data, f.content_type or "image/jpeg")
        photos.append({"id": str(uuid.uuid4()), "storage_path": path,
                       "filename": f.filename, "content_type": f.content_type or "image/jpeg"})
    await db.notes.update_one({"id": note_id},
                              {"$set": {"photos": photos,
                                        "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"photos": photos}


@api_router.delete("/notes/{note_id}/photos/{photo_id}")
async def delete_photo(note_id: str, photo_id: str, user: dict = Depends(get_current_user)):
    doc = await _get_own_note(note_id, user)
    photos = [p for p in doc.get('photos', []) if p.get('id') != photo_id]
    await db.notes.update_one({"id": note_id},
                              {"$set": {"photos": photos,
                                        "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"photos": photos}


@api_router.get("/files")
async def download_file(path: str = Query(...)):
    # Guard: only serve objects inside this app's storage prefix (anti path-traversal)
    if ".." in path or not path.startswith(APP_NAME + "/"):
        raise HTTPException(status_code=404, detail="File non trovato")
    try:
        data, ct = get_object(path)
    except Exception:
        raise HTTPException(status_code=404, detail="File non trovato")
    return Response(content=data, media_type=ct)


# ---------- Inventory / Magazzino ----------
async def get_magazzino_or_admin(user: dict = Depends(get_current_user)) -> dict:
    role = user.get("role")
    if role not in ("admin", "magazzino"):
        raise HTTPException(status_code=403, detail="Accesso riservato al magazzino / admin")
    return user


def _serial_from_doc(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@api_router.get("/inventory/serials")
async def list_serials(
    search: str = Query(''),
    status: str = Query(''),
    tipo: str = Query(''),
    user: dict = Depends(get_magazzino_or_admin),
):
    q = {}
    if status:
        q["status"] = status
    if tipo:
        q["tipo"] = tipo
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q = {"$and": [q, {"$or": [{"serial": rx}, {"assigned_to_name": rx}, {"downloaded_by_name": rx}]}]} if q else {"$or": [{"serial": rx}, {"assigned_to_name": rx}, {"downloaded_by_name": rx}]}
    docs = await db.serials.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return docs


@api_router.post("/inventory/serials")
async def create_serial(req: SerialCreate, user: dict = Depends(get_magazzino_or_admin)):
    raw = (req.serial or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Seriale richiesto")
    # Split by whitespace/commas/semicolons/newlines → multi-serial paste
    tokens = [t.strip() for t in re.split(r"[\s,;]+", raw) if t.strip()]
    if len(tokens) > 1:
        created, skipped = [], []
        tipo = (req.tipo or "").strip()
        actor_name = user.get("name") or user.get("email") or ""
        for s in tokens:
            if await db.serials.find_one({"serial": s}):
                skipped.append(s); continue
            item = SerialItem(serial=s, tipo=tipo)
            await db.serials.insert_one(dict(item.model_dump()))
            await add_serial_event(s, "created", user["id"], actor_name,
                                    extra={"tipo": tipo, "multi_paste": True})
            created.append(s)
        if tipo:
            try: await _check_threshold(tipo, actor_name=actor_name)
            except Exception: pass
        return {"multi": True, "created": created, "skipped": skipped, "created_count": len(created)}

    serial = tokens[0]
    if await db.serials.find_one({"serial": serial}):
        raise HTTPException(status_code=400, detail="Seriale già presente")
    item = SerialItem(serial=serial, tipo=(req.tipo or "").strip(), note=req.note or "")
    if req.assigned_to_user_id:
        u = await db.users.find_one({"id": req.assigned_to_user_id})
        if u:
            item.assigned_to_user_id = u["id"]
            item.assigned_to_name = u.get("name") or u.get("email") or ""
            item.status = "assegnato"
    doc = item.model_dump()
    await db.serials.insert_one(dict(doc))
    actor_name = user.get("name") or user.get("email") or ""
    await add_serial_event(serial, "created", user["id"], actor_name,
                            extra={"tipo": item.tipo, "status": item.status})
    if item.assigned_to_user_id:
        await add_serial_event(serial, "assigned", user["id"], actor_name,
                                extra={"to_user_id": item.assigned_to_user_id,
                                       "to_user_name": item.assigned_to_name})
    if item.tipo:
        try: await _check_threshold(item.tipo, actor_name=actor_name)
        except Exception: pass
    return doc


@api_router.post("/inventory/serials/bulk")
async def create_serials_bulk(req: BulkSerialsRequest, user: dict = Depends(get_magazzino_or_admin)):
    created, skipped = [], []
    actor_name = user.get("name") or user.get("email") or ""
    for raw in req.serials:
        s = (raw or "").strip()
        if not s:
            continue
        if await db.serials.find_one({"serial": s}):
            skipped.append(s); continue
        item = SerialItem(serial=s, tipo=(req.tipo or "").strip())
        d = item.model_dump()
        await db.serials.insert_one(dict(d))
        await add_serial_event(s, "created", user["id"], actor_name,
                                extra={"tipo": item.tipo, "bulk": True})
        created.append(d)
    return {"created": len(created), "skipped": skipped, "items": created}


@api_router.patch("/inventory/serials/{sid}")
async def update_serial(sid: str, upd: SerialUpdate, user: dict = Depends(get_magazzino_or_admin)):
    doc = await db.serials.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Seriale non trovato")
    updates = {k: v for k, v in upd.model_dump().items() if v is not None}
    if "tipo" in updates:
        updates["tipo"] = (updates["tipo"] or "").strip()
    actor_name = user.get("name") or user.get("email") or ""
    event_to_emit = None
    event_extra = {}
    if "assigned_to_user_id" in updates:
        uid = updates["assigned_to_user_id"]
        if uid:
            u = await db.users.find_one({"id": uid})
            if not u:
                raise HTTPException(status_code=400, detail="Utente assegnatario inesistente")
            updates["assigned_to_user_id"] = u["id"]
            updates["assigned_to_name"] = u.get("name") or u.get("email") or ""
            if doc.get("status") == "in_stock":
                updates["status"] = "assegnato"
            event_to_emit = "assigned"
            event_extra = {"to_user_id": u["id"], "to_user_name": updates["assigned_to_name"]}
        else:
            updates["assigned_to_user_id"] = ""
            updates["assigned_to_name"] = ""
            if doc.get("status") == "assegnato":
                updates["status"] = "in_stock"
            event_to_emit = "unassigned"
            event_extra = {"from_user_name": doc.get("assigned_to_name", "")}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.serials.update_one({"id": sid}, {"$set": updates})
    fresh = await db.serials.find_one({"id": sid}, {"_id": 0})
    if event_to_emit:
        await add_serial_event(fresh["serial"], event_to_emit, user["id"], actor_name, extra=event_extra)
    elif updates:
        await add_serial_event(fresh["serial"], "manual_update", user["id"], actor_name,
                                extra={k: v for k, v in updates.items() if k != "updated_at"})
    return fresh


@api_router.delete("/inventory/serials/{sid}")
async def delete_serial(sid: str, user: dict = Depends(get_magazzino_or_admin)):
    doc = await db.serials.find_one({"id": sid}, {"_id": 0})
    res = await db.serials.delete_one({"id": sid})
    if doc and res.deleted_count:
        actor_name = user.get("name") or user.get("email") or ""
        await add_serial_event(doc["serial"], "deleted", user["id"], actor_name)
        try: await _check_threshold(doc.get("tipo") or "", actor_name=actor_name)
        except Exception: pass
    return {"deleted": res.deleted_count}


@api_router.get("/inventory/serials/{sid}/history")
async def serial_history(sid: str, user: dict = Depends(get_magazzino_or_admin)):
    doc = await db.serials.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Seriale non trovato")
    events = await db.serial_events.find(
        {"serial": doc["serial"]}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    return {"serial": doc, "events": events}


class BulkSearchSerials(BaseModel):
    serials: List[str]


@api_router.post("/inventory/serials/search-bulk")
async def search_serials_bulk(req: BulkSearchSerials, user: dict = Depends(get_magazzino_or_admin)):
    """Cerca più seriali in blocco con corrispondenza ESATTA (non 'contiene'),
    utile quando i seriali condividono un prefisso comune."""
    wanted = [s.strip() for s in req.serials if s.strip()]
    if not wanted:
        return {"found": [], "not_found": []}
    docs = await db.serials.find({"serial": {"$in": wanted}}, {"_id": 0}).to_list(len(wanted) + 1)
    found_serials = {d["serial"] for d in docs}
    not_found = [s for s in wanted if s not in found_serials]
    return {"found": docs, "not_found": not_found}


@api_router.get("/inventory/tags")
async def list_tags(user: dict = Depends(get_magazzino_or_admin)):
    tags = await db.serials.distinct("tipo")
    tags = sorted([t for t in tags if isinstance(t, str) and t.strip()])
    return {"tags": tags}


@api_router.get("/inventory/stats")
async def inventory_stats(user: dict = Depends(get_magazzino_or_admin)):
    pipeline = [
        {"$group": {
            "_id": {"$ifNull": ["$tipo", ""]},
            "total": {"$sum": 1},
            "in_stock": {"$sum": {"$cond": [{"$eq": ["$status", "in_stock"]}, 1, 0]}},
            "assegnato": {"$sum": {"$cond": [{"$eq": ["$status", "assegnato"]}, 1, 0]}},
            "scaricato": {"$sum": {"$cond": [{"$eq": ["$status", "scaricato"]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
    ]
    by_tag = []
    async for row in db.serials.aggregate(pipeline):
        by_tag.append({
            "tag": row["_id"] or "",
            "total": row["total"],
            "in_stock": row["in_stock"],
            "assegnato": row["assegnato"],
            "scaricato": row["scaricato"],
        })
    total = sum(x["total"] for x in by_tag)
    return {"total": total, "by_tag": by_tag}


@api_router.get("/inventory/export.csv")
async def export_inventory_csv(user: dict = Depends(get_magazzino_or_admin)):
    docs = await db.serials.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    def esc(v):
        s = "" if v is None else str(v)
        if any(c in s for c in [",", "\"", "\n", "\r"]):
            return "\"" + s.replace("\"", "\"\"") + "\""
        return s
    header = ["seriale", "tipo", "stato", "assegnato_a", "scaricato_da", "data_scarico",
              "note", "creato_il", "aggiornato_il"]
    rows = [",".join(header)]
    for d in docs:
        rows.append(",".join([
            esc(d.get("serial")), esc(d.get("tipo")), esc(d.get("status")),
            esc(d.get("assigned_to_name")), esc(d.get("downloaded_by_name")),
            esc(d.get("downloaded_at")), esc(d.get("note")),
            esc(d.get("created_at")), esc(d.get("updated_at")),
        ]))
    body = "\ufeff" + "\n".join(rows)  # BOM per Excel
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=magazzino.csv"},
    )


@api_router.get("/inventory/users")
async def list_users_for_assignment(user: dict = Depends(get_magazzino_or_admin)):
    docs = await db.users.find({"is_approved": True, "role": {"$in": ["user", "admin"]}},
                               {"_id": 0, "password_hash": 0}).sort("email", 1).to_list(500)
    return docs


# ---------- Note Sync (marks CPE + ONT serials as scaricato) ----------
@api_router.post("/notes/{note_id}/sync")
async def sync_note_serials(note_id: str, user: dict = Depends(get_current_user)):
    doc = await _get_own_note(note_id, user)
    updates_count = 0
    synced_serials = []
    now_iso = datetime.now(timezone.utc).isoformat()
    display_name = user.get("name") or user.get("email") or user.get("id")
    olo_val = (doc.get("olo") or "").strip()
    for field, tipo in (("cpe", "CPE"), ("ont_sfp", "ONT")):
        raw = (doc.get(field) or "").strip()
        if not raw:
            continue
        existing = await db.serials.find_one({"serial": raw})
        if existing:
            existing_tipo = existing.get("tipo") or tipo
            await db.serials.update_one(
                {"id": existing["id"]},
                {"$set": {
                    "status": "scaricato",
                    "downloaded_by_user_id": user["id"],
                    "downloaded_by_name": display_name,
                    "downloaded_at": now_iso,
                    "downloaded_olo": olo_val,
                    "downloaded_note_wr": doc.get("wr", ""),
                    "downloaded_note_id": doc.get("id", ""),
                    "updated_at": now_iso,
                }},
            )
            tipo_for_event = existing_tipo
        else:
            item = SerialItem(
                serial=raw, tipo=tipo, status="scaricato",
                downloaded_by_user_id=user["id"], downloaded_by_name=display_name,
                downloaded_at=now_iso,
            )
            d_ins = dict(item.model_dump())
            d_ins["downloaded_olo"] = olo_val
            d_ins["downloaded_note_wr"] = doc.get("wr", "")
            d_ins["downloaded_note_id"] = doc.get("id", "")
            await db.serials.insert_one(d_ins)
            await add_serial_event(raw, "created", user["id"], display_name,
                                    extra={"tipo": tipo, "auto_from_sync": True})
            tipo_for_event = tipo
        await add_serial_event(raw, "downloaded", user["id"], display_name,
                                note_id=doc.get("id", ""), note_wr=doc.get("wr", ""),
                                extra={"tipo": tipo_for_event, "olo": olo_val})
        synced_serials.append(raw)
        updates_count += 1
        # Threshold check for this tag
        try: await _check_threshold(tipo_for_event, actor_name=display_name)
        except Exception: pass
    await db.notes.update_one({"id": note_id},
                              {"$set": {"synced": True, "synced_at": now_iso, "updated_at": now_iso}})
    if synced_serials:
        wr = doc.get("wr", "")
        msg = f"{display_name} ha scaricato {len(synced_serials)} seriale/i sulla WR {wr}"
        await notify_magazzino("note_sync", msg, from_user_name=display_name,
                                note_id=note_id, note_wr=wr, serials=synced_serials)
    fresh = await db.notes.find_one({"id": note_id}, {"_id": 0})
    return {"synced": updates_count, "note": fresh}


@api_router.post("/notes/{note_id}/unsync")
async def unsync_note_serials(note_id: str, user: dict = Depends(get_current_user)):
    """Annulla la sincronizzazione: ripristina i seriali scaricati da questa nota
    (status → assegnato/in_stock) e segna la nota come non sincronizzata."""
    doc = await _get_own_note(note_id, user)
    now_iso = datetime.now(timezone.utc).isoformat()
    display_name = user.get("name") or user.get("email") or user.get("id")
    restored = []
    async for s in db.serials.find({"downloaded_note_id": note_id, "status": "scaricato"}, {"_id": 0}):
        new_status = "assegnato" if s.get("assigned_to_user_id") else "in_stock"
        await db.serials.update_one({"id": s["id"]}, {"$set": {
            "status": new_status,
            "downloaded_by_user_id": "", "downloaded_by_name": "", "downloaded_at": "",
            "downloaded_olo": "", "downloaded_note_wr": "", "downloaded_note_id": "",
            "updated_at": now_iso,
        }})
        await add_serial_event(s["serial"], "manual_update", user["id"], display_name,
                                note_id=note_id, note_wr=doc.get("wr", ""),
                                extra={"reason": "unsync_note"})
        restored.append(s["serial"])
    await db.notes.update_one({"id": note_id},
                              {"$set": {"synced": False, "synced_at": "", "updated_at": now_iso}})
    if restored:
        wr = doc.get("wr", "")
        await notify_magazzino("note_unsync",
                               f"{display_name} ha annullato lo scarico di {len(restored)} seriale/i sulla WR {wr}",
                               from_user_name=display_name, note_id=note_id, note_wr=wr, serials=restored)
    fresh = await db.notes.find_one({"id": note_id}, {"_id": 0})
    return {"unsynced": len(restored), "serials": restored, "note": fresh}


# ---------- Notifications ----------
# ---------- Team (compagno di squadra giornaliero) ----------
@api_router.get("/team/today")
async def team_today(date: str = Query(""), user: dict = Depends(get_current_user)):
    d = date or datetime.now(timezone.utc).date().isoformat()
    t = await db.teams.find_one({"primary_user_id": user["id"], "date": d}, {"_id": 0})
    partners = await _get_team_partners(user["id"], d)
    partner_info = None
    if partners:
        p = await db.users.find_one({"id": partners[0]}, {"_id": 0, "id": 1, "email": 1, "name": 1})
        partner_info = p
    return {"date": d, "record": t, "partner": partner_info, "partner_ids": partners}


@api_router.post("/team/today")
async def set_team_today(req: TeamRequest, user: dict = Depends(get_current_user)):
    # Solo i caposquadra (o admin) possono impostare il compagno di squadra
    if not user.get("is_team_leader", False) and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo il caposquadra può impostare il compagno di squadra. Chiedi all'amministratore di designarti caposquadra.")
    d = req.date or datetime.now(timezone.utc).date().isoformat()
    # Clear existing partnerships owned by me for that day (only 1 partner per day per direction)
    await db.teams.delete_many({"primary_user_id": user["id"], "date": d})
    partner_ids: List[str] = []
    if req.partner_user_id:
        partner = await db.users.find_one({"id": req.partner_user_id})
        if not partner:
            raise HTTPException(status_code=400, detail="Compagno non trovato")
        if partner["id"] == user["id"]:
            raise HTTPException(status_code=400, detail="Non puoi selezionare te stesso")
        await db.teams.insert_one({
            "id": str(uuid.uuid4()),
            "primary_user_id": user["id"],
            "partner_user_id": partner["id"],
            "date": d,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        partner_ids = [partner["id"]]
    # Recompute shared_with on today's notes (both directions)
    all_partners = await _get_team_partners(user["id"], d)
    await db.notes.update_many(
        {"user_id": user["id"], "note_date": d},
        {"$set": {"shared_with": all_partners}}
    )
    return {"ok": True, "partner_ids": partner_ids}


@api_router.get("/users/approved")
async def list_approved_users(user: dict = Depends(get_current_user)):
    docs = await db.users.find(
        {"is_approved": True, "id": {"$ne": user["id"]}},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1}
    ).sort("email", 1).to_list(500)
    return docs


# ---------- Sospesi: invio mail ----------
@api_router.post("/notes/{note_id}/send-suspend-email")
async def send_suspend_email(note_id: str, req: SuspendEmailRequest, user: dict = Depends(get_current_user)):
    doc = await _get_own_note(note_id, user)
    if (doc.get('note_type') or doc.get('status')) != 'sospeso':
        raise HTTPException(status_code=400, detail="La nota non è sospesa")
    body = {
        "to": str(req.to),
        "subject": f"Nota sospesa - WR {doc.get('wr','')} - OLO {doc.get('olo','')}",
        "body": f"Codice OLO: {doc.get('olo','')}\nCodice WR: {doc.get('wr','')}\nMotivo sospensione: {doc.get('suspend_reason','')}\n",
    }
    return body  # Client-side handled via mailto: — return prepared fields


# ---------- Warehouse Thresholds ----------
@api_router.get("/inventory/thresholds")
async def list_thresholds(user: dict = Depends(get_magazzino_or_admin)):
    docs = await db.tag_thresholds.find({}, {"_id": 0}).sort("tag", 1).to_list(500)
    return docs


@api_router.post("/inventory/thresholds")
async def set_threshold(req: TagThreshold, user: dict = Depends(get_magazzino_or_admin)):
    tag = (req.tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag richiesto")
    thr = max(0, int(req.threshold or 0))
    now = datetime.now(timezone.utc).isoformat()
    if thr == 0:
        await db.tag_thresholds.delete_one({"tag": tag})
        return {"tag": tag, "threshold": 0}
    await db.tag_thresholds.update_one(
        {"tag": tag},
        {"$set": {"tag": tag, "threshold": thr, "updated_at": now}},
        upsert=True,
    )
    await _check_threshold(tag, actor_name=(user.get('name') or user.get('email') or ''))
    return {"tag": tag, "threshold": thr}


async def _check_threshold(tag: str, actor_name: str = ""):
    """If tag stock <= threshold, notify magazzino/admin (dedup by 6h window)."""
    thr_doc = await db.tag_thresholds.find_one({"tag": tag})
    if not thr_doc or thr_doc.get("threshold", 0) <= 0:
        return
    in_stock = await db.serials.count_documents({"tipo": tag, "status": "in_stock"})
    if in_stock > thr_doc["threshold"]:
        return
    # Dedup: skip if we already sent a threshold alert for this tag in the last 6 hours
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    existing = await db.notifications.find_one(
        {"kind": "threshold_alert", "note_wr": tag, "created_at": {"$gt": cutoff}}
    )
    if existing:
        return
    await notify_magazzino(
        "threshold_alert",
        f"⚠️ Scorte basse: solo {in_stock} '{tag}' in stock (soglia: {thr_doc['threshold']})",
        from_user_name=actor_name or "sistema",
        note_wr=tag,  # reuse field to identify the tag
    )


# ---------- Warehouse: bulk delete + delete tag ----------
@api_router.post("/inventory/serials/bulk-delete")
async def bulk_delete_serials(req: BulkDeleteRequest, user: dict = Depends(get_magazzino_or_admin)):
    if not req.ids:
        return {"deleted": 0}
    docs = await db.serials.find({"id": {"$in": req.ids}}, {"_id": 0}).to_list(len(req.ids) + 1)
    r = await db.serials.delete_many({"id": {"$in": req.ids}})
    actor_name = user.get("name") or user.get("email") or ""
    affected_tags = set()
    for d in docs:
        await add_serial_event(d["serial"], "deleted", user["id"], actor_name, extra={"bulk": True})
        if d.get("tipo"): affected_tags.add(d["tipo"])
    for tag in affected_tags:
        try: await _check_threshold(tag, actor_name=actor_name)
        except Exception: pass
    return {"deleted": r.deleted_count}


class BulkUpdateSerials(BaseModel):
    ids: List[str]
    tipo: Optional[str] = None
    assigned_to_user_id: Optional[str] = None


@api_router.post("/inventory/serials/bulk-update")
async def bulk_update_serials(req: BulkUpdateSerials, user: dict = Depends(get_magazzino_or_admin)):
    """Modifica massiva di tag e/o assegnazione per i seriali selezionati."""
    if not req.ids:
        return {"updated": 0}
    actor_name = user.get("name") or user.get("email") or ""
    now = datetime.now(timezone.utc).isoformat()
    set_assignment = req.assigned_to_user_id is not None
    assignee = None
    if set_assignment and req.assigned_to_user_id:
        assignee = await db.users.find_one({"id": req.assigned_to_user_id})
        if not assignee:
            raise HTTPException(status_code=400, detail="Utente assegnatario inesistente")
    tag = req.tipo.strip() if req.tipo is not None else None
    affected_tags = set()
    updated = 0
    docs = await db.serials.find({"id": {"$in": req.ids}}, {"_id": 0}).to_list(len(req.ids) + 1)
    for d in docs:
        updates = {}
        event_type = None
        event_extra = {}
        if tag is not None:
            updates["tipo"] = tag
            if d.get("tipo"): affected_tags.add(d["tipo"])
            if tag: affected_tags.add(tag)
        if set_assignment and d.get("status") != "scaricato":
            if req.assigned_to_user_id:
                updates["assigned_to_user_id"] = assignee["id"]
                updates["assigned_to_name"] = assignee.get("name") or assignee.get("email") or ""
                if d.get("status") == "in_stock":
                    updates["status"] = "assegnato"
                event_type = "assigned"
                event_extra = {"to_user_id": assignee["id"], "to_user_name": updates["assigned_to_name"], "bulk": True}
            else:
                updates["assigned_to_user_id"] = ""
                updates["assigned_to_name"] = ""
                if d.get("status") == "assegnato":
                    updates["status"] = "in_stock"
                event_type = "unassigned"
                event_extra = {"from_user_name": d.get("assigned_to_name", ""), "bulk": True}
        if not updates:
            continue
        updates["updated_at"] = now
        await db.serials.update_one({"id": d["id"]}, {"$set": updates})
        if event_type:
            await add_serial_event(d["serial"], event_type, user["id"], actor_name, extra=event_extra)
        elif tag is not None:
            await add_serial_event(d["serial"], "manual_update", user["id"], actor_name,
                                    extra={"tipo": tag, "bulk": True})
        updated += 1
    for t in affected_tags:
        try: await _check_threshold(t, actor_name=actor_name)
        except Exception: pass
    return {"updated": updated}


@api_router.post("/inventory/tags/delete")
async def delete_tag(req: DeleteTagRequest, user: dict = Depends(get_magazzino_or_admin)):
    tag = (req.tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag richiesto")
    r = await db.serials.update_many({"tipo": tag}, {"$set": {"tipo": ""}})
    await db.tag_thresholds.delete_one({"tag": tag})
    return {"tag": tag, "updated": r.modified_count}


# ---------- Warehouse: materiali assegnati all'utente corrente (per dropdown in nota) ----------
@api_router.get("/inventory/my-assigned")
async def my_assigned(tipo: str = Query(""), user: dict = Depends(get_current_user)):
    """Ritorna TUTTI i seriali assegnati a me o al mio partner di squadra oggi (non scaricati).
    Il parametro `tipo` è ignorato: qualsiasi seriale assegnato può essere selezionato in qualsiasi
    campo (CPE, ONT o extra) — il magazzino può darti un CPEWIFI e tu lo usi dove serve."""
    today_iso = datetime.now(timezone.utc).date().isoformat()
    partners = await _get_team_partners(user["id"], today_iso)
    user_ids = [user["id"]] + partners
    q = {
        "assigned_to_user_id": {"$in": user_ids},
        "status": {"$ne": "scaricato"},
    }
    docs = await db.serials.find(q, {"_id": 0}).sort("assigned_to_name", 1).to_list(500)
    return docs


@api_router.post("/inventory/serials/{sid}/return")
async def return_to_warehouse(sid: str, user: dict = Depends(get_current_user)):
    """Un tecnico rimette in magazzino un modem non usato (assegnato a lui o al compagno di squadra)."""
    doc = await db.serials.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Seriale non trovato")
    if doc.get("status") == "scaricato":
        raise HTTPException(status_code=400, detail="Il seriale è già scaricato: non può essere restituito")
    today_iso = datetime.now(timezone.utc).date().isoformat()
    partners = await _get_team_partners(user["id"], today_iso)
    allowed = user.get("role") in ("admin", "magazzino") or doc.get("assigned_to_user_id") in ([user["id"]] + partners)
    if not allowed:
        raise HTTPException(status_code=403, detail="Non puoi restituire questo seriale")
    prev_assignee = doc.get("assigned_to_name", "")
    now = datetime.now(timezone.utc).isoformat()
    await db.serials.update_one({"id": sid}, {"$set": {
        "status": "in_stock",
        "assigned_to_user_id": "",
        "assigned_to_name": "",
        "updated_at": now,
    }})
    display_name = user.get("name") or user.get("email") or ""
    await add_serial_event(doc["serial"], "unassigned", user["id"], display_name,
                            extra={"reason": "returned_to_warehouse", "from_user_name": prev_assignee})
    # Notify magazzino
    await notify_magazzino(
        "returned",
        f"🔄 {display_name} ha restituito il modem {doc['serial']} al magazzino",
        from_user_name=display_name,
        serials=[doc["serial"]],
    )
    return await db.serials.find_one({"id": sid}, {"_id": 0})


# ---------- Vacations ----------
@api_router.post("/vacations")
async def create_vacation(req: VacationRequestCreate, user: dict = Depends(get_current_user)):
    from datetime import date
    try:
        date.fromisoformat(req.from_date); date.fromisoformat(req.to_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato date non valido (usa YYYY-MM-DD)")
    if req.from_date > req.to_date:
        raise HTTPException(status_code=400, detail="Data inizio dopo data fine")
    now_iso = datetime.now(timezone.utc).isoformat()
    # Detect overlaps with other users' pending/approved vacations
    overlaps = []
    async for v in db.vacations.find({
        "user_id": {"$ne": user["id"]},
        "status": {"$in": ["pending", "approved"]},
        "from_date": {"$lte": req.to_date},
        "to_date": {"$gte": req.from_date},
    }):
        overlaps.append({"user_name": v.get("user_name", ""), "from": v["from_date"], "to": v["to_date"], "status": v["status"]})
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_email": user.get("email", ""),
        "user_name": user.get("name") or user.get("email", ""),
        "from_date": req.from_date,
        "to_date": req.to_date,
        "reason": req.reason or "",
        "status": "pending",
        "admin_note": "",
        "decided_by": "",
        "decided_at": "",
        "has_overlap": len(overlaps) > 0,
        "overlap_with": overlaps,
        "created_at": now_iso,
    }
    await db.vacations.insert_one(dict(doc))
    # Notify all admins
    admins = await db.users.find({"role": "admin", "is_approved": True}, {"_id": 0, "id": 1}).to_list(50)
    from_who = user.get("name") or user.get("email") or ""
    for a in admins:
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": a["id"],
            "kind": "vacation_request",
            "message": f"🏖️ {from_who} ha richiesto ferie dal {req.from_date} al {req.to_date}",
            "from_user_name": from_who,
            "note_id": doc["id"],
            "note_wr": "",
            "serials": [],
            "read": False,
            "created_at": now_iso,
        })
        if overlaps:
            names = ", ".join(o["user_name"] for o in overlaps[:3])
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": a["id"],
                "kind": "vacation_overlap",
                "message": f"⚠️ Ferie sovrapposte: {from_who} coincide con {names}",
                "from_user_name": from_who,
                "note_id": doc["id"],
                "note_wr": "",
                "serials": [],
                "read": False,
                "created_at": now_iso,
            })
    return doc


@api_router.get("/vacations")
async def list_vacations(user: dict = Depends(get_current_user)):
    if user.get("role") in ("admin", "magazzino"):
        docs = await db.vacations.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    else:
        docs = await db.vacations.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api_router.post("/vacations/{vid}/decision")
async def decide_vacation(vid: str, req: VacationDecisionRequest, user: dict = Depends(get_current_admin)):
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Decisione non valida")
    doc = await db.vacations.find_one({"id": vid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.vacations.update_one({"id": vid}, {"$set": {
        "status": req.decision,
        "admin_note": req.admin_note or "",
        "decided_by": user.get("email", ""),
        "decided_at": now_iso,
    }})
    # Notify the technician
    label = "approvata ✅" if req.decision == "approved" else "rifiutata ❌"
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": doc["user_id"],
        "kind": "vacation_decision",
        "message": f"La tua richiesta ferie ({doc['from_date']} → {doc['to_date']}) è stata {label}" + (f": {req.admin_note}" if req.admin_note else ""),
        "from_user_name": user.get("email", ""),
        "note_id": vid,
        "note_wr": "",
        "serials": [],
        "read": False,
        "created_at": now_iso,
    })
    return await db.vacations.find_one({"id": vid}, {"_id": 0})


@api_router.delete("/vacations/{vid}")
async def cancel_vacation(vid: str, user: dict = Depends(get_current_user)):
    q = {"id": vid} if user.get("role") == "admin" else {"id": vid, "user_id": user["id"], "status": "pending"}
    r = await db.vacations.delete_one(q)
    if not r.deleted_count:
        raise HTTPException(status_code=404, detail="Richiesta non trovata o non annullabile")
    return {"deleted": 1}


# ---------- Admin dashboard: media giornaliera per tecnico + giacenza per tecnico ----------
@api_router.get("/admin/dashboard")
async def admin_dashboard(
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    user: dict = Depends(get_current_admin),
):
    from datetime import date
    today = datetime.now(timezone.utc).date()
    if not from_date: from_date = today.replace(day=1).isoformat()
    if not to_date: to_date = today.isoformat()

    all_notes = await db.notes.find({}, {"_id": 0, "user_id": 1, "note_type": 1, "status": 1, "note_date": 1, "created_at": 1}).to_list(50000)
    users = await db.users.find({"is_approved": True}, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1}).to_list(500)

    counted_days = [d for d in _daterange(from_date, to_date) if d.weekday() != 5]
    wd = max(len(counted_days), 1)

    def _classify(d):
        t = d.get('note_type') or d.get('status') or 'limbo'
        return t if t in ('espletato', 'sospeso', 'guasto', 'migrazione') else 'limbo'

    def _get_date(d):
        return (d.get('note_date') or (d.get('created_at') or '')[:10])

    per_user = {u["id"]: {
        "id": u["id"], "email": u.get("email", ""), "name": u.get("name") or u.get("email", ""),
        "role": u.get("role", "user"),
        "totals": {"limbo": 0, "espletato": 0, "sospeso": 0, "guasto": 0, "migrazione": 0},
        "avg_completed": 0.0,
        "stock": {"in_stock": 0, "assegnato": 0, "scaricato": 0},
    } for u in users}

    for n in all_notes:
        dt = _get_date(n)
        if not dt or dt < from_date or dt > to_date: continue
        uid = n.get("user_id")
        if uid not in per_user: continue
        c = _classify(n)
        per_user[uid]["totals"][c] = per_user[uid]["totals"].get(c, 0) + 1

    # Personal stock = serials assegnati o scaricati da ciascun utente
    async for s in db.serials.find({}, {"_id": 0, "assigned_to_user_id": 1, "downloaded_by_user_id": 1, "status": 1}):
        aid = s.get("assigned_to_user_id") or ""
        did = s.get("downloaded_by_user_id") or ""
        st = s.get("status", "in_stock")
        if aid and aid in per_user and st in ("in_stock", "assegnato"):
            per_user[aid]["stock"][st] = per_user[aid]["stock"].get(st, 0) + 1
        if did and did in per_user and st == "scaricato":
            per_user[did]["stock"]["scaricato"] = per_user[did]["stock"].get("scaricato", 0) + 1

    for u in per_user.values():
        completed = u["totals"]["espletato"] + u["totals"]["migrazione"]
        u["avg_completed"] = round(completed / wd, 2)

    users_list = sorted(per_user.values(), key=lambda x: (-x["totals"]["espletato"], x["name"].lower()))
    return {"from": from_date, "to": to_date, "working_days": wd, "users": users_list}


# ---------- Notifications ----------
@api_router.get("/notifications")
async def list_notifications(unread_only: bool = Query(False),
                             limit: int = Query(50),
                             user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"]}
    if unread_only:
        q["read"] = False
    docs = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    unread_count = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"items": docs, "unread": unread_count}


@api_router.post("/notifications/{nid}/read")
async def mark_notification_read(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    r = await db.notifications.update_many({"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"updated": r.modified_count}


# ---------- Email Recipients (destinatari preimpostati, per utente) ----------
DEFAULT_RECIPIENTS = [
    "g.c.impiantiufficio@gmail.com",
    "g.c.impiantisnc4@gmail.com",
    "giuseppe.abbatiscianni@circet.it",
    "dario.naviglio@circet.it",
    "vito.lalario@circet.it",
]


class RecipientsUpdate(BaseModel):
    recipients: List[str] = Field(default_factory=list)


@api_router.get("/email-recipients")
async def get_email_recipients(user: dict = Depends(get_current_user)):
    doc = await db.email_recipients.find_one({"user_id": user["id"]}, {"_id": 0})
    if not doc:
        return {"recipients": DEFAULT_RECIPIENTS}
    return {"recipients": doc.get("recipients", DEFAULT_RECIPIENTS)}


@api_router.put("/email-recipients")
async def set_email_recipients(req: RecipientsUpdate, user: dict = Depends(get_current_user)):
    cleaned: List[str] = []
    for r in req.recipients:
        e = (r or "").strip()
        if e and e not in cleaned:
            cleaned.append(e)
    await db.email_recipients.update_one(
        {"user_id": user["id"]},
        {"$set": {"user_id": user["id"], "recipients": cleaned,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"recipients": cleaned}


# ---------- Istruzioni Configurazioni (CRUD, modifica solo admin) ----------
class InstructionCreate(BaseModel):
    title: str
    description: str = ""


class InstructionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


@api_router.get("/instructions")
async def list_instructions(user: dict = Depends(get_current_user)):
    docs = await db.instructions.find({}, {"_id": 0}).sort([("order", 1), ("created_at", 1)]).to_list(1000)
    return docs


@api_router.post("/instructions")
async def create_instruction(req: InstructionCreate, admin: dict = Depends(get_current_admin)):
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Titolo richiesto")
    now = datetime.now(timezone.utc).isoformat()
    order = await db.instructions.count_documents({})
    doc = {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": (req.description or "").strip(),
        "images": [],
        "order": order,
        "created_by": admin.get("email", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.instructions.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api_router.patch("/instructions/{iid}")
async def update_instruction(iid: str, req: InstructionUpdate, admin: dict = Depends(get_current_admin)):
    updates = {k: (v or "").strip() for k, v in req.model_dump().items() if v is not None}
    if "title" in updates and not updates["title"]:
        raise HTTPException(status_code=400, detail="Titolo richiesto")
    if not updates:
        raise HTTPException(status_code=400, detail="Nessuna modifica")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.instructions.update_one({"id": iid}, {"$set": updates})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Riquadro non trovato")
    return await db.instructions.find_one({"id": iid}, {"_id": 0})


@api_router.delete("/instructions/{iid}")
async def delete_instruction(iid: str, admin: dict = Depends(get_current_admin)):
    res = await db.instructions.delete_one({"id": iid})
    return {"deleted": res.deleted_count}


class InstructionReorder(BaseModel):
    ids: List[str]


@api_router.post("/instructions/reorder")
async def reorder_instructions(req: InstructionReorder, admin: dict = Depends(get_current_admin)):
    now = datetime.now(timezone.utc).isoformat()
    for idx, iid in enumerate(req.ids):
        await db.instructions.update_one({"id": iid}, {"$set": {"order": idx, "updated_at": now}})
    return {"ok": True, "count": len(req.ids)}


@api_router.post("/instructions/{iid}/image")
async def upload_instruction_image(iid: str, file: UploadFile = File(...),
                                   admin: dict = Depends(get_current_admin)):
    doc = await db.instructions.find_one({"id": iid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Riquadro non trovato")
    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="Il file deve essere un'immagine")
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg").lower()
    path = f"{APP_NAME}/instructions/{iid}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    put_object(path, data, ct or "image/jpeg")
    img = {"id": str(uuid.uuid4()), "storage_path": path,
           "filename": file.filename or "immagine", "content_type": ct or "image/jpeg"}
    images = doc.get("images", []) + [img]
    await db.instructions.update_one(
        {"id": iid},
        {"$set": {"images": images, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"images": images}


@api_router.delete("/instructions/{iid}/image/{img_id}")
async def delete_instruction_image(iid: str, img_id: str, admin: dict = Depends(get_current_admin)):
    doc = await db.instructions.find_one({"id": iid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Riquadro non trovato")
    images = [im for im in doc.get("images", []) if im.get("id") != img_id]
    await db.instructions.update_one(
        {"id": iid},
        {"$set": {"images": images, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"images": images}


@api_router.post("/instructions/{iid}/file")
async def upload_instruction_file(iid: str, file: UploadFile = File(...),
                                  admin: dict = Depends(get_current_admin)):
    doc = await db.instructions.find_one({"id": iid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Riquadro non trovato")
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin").lower()
    path = f"{APP_NAME}/instructions/{iid}/files/{uuid.uuid4()}.{ext}"
    data = await file.read()
    put_object(path, data, file.content_type or "application/octet-stream")
    f = {"id": str(uuid.uuid4()), "storage_path": path,
         "filename": file.filename or f"file.{ext}",
         "content_type": file.content_type or "application/octet-stream",
         "size": len(data)}
    files = doc.get("files", []) + [f]
    await db.instructions.update_one(
        {"id": iid},
        {"$set": {"files": files, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"files": files}


@api_router.delete("/instructions/{iid}/file/{file_id}")
async def delete_instruction_file(iid: str, file_id: str, admin: dict = Depends(get_current_admin)):
    doc = await db.instructions.find_one({"id": iid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Riquadro non trovato")
    files = [f for f in doc.get("files", []) if f.get("id") != file_id]
    await db.instructions.update_one(
        {"id": iid},
        {"$set": {"files": files, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"files": files}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def seed_admin():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        logger.warning("ADMIN_EMAIL / ADMIN_PASSWORD non impostati; salto seed admin")
        return
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": ADMIN_EMAIL, "name": "Giuseppe Belviso",
            "password_hash": hash_password(ADMIN_PASSWORD),
            "role": "admin", "is_approved": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Admin creato: {ADMIN_EMAIL}")
    else:
        # Keep admin's password in sync with .env AND ensure role/approved flags
        update = {"role": "admin", "is_approved": True}
        if not verify_password(ADMIN_PASSWORD, existing.get("password_hash", "")):
            update["password_hash"] = hash_password(ADMIN_PASSWORD)
        await db.users.update_one({"email": ADMIN_EMAIL}, {"$set": update})
        logger.info(f"Admin verificato: {ADMIN_EMAIL}")


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info(f"Storage initialized (backend={'R2' if USE_R2 else 'Emergent'})")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    try:
        await db.users.create_index("email", unique=True)
        await db.serials.create_index("serial", unique=True)
        await db.serial_events.create_index([("serial", 1), ("created_at", 1)])
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        await db.notifications.create_index([("user_id", 1), ("read", 1)])
        await seed_admin()
    except Exception as e:
        logger.error(f"Admin seed failed: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
