# 📱 Guida Migrazione da Smartphone (100% gratis)

> Sposta la tua app GC Impianti fuori da Emergent usando **solo lo smartphone** e servizi con piano **gratuito**.

**Tempo stimato**: 45-60 minuti
**Costo**: **0 €** (piani free)
**Cosa ti serve**: telefono con Chrome/Safari, un email valida

---

## 🎯 Architettura finale

| Componente | Servizio | Piano Free |
|---|---|---|
| Codice sorgente | **GitHub** | ✅ Illimitato repo privati |
| Database MongoDB | **MongoDB Atlas** | ✅ 512 MB cluster M0 |
| Backend API (FastAPI) | **Render.com** | ✅ 750h/mese |
| Frontend React | **Cloudflare Pages** | ✅ 500 build/mese, banda illimitata |
| File storage (PDF/foto) | **Cloudflare R2** | ✅ 10 GB + 10M richieste/mese |
| Dominio | Sottodominio gratis dei servizi | ✅ `*.pages.dev`, `*.onrender.com` |

---

## 📥 FASE 1 — Salva il codice su GitHub (2 min)

1. Se non hai un account, crea uno gratis su **`github.com/signup`** dal telefono
2. Torna nella chat di Emergent
3. Tocca il pulsante **"Save to GitHub"** (in fondo alla chat)
4. Autorizza l'accesso → seleziona il tuo account
5. Nome repo suggerito: `gc-impianti-app` → **Create**
6. Aspetta il messaggio di conferma con il link al repo

✅ Da qui in poi tutto il codice è al sicuro su GitHub.

---

## 🗄️ FASE 2 — Database MongoDB Atlas (10 min)

