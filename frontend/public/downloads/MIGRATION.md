# 📦 Guida Completa alla Migrazione — GC Impianti / OpenFiber Notes

> Documento self-contained con tutto il necessario per portare l'app fuori da Emergent verso la tua infrastruttura (VPS, Cloud Provider, Docker, etc.).

**Data documento**: Febbraio 2026
**Versione app**: Iterazione 10 (con Magazzino, Notifiche, Storico seriali, CSV export)

---

## 1) Come scaricare il codice sorgente completo

### Opzione A — Save to GitHub (raccomandato)
1. Nella chat di Emergent premi il pulsante **"Save to GitHub"**
2. Autorizza l'accesso al tuo account GitHub
3. Verrà creato/aggiornato un repository con **tutto**: `backend/`, `frontend/`, `.env` (senza segreti), `requirements.txt`, `package.json`, questo file `MIGRATION.md`, PRD, documenti in `/memory`.
4. Clona il repo in locale: `git clone git@github.com:<tuo-utente>/<tuo-repo>.git`

### Opzione B — Zip da chat
- Chiedi in chat: "scaricami il codice come zip" → riceverai un archivio.

---

## 2) Come esportare il database MongoDB

**Percorso UI**: `Republish → Database → Copia MongoDB URL → MongoDB Viewer → Dump DB`

**Passi dettagliati**:
1. Clicca **"Republish"** in alto nella barra dell'app
2. Vai alla scheda **"Database"**
3. Copia la **stringa MongoDB URL** mostrata
4. Apri **`https://mongoview.emergent.host`** (o clicca "Go to database")
5. Incolla la connection string → **"Connect to MongoDB"**
6. Clicca **"Dump DB"** in alto a destra → scaricherai un archivio con tutte le collezioni in JSON

**Import sul tuo MongoDB personale** (locale, Atlas o VPS):
```bash
# Se hai i file JSON di export
mongoimport --uri "mongodb://<user>:<pass>@<host>:27017/test_database" \
            --collection users \
            --file users.json
mongoimport --uri "..." --collection notes --file notes.json
mongoimport --uri "..." --collection serials --file serials.json
mongoimport --uri "..." --collection serial_events --file serial_events.json
mongoimport --uri "..." --collection notifications --file notifications.json

# Oppure se hai un dump BSON (mongodump)
mongorestore --uri "mongodb://<user>:<pass>@<host>:27017" ./dump
```

---

## 3) Variabili d'ambiente da configurare

### `backend/.env`
```env
# --- MongoDB (obbligatorio) ---
MONGO_URL=mongodb://user:pass@host:27017        # OPPURE Atlas: mongodb+srv://...
DB_NAME=test_database                            # nome del DB (mantieni lo stesso per compatibilità dati)

# --- CORS (obbligatorio) ---
CORS_ORIGINS=https://tuo-dominio.it,https://www.tuo-dominio.it

# --- JWT Auth (obbligatorio, genera una stringa random di almeno 32 caratteri) ---
JWT_SECRET=<random-string-32-chars-minimum>

# --- Seed Admin (creato al primo boot se non esiste) ---
ADMIN_EMAIL=Giuseppe97belviso@gmail.com
ADMIN_PASSWORD=Mucchetta4!

# --- Emergent LLM Key (OPZIONALE) ---
# Serve solo se usi funzioni AI (attualmente NON usato dall'app in produzione)
# Puoi rimuovere se non lo usi
EMERGENT_LLM_KEY=<chiave>
```

