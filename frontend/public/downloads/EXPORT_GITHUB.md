# 🐙 Esporta il progetto su GitHub — Guida rapida

> Per aggiornare il tuo repository GitHub con tutte le ultime modifiche e portare il progetto sulla tua infrastruttura personale.

**Tempo**: 2-3 minuti | **Costo**: 0€

---

## PASSO 1 — Salva il codice su GitHub

1. In questa chat Emergent, cerca in fondo il pulsante **"Save to GitHub"** (icona GitHub)
2. Al primo click ti chiede di **autorizzare Emergent** ad accedere al tuo account GitHub → clicca **Authorize**
3. Seleziona il tuo account GitHub e conferma
4. Nome repository suggerito: `gc-impianti-app` (puoi cambiarlo)
5. Scegli se pubblico o **privato** (consigliato **privato**) → **Save**
6. In pochi secondi ti apparirà il link diretto al repo, tipo:
   ```
   https://github.com/<tuo-user>/gc-impianti-app
   ```

✅ Da questo momento tutto il codice, i documenti (`MIGRATION.md`, `MIGRAZIONE_SMARTPHONE.md`, `PRD.md`), il PWA e le guide sono sul tuo GitHub.

---

## PASSO 2 — Aggiornamenti successivi

Ogni volta che vuoi sincronizzare le ultime modifiche fatte in chat:

1. Torna nella chat e clicca di nuovo **"Save to GitHub"**
2. Verrà creato un **nuovo commit** sul repo esistente con solo le modifiche
3. Su GitHub puoi vedere lo storico completo di ogni cambiamento

⚠️ **Importante**: Il repo GitHub è di sola sincronizzazione da Emergent. Se modifichi il codice direttamente su GitHub, quelle modifiche NON tornano indietro in Emergent.

---

## PASSO 3 — Clona il repo in locale (facoltativo)

Se vuoi lavorarci sul tuo PC:

```bash
git clone https://github.com/<tuo-user>/gc-impianti-app.git
cd gc-impianti-app

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Configura backend/.env (vedi MIGRATION.md)
uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend (in un altro terminale)
cd ../frontend
yarn install
# Configura frontend/.env (vedi MIGRATION.md)
yarn start
```

---

## PASSO 4 — Deployment gratis (da telefono)

Segui la guida **[MIGRAZIONE_SMARTPHONE.md](./MIGRAZIONE_SMARTPHONE.md)** per fare deploy dal telefono su:
- **Cloudflare Pages** (frontend, gratis)
- **Render.com** (backend FastAPI, gratis)
- **MongoDB Atlas** (database, 512 MB gratis)
- **Cloudflare R2** (foto e PDF, 10 GB gratis)

---

## PASSO 5 — Deployment su infrastruttura personale

Per un deploy più tecnico (VPS, Docker, cloud managed) consulta **[MIGRATION.md](./MIGRATION.md)** che contiene:
- Schema completo del database
- Variabili d'ambiente
- Docker Compose pronto all'uso
- Configurazione Nginx
- Guida R2 / S3

---

## Struttura del repository

```
gc-impianti-app/
├── backend/
│   ├── server.py                    ← FastAPI + MongoDB + Auth JWT + Storage
│   ├── requirements.txt             ← Dipendenze Python
│   ├── .env                         ← Config (SEGRETI — non committati per default)
│   └── tests/                       ← Test pytest
├── frontend/
│   ├── src/
│   │   ├── App.js                   ← React SPA (~2500 righe monolitiche)
│   │   ├── index.css                ← Tailwind + custom styles
│   │   └── components/ui/           ← Shadcn UI components
│   ├── public/
│   │   ├── standalone_offline.html  ← Versione offline 2.5MB
│   │   ├── downloads/
│   │   │   ├── index.html           ← Pagina di download
│   │   │   ├── pwa/                 ← PWA installabile
│   │   │   │   ├── index.html
│   │   │   │   ├── manifest.json
│   │   │   │   ├── sw.js
│   │   │   │   └── icon-*.png
│   │   │   └── gc-impianti-*.zip
│   ├── package.json
│   └── .env                         ← REACT_APP_BACKEND_URL
├── memory/
│   ├── PRD.md                       ← Product Requirements Doc
│   └── test_credentials.md          ← Credenziali test
├── MIGRATION.md                     ← Guida tecnica completa migrazione
├── MIGRAZIONE_SMARTPHONE.md         ← Guida da smartphone (Cloudflare)
├── EXPORT_GITHUB.md                 ← Questo file
└── README.md
```

---

## Cose importanti da sapere

### 📦 Archivio & pulizia DB (nuovo — Iter 18)
Se il DB si sta riempiendo, l'admin può liberare spazio direttamente dal Pannello Amministratore:
1. **Backup completo** → scarica tutto il DB in un file JSON (`archivio_completo_YYYY-MM-DD.json`)
2. **Esporta archivio (pre data)** → scarica solo i dati più vecchi di una data (`archivio_pre_YYYY-MM-DD.json`)
3. **Elimina & libera spazio** → cancella note, eventi seriali, notifiche e ferie più vecchi di quella data. Utenti e seriali attivi restano intatti.

⚠️ **Sempre in questo ordine**: prima scarica il backup, poi elimina. Il JSON scaricato è ripristinabile via `mongoimport` (vedi MIGRATION.md).

### 👥 Caposquadra (nuovo — Iter 18)
- Nel pannello admin ogni tecnico ha un pulsante ⭐ **Caposquadra** per attivare/rimuovere il ruolo.
- Solo i caposquadra possono scegliere il compagno di giornata dal menù in alto.
- Quando il caposquadra sceglie un collega, quest'ultimo vede automaticamente i seriali assegnati al caposquadra nel proprio dropdown, e le note della giornata vengono condivise bidirezionalmente.

### 🔐 Super-admin (Iter 17)
- `giuseppe97belviso@gmail.com` è il **super-admin** definito nella variabile d'ambiente `ADMIN_EMAIL`.
- Solo il super-admin può declassare altri admin. Se cambi `ADMIN_EMAIL` nel `.env` deployato, sarà quell'email il nuovo super-admin.

### 🔐 Segreti nel repo
Il file `backend/.env` NON viene committato per default (contiene chiavi sensibili). Prima di deployare:
1. Genera una nuova `JWT_SECRET` (vedi `MIGRAZIONE_SMARTPHONE.md`)
2. Configura il tuo `MONGO_URL` di MongoDB Atlas
3. Aggiorna `ADMIN_EMAIL` e `ADMIN_PASSWORD`

### 🎨 Personalizzazioni
Se vuoi cambiare logo, colori, testo:
- Colore principale (rosa): cerca `brand-pink` in `frontend/src/index.css` e `App.js`
- Logo: sostituisci le icone in `frontend/public/downloads/pwa/icon-*.png`
- Nome app: `frontend/public/downloads/pwa/manifest.json` (`name`, `short_name`)

### 📊 Dati esistenti
Se vuoi portarti anche i dati del database attuale:
1. Su Emergent → **Republish → Database → Copia URL MongoDB**
2. Su MongoDB Viewer (`mongoview.emergent.host`) → **Dump DB**
3. Su Atlas → **Browse Collections → Insert → Import JSON** per ogni collezione

---

## Supporto

- 📘 `MIGRATION.md` — Guida tecnica dettagliata
- 📱 `MIGRAZIONE_SMARTPHONE.md` — Deploy da telefono
- 📋 `memory/PRD.md` — Documentazione completa del progetto

Buon lavoro! 🚀