1. Apri **`cloud.mongodb.com`** su Chrome
2. **Sign up** con email o Google (usa lo stesso account Google del telefono per velocità)
3. Alla domanda "What is your goal?" → seleziona **"Learn MongoDB"** o **"Build a new application"**
4. **Deploy your database** → scegli **M0 FREE** (512 MB, gratis per sempre)
5. Provider: **AWS** — Region: **Frankfurt (eu-central-1)** (più vicino all'Italia)
6. Cluster name: `gc-impianti` → **Create Deployment**
7. Ti chiederà di creare un **utente database**:
   - Username: `gcadmin`
   - Password: tocca **"Autogenerate Secure Password"** → **COPIA E SALVA** la password in Note dello smartphone
   - **Create User**
8. **Network Access** → **"Add IP Address"** → **"Allow Access from Anywhere"** (`0.0.0.0/0`) → **Confirm**
   > ⚠️ In un secondo momento potrai restringere solo agli IP di Render
9. **Finish and Close**
10. Torna alla dashboard → clicca sul cluster **gc-impianti** → **"Connect"** → **"Drivers"**
11. Seleziona **Python** → **3.6 or later**
12. **COPIA** la connection string, sarà simile a:
    ```
    mongodb+srv://gcadmin:<password>@gc-impianti.xxxxx.mongodb.net/?retryWrites=true&w=majority
    ```
13. Sostituisci `<password>` con la password vera copiata al punto 7
14. **Salva questa stringa nelle Note** — la userai nella FASE 4

✅ Database pronto.

### (Opzionale) Importare i dati esistenti da Emergent
Dal telefono è complicato fare `mongodump`, ma puoi:
- Su Emergent: **Republish → Database → MongoDB Viewer**
- Per ogni collezione (`users`, `notes`, `serials`, ecc.): apri → **"Run query"** → **"Export all"** → scarica JSON
- Poi su MongoDB Atlas: **Browse Collections → Insert Document → Import JSON**
- **Consiglio pratico**: se non hai dati critici, lascia perdere e ricrea l'admin al primo login (il seed automatico rifà tutto)

---

## 🚀 FASE 3 — Deploy Backend su Render.com (15 min)

1. Apri **`render.com`** dal telefono → **"Get Started"**
2. **Sign up with GitHub** (usa lo stesso account GitHub della FASE 1)
3. Autorizza Render
4. Nella dashboard tocca **"New +"** → **"Web Service"**
5. **"Connect a repository"** → cerca `gc-impianti-app` → **"Connect"**
6. Compila il form:
   | Campo | Valore |
   |---|---|
   | **Name** | `gc-impianti-backend` |
   | **Region** | Frankfurt |
   | **Branch** | `main` |
   | **Root Directory** | `backend` |
   | **Runtime** | `Python 3` |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `uvicorn server:app --host 0.0.0.0 --port $PORT` |
   | **Instance Type** | **Free** |

7. Scorri giù → **"Advanced"** → **"Add Environment Variable"** → aggiungi UNA per UNA:

   | Key | Value |
   |---|---|
   | `MONGO_URL` | *(la connection string di Atlas dalla FASE 2)* |
   | `DB_NAME` | `test_database` |
   | `JWT_SECRET` | *(genera con il metodo qui sotto)* |
   | `ADMIN_EMAIL` | `Giuseppe97belviso@gmail.com` |
   | `ADMIN_PASSWORD` | `Mucchetta4!` *(cambiala dopo!)* |
   | `CORS_ORIGINS` | `*` *(la aggiorneremo dopo con il vero dominio)* |

   **Come generare JWT_SECRET dallo smartphone**:
   - Apri Chrome → digita nella barra URL: `javascript:prompt("copia",Array.from(crypto.getRandomValues(new Uint8Array(32))).map(b=>b.toString(16).padStart(2,"0")).join(""))`
   - ⚠️ Chrome blocca `javascript:` incollato — alternativa: apri `random.org/passwords/?num=1&len=64&format=plain` → copia la stringa generata
   - Oppure semplicemente inventa una stringa lunga random di almeno 40 caratteri: `MioSuperSegretoGCImpianti2026XyZ!@$%RandomString`

8. **"Create Web Service"** → aspetta 3-5 minuti che finisca il build
9. Quando vedi **"Your service is live"** copia l'URL che appare in alto (es. `https://gc-impianti-backend.onrender.com`)
10. **Test rapido**: incolla nel browser `https://gc-impianti-backend.onrender.com/docs` → deve aprire la Swagger UI di FastAPI

⚠️ **Nota Render Free**: dopo 15 minuti di inattività il servizio va in "sleep" e il primo request successivo impiega ~30 secondi a rispondere. Per la maggior parte degli usi è accettabile.

✅ Backend pronto.

---

## 🌐 FASE 4 — Deploy Frontend su Cloudflare Pages (10 min)

1. Apri **`dash.cloudflare.com/sign-up`** dal telefono
2. Sign up (email + password) → verifica email
3. Nella dashboard, in basso a sinistra tocca **"Workers & Pages"** → **"Create"** → **"Pages"** → **"Connect to Git"**
4. **"Connect GitHub"** → autorizza → seleziona il repo `gc-impianti-app` → **"Begin setup"**
5. Compila:
   | Campo | Valore |
   |---|---|
   | **Project name** | `gc-impianti` |
   | **Production branch** | `main` |
   | **Framework preset** | `Create React App` |
   | **Build command** | `yarn install && yarn build` |
   | **Build output directory** | `build` |
   | **Root directory** | `frontend` *(cliccando "Advanced")* |

6. **Environment variables** → **"Add variable"**:
   | Key | Value |
   |---|---|
   | `REACT_APP_BACKEND_URL` | `https://gc-impianti-backend.onrender.com` *(URL dalla FASE 3)* |
   | `NODE_VERSION` | `20` |
   | `CI` | `false` |

7. **"Save and Deploy"** → aspetta 4-8 minuti
8. Quando vedi **"Success!"** copia l'URL pubblico (es. `https://gc-impianti.pages.dev`)
9. Apri l'URL nel telefono → deve mostrarti la pagina di login GC Impianti 🎉

✅ Frontend online.

---

## 🔧 FASE 5 — Correggere CORS (3 min)

Il backend deve accettare richieste dal dominio Cloudflare.

1. Torna su **Render.com** → seleziona `gc-impianti-backend` → **Environment**
2. Modifica la variabile `CORS_ORIGINS`:
   - Valore: `https://gc-impianti.pages.dev`
3. **"Save Changes"** → Render riavvia automaticamente il backend (~1 min)
4. Ricarica la tua app su `gc-impianti.pages.dev` → prova a fare login con `Giuseppe97belviso@gmail.com` / `Mucchetta4!`

Se il login funziona → 🎉 **HAI MIGRATO L'APP!**

---

## 🎨 FASE 6 (opzionale) — Dominio personalizzato

### Su Cloudflare (frontend)
1. Se hai un dominio (es. `gcimpianti.it`), aggiungilo a Cloudflare: **Websites → Add site**
2. Nel progetto Pages → **Custom domains → Set up custom domain** → `app.gcimpianti.it`
3. Cloudflare configura il DNS automaticamente

### Aggiorna CORS
- Aggiungi il nuovo dominio in `CORS_ORIGINS` (separati da virgola):
  ```
  https://gc-impianti.pages.dev,https://app.gcimpianti.it
  ```

### File offline standalone Android
- Il file `standalone_offline.html` è già servito da Cloudflare Pages su:
  `https://gc-impianti.pages.dev/standalone_offline.html`
- Scaricalo sul telefono e apri come app offline

---

## 📂 FASE 7 (opzionale) — File storage con Cloudflare R2

Se vuoi salvare PDF e foto su R2 gratis (10 GB) invece di Emergent Object Storage:

1. Cloudflare Dashboard → **R2 Object Storage** → **Create bucket** → nome `gc-impianti-files`
2. **Manage R2 API Tokens** → **Create API Token** → permessi **Read & Write** → salva `Access Key ID` e `Secret Access Key`
3. Su Render aggiungi env vars:
   ```
   R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
   R2_BUCKET=gc-impianti-files
   R2_ACCESS_KEY=<access_key>
   R2_SECRET_KEY=<secret_key>
   ```
4. Il codice backend va aggiornato per usare `boto3` con endpoint R2 (chiedi a un agente E1 di farti la modifica: "sostituisci Emergent Object Storage con Cloudflare R2 usando boto3")

⚠️ Se non fai questa fase, l'app funziona lo stesso, ma **NON potrai caricare foto e PDF nuovi** (Emergent Object Storage non è accessibile fuori da Emergent). Le note testuali però funzionano.

---

## 🔐 CHECKLIST DI SICUREZZA POST-MIGRAZIONE

- [ ] **Cambia la password admin** dopo il primo login (dal profilo dell'app)
- [ ] Su MongoDB Atlas → **Network Access** → rimuovi `0.0.0.0/0` e aggiungi solo gli IP di Render (li trovi in `render.com/docs/static-outbound-ip-addresses`)
- [ ] Su Render → env var `CORS_ORIGINS` → restringi solo al tuo dominio Cloudflare (NON usare `*` in produzione)
- [ ] Su GitHub → Repository → Settings → rendi **privato** se il codice contiene info sensibili
- [ ] Genera un `JWT_SECRET` davvero random (almeno 64 caratteri) — non riutilizzare vecchi

---

## 🆘 TROUBLESHOOTING

**"CORS error" nel browser dopo login**
→ Ricontrolla che `CORS_ORIGINS` su Render contenga esattamente il dominio Pages (con `https://`, senza slash finale)

**Login dice "Errore di rete"**
→ Il backend Render è in sleep. Aspetta 30-60 secondi al primo tentativo

**"MongoNetworkError"**
→ Su Atlas verifica che Network Access permetta `0.0.0.0/0` (o gli IP di Render)

**Build Cloudflare Pages fallisce con "yarn not found"**
→ Vai su Pages → Settings → Build & deployments → cambia il build command in: `npm install && npm run build`

**Le foto/PDF non si caricano**
→ È previsto senza FASE 7 (R2). Le note testuali funzionano comunque.

**Non ricordo la password admin**
→ Su MongoDB Atlas: **Browse Collections → users** → cancella il documento admin → riavvia il backend su Render → verrà ricreato con `ADMIN_EMAIL`/`ADMIN_PASSWORD` dalle env vars

---

## 💰 Costi (piani free — limiti)

| Servizio | Limite free | Cosa succede se supero |
|---|---|---|
| GitHub | Illimitato | – |
| MongoDB Atlas M0 | 512 MB storage | Devi upgradare a M2 (~9$/mese) |
| Render Free | 750h/mese + sleep dopo 15min | Devi upgradare a Starter (7$/mese) |
| Cloudflare Pages | 500 build/mese, banda illimitata | Devi upgradare a Pro (20$/mese) |
| Cloudflare R2 | 10 GB storage + 10M ops | 0.015$/GB extra |

Per un uso normale (1-3 tecnici, ~100 note/mese) rimani **abbondantemente sotto i limiti gratis** per anni.

---

## 🎯 RIEPILOGO VELOCE

```
GitHub          → codice
MongoDB Atlas   → database (M0 free)
Render.com      → backend FastAPI
Cloudflare Pages→ frontend React
[Cloudflare R2] → file uploads (opzionale)
```

**Tempo totale**: 45-60 min dal telefono
**URL app finale**: `https://gc-impianti.pages.dev`
**Costo**: **0€/mese**

Buona migrazione! 📱🚀