**Come generare `JWT_SECRET`**:
```bash
openssl rand -hex 32
# oppure
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### `frontend/.env`
```env
# URL pubblico del backend (senza slash finale)
REACT_APP_BACKEND_URL=https://api.tuo-dominio.it
WDS_SOCKET_PORT=443
```

**Importante**: `REACT_APP_BACKEND_URL` deve puntare al backend. Le rotte del backend sono tutte prefissate con `/api`.

---

## 4) Dipendenze

### Backend Python (`backend/requirements.txt`)
Le principali:
- `fastapi` — framework REST
- `uvicorn[standard]` — ASGI server
- `motor` — MongoDB async driver
- `pymongo` — driver base
- `pydantic` — validation
- `python-jose[cryptography]` — JWT
- `passlib[bcrypt]` — password hashing
- `python-multipart` — file upload
- `python-dotenv` — .env loader
- `pdfplumber` — parsing PDF OpenFiber
- `pillow` — immagini
- `requests`, `httpx` — HTTP client

Installa tutto:
```bash
cd backend
pip install -r requirements.txt
```

### Frontend Node (`frontend/package.json`)
Le principali:
- `react` 19
- `axios` — HTTP client
- `tailwindcss` + `tailwindcss-animate` — styling
- `lucide-react` — icone
- `sonner` — toast notifications
- `html5-qrcode` — scanner barcode/QR
- `jsbarcode` — generazione barcode CODE128
- `qrcode` — generazione QR code
- shadcn/ui components (radix-ui base)

Installa tutto:
```bash
cd frontend
yarn install                # oppure npm install
yarn build                  # produce /frontend/build servibile con nginx
```

---

## 5) Schema del Database

Nome DB: `test_database` (personalizzabile via `DB_NAME`)

### Collezione `users`
```json
{
  "id": "uuid",
  "email": "string (unique, lowercase)",
  "name": "string",
  "password_hash": "string (bcrypt)",
  "role": "admin | user | magazzino",
  "is_approved": false,
  "created_at": "iso datetime"
}
```
**Indici**: `email` (unique)

### Collezione `notes`
```json
{
  "id": "uuid",
  "user_id": "uuid (owner)",
  "wr": "string",
  "cliente": "string",
  "olo": "string",
  "splitter": "string",
  "via": "string",
  "n_porta_perm": "string",
  "porta_pte": "string",
  "cpe": "string (seriale modem)",
  "ont_sfp": "string (seriale ONT)",
  "indirizzo": "string",
  "pte_est": "string",
  "ts": "string", "tc": "string",
  "d": "string", "a": "string",
  "mono": "string",
  "internal": "string",
  "note_text": "string (nota generata)",
  "note_text_manual": "string (override manuale)",
  "photos": ["storage_path", ...],
  "pdf_filename": "string",
  "pdf_storage_path": "string",
  "status": "espletato | sospeso",
  "suspend_reason": "string",
  "synced": false,
  "synced_at": "iso datetime | null",
  "created_at": "iso datetime",
  "updated_at": "iso datetime"
}
```

### Collezione `serials` (magazzino)
```json
{
  "id": "uuid",
  "serial": "string (unique)",
  "tipo": "CPE | ONT | ALTRO",
  "status": "in_stock | assegnato | scaricato",
  "assigned_to_user_id": "uuid | \"\"",
  "assigned_to_name": "string",
  "downloaded_by_user_id": "uuid | \"\"",
  "downloaded_by_name": "string",
  "downloaded_at": "iso datetime | \"\"",
  "note": "string",
  "created_at": "iso datetime",
  "updated_at": "iso datetime"
}
```
**Indici**: `serial` (unique)

### Collezione `serial_events` (storico timeline)
```json
{
  "id": "uuid",
  "serial": "string",
  "event_type": "created | assigned | unassigned | downloaded | manual_update | deleted",
  "actor_id": "uuid",
  "actor_name": "string",
  "note_id": "uuid | \"\"",
  "note_wr": "string",
  "extra": { "...": "campi liberi" },
  "created_at": "iso datetime"
}
```
**Indici**: `(serial, created_at)`

### Collezione `notifications`
```json
{
  "id": "uuid",
  "user_id": "uuid (destinatario)",
  "kind": "note_sync",
  "message": "string",
  "from_user_name": "string",
  "note_id": "uuid",
  "note_wr": "string",
  "serials": ["string", ...],
  "read": false,
  "created_at": "iso datetime"
}
```
**Indici**: `(user_id, created_at desc)`, `(user_id, read)`

---

## 6) Sistema di Autenticazione

**Tipo**: JWT stateless custom (nessuna dipendenza da provider esterni).

**Flusso**:
1. **Registrazione** (`POST /api/auth/register`): crea utente con `is_approved=false`. L'admin deve approvarlo prima che possa loggarsi.
2. **Approvazione admin** (`POST /api/auth/admin/approve/{user_id}`): setta `is_approved=true`.
3. **Login** (`POST /api/auth/login`): verifica bcrypt hash, rifiuta se `is_approved=false`. Restituisce JWT.
4. **JWT payload**: `{sub: user_id, email, role, exp}` — firmato con `HS256` usando `JWT_SECRET`.
5. **Auth guard**: middleware `Authorization: Bearer <jwt>` legge lo user da MongoDB.
6. **Ruoli**:
   - `admin` — tutto
   - `magazzino` — solo pagina magazzino + notifiche
   - `user` (tecnico) — solo proprie note

**Seed admin al boot**: se `ADMIN_EMAIL` non esiste in DB, viene creato automaticamente con `ADMIN_PASSWORD` (hash bcrypt) e ruolo `admin` approvato.

**Endpoint chiave**:
| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/api/auth/register` | Registra utente (non approvato) |
| POST | `/api/auth/login` | Login → JWT |
| GET  | `/api/auth/me` | Profilo utente corrente |
| GET  | `/api/auth/admin/users` | Lista utenti (admin) |
| POST | `/api/auth/admin/approve/{uid}` | Approva utente |
| POST | `/api/auth/admin/set-role/{uid}` | Cambia ruolo |
| DELETE | `/api/auth/admin/users/{uid}` | Elimina utente |

