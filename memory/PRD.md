# PRD — OpenFiber Notes & Warehouse (GC Impianti)

## Problem Statement (original, Italian)
Web app che automatizza la generazione delle note tecniche OpenFiber a partire dai PDF di pratica, con supporto foto, invio Gmail, autenticazione admin/tecnico/magazzino, scanner barcode/QR per seriali CPE/ONT, statistiche giornaliere/mensili, gestione magazzino modem, notifiche real-time e storico eventi per audit.

## Users
- **Admin** (Giuseppe Belviso): full access, approva utenti, vede tutte le sezioni.
- **Tecnico (user)**: crea/edita note, scansiona seriali, invia Gmail, sincronizza al magazzino.
- **Magazzino**: gestisce inventario seriali, riceve notifiche di scarico, esporta CSV.

## Tech Stack
- **Frontend**: React 19 (single-file `App.js` ~1700 lines), Tailwind, sonner (toast), lucide-react, html5-qrcode, jsbarcode, qrcode.
- **Backend**: FastAPI, Motor (async MongoDB), bcrypt+PyJWT, pdfplumber.
- **Storage**: Emergent Object Storage (PDF + foto).
- **Offline**: `standalone_offline.html` 2.5MB con librerie inlinate (usato su Android).

## Implemented (as of 12 Feb 2026)

### Iteration 20 (14 Jun 2026) — Ristrutturazione note + auto-sync + Istruzioni immagini/riordino
- **Rimosso tasto "Scansiona seriale"** dalle azioni della nota (non più necessario).
- **Auto-sync su Espletato**: cliccando "Espletato", se la nota ha CPE/ONT, chiama automaticamente `POST /notes/{id}/sync` col magazzino; il tasto "Sincronizza magazzino" resta come fallback di sicurezza.
- **Note: gerarchia Mese > Giorno > Note** (3 livelli comprimibili). Rimossa la sezione "Espletati" separata e il toggle globale "Aggrega note". Le note espletate restano nel loro giorno ma vanno **in fondo alla lista del giorno**. Ogni giorno ha una freccia (`day-toggle-<data>`) per comprimere/espandere le sue note; ogni mese è una cartella (`month-folder-<YYYY-MM>`), mese corrente aperto di default.
- **Istruzioni Configurazioni**: gli admin possono **allegare immagini** ai riquadri (upload/elimina, `POST/DELETE /api/instructions/{id}/image`) e **riordinare i riquadri con drag-and-drop** (`POST /api/instructions/reorder`, campo `order` persistente). Tecnici in sola lettura.

### Iteration 19 (14 Jun 2026) — 7 modifiche GCgestionale (import da GitHub Dispel97/GCgestionale)
- **#5 Rinomina nav**: etichetta barra in alto "Note" → "Tecnico" (solo label, `data-testid='nav-notes'`).
- **#3 BUGFIX redirect modifica nota**: `fetchNotes` in `AppContent` ora usa un `initialLoad` ref e NON attiva lo spinner full-page sui refetch in background → salvando una nota (PATCH) la lista non viene smontata, scroll e stato card preservati. Verificato dall'agente di test (100%).
- **#1 Toggle "Aggrega note"**: `toggle-aggregate` comprime tutte le note mostrando solo le righe data; pulsante `expand-notes-bottom` in basso ripristina la vista espansa. Solo stato frontend.
- **#2 Sezione "Espletati"**: le note `note_type='espletato'` escono dalla lista principale ed entrano in `EspletatiSection` (`toggle-espletati`, badge count). Visibilità garantita dai dati già filtrati (creatore/admin/condivisione team esistente).
- **#7 Visibilità admin**: `list_notes` e `_get_own_note` → se `role=='admin'` query senza filtro utente (vede/apre tutte le note).
- **#4 Destinatari email editabili**: nuova collection `email_recipients` (per utente), endpoint `GET/PUT /api/email-recipients`, componente `RecipientsEditor` (aggiungi/modifica/rimuovi, persistente). `sendGmail` usa i destinatari salvati via `RecipientsContext`.
- **#6 Pagina "Istruzioni Configurazioni"**: nuova collection `instructions`, CRUD `GET/POST/PATCH/DELETE /api/instructions` (create/patch/delete solo admin via `get_current_admin`). Pagina `InstructionsPage` con card titolo+descrizione, editabili solo da admin, sola lettura per gli altri. Nav `nav-instructions` per tutti i ruoli.


### Iteration 18 (12 Feb 2026) — Caposquadra + Archivio DB + Dati di lavoro editabili
- **Caposquadra**: nuovo flag `is_team_leader` sull'utente. Endpoint `POST /api/auth/admin/set-team-leader/{user_id}` per designarlo (admin only). Solo i caposquadra possono impostare il compagno di squadra tramite `POST /team/today` (che ora ritorna 403 per i non-leader). Quando il caposquadra sceglie un collega, il collega vede automaticamente i seriali del caposquadra nel dropdown (via `_get_team_partners` bidirezionale già esistente) e le note della giornata vengono condivise. Rimuovere il flag caposquadra elimina anche le sue partnership attive.
- **Frontend Header**: `TeamPicker` mostra `⭐ CAPOSQUADRA` + dropdown per i leader; per i tecnici normali mostra solo il badge in sola lettura "👥 In squadra con ..." o "Nessuna squadra oggi".
- **Frontend AdminPanel**: nuovo pulsante `toggle-leader-{email}` per ogni tecnico (attiva/rimuove caposquadra). Badge `⭐ CAPOSQUADRA` sulle righe.
- **Archivio & Manutenzione DB**: sezione dedicata nel Pannello Admin con 3 pulsanti (`archive-export-filtered`, `archive-export-all`, `archive-purge`) + date picker. Endpoint:
  - `GET /admin/archive/export?before=YYYY-MM-DD` → JSON completo di notes+serial_events+notifications+vacations+users+serials (con filtro data opzionale)
  - `POST /admin/archive/purge` → cancella docs più vecchi di `before` (whitelist: notes, serial_events, notifications, vacations). Utenti e seriali attivi non vengono toccati.
- **Dati di lavoro sempre visibili + inline edit**: la sezione mostra ORA sempre tutte e 4 le card (Telefono cliente, ID SERVIZIO, ID RISORSA, Password). Se un campo è vuoto compare "+ aggiungi ..." cliccabile che apre un input inline; Enter salva sul server via `PATCH /notes/{id}`, Esc annulla. Se popolato: tap sul valore = copia + `tel:` link per il telefono, `<Edit3>` icon per modificare.
- **EXPORT_GITHUB.md aggiornato**: nuova sezione "Archivio & pulizia DB" e "Caposquadra". File copiato in `frontend/public/downloads/` per download pubblico.

### Iteration 17 (12 Feb 2026) — Fix dropdown seriali + Super-admin & multi-admin
- **Fix dropdown seriali → nota**: quando selezioni un seriale dal menù a tendina viene ora **salvato immediatamente sul server** (`PATCH /notes/{id}` con il campo target) PRIMA del refetch, così la nota viene rigenerata con il nuovo seriale. Prima il refetch sovrascriveva la selezione locale con lo stato server "vecchio".
- **Nessun vincolo di tipo**: `GET /inventory/my-assigned` ignora ora il parametro `tipo` — qualsiasi seriale assegnato può essere selezionato in qualsiasi campo (CPE, ONT o extra). Utile quando il magazzino dà un CPEWIFI da usare come ONT o come extra. Nel dropdown i seriali con tipo coincidente all'hint restano in cima con badge verde, gli altri seguono con badge rosa.
- **Multi-admin**: nuovo endpoint `POST /api/auth/admin/promote/{user_id}` — qualsiasi admin può promuovere un utente a admin (stessi poteri). Nuovo endpoint `POST /api/auth/admin/demote/{user_id}` — **solo il super-admin (ADMIN_EMAIL = giuseppe97belviso@gmail.com)** può declassare un altro admin a `user` o `magazzino`. Il super-admin non può essere declassato da nessuno.
- **`/auth/me` e `/auth/login`** ora ritornano `is_super_admin: bool`. AdminPanel: nuovi pulsanti `promote-admin-{email}` (visibile a tutti gli admin, sui non-admin) e `demote-admin-{email}` (visibile SOLO al super-admin, sugli altri admin).
- **Dati di lavoro completi + copia singola**: la sezione "Dati di lavoro" nella nota mostra ora ogni campo (Telefono cliente, ID SERVIZIO, ID RISORSA, Password) in card bianche 2-col, con testo **completamente visibile** (`break-all`, `select-all`), tap sul valore o sul pulsante "Copia" per copiare, `tel:` link sul telefono che copia+chiama.