---

## 7) API Endpoints (tutti prefissati `/api`)

### Note
- `POST /api/pdf/parse` — upload PDF OpenFiber, restituisce campi estratti
- `GET  /api/notes?search=&from=&to=` — lista note utente
- `POST /api/notes` — crea nota
- `PATCH /api/notes/{id}` — aggiorna nota (incluso `status`, `suspend_reason`)
- `DELETE /api/notes/{id}` — elimina
- `POST /api/notes/bulk-delete` — elimina multipla
- `POST /api/notes/{id}/photos` — upload foto (multipart)
- `POST /api/notes/{id}/sync` — sincronizza CPE/ONT nel magazzino (crea eventi + notifiche)
- `GET  /api/notes/stats` — statistiche

### Magazzino
- `GET  /api/inventory/serials?status=&tipo=&search=`
- `POST /api/inventory/serials`
- `POST /api/inventory/serials/bulk`
- `PATCH /api/inventory/serials/{sid}` — riassegna/aggiorna
- `DELETE /api/inventory/serials/{sid}`
- `GET  /api/inventory/serials/{sid}/history` — timeline eventi
- `GET  /api/inventory/export.csv` — export CSV (BOM UTF-8)
- `GET  /api/inventory/users` — lista utenti (per assegnazione)

### Notifiche
- `GET  /api/notifications?unread_only=&limit=`
- `POST /api/notifications/{nid}/read`
- `POST /api/notifications/read-all`

---

## 8) File Storage

L'app supporta **due backend** di storage in modo trasparente:

### A) Emergent Object Storage (default in Emergent)
Nessuna configurazione richiesta se `EMERGENT_LLM_KEY` è impostato. Funziona solo dentro Emergent.

### B) Cloudflare R2 / S3-compatible (raccomandato per migrazione)
Basta impostare 4 env variables e il backend passa automaticamente a R2. Nessuna modifica al codice.

```env
R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
R2_BUCKET=gc-impianti-files
R2_ACCESS_KEY=<access_key>
R2_SECRET_KEY=<secret_key>
R2_REGION=auto
```

**Come ottenere le credenziali R2**:
1. Cloudflare Dashboard → **R2 Object Storage** → **Create bucket** (nome es. `gc-impianti-files`)
2. **R2 → Manage R2 API Tokens** → **Create API Token** → permessi **Object Read & Write** su quel bucket
3. Copia `Access Key ID` + `Secret Access Key` (mostrati una sola volta!)
4. L'`Endpoint` è mostrato nella pagina del bucket: `https://<account_id>.r2.cloudflarestorage.com`

Il backend rileva automaticamente la presenza di queste variabili e usa R2. Se assenti, ricade su Emergent.

**Piano gratuito Cloudflare R2**: 10 GB storage + 10M richieste classe A + 1M classe B al mese.

---

## 9) Come deployare sulla tua infrastruttura