## Implemented (as of 11 Feb 2026)
### Core (prior iterations)
- OpenFiber PDF parsing (WR, cliente, OLO, splitter, via, PFS, PTE, etc.)
- JWT auth con approvazione admin, RBAC (admin/user/magazzino)
- Note CRUD, edit inline, rigenerazione da campi, foto (camera + gallery)
- Invio Gmail: Web Share API (mobile con foto allegate) + mailto/Gmail Web fallback
- Scanner barcode/QR in-app con html5-qrcode
- Statistiche: totale, oggi, media giornaliera, mensile, istogramma 30gg
- Filtri data range, ricerca, bulk-delete, reset mese, export JSON/OLO
- Magazzino: aggiunta USB scanner, bulk, assegnazione utenti, sync note → scaricato
- Note status espletato/sospeso (era singolo toggle)
- File offline standalone HTML per Android

### Iteration 16 (12 Feb 2026) — Ferie avanzate + Restituzioni + Barcode automatico
- **Alert ferie sovrapposte**: `create_vacation` calcola overlap con richieste pending/approved altrui, imposta `has_overlap=true` + `overlap_with[]` sul doc, notifica admin con `kind='vacation_overlap'`.
- **Piano ferie per magazzino**: `role=magazzino` ora vede tutte le richieste (via `GET /api/vacations`). Nav-vacations visibile per magazzino con label "Piano ferie".
- **Calendario ferie colorato**: nuovo componente `VacationsCalendar` con vista mensile, hue stabile per user_id, celle con pill colorate (approved solide, pending dashed), navigazione prev/next/today, legenda automatica con l'associazione colore↔tecnico.
- **Storico restituzioni**: `SerialHistoryModal` ha tab `Tutti / Restituzioni` con contatore; il filtro isola gli eventi `unassigned` con `reason=returned_to_warehouse`.
- **Foto barcode automatica**: `AssignedSerialInput.pick()` genera e uploada la PNG barcode+QR al `POST /api/notes/{id}/photos` non appena selezioni un seriale dal menù, con toast "Barcode di X allegato".
- **EXPORT_GITHUB.md**: nuovo documento step-by-step per usare "Save to GitHub" e clonare/deployare.

### Iteration 15 (12 Feb 2026) — Polish avanzato
- **Dropdown vero per seriali assegnati** (non più `<datalist>`): pulsante `open-dropdown` apre menù cliccabile con chip per tag e nome tecnico, click su una voce compila il campo.
- **Dati privati estratti automaticamente dal PDF** (telefono cliente, ID SERVIZIO `AAA\d{4,}`, ID RISORSA, password apparato) e mostrati **in cima alla nota espansa** (`private-data-{wr}`) con click-to-copy e link `tel:` sul telefono.
- **Restituisci a magazzino**: pulsante `return-serial-{serial}` nel tab Assegnati (icona RotateCcw). Nuovo endpoint `POST /api/inventory/serials/{sid}/return` che ripristina `status='in_stock'`, aggiunge evento `unassigned` con `reason='returned_to_warehouse'`, notifica il magazzino.
- **Scanner auto-compile**: NoteCard traccia `lastField` (cpe/ont_sfp) sul focus/onChange, e passa il target come hint al ScannerModal. Etichetta del pulsante diventa `Scansiona → CPE` (o `→ ONT/SFP`) — nessuna domanda in più.
- **Guasto Auto-Detect**: le WR non numeriche vengono ora create come note con `note_type='guasto'` invece di essere scartate. Nella response del parse: nuovo campo `fault_count` (retrocompatibile con `skipped_wr`).