### Opzione A — VPS con Docker Compose (più semplice)
Crea `docker-compose.yml`:
```yaml
version: "3.8"
services:
  mongo:
    image: mongo:7
    restart: always
    volumes: [mongo_data:/data/db]
    environment:
      MONGO_INITDB_ROOT_USERNAME: root
      MONGO_INITDB_ROOT_PASSWORD: change_me

  backend:
    build: ./backend
    restart: always
    env_file: ./backend/.env
    ports: ["8001:8001"]
    depends_on: [mongo]
    command: uvicorn server:app --host 0.0.0.0 --port 8001

  frontend:
    build: ./frontend       # multi-stage: yarn build → nginx
    restart: always
    ports: ["80:80", "443:443"]
    depends_on: [backend]

volumes:
  mongo_data:
```

**Dockerfile backend** (`backend/Dockerfile`):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
```

**Dockerfile frontend** (`frontend/Dockerfile`):
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile
COPY . .
RUN yarn build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

**Nginx config** (`frontend/nginx.conf`):
```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;

  # SPA routing
  location / { try_files $uri /index.html; }

  # Proxy /api verso backend
  location /api/ {
    proxy_pass http://backend:8001/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    client_max_body_size 50M;   # per upload PDF/foto
  }
}
```

Avvia:
```bash
docker-compose up -d
```

### Opzione B — Cloud managed
- **Backend**: Railway / Render / Fly.io (deploy da GitHub, aggiungi env vars)
- **Frontend**: Vercel / Netlify / Cloudflare Pages (build automatica da GitHub)
- **DB**: MongoDB Atlas (free tier M0)
- **File storage**: Cloudflare R2 (10GB gratis) o AWS S3

### Opzione C — Aggiornare Emergent per usare i tuoi servizi
- Vai su **Republish → Secrets → System keys**
- Modifica `MONGO_URL` con il tuo cluster Atlas
- Aggiungi gli IP di egress di Emergent (`app.emergent.sh/ip-addresses`) alla allowlist Atlas
- **"Save and republish"**

---

## 10) Credenziali attuali

**Admin seed (creato al primo boot)**:
- Email: `Giuseppe97belviso@gmail.com`
- Password: `Mucchetta4!`

⚠️ **Cambia la password subito dopo la migrazione**! Il seed è automatico solo se l'utente non esiste già.

---

## 11) File offline standalone Android

Il file `frontend/public/standalone_offline.html` è **completamente autonomo** (2.5MB, tutte le librerie inlinate).
- Basta scaricarlo sul telefono e aprirlo con Chrome/Firefox
- Funziona **senza server**: parse PDF, generazione nota, scanner barcode/QR, foto, invio Gmail via Web Share API
- URL di download attuale: `https://<tuo-dominio>/scarica.html`
- Dopo la migrazione, mantieni questi due file su qualsiasi hosting statico (Netlify, GitHub Pages, S3)

---

## 12) Checklist finale migrazione

- [ ] Codice esportato via GitHub (Save to GitHub)
- [ ] Dump database MongoDB scaricato (`Republish → Database → Dump DB`)
- [ ] Copiati valori attuali di `MONGO_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` (dai Secrets Emergent)
- [ ] File uploads (PDF + foto) esportati dall'Object Storage Emergent
- [ ] Setup nuovo MongoDB (Atlas o self-hosted) + importato dump
- [ ] Setup nuovo Object Storage (S3/R2) e modificato codice backend
- [ ] Backend deployato, healthcheck `/api/notes/stats` risponde 401 (auth ok)
- [ ] Frontend deployato con `REACT_APP_BACKEND_URL` corretto
- [ ] CORS_ORIGINS aggiornato con il nuovo dominio frontend
- [ ] Testato login admin, creazione nota, scanner, magazzino, notifiche
- [ ] Password admin cambiata
- [ ] `standalone_offline.html` disponibile su hosting statico
- [ ] Backup automatico del DB configurato (cron `mongodump` giornaliero)

---

## 13) Supporto

- Documentazione codice: `/app/memory/PRD.md`
- Report test: `/app/test_reports/iteration_10.json` (100% pass)
- Ogni endpoint API è documentato inline in `backend/server.py`
- Swagger auto-generato disponibile a `<backend-url>/docs`

Buona migrazione! 🚀