### Iteration 14 (12 Feb 2026) — Fase 3 + Fase 5 + Extra magazzino
**Fase 3 — Magazzino avanzato**
- **Tab Stato** nel magazzino: In stock (default homepage) / Assegnati / Scaricati / Tutti (testid `wh-tab-*`).
- **Bulk delete** con checkbox per riga (`wh-select-{serial}`) + select-all (`wh-select-all`) + pulsante `warehouse-bulk-delete` per eliminare più seriali insieme.
- **Elimina tag**: `POST /api/inventory/tags/delete` — rimuove il tag da tutti i seriali (rimangono in magazzino senza tag) e cancella la soglia associata. Pulsante `warehouse-delete-tag` compare quando c'è un filtro tag attivo.

**Fase 5 — Ferie**
- Pagina `nav-vacations` con form richiesta (from/to/motivo) per tecnici e magazzino.
- Admin vede tutte le richieste con azioni Approva/Rifiuta + nota opzionale.
- Notifiche automatiche: admin riceve `vacation_request` alla creazione, tecnico riceve `vacation_decision` alla decisione.

**Fase 5 — Admin Dashboard**
- Nuova pagina `nav-dashboard` (solo admin) con date range.
- Card per ogni utente approvato: media giornaliera (espletati+migrazioni ÷ giorni lavorati, sabato escluso), 4 contatori (espl./sosp./guast./migr.), giacenza personale (in stock/assegnati/scaricati).
- Ordinamento per performance (più espletati in cima).

**Note editor — Dropdown seriali assegnati + barcode preview**
- Nuovo componente `AssignedSerialInput`: input testo con `<datalist>` popolato dalla lista dei seriali assegnati al tecnico o al compagno di squadra (`GET /api/inventory/my-assigned`).
- Pulsante `field-cpe-{wr}-toggle-barcode` mostra l'immagine generata (barcode CODE128 + QR + testo grande) da tap per ingrandire.
- Applicato a CPE, ONT/SFP e ai materiali extra (EXT ecc.).

### Iteration 13 (12 Feb 2026) — Fasi 1+2+4 + Threshold
**Fase 1 — Workflow note**
- 4 stati distinti: `espletato` / `sospeso` / `guasto` / `migrazione` (+ `limbo` di default). Le 4 categorie hanno pulsanti separati con colori dedicati e badge nella card.
- **Sabato escluso** dalla media giornaliera (weekday=5 in `working_days_count`).
- `note_date` (data lavoro) modificabile: input date nell'edit form → puoi inserire pratiche anche in giorni passati.
- **Dropdown unificato** `mono_type`: `MONO INT` / `MONO EST` / `SBR` / `VRT STR SBR`. Se impostato, sostituisce MONO+INT nella nota.
- **Campi vuoti non appaiono** più nella nota generata (sia backend che frontend `composeNote`).
- Report top: 4 counter Espletati / Sospesi / Guasti / Migrazioni (sostituiscono il vecchio "totale note").

**Fase 2 — Campi extra + Report + Foto**
- Campi privati **non copiati nella nota**: telefono cliente, password apparato, ID SERVIZIO, ID RISORSA (in sezione collapsible).
- **Materiali multipli**: array `materials: [{tipo, serial}]` con UI add/remove; ogni voce appare in nota come `TIPO: SERIALE`.
- Endpoint `GET /api/notes/stats?from=&to=` con date range personalizzabile (preset "Mese" e "15→15").
- Endpoint `POST /api/notes/{id}/send-suspend-email`: pulsante `Mail sospensione` che apre `mailto:` con solo OLO+WR+motivo.
- **Photo lightbox** fullscreen con download originale.

**Fase 4 — Squadre**
- Endpoint `GET/POST /api/team/today` (compagno per il giorno) + `GET /api/users/approved`.
- Nel PDF parse le note create ricevono `shared_with = [partner_id]` in automatico se squadra settata.
- Il partner vede le note nella sua lista (`$or user_id / shared_with`); foto e modifiche condivise bidirezionalmente.
- `TeamPicker` in header (visibile solo per role=user) con dropdown compagno.

**Magazzino**
- **Soglie configurabili** per tag: `POST /api/inventory/thresholds`. Notifica `threshold_alert` automatica quando stock ≤ soglia (dedup 6h). Badge lampeggiante nella card tag e input inline per settare la soglia.
- **Multi-serial paste**: se in `POST /api/inventory/serials` il campo `serial` contiene spazi/virgole/newline, viene splittato e ogni token creato singolarmente.
- **OLO auto-associato** al seriale scaricato: quando un tecnico fa sync di una nota, il seriale ottiene `downloaded_olo`, `downloaded_note_wr`, `downloaded_note_id`, ed è visibile nello storico anche se l'etichetta è sbagliata.

### Iteration 12 (11 Feb 2026)
- **PWA installabile**: creato `/downloads/pwa/` con `manifest.json`, service worker (`sw.js`), 6 icone PNG (48/96/180/192/512 + maskable). L'offline HTML esistente è wrappato in una PWA con "Aggiungi alla schermata Home" (icona rosa GC Impianti). Zip pronto: `gc-impianti-pwa.zip` (852 KB). Istruzioni PWABuilder.com per convertirlo in APK reale firmato.
- **Cloudflare R2 storage (fallback trasparente)**: backend aggiornato con `boto3`; se env vars `R2_ENDPOINT/R2_BUCKET/R2_ACCESS_KEY/R2_SECRET_KEY` sono presenti, usa R2 (S3-compatibile); altrimenti fallback su Emergent Object Storage. Nessuna modifica al codice, solo env vars.
- **Statistiche per Tag**: endpoint `GET /api/inventory/stats` con aggregazione per tag; nuova sezione "Ripartizione magazzino" con barra colorata a 3 segmenti (in_stock/assegnato/scaricato) per tag, click-to-filter integrato.

### Iteration 11 (11 Feb 2026)
- **Tag magazzino liberi**: sostituito il dropdown fisso CPE/ONT/ALTRO con un **input free-form** con autocompletamento (`<datalist>`) basato sui tag già usati. Nuovo endpoint `GET /api/inventory/tags`.
- **Modifica tag inline**: nella tabella magazzino ogni riga mostra un **chip cliccabile** — al click diventa un input con Enter=salva, Esc=annulla. Chip vuoto = "+ tag".
- **Filtro dinamico**: il dropdown "Tutti i tag" nella lista magazzino è popolato solo con i tag realmente usati (non più valori fissi).
- **Download pubblici**: creato `/downloads/` con `index.html` che espone: build online (zip 2 MB), file offline (2.6 MB), guida migrazione smartphone, guida tecnica.

### Iteration 10 (11 Feb 2026)
- **Tasti stato separati**: `status-espletato-{wr}` (verde) e `status-sospeso-{wr}` (giallo). Il vecchio toggle unico è rimosso.
- **Scanner migliorato**: 
  - Genera automaticamente immagine PNG pulita del seriale (CODE128 barcode + QR + testo grande + data) — non più frame video sfocato
  - Torcia/flash toggle quando supportato dal device
  - Beep + vibrazione a scansione riuscita
  - Formati supportati estesi (CODE128, CODE39, CODE93, EAN, UPC, ITF, DataMatrix, PDF417, Aztec, QR)
  - Continuous focus + qrbox più ampio (85% viewport)
- **Storico seriale (Magazzino)**: cliccando un seriale si apre modal con timeline eventi (created, assigned, unassigned, downloaded on WR, manual_update, deleted). Endpoint `GET /api/inventory/serials/{sid}/history`.
- **Notifiche magazzino real-time**: campanella in header con badge unread, polling ogni 15s. Quando un tecnico sincronizza una nota, tutti gli admin + magazzino ricevono notifica con toast + vibrazione. Endpoints `/api/notifications`, `/notifications/{id}/read`, `/notifications/read-all`.
- **Export CSV magazzino**: pulsante nella pagina Magazzino → scarica `magazzino_YYYY-MM-DD.csv` con BOM UTF-8 per Excel. Endpoint `GET /api/inventory/export.csv` protetto RBAC.

## Data Models
```
users:         {id, email, name, password_hash, role, is_approved, created_at}
notes:         {id, user_id, wr, cliente, olo, splitter, via, n_porta_perm, porta_pte, cpe, ont_sfp, 
                indirizzo, pte_est, ts, tc, d, a, mono, internal, note_text, note_text_manual,
                photos[], pdf_filename, pdf_storage_path, status, suspend_reason,
                synced, synced_at, created_at, updated_at}
serials:       {id, serial, tipo, status, assigned_to_user_id, assigned_to_name,
                downloaded_by_user_id, downloaded_by_name, downloaded_at, note, created_at, updated_at}
serial_events: {id, serial, event_type, actor_id, actor_name, note_id, note_wr, extra{}, created_at}
notifications: {id, user_id, kind, message, from_user_name, note_id, note_wr, serials[], read, created_at}
```

## Key API Endpoints
- Auth: `POST /api/auth/login|register`, `GET /api/auth/me`, `GET/POST/DELETE /api/auth/admin/*`
- Notes: `POST /api/pdf/parse`, `GET|POST /api/notes`, `PATCH|DELETE /api/notes/{id}`, `POST /api/notes/bulk-delete`, `POST /api/notes/{id}/sync`, `POST /api/notes/{id}/photos`
- Inventory: `GET|POST /api/inventory/serials`, `POST /api/inventory/serials/bulk`, `PATCH|DELETE /api/inventory/serials/{sid}`, `GET /api/inventory/serials/{sid}/history`, `GET /api/inventory/export.csv`, `GET /api/inventory/users`
- Notifications: `GET /api/notifications`, `POST /api/notifications/{nid}/read`, `POST /api/notifications/read-all`

## Testing status
- Iteration 10 report: `/app/test_reports/iteration_10.json` — **100% pass** (5/5 backend pytest, frontend Playwright OK, code review passed with 2 minor stylistic notes non blockers).

## Backlog / Roadmap
### P1
- **QR Assegnazione utente**: generare QR per ogni utente da scansionare al magazzino per bulk-assign modem.
- **Offline HTML aggiornamento**: importare split-status buttons e immagine seriale generata (richiede inlining di ~40KB JsBarcode+QRCode UMD).
- **Notifiche push mobile**: usare Web Push API con service worker per notifiche fuori dall'app.

### P2
- **Refactor App.js** in cartelle `/components`, `/pages` per manutenibilità (attuale ~1700 righe).
- **Dashboard admin**: overview stato flotta modem + tecnici per periodo.
- **Backup automatico** MongoDB → export JSON schedulato.

## Migration guide (for user's own infra)
- Codice → **Save to GitHub** dalla chat (esporta repo completo)
- Database → **Republish → Database → Dump DB** (JSON compatibile con mongorestore)
- Env → **Republish → Secrets** (MONGO_URL, DB_NAME, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, EMERGENT_LLM_KEY)
- Auth: JWT-based custom (nessuna dipendenza da servizio esterno), bcrypt password hash. Seed admin al boot da ADMIN_EMAIL/PASSWORD env.

## Credentials
- Admin: `Giuseppe97belviso@gmail.com` / `Mucchetta4!` (vedere `/app/memory/test_credentials.md`)
