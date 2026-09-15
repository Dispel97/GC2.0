import { useEffect, useState, useCallback, useRef, useMemo, createContext, useContext } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Upload, FileText, Copy, Mail, Trash2, Image as ImageIcon,
  Loader2, Search, ChevronDown, ChevronUp, Save, X, Camera, RotateCcw,
  LogOut, Shield, UserCheck, UserX, Users, ScanLine, LogIn, UserPlus,
  Package, RefreshCw, Calendar, CheckCircle2, PauseCircle, Warehouse,
  Bell, History, Zap, ZapOff, Download, Edit3, BookOpen, Plus, ChevronRight, Folder, GripVertical,
} from "lucide-react";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import JsBarcode from "jsbarcode";
import QRCode from "qrcode";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const RECIPIENTS = [
  "g.c.impiantiufficio@gmail.com",
  "g.c.impiantisnc4@gmail.com",
  "giuseppe.abbatiscianni@circet.it",
  "dario.naviglio@circet.it",
  "vito.lalario@circet.it",
];

const RecipientsContext = createContext({ recipients: RECIPIENTS, saveRecipients: async () => {} });
const useRecipients = () => useContext(RecipientsContext);

const LOGO_GC = "https://customer-assets-jai6qajn.emergentagent.net/job_ccf322e9-af2b-47ac-bdda-c765aa29fe4c/artifacts/26fm2fx6_1682096608045.jpeg";
const LOGO_OF = "https://customer-assets-jai6qajn.emergentagent.net/job_ccf322e9-af2b-47ac-bdda-c765aa29fe4c/artifacts/hfc42618_Open_Fiber_logo.svg.png";

const composeNote = (n) => {
  const push = (arr, v) => { if (v !== undefined && v !== null && String(v).trim() !== "") arr.push(String(v).trim()); };
  const parts = [];
  push(parts, n.splitter); push(parts, n.via); push(parts, n.pte_est);
  if (n.n_porta_perm && String(n.n_porta_perm).trim()) parts.push(`PFS ${n.n_porta_perm}`);
  if (n.porta_pte && String(n.porta_pte).trim()) parts.push(`PTE ${n.porta_pte}`);
  push(parts, n.ts); push(parts, n.tc); push(parts, n.d); push(parts, n.a);
  if (n.mono_type && String(n.mono_type).trim()) {
    parts.push(String(n.mono_type).trim());
  } else {
    push(parts, n.mono); push(parts, n.internal);
  }
  const tech = parts.join(" ");
  const lines = [`WR: ${n.wr || ""}`];
  if (n.cliente && n.cliente.trim()) lines.push(n.cliente.trim().toLowerCase());
  if (n.olo && String(n.olo).trim()) lines.push(String(n.olo).trim());
  if (tech) lines.push(tech);
  if (n.cpe && n.cpe.trim()) lines.push(`CPE: ${n.cpe.trim()}`);
  if (n.ont_sfp && String(n.ont_sfp).trim()) lines.push(`(ONT/SFP): ${n.ont_sfp.trim()}`);
  for (const m of (n.materials || [])) {
    const tipo = (m?.tipo || "").trim();
    const ser = (m?.serial || "").trim();
    if (tipo && ser) lines.push(`${tipo}: ${ser}`);
    else if (tipo) lines.push(`${tipo}:`);
  }
  return lines.join("\n");
};

const errorText = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  if (d && typeof d.msg === "string") return d.msg;
  return e?.message || "Errore";
};

// ---------- Generate a clean serial image (barcode + QR + text) ----------
async function generateSerialImage(serial, label = "") {
  const W = 800, H = 600;
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  // White background
  ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, W, H);
  // Header
  ctx.fillStyle = "#0f172a"; // slate-900
  ctx.font = "bold 26px system-ui, -apple-system, sans-serif";
  ctx.textBaseline = "top";
  ctx.fillText(label ? `SERIALE ${label}` : "SERIALE", 30, 24);
  ctx.fillStyle = "#64748b"; // slate-500
  ctx.font = "500 14px system-ui, -apple-system, sans-serif";
  ctx.fillText(new Date().toLocaleString("it-IT"), 30, 58);

  // Barcode CODE128 into its own canvas, then draw
  try {
    const bc = document.createElement("canvas");
    JsBarcode(bc, serial, {
      format: "CODE128",
      width: 3,
      height: 140,
      displayValue: false,
      margin: 8,
      background: "#ffffff",
      lineColor: "#0f172a",
    });
    const targetW = 520;
    const scale = targetW / bc.width;
    ctx.drawImage(bc, 30, 100, targetW, bc.height * scale);
  } catch (e) {
    ctx.fillStyle = "#dc2626";
    ctx.fillText("Barcode non generabile", 30, 100);
  }

  // QR on the right
  try {
    const qrDataUrl = await QRCode.toDataURL(serial, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 220,
      color: { dark: "#0f172a", light: "#ffffff" },
    });
    await new Promise((res) => {
      const img = new Image();
      img.onload = () => { ctx.drawImage(img, W - 250, 90, 220, 220); res(); };
      img.onerror = res;
      img.src = qrDataUrl;
    });
  } catch (_) { /* ignore */ }

  // Serial number in monospace big
  ctx.fillStyle = "#0f172a";
  ctx.font = "bold 44px 'Courier New', monospace";
  const textY = 360;
  // Measure and center
  const tw = ctx.measureText(serial).width;
  const maxTw = W - 60;
  if (tw > maxTw) {
    const size = Math.max(20, Math.floor(44 * (maxTw / tw)));
    ctx.font = `bold ${size}px 'Courier New', monospace`;
  }
  const tw2 = ctx.measureText(serial).width;
  ctx.fillText(serial, (W - tw2) / 2, textY);

  // Divider
  ctx.strokeStyle = "#e2e8f0"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(30, 440); ctx.lineTo(W - 30, 440); ctx.stroke();

  // Footer
  ctx.fillStyle = "#64748b";
  ctx.font = "500 14px system-ui, -apple-system, sans-serif";
  ctx.fillText("Generato automaticamente dallo scanner GC Impianti", 30, 460);
  ctx.fillStyle = "#94a3b8";
  ctx.font = "500 12px system-ui, -apple-system, sans-serif";
  ctx.fillText("Barcode CODE128 + QR contengono il seriale sopra riportato", 30, 484);

  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/png", 0.95));
}

// ---------- Axios interceptor ----------
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem("gc_token");
  if (token) config.headers["Authorization"] = `Bearer ${token}`;
  return config;
});

// ---------- Auth Context ----------
const AuthCtx = createContext(null);
function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=loading, false=guest, obj=auth
  useEffect(() => {
    const token = localStorage.getItem("gc_token");
    if (!token) { setUser(false); return; }
    axios.get(`${API}/auth/me`).then((r) => setUser(r.data)).catch(() => { localStorage.removeItem("gc_token"); setUser(false); });
  }, []);
  const login = async (email, password) => {
    const r = await axios.post(`${API}/auth/login`, { email, password });
    localStorage.setItem("gc_token", r.data.access_token);
    setUser(r.data.user);
  };
  const register = async (email, password, name) => {
    const r = await axios.post(`${API}/auth/register`, { email, password, name });
    return r.data;
  };
  const logout = () => { localStorage.removeItem("gc_token"); setUser(false); };
  return <AuthCtx.Provider value={{ user, setUser, login, register, logout }}>{children}</AuthCtx.Provider>;
}
const useAuth = () => useContext(AuthCtx);

// ---------- Header ----------
function Header({ onAdmin, showAdminBtn, page, onPageChange, canSwitchPage }) {
  const { user, logout } = useAuth();
  return (
    <header className="bg-white border-b border-slate-200" data-testid="header-admin-bar">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <img src={LOGO_GC} alt="GC Impianti SNC" className="h-10 sm:h-12 w-auto object-contain rounded" data-testid="logo-gc" />
          <div className="hidden sm:block h-8 w-px bg-slate-200" />
          <img src={LOGO_OF} alt="Open Fiber" className="h-8 sm:h-10 w-auto object-contain" data-testid="logo-openfiber" />
        </div>
        <div className="ml-auto text-right">
          <h1 className="text-lg sm:text-xl font-display font-extrabold tracking-tight text-slate-900" data-testid="app-title">
            {page === "warehouse" ? "Magazzino Modem" : "Gestione Pratiche & Note"}
          </h1>
          <p className="text-xs sm:text-[13px] text-slate-500 font-medium">
            creato e amministrato da <span className="text-slate-800 font-semibold">Giuseppe Belviso</span>
          </p>
        </div>
        {user && (
          <div className="w-full flex items-center gap-2 pt-2 border-t border-slate-100 flex-wrap" data-testid="user-bar">
            <div className="text-xs text-slate-600 truncate">
              <span className="font-semibold text-slate-800">{user.email}</span>
              {user.role === "admin" && <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-bold text-brand-pink brand-pink"><Shield size={10} /> ADMIN</span>}
              {user.role === "magazzino" && <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-bold text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded"><Warehouse size={10} /> MAGAZZINO</span>}
            </div>
            {canSwitchPage && (
              <div className="ml-auto flex gap-1 bg-slate-100 rounded-full p-1 flex-wrap" data-testid="page-switcher">
                {user.role !== "magazzino" && (
                <button onClick={() => onPageChange("notes")}
                  className={`px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${page === "notes" ? "bg-white text-slate-900 shadow" : "text-slate-500 hover:text-slate-800"}`}
                  data-testid="nav-notes">
                  <FileText size={12} /> Tecnico
                </button>
                )}
                <button onClick={() => onPageChange("warehouse")}
                  className={`px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${page === "warehouse" ? "bg-white text-slate-900 shadow" : "text-slate-500 hover:text-slate-800"}`}
                  data-testid="nav-warehouse">
                  <Warehouse size={12} /> Magazzino
                </button>
                <button onClick={() => onPageChange("vacations")}
                  className={`px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${page === "vacations" ? "bg-white text-slate-900 shadow" : "text-slate-500 hover:text-slate-800"}`}
                  data-testid="nav-vacations">
                  <Calendar size={12} /> {user.role === "magazzino" ? "Piano ferie" : "Ferie"}
                </button>
                <button onClick={() => onPageChange("instructions")}
                  className={`px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${page === "instructions" ? "bg-white text-slate-900 shadow" : "text-slate-500 hover:text-slate-800"}`}
                  data-testid="nav-instructions">
                  <BookOpen size={12} /> Istruzioni
                </button>
                {user.role === "admin" && (
                  <button onClick={() => onPageChange("dashboard")}
                    className={`px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${page === "dashboard" ? "bg-white text-slate-900 shadow" : "text-slate-500 hover:text-slate-800"}`}
                    data-testid="nav-dashboard">
                    <Shield size={12} /> Dashboard
                  </button>
                )}
              </div>
            )}
            <div className={`${canSwitchPage ? "" : "ml-auto"} flex gap-2 items-center flex-wrap`}>
              {(user.role === "user" && page === "notes") && <TeamPicker />}
              {(user.role === "admin" || user.role === "magazzino") && <NotificationsBell />}
              {showAdminBtn && (
                <button onClick={onAdmin} className="btn-ghost text-xs font-semibold text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-full px-3 py-1.5 inline-flex items-center gap-1" data-testid="btn-admin-panel">
                  <Users size={14} /> Admin
                </button>
              )}
              <button onClick={logout} className="btn-ghost text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 rounded-full px-3 py-1.5 inline-flex items-center gap-1" data-testid="btn-logout">
                <LogOut size={14} /> Esci
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

// ---------- Auth Screen ----------
function AuthScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
        toast.success("Accesso effettuato");
      } else {
        await register(email, password, name);
        toast.success("Registrazione inviata! Attendi l'approvazione dell'amministratore.");
        setMode("login");
      }
    } catch (e) {
      toast.error(errorText(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl card-shadow p-6 sm:p-8" data-testid="auth-card">
        <div className="flex items-center gap-3 mb-6">
          <img src={LOGO_GC} alt="GC" className="h-10 rounded" />
          <div className="h-8 w-px bg-slate-200" />
          <img src={LOGO_OF} alt="Open Fiber" className="h-8" />
        </div>
        <h1 className="text-2xl font-display font-extrabold text-slate-900 mb-1">
          {mode === "login" ? "Accedi" : "Crea account"}
        </h1>
        <p className="text-sm text-slate-500 mb-6">
          {mode === "login" ? "Entra con la tua email e password" : "La registrazione richiede l'approvazione dell'amministratore"}
        </p>
        <form onSubmit={submit} className="space-y-3">
          {mode === "register" && (
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Nome (opzionale)</span>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-pink"
                data-testid="input-name" />
            </label>
          )}
          <label className="block">
            <span className="text-xs font-semibold text-slate-600">Email</span>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-pink"
              data-testid="input-email" />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-slate-600">Password</span>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-pink"
              data-testid="input-password" />
          </label>
          <button type="submit" disabled={busy}
            className="btn-primary rounded-full w-full py-3 text-sm font-semibold inline-flex items-center justify-center gap-2"
            data-testid={mode === "login" ? "btn-login" : "btn-register"}>
            {busy ? <Loader2 className="animate-spin" size={16} /> : (mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />)}
            {mode === "login" ? "Accedi" : "Registrati"}
          </button>
        </form>
        <div className="mt-5 text-center text-sm text-slate-600">
          {mode === "login" ? (
            <>Non hai un account? <button onClick={() => setMode("register")} className="brand-pink font-semibold hover:underline" data-testid="switch-register">Registrati</button></>
          ) : (
            <>Hai già un account? <button onClick={() => setMode("login")} className="brand-pink font-semibold hover:underline" data-testid="switch-login">Accedi</button></>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------- Admin Panel ----------
function AdminPanel({ onClose }) {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/auth/admin/users`); setUsers(r.data); }
    catch (e) { toast.error(errorText(e)); } finally { setLoading(false); }
  };
  useEffect(() => { fetchUsers(); }, []);

  const approve = async (id, role) => { try { await axios.post(`${API}/auth/admin/approve/${id}`, { role }); toast.success(`Utente approvato come ${role === "magazzino" ? "Magazzino" : "Tecnico"}`); fetchUsers(); } catch (e) { toast.error(errorText(e)); } };
  const setRole = async (id, role) => { try { await axios.post(`${API}/auth/admin/set-role/${id}`, { role }); toast.success("Ruolo aggiornato"); fetchUsers(); } catch (e) { toast.error(errorText(e)); } };
  const revoke = async (id) => { try { await axios.post(`${API}/auth/admin/revoke/${id}`); toast.success("Approvazione revocata"); fetchUsers(); } catch (e) { toast.error(errorText(e)); } };
  const del = async (id, email) => {
    if (!window.confirm(`Eliminare definitivamente ${email} e tutte le sue note?`)) return;
    try { await axios.delete(`${API}/auth/admin/users/${id}`); toast.success("Utente eliminato"); fetchUsers(); } catch (e) { toast.error(errorText(e)); }
  };
  const promote = async (id, email) => {
    if (!window.confirm(`Promuovere ${email} ad ADMIN? Avrà tutti i poteri di amministrazione.`)) return;
    try { await axios.post(`${API}/auth/admin/promote/${id}`); toast.success(`${email} è ora ADMIN`); fetchUsers(); } catch (e) { toast.error(errorText(e)); }
  };
  const demote = async (id, email) => {
    const choice = window.prompt(`Declassare ${email} — inserisci il nuovo ruolo:\n\n"user"  → Tecnico\n"magazzino"  → Magazzino`, "user");
    if (!choice) return;
    const role = choice.trim().toLowerCase();
    if (!["user", "magazzino"].includes(role)) { toast.error("Ruolo non valido (usa 'user' o 'magazzino')"); return; }
    try { await axios.post(`${API}/auth/admin/demote/${id}`, { role }); toast.success(`${email} declassato a ${role === "magazzino" ? "Magazzino" : "Tecnico"}`); fetchUsers(); } catch (e) { toast.error(errorText(e)); }
  };
  const toggleLeader = async (id, email, currently) => {
    const target = !currently;
    if (!window.confirm(target ? `Rendere ${email} CAPOSQUADRA? Potrà scegliere il collega di giornata e condividere note e seriali.` : `Rimuovere il ruolo di caposquadra a ${email}?`)) return;
    try { await axios.post(`${API}/auth/admin/set-team-leader/${id}`, { is_team_leader: target }); toast.success(target ? `${email} è ora caposquadra` : `${email} non è più caposquadra`); fetchUsers(); } catch (e) { toast.error(errorText(e)); }
  };

  const pending = users.filter((u) => !u.is_approved && u.role !== "admin");
  const approved = users.filter((u) => u.is_approved || u.role === "admin");
  const isSuperAdmin = !!currentUser?.is_super_admin;
  const superAdminEmail = (currentUser?.is_super_admin ? currentUser.email : "").toLowerCase();

  return (
    <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-start sm:items-center justify-center p-3 overflow-y-auto" onClick={onClose} data-testid="admin-modal">
      <div className="bg-white rounded-2xl max-w-3xl w-full my-4 max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center gap-3 z-10">
          <Users size={18} className="brand-pink" />
          <h2 className="text-lg font-display font-bold">Pannello amministratore</h2>
          <button onClick={onClose} className="ml-auto btn-ghost rounded-full p-1.5 hover:bg-slate-100" data-testid="close-admin"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-6">
          {loading && <div className="flex items-center gap-2 text-slate-500 text-sm"><Loader2 className="animate-spin" size={16} /> Caricamento…</div>}
          <section data-testid="pending-section">
            <h3 className="text-sm font-semibold text-slate-900 mb-2">In attesa di approvazione ({pending.length})</h3>
            {pending.length === 0 ? (
              <div className="text-sm text-slate-400 border border-dashed border-slate-200 rounded-lg p-4 text-center">Nessuna richiesta in attesa</div>
            ) : (
              <div className="space-y-2">
                {pending.map((u) => (
                  <div key={u.id} className="border border-slate-200 rounded-xl p-3 flex items-center gap-3 flex-wrap" data-testid={`pending-${u.email}`}>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-slate-900 truncate">{u.email}</div>
                      <div className="text-xs text-slate-500">{u.name || "—"} • {new Date(u.created_at).toLocaleString("it-IT")}</div>
                    </div>
                    <button onClick={() => approve(u.id, "user")} className="btn-primary rounded-full px-3 py-1.5 text-xs font-semibold inline-flex items-center gap-1" data-testid={`approve-user-${u.email}`}><UserCheck size={12} /> Tecnico</button>
                    <button onClick={() => approve(u.id, "magazzino")} className="rounded-full px-3 py-1.5 text-xs font-semibold bg-slate-900 text-white inline-flex items-center gap-1 hover:bg-slate-800" data-testid={`approve-magazzino-${u.email}`}><Warehouse size={12} /> Magazzino</button>
                    <button onClick={() => del(u.id, u.email)} className="btn-ghost rounded-full px-3 py-1.5 text-xs font-semibold bg-red-50 text-red-600 hover:bg-red-100 inline-flex items-center gap-1" data-testid={`reject-${u.email}`}><UserX size={12} /> Rifiuta</button>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section data-testid="approved-section">
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Utenti attivi ({approved.length})</h3>
            <div className="space-y-2">
              {approved.map((u) => {
                const isSelf = currentUser?.id === u.id;
                const isTargetSuperAdmin = u.email && superAdminEmail && u.email.toLowerCase() === superAdminEmail;
                return (
                <div key={u.id} className="border border-slate-200 rounded-xl p-3 flex items-center gap-3 flex-wrap" data-testid={`approved-${u.email}`}>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-slate-900 truncate">
                      {u.email}{" "}
                      {u.role === "admin" && <span className="ml-1 text-[10px] font-bold text-brand-pink brand-pink">ADMIN{isTargetSuperAdmin ? " ★" : ""}</span>}
                      {u.role === "magazzino" && <span className="ml-1 text-[10px] font-bold text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded">MAGAZZINO</span>}
                      {u.role === "user" && <span className="ml-1 text-[10px] font-bold text-slate-500">TECNICO</span>}
                      {u.is_team_leader && <span className="ml-1 text-[10px] font-bold text-pink-800 bg-pink-100 px-1.5 py-0.5 rounded" title="Caposquadra: può scegliere il collega di giornata">⭐ CAPOSQUADRA</span>}
                    </div>
                    <div className="text-xs text-slate-500">{u.name || "—"} • {new Date(u.created_at).toLocaleString("it-IT")}</div>
                  </div>
                  {u.role === "user" && (
                    <button onClick={() => toggleLeader(u.id, u.email, !!u.is_team_leader)}
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold inline-flex items-center gap-1 ${u.is_team_leader ? "bg-pink-100 text-pink-800 hover:bg-pink-200" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}
                      data-testid={`toggle-leader-${u.email}`}
                      title={u.is_team_leader ? "Rimuovi ruolo caposquadra" : "Rendi caposquadra"}>
                      ⭐ {u.is_team_leader ? "Rimuovi caposq." : "Caposquadra"}
                    </button>
                  )}
                  {u.role !== "admin" && (
                    <>
                      <select value={u.role} onChange={(e) => setRole(u.id, e.target.value)}
                        className="text-xs rounded-full border border-slate-200 bg-white px-2 py-1.5"
                        data-testid={`role-select-${u.email}`}>
                        <option value="user">Tecnico</option>
                        <option value="magazzino">Magazzino</option>
                      </select>
                      <button onClick={() => promote(u.id, u.email)}
                        className="rounded-full px-3 py-1.5 text-xs font-semibold bg-brand-pink/10 text-brand-pink brand-pink hover:bg-brand-pink/20 inline-flex items-center gap-1"
                        data-testid={`promote-admin-${u.email}`} title="Promuovi ad Admin">
                        <Shield size={12} /> Promuovi Admin
                      </button>
                      <button onClick={() => revoke(u.id)} className="btn-ghost rounded-full px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 inline-flex items-center gap-1"><UserX size={12} /> Sospendi</button>
                      <button onClick={() => del(u.id, u.email)} className="btn-ghost rounded-full px-3 py-1.5 text-xs font-semibold bg-red-50 text-red-600 hover:bg-red-100 inline-flex items-center gap-1"><Trash2 size={12} /> Elimina</button>
                    </>
                  )}
                  {u.role === "admin" && isSuperAdmin && !isTargetSuperAdmin && !isSelf && (
                    <button onClick={() => demote(u.id, u.email)}
                      className="rounded-full px-3 py-1.5 text-xs font-semibold bg-amber-100 text-amber-800 hover:bg-amber-200 inline-flex items-center gap-1"
                      data-testid={`demote-admin-${u.email}`} title="Declassa questo admin">
                      <UserX size={12} /> Declassa
                    </button>
                  )}
                  {u.role === "admin" && isTargetSuperAdmin && (
                    <span className="text-[10px] italic text-slate-400" title="Il super-admin non può essere declassato">super-admin</span>
                  )}
                </div>
                );
              })}
            </div>
          </section>
          <ArchiveSection />
        </div>
      </div>
    </div>
  );
}

// ---------- Archive Section (admin only) ----------
function ArchiveSection() {
  const today = new Date().toISOString().slice(0, 10);
  const oneYearAgo = new Date(Date.now() - 365 * 86400 * 1000).toISOString().slice(0, 10);
  const [before, setBefore] = useState(oneYearAgo);
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState(null);

  const exportArchive = async (withFilter) => {
    setBusy(true);
    try {
      const params = withFilter ? { before } : {};
      const r = await axios.get(`${API}/admin/archive/export`, { params });
      const filename = withFilter ? `archivio_pre_${before}.json` : `archivio_completo_${today}.json`;
      downloadFile(filename, JSON.stringify(r.data, null, 2), "application/json");
      const counts = Object.entries(r.data.collections || {}).map(([k, v]) => `${k}: ${v.length}`).join(", ");
      toast.success(`Archivio scaricato — ${counts}`);
    } catch (e) { toast.error(errorText(e)); }
    finally { setBusy(false); }
  };

  const purge = async () => {
    if (!window.confirm(`⚠️ Sei sicuro?\n\nVerranno ELIMINATI definitivamente:\n• Note create prima del ${before}\n• Eventi seriali prima del ${before}\n• Notifiche prima del ${before}\n• Richieste ferie prima del ${before}\n\nUsers e seriali NON vengono toccati.\n\nPrima assicurati di aver scaricato l'archivio!`)) return;
    if (!window.confirm("Ultima conferma: procedo con l'eliminazione?")) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/admin/archive/purge`, { before, collections: ["notes", "serial_events", "notifications", "vacations"] });
      setLastResult(r.data);
      const counts = Object.entries(r.data.deleted || {}).map(([k, v]) => `${k}: ${v}`).join(", ");
      toast.success(`Archiviato — eliminati ${counts}`);
    } catch (e) { toast.error(errorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <section data-testid="archive-section" className="border-t border-slate-200 pt-5">
      <h3 className="text-sm font-semibold text-slate-900 mb-1 inline-flex items-center gap-2">
        📦 Archivio & Manutenzione DB
      </h3>
      <p className="text-xs text-slate-500 mb-3">Scarica una copia JSON dei dati e libera spazio eliminando note/eventi/notifiche vecchie. Il super-admin lo usa quando il DB si riempie.</p>
      <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs font-semibold text-slate-700">Data limite (elimina/esporta prima di):</label>
          <input type="date" value={before} onChange={(e) => setBefore(e.target.value)}
            max={today}
            className="rounded-full border border-amber-300 bg-white px-3 py-1.5 text-xs font-mono"
            data-testid="archive-before-date" />
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => exportArchive(true)} disabled={busy}
            className="rounded-full px-3 py-1.5 text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 inline-flex items-center gap-2 disabled:opacity-60"
            data-testid="archive-export-filtered">
            {busy ? <Loader2 className="animate-spin" size={12} /> : <Download size={12} />}
            Esporta archivio (pre {before})
          </button>
          <button onClick={() => exportArchive(false)} disabled={busy}
            className="rounded-full px-3 py-1.5 text-xs font-semibold bg-slate-100 text-slate-800 hover:bg-slate-200 inline-flex items-center gap-2 disabled:opacity-60"
            data-testid="archive-export-all">
            <Download size={12} /> Backup completo
          </button>
          <button onClick={purge} disabled={busy}
            className="rounded-full px-3 py-1.5 text-xs font-semibold bg-red-600 text-white hover:bg-red-700 inline-flex items-center gap-2 disabled:opacity-60"
            data-testid="archive-purge">
            <Trash2 size={12} /> Elimina & libera spazio
          </button>
        </div>
        {lastResult && (
          <div className="text-[11px] text-slate-600 bg-white rounded-lg border border-slate-200 p-2" data-testid="archive-last-result">
            Ultima pulizia ({lastResult.before}): {Object.entries(lastResult.deleted || {}).map(([k, v]) => `${k}=${v}`).join(" • ")}
          </div>
        )}
        <div className="text-[10px] text-amber-900 leading-snug">
          <strong>Nota:</strong> "Backup completo" scarica tutti i dati (note+seriali+eventi+notifiche+ferie+utenti). "Elimina" rimuove solo note, eventi, notifiche e ferie più vecchie di quella data. Utenti e seriali attivi restano intatti.
        </div>
      </div>
    </section>
  );
}

// ---------- Barcode Scanner Modal ----------
function beepAndVibrate() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) {
      const ac = new Ctx();
      const o = ac.createOscillator(); const g = ac.createGain();
      o.type = "sine"; o.frequency.value = 880;
      g.gain.value = 0.15;
      o.connect(g); g.connect(ac.destination);
      o.start(); o.stop(ac.currentTime + 0.12);
      setTimeout(() => ac.close().catch(() => {}), 300);
    }
  } catch (_) {}
  try { if (navigator.vibrate) navigator.vibrate([80, 40, 80]); } catch (_) {}
}

function ScannerModal({ onClose, onScan, target, setTarget }) {
  const containerId = "gc-scanner";
  const ref = useRef(null);
  const [torchOn, setTorchOn] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);

  useEffect(() => {
    if (!target) return;
    let stopped = false;
    const q = new Html5Qrcode(containerId, { formatsToSupport: [
      Html5QrcodeSupportedFormats.QR_CODE,
      Html5QrcodeSupportedFormats.CODE_128, Html5QrcodeSupportedFormats.CODE_39,
      Html5QrcodeSupportedFormats.CODE_93, Html5QrcodeSupportedFormats.CODABAR,
      Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8,
      Html5QrcodeSupportedFormats.UPC_A, Html5QrcodeSupportedFormats.UPC_E,
      Html5QrcodeSupportedFormats.ITF, Html5QrcodeSupportedFormats.DATA_MATRIX,
      Html5QrcodeSupportedFormats.PDF_417, Html5QrcodeSupportedFormats.AZTEC,
    ] });
    ref.current = q;
    const qrbox = (vw, vh) => {
      const min = Math.min(vw, vh);
      const size = Math.floor(min * 0.85);
      return { width: size, height: Math.floor(size * 0.55) };
    };
    q.start(
      { facingMode: "environment" },
      {
        fps: 15,
        qrbox,
        aspectRatio: 1.4,
        advanced: [{ focusMode: "continuous" }, { zoom: 1 }],
      },
      async (decoded) => {
        if (stopped) return;
        stopped = true;
        beepAndVibrate();
        // Generate a clean serial image (barcode + QR + text) — no blurry video frame
        let snapshot = null;
        try {
          const blob = await generateSerialImage(decoded, target === "cpe" ? "CPE" : "ONT/SFP");
          if (blob) snapshot = new File([blob], `serial_${target}_${decoded}.png`, { type: "image/png" });
        } catch (_) { /* ignore */ }
        onScan(decoded, target, snapshot);
        q.stop().then(() => q.clear()).catch(() => {});
      },
      () => {}
    ).then(async () => {
      // Detect torch capability
      try {
        const caps = q.getRunningTrackCameraCapabilities && q.getRunningTrackCameraCapabilities();
        if (caps && typeof caps.torchFeature === "function") {
          setTorchAvailable(caps.torchFeature().isSupported());
        }
      } catch (_) {}
    }).catch((err) => toast.error("Impossibile avviare la fotocamera: " + err));
    return () => {
      stopped = true;
      try { q.stop().then(() => q.clear()).catch(() => {}); } catch (_) {}
    };
  }, [target, onScan]);

  const toggleTorch = async () => {
    try {
      const caps = ref.current?.getRunningTrackCameraCapabilities?.();
      const torch = caps?.torchFeature?.();
      if (!torch || !torch.isSupported()) { toast.message("Torcia non supportata da questo dispositivo"); return; }
      const next = !torchOn;
      await torch.apply(next);
      setTorchOn(next);
    } catch (e) { toast.error("Impossibile attivare la torcia"); }
  };

  return (
    <div className="fixed inset-0 bg-slate-900/70 z-50 flex items-start sm:items-center justify-center p-3" onClick={onClose} data-testid="scanner-modal">
      <div className="bg-white rounded-2xl max-w-md w-full" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200 flex items-center gap-3">
          <ScanLine size={18} className="brand-pink" />
          <h3 className="text-base font-display font-bold">Scansiona seriale modem</h3>
          {target && torchAvailable && (
            <button onClick={toggleTorch} className={`ml-auto rounded-full p-1.5 ${torchOn ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`} data-testid="scanner-torch" title="Torcia">
              {torchOn ? <Zap size={16} /> : <ZapOff size={16} />}
            </button>
          )}
          <button onClick={onClose} className={`${target && torchAvailable ? "" : "ml-auto"} btn-ghost rounded-full p-1.5 hover:bg-slate-100`} data-testid="close-scanner"><X size={18} /></button>
        </div>
        <div className="p-4">
          {!target ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-600 mb-2">In quale campo vuoi inserire il codice scansionato?</p>
              <div className="grid grid-cols-2 gap-3">
                <button onClick={() => setTarget("cpe")} className="border border-slate-200 rounded-xl px-4 py-6 hover:border-brand-pink hover:bg-pink-50 text-center transition" data-testid="scan-target-cpe">
                  <div className="text-lg font-display font-extrabold text-slate-900">CPE</div>
                  <div className="text-xs text-slate-500 mt-0.5">Seriale modem</div>
                </button>
                <button onClick={() => setTarget("ont_sfp")} className="border border-slate-200 rounded-xl px-4 py-6 hover:border-brand-pink hover:bg-pink-50 text-center transition" data-testid="scan-target-ont">
                  <div className="text-lg font-display font-extrabold text-slate-900">ONT / SFP</div>
                  <div className="text-xs text-slate-500 mt-0.5">Seriale ONT</div>
                </button>
              </div>
            </div>
          ) : (
            <div>
              <div id={containerId} style={{ width: "100%" }} className="rounded-lg overflow-hidden bg-slate-900" />
              <p className="text-xs text-slate-500 mt-3">
                Inquadra il codice a barre o QR — verrà inserito nel campo <strong>{target === "cpe" ? "CPE" : "ONT / SFP"}</strong> e verrà generata automaticamente un'immagine pulita del seriale (barcode + QR + testo) da allegare alla nota.
              </p>
              {torchAvailable && (
                <p className="text-[11px] text-slate-400 mt-1">Suggerimento: tocca l'icona <Zap size={10} className="inline" /> per attivare la torcia in ambienti bui.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------- PDF Uploader ----------
function PdfUploader({ onParsed }) {
  const [drag, setDrag] = useState(false);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  const handleFile = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) { toast.error("Seleziona un file PDF valido"); return; }
    setLoading(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await axios.post(`${API}/pdf/parse`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      const { created_count, skipped_wr, duplicate_count, fault_count } = res.data;
if (created_count === 0 && fault_count === 0 && duplicate_count > 0) {
  toast.error("Note già presenti");
} else if (created_count === 0) {
  toast.warning("Nessuna pratica con WR numerico trovata");
} else {
  toast.success(`${created_count} nota/note create`);
}
if (duplicate_count > 0) toast.message(`${duplicate_count} nota/e già presente/i saltate`);
if (skipped_wr && skipped_wr.length) toast.message(`WR non numerici saltati: ${skipped_wr.join(", ")}`);
      onParsed?.();
    } catch (e) { toast.error(errorText(e)); }
    finally { setLoading(false); if (inputRef.current) inputRef.current.value = ""; }
  };

  return (
    <div className={`dropzone ${drag ? "drag" : ""} p-6 sm:p-8 text-center`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files?.[0]); }}
      data-testid="pdf-upload-dropzone">
      <div className="flex flex-col items-center gap-3">
        <div className="w-14 h-14 rounded-full bg-brand-pink/10 flex items-center justify-center brand-pink">
          {loading ? <Loader2 className="animate-spin" size={26} /> : <Upload size={26} />}
        </div>
        <div>
          <div className="text-base sm:text-lg font-semibold text-slate-900">Carica la pratica Open Fiber (PDF)</div>
          <div className="text-sm text-slate-500 mt-1">Trascina qui il file o clicca per selezionarlo.</div>
        </div>
        <input ref={inputRef} type="file" accept="application/pdf" className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])} data-testid="upload-pdf-input" />
        <button onClick={() => inputRef.current?.click()} disabled={loading}
          className="btn-primary rounded-full px-5 py-2.5 text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-60"
          data-testid="upload-pdf-button">
          <FileText size={16} /> {loading ? "Analisi…" : "Seleziona PDF"}
        </button>
      </div>
    </div>
  );
}

// ---------- Private field helpers (inline edit for dati di lavoro) ----------
function PrivateFieldValue({ v, isTel, label, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(v);
  useEffect(() => setDraft(v), [v]);
  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input type={isTel ? "tel" : "text"} value={draft} autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { onEdit(draft); setEditing(false); } if (e.key === "Escape") setEditing(false); }}
          className="flex-1 rounded border border-brand-pink/50 px-2 py-1 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-pink" />
        <button onClick={() => { onEdit(draft); setEditing(false); }} className="text-emerald-600 text-xs font-bold px-1" title="Salva">✓</button>
        <button onClick={() => setEditing(false)} className="text-slate-400 text-xs font-bold px-1" title="Annulla">✕</button>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-1">
      {isTel ? (
        <a href={`tel:${v}`}
          onClick={(e) => { e.preventDefault(); navigator.clipboard.writeText(v); toast.success(`${label} copiato`); window.location.href = `tel:${v}`; }}
          className="flex-1 text-sm font-mono font-semibold text-brand-pink brand-pink hover:underline break-all select-all cursor-pointer">
          {v}
        </a>
      ) : (
        <div onClick={() => { navigator.clipboard.writeText(v); toast.success(`${label} copiato`); }}
          className="flex-1 text-sm font-mono font-semibold text-slate-900 break-all select-all cursor-pointer hover:bg-slate-50 rounded px-1 -mx-1">
          {v}
        </div>
      )}
      <button onClick={() => setEditing(true)} className="text-slate-300 hover:text-slate-700 shrink-0" title="Modifica"><Edit3 size={11} /></button>
    </div>
  );
}

function PrivateFieldEmpty({ placeholder, label, testId, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  if (!editing) {
    return (
      <button onClick={() => setEditing(true)}
        className="w-full text-left text-xs text-slate-400 italic hover:text-brand-pink brand-pink hover:bg-white rounded px-1 py-1 -mx-1 border border-dashed border-slate-200 hover:border-brand-pink"
        data-testid={testId}>
        + aggiungi {label.toLowerCase()}
      </button>
    );
  }
  return (
    <div className="flex items-center gap-1">
      <input type="text" value={draft} autoFocus placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && draft.trim()) { onSave(draft); setEditing(false); setDraft(""); } if (e.key === "Escape") { setEditing(false); setDraft(""); } }}
        className="flex-1 rounded border border-brand-pink/50 px-2 py-1 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-pink" />
      <button onClick={() => { if (draft.trim()) { onSave(draft); setEditing(false); setDraft(""); } }} className="text-emerald-600 text-xs font-bold px-1" title="Salva">✓</button>
      <button onClick={() => { setEditing(false); setDraft(""); }} className="text-slate-400 text-xs font-bold px-1" title="Annulla">✕</button>
    </div>
  );
}

// ---------- Photo Manager (with camera capture) ----------
// ---------- Assigned Serial Input (dropdown a tendina + barcode preview) ----------
function AssignedSerialInput({ value, onChange, tipoHint, placeholder, testId, noteId, onPhotoAttached, onPersist }) {
  const [assigned, setAssigned] = useState([]);
  const [showBarcode, setShowBarcode] = useState(false);
  const [imgUrl, setImgUrl] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [attaching, setAttaching] = useState(false);

  useEffect(() => {
    // Nessun filtro per tipo: mostriamo TUTTI i seriali assegnati alla squadra
    // (il magazzino può darti un CPEWIFI da usare in CPE, ONT o extra)
    axios.get(`${API}/inventory/my-assigned`)
      .then((r) => setAssigned(r.data || []))
      .catch(() => setAssigned([]));
  }, []);

  // Ordina: prima i seriali con tipo corrispondente all'hint, poi gli altri
  const sortedAssigned = useMemo(() => {
    if (!tipoHint) return assigned;
    const norm = (s) => (s || "").toString().toUpperCase();
    const hint = norm(tipoHint);
    return [...assigned].sort((a, b) => {
      const am = norm(a.tipo).includes(hint) ? 0 : 1;
      const bm = norm(b.tipo).includes(hint) ? 0 : 1;
      return am - bm;
    });
  }, [assigned, tipoHint]);

  useEffect(() => {
    let cancelled = false;
    if (value && showBarcode) {
      generateSerialImage(value, tipoHint || "").then((blob) => {
        if (cancelled) return;
        if (imgUrl) URL.revokeObjectURL(imgUrl);
        setImgUrl(URL.createObjectURL(blob));
      });
    } else {
      if (imgUrl) URL.revokeObjectURL(imgUrl);
      setImgUrl(null);
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, showBarcode]);

  const pick = async (serial) => {
    onChange(serial);
    setMenuOpen(false);
    if (!noteId || !serial) return;
    try {
      setAttaching(true);
      // 1) Persisti il campo sul server PRIMA di refetch (altrimenti il refetch sovrascriverebbe con il vecchio valore)
      if (onPersist) {
        try { await onPersist(serial); } catch (_) { /* silent */ }
      }
      // 2) Genera e allega la foto barcode
      try {
        const blob = await generateSerialImage(serial, tipoHint || "");
        const file = new File([blob], `barcode_${tipoHint || 'seriale'}_${serial}.png`, { type: "image/png" });
        const fd = new FormData();
        fd.append("files", file);
        await axios.post(`${API}/notes/${noteId}/photos`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        toast.success(`Barcode di ${serial} allegato`);
      } catch (_) { /* silent — user can still toggle manually */ }
      // 3) Segnala al parent di ricaricare la nota (ora il server ha il valore aggiornato)
      onPhotoAttached?.();
    } finally { setAttaching(false); }
  };

  return (
    <div>
      <div className="relative flex gap-1">
        <input type="text" value={value ?? ""} onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder || "Seriale…"}
          className="flex-1 mt-1 rounded-lg border border-slate-200 bg-white px-3 py-2 pr-2 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-pink"
          data-testid={testId} />
        <button type="button" onClick={() => setMenuOpen(!menuOpen)} disabled={!assigned.length}
          className="mt-1 rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs font-semibold hover:bg-slate-50 disabled:opacity-40 inline-flex items-center gap-1"
          title="Scegli dai seriali assegnati" data-testid={`${testId}-open-dropdown`}>
          <Users size={12} />
          <span className="hidden sm:inline">{assigned.length}</span>
          <ChevronDown size={12} />
        </button>
        <button type="button" onClick={() => setShowBarcode(!showBarcode)} disabled={!value}
          className={`mt-1 rounded-lg px-2 py-2 text-xs font-semibold disabled:opacity-30 ${showBarcode ? "bg-brand-pink brand-pink-bg text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
          title="Mostra barcode + QR" data-testid={`${testId}-toggle-barcode`}>
          <ScanLine size={12} />
        </button>
      </div>
      {menuOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
          <div className="relative z-50">
            <div className="absolute right-0 mt-1 w-full max-w-sm bg-white border border-slate-200 rounded-xl shadow-xl max-h-64 overflow-y-auto" data-testid={`${testId}-dropdown-menu`}>
              <div className="sticky top-0 bg-white border-b border-slate-100 px-3 py-2 flex items-center gap-2">
                <Users size={12} className="brand-pink" />
                <span className="text-xs font-semibold text-slate-700">Seriali assegnati alla squadra</span>
                <span className="ml-auto text-[10px] text-slate-400">{assigned.length}</span>
              </div>
              {sortedAssigned.length === 0 ? (
                <div className="p-4 text-xs text-slate-400 text-center italic">Nessun seriale assegnato</div>
              ) : (
                <div className="py-1">
                  {sortedAssigned.map((s) => {
                    const matchesHint = tipoHint && (s.tipo || "").toString().toUpperCase().includes(tipoHint.toString().toUpperCase());
                    return (
                      <button key={s.id} type="button" onClick={() => pick(s.serial)}
                        className={`w-full text-left px-3 py-2 text-sm font-mono hover:bg-pink-50 flex items-center gap-2 ${value === s.serial ? "bg-pink-100" : ""}`}
                        data-testid={`${testId}-option-${s.serial}`}>
                        <span className="flex-1 truncate">{s.serial}</span>
                        {s.tipo && <span className={`text-[10px] font-bold rounded-full px-1.5 py-0.5 ${matchesHint ? "text-emerald-800 bg-emerald-100" : "text-pink-800 bg-pink-100"}`}>{s.tipo}</span>}
                        {s.assigned_to_name && <span className="text-[10px] text-slate-500 truncate max-w-[80px]">{s.assigned_to_name}</span>}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}
      {assigned.length > 0 && !menuOpen && (
        <div className="text-[10px] text-slate-400 mt-0.5">📦 {assigned.length} disponibili — apri il menù{attaching ? " · allego barcode…" : ""}</div>
      )}
      {showBarcode && imgUrl && (
        <div className="mt-2 rounded-lg border border-pink-200 bg-white p-2" data-testid={`${testId}-barcode-preview`}>
          <img src={imgUrl} alt={value} className="w-full max-w-xs mx-auto cursor-zoom-in"
            onClick={() => window.open(imgUrl, "_blank")} />
          <div className="text-[10px] text-center text-slate-500 mt-1">Tap sull'immagine per ingrandire</div>
        </div>
      )}
    </div>
  );
}


function PhotoManager({ note, onChanged }) {
  const [uploading, setUploading] = useState(false);
  const [lightbox, setLightbox] = useState(null); // photo object
  const galleryRef = useRef(null);
  const cameraRef = useRef(null);

  const upload = async (files) => {
    if (!files || !files.length) return;
    setUploading(true);
    try {
      const fd = new FormData();
      Array.from(files).forEach((f) => fd.append("files", f));
      await axios.post(`${API}/notes/${note.id}/photos`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Foto caricate");
      onChanged?.();
    } catch (e) { toast.error(errorText(e)); }
    finally { setUploading(false); if (galleryRef.current) galleryRef.current.value = ""; if (cameraRef.current) cameraRef.current.value = ""; }
  };

  const removePhoto = async (pid) => {
    try { await axios.delete(`${API}/notes/${note.id}/photos/${pid}`); toast.success("Foto rimossa"); onChanged?.(); }
    catch (e) { toast.error(errorText(e)); }
  };

  return (
    <div data-testid={`photo-manager-${note.wr}`}>
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="text-sm font-semibold text-slate-800 flex items-center gap-2">
          <ImageIcon size={16} className="brand-pink" /> Foto ({note.photos?.length || 0})
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden"
            onChange={(e) => upload(e.target.files)} data-testid={`photo-camera-${note.wr}`} />
          <input ref={galleryRef} type="file" accept="image/*" multiple className="hidden"
            onChange={(e) => upload(e.target.files)} data-testid={`photo-gallery-${note.wr}`} />
          <button onClick={() => cameraRef.current?.click()} disabled={uploading}
            className="text-xs font-semibold bg-slate-900 text-white rounded-full px-3 py-1.5 inline-flex items-center gap-1 hover:bg-slate-800 disabled:opacity-60"
            data-testid={`photo-camera-button-${note.wr}`}>
            {uploading ? <Loader2 className="animate-spin" size={12} /> : <Camera size={12} />} Scatta foto
          </button>
          <button onClick={() => galleryRef.current?.click()} disabled={uploading}
            className="text-xs font-semibold bg-slate-100 text-slate-900 rounded-full px-3 py-1.5 inline-flex items-center gap-1 hover:bg-slate-200 disabled:opacity-60"
            data-testid={`photo-gallery-button-${note.wr}`}>
            <ImageIcon size={12} /> Galleria
          </button>
        </div>
      </div>
      {note.photos?.length > 0 ? (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {note.photos.map((p) => (
            <div key={p.id} className="relative group">
              <img src={`${API}/files?path=${encodeURIComponent(p.storage_path)}`} alt={p.filename}
                onClick={() => setLightbox(p)}
                className="photo-thumb w-full cursor-zoom-in" loading="lazy"
                data-testid={`photo-thumb-${p.id}`} />
              <button onClick={() => removePhoto(p.id)}
                className="absolute top-1 right-1 rounded-full bg-black/70 text-white p-1 opacity-0 group-hover:opacity-100 transition"
                data-testid={`photo-delete-${p.id}`}>
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg p-3 text-center">
          Nessuna foto — usa "Scatta foto" per usare la fotocamera o "Galleria" per selezionare
        </div>
      )}
      {lightbox && (
        <div className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4" onClick={() => setLightbox(null)} data-testid="photo-lightbox">
          <button onClick={(e) => { e.stopPropagation(); setLightbox(null); }} className="absolute top-4 right-4 rounded-full bg-white/10 text-white p-2 hover:bg-white/20" data-testid="close-lightbox"><X size={20} /></button>
          <a href={`${API}/files?path=${encodeURIComponent(lightbox.storage_path)}`} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="absolute bottom-4 right-4 rounded-full bg-white/10 text-white p-2 hover:bg-white/20" title="Apri originale">
            <Download size={20} />
          </a>
          <img src={`${API}/files?path=${encodeURIComponent(lightbox.storage_path)}`} alt={lightbox.filename}
            className="max-w-full max-h-full object-contain" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

// ---------- Note Card ----------
function NoteCard({ note, onChanged, defaultOpen, selected, onToggleSelect, onOpenScanner }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(note);
  const [saving, setSaving] = useState(false);
  const [noteDraft, setNoteDraft] = useState(note.note_text || composeNote(note));
  const [noteDirty, setNoteDirty] = useState(false);
  const [sending, setSending] = useState(false);
  const [lastField, setLastField] = useState(null); // "cpe" | "ont_sfp"
  const { recipients } = useRecipients();

  useEffect(() => {
    setForm(note);
    if (!noteDirty) setNoteDraft(note.note_text || composeNote(note));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note]);

  useEffect(() => {
    if (edit && !noteDirty && !note.note_text_manual) setNoteDraft(composeNote(form));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, edit]);

  const noteText = noteDraft;

  const copy = async () => {
    try { await navigator.clipboard.writeText(noteText); toast.success("Nota copiata negli appunti!"); }
    catch { toast.error("Copia non riuscita"); }
  };

  const sendGmail = async () => {
    const subject = `WR: ${note.wr}`;
    const to = (recipients || []).join(",");
    const ua = navigator.userAgent || "";
    const isMobile = /Android|iPhone|iPad|iPod/i.test(ua);
    setSending(true);
    try {
      // Sempre copia i destinatari negli appunti
      try { await navigator.clipboard.writeText((recipients || []).join(", ")); } catch (_) {}

      // Raccogli i file (PDF + foto)
      const files = [];
      try {
        if (note.pdf_storage_path) {
          const r = await fetch(`${API}/files?path=${encodeURIComponent(note.pdf_storage_path)}`);
          if (r.ok) { const b = await r.blob(); files.push(new File([b], note.pdf_filename || `pratica_WR_${note.wr}.pdf`, { type: "application/pdf" })); }
        }
        for (const p of note.photos || []) {
          const r = await fetch(`${API}/files?path=${encodeURIComponent(p.storage_path)}`);
          if (r.ok) { const b = await r.blob(); files.push(new File([b], p.filename || `foto_${p.id}.jpg`, { type: p.content_type || "image/jpeg" })); }
        }
      } catch (fe) { console.warn("fetch attachments failed", fe); }

      // Su mobile con file: Web Share (share sheet → l'utente sceglie l'app Gmail con foto già allegate)
      if (isMobile && files.length && navigator.canShare) {
        const shareData = { title: subject, text: noteText, files };
        try {
          if (navigator.canShare(shareData)) {
            await navigator.share(shareData);
            toast.success("Condivisione aperta — scegli Gmail. Destinatari negli appunti: incollali nel campo A:");
            setSending(false); return;
          }
        } catch (err) {
          if (err && err.name === "AbortError") { setSending(false); return; }
          console.warn("Web Share failed", err);
        }
      }

      // Mobile senza file (o Web Share non disponibile): mailto: apre l'app Gmail nativa con destinatari, oggetto, corpo
      if (isMobile) {
        window.location.href = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(noteText)}`;
        toast.message("Apertura Gmail…" + (files.length ? " Aggiungi manualmente le foto dopo." : ""));
        setSending(false); return;
      }

      // Desktop: Gmail Web
      const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1&tf=1&to=${encodeURIComponent(to)}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(noteText)}`;
      const a = document.createElement("a"); a.href = gmailUrl; a.target = "_blank"; a.rel = "noopener noreferrer";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      toast.message("Gmail aperto — allega manualmente PDF e foto");
    } finally { setSending(false); }
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        cliente: form.cliente, olo: form.olo, splitter: form.splitter,
        via: form.via, n_porta_perm: form.n_porta_perm, porta_pte: form.porta_pte,
        cpe: form.cpe, ont_sfp: form.ont_sfp, indirizzo: form.indirizzo,
        pte_est: form.pte_est ?? "PTE-EST",
        ts: form.ts ?? "TS", tc: form.tc ?? "TC", d: form.d ?? "D", a: form.a ?? "A",
        mono: form.mono ?? "MONO", internal: form.internal ?? "INT",
        mono_type: form.mono_type ?? "",
        materials: form.materials ?? [],
        phone_client: form.phone_client ?? "",
        apparato_password: form.apparato_password ?? "",
        id_servizio: form.id_servizio ?? "",
        id_risorsa: form.id_risorsa ?? "",
        note_date: form.note_date || note.note_date || "",
      };
      if (noteDirty) { payload.note_text = noteDraft; payload.note_text_manual = true; }
      else payload.note_text_manual = false;
      await axios.patch(`${API}/notes/${note.id}`, payload);
      toast.success("Nota salvata"); setNoteDirty(false); setEdit(false); onChanged?.();
    } catch (e) { toast.error(errorText(e)); }
    finally { setSaving(false); }
  };

  const regenerate = async () => {
    try { const r = await axios.post(`${API}/notes/${note.id}/regenerate`); setNoteDraft(r.data.note_text); setNoteDirty(false); toast.success("Nota rigenerata"); onChanged?.(); }
    catch (e) { toast.error(errorText(e)); }
  };

  const del = async () => {
    if (!window.confirm("Eliminare questa nota?")) return;
    try { await axios.delete(`${API}/notes/${note.id}`); toast.success("Nota eliminata"); onChanged?.(); }
    catch (e) { toast.error(errorText(e)); }
  };

  const applyScan = async (value, target, snapshot) => {
    setForm((f) => ({ ...f, [target]: value }));
    setEdit(true);
    toast.success(`Codice inserito in ${target === "cpe" ? "CPE" : "ONT/SFP"}`);
    if (snapshot) {
      try {
        const fd = new FormData();
        fd.append("files", snapshot);
        await axios.post(`${API}/notes/${note.id}/photos`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        toast.message("Foto del codice aggiunta alla nota");
        onChanged?.();
      } catch (_) { /* silent */ }
    }
  };

  const syncNote = async () => {
    if (!note.cpe && !note.ont_sfp) { toast.error("Nessun seriale CPE o ONT da sincronizzare"); return; }
    try { const r = await axios.post(`${API}/notes/${note.id}/sync`); toast.success(`Sincronizzati ${r.data.synced} seriale/i con il magazzino`); onChanged?.(); }
    catch (e) { toast.error(errorText(e)); }
  };

  const setStatus = async (newStatus) => {
    let reason = note.suspend_reason || "";
    if (newStatus === "sospeso") {
      reason = window.prompt("Motivo della sospensione:", reason || "");
      if (reason === null) return;
    } else {
      reason = "";
    }
    try {
      await axios.patch(`${API}/notes/${note.id}`, { note_type: newStatus, status: newStatus, suspend_reason: reason });
      const labels = { espletato: "Nota espletata", sospeso: "Nota sospesa (esclusa dalla media)", guasto: "Nota marcata come guasto", migrazione: "Nota marcata come migrazione" };
      toast.success(labels[newStatus] || "Stato aggiornato");
      if (newStatus === "espletato" && (note.cpe || note.ont_sfp)) {
        try {
          const r = await axios.post(`${API}/notes/${note.id}/sync`);
          if (r.data?.synced) toast.success(`Sincronizzati automaticamente ${r.data.synced} seriale/i col magazzino`);
        } catch (_) { toast.message("Sync magazzino non riuscito — usa il tasto Sincronizza magazzino"); }
      }
      onChanged?.();
    } catch (e) { toast.error(errorText(e)); }
  };

  const undoEspletato = async () => {
    try {
      await axios.patch(`${API}/notes/${note.id}`, { note_type: "limbo", status: "limbo" });
      try {
        const r = await axios.post(`${API}/notes/${note.id}/unsync`);
        if (r.data?.unsynced) toast.message(`${r.data.unsynced} seriale/i ripristinati in magazzino`);
      } catch (_) {}
      toast.success("Espletato annullato — nota tornata normale");
      onChanged?.();
    } catch (e) { toast.error(errorText(e)); }
  };

  const currentType = note.note_type || note.status || "limbo";
  const isSuspended = currentType === "sospeso";
  const isFault = currentType === "guasto";
  const isMigration = currentType === "migrazione";
  const isDone = currentType === "espletato";

  const sendSuspendMail = () => {
    const to = window.prompt("Email destinatario per nota sospesa:", "");
    if (!to) return;
    const subject = `Nota sospesa - WR ${note.wr} - OLO ${note.olo || ''}`;
    const body = `Codice OLO: ${note.olo || ''}\nCodice WR: ${note.wr}\nMotivo sospensione: ${note.suspend_reason || ''}\n`;
    window.location.href = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

  return (
    <div className={`bg-white border rounded-2xl card-shadow overflow-hidden stagger-in ${selected ? "border-brand-pink ring-1 ring-brand-pink/40" : isSuspended ? "border-amber-200 bg-amber-50/30" : isFault ? "border-red-200 bg-red-50/30" : isMigration ? "border-indigo-200 bg-indigo-50/30" : isDone ? "border-emerald-200" : "border-slate-200"}`}>
      <div className="w-full flex items-center gap-3 px-4 sm:px-5 py-4 hover:bg-slate-50 transition">
        <input type="checkbox" checked={!!selected} onChange={() => onToggleSelect?.(note.id)}
          onClick={(e) => e.stopPropagation()} className="h-4 w-4 rounded border-slate-300 accent-pink-600 cursor-pointer"
          data-testid={`select-note-${note.wr}`} />
        <button onClick={() => setOpen(!open)} className="flex-1 text-left flex items-center gap-3 min-w-0" data-testid={`note-toggle-${note.wr}`}>
          <div className="wr-badge rounded-full px-3 py-1 text-xs sm:text-sm">WR {note.wr}</div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-slate-900 truncate">
              {note.cliente || <span className="text-slate-400 italic">senza cliente</span>}
              {isSuspended && <span className="ml-2 text-[10px] font-bold text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">SOSPESA</span>}
              {isFault && <span className="ml-2 text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded">GUASTO</span>}
              {isMigration && <span className="ml-2 text-[10px] font-bold text-indigo-700 bg-indigo-100 px-1.5 py-0.5 rounded">MIGRAZIONE</span>}
              {isDone && <span className="ml-2 text-[10px] font-bold text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">ESPLETATA</span>}
              {note.synced && <span className="ml-2 text-[10px] font-bold text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">SYNC ✓</span>}
              {(note.shared_with?.length > 0) && <span className="ml-2 text-[10px] font-bold text-pink-700 bg-pink-100 px-1.5 py-0.5 rounded" title="Condivisa con la squadra">👥</span>}
            </div>
            <div className="text-xs text-slate-500 truncate">{note.olo || "—"} • {note.indirizzo || note.via || "—"}</div>
          </div>
          <div className="hidden sm:flex items-center gap-1 text-xs text-slate-500">
            {note.photos?.length ? <span className="inline-flex items-center gap-1"><ImageIcon size={12} /> {note.photos.length}</span> : null}
          </div>
          {open ? <ChevronUp size={18} className="text-slate-400" /> : <ChevronDown size={18} className="text-slate-400" />}
        </button>
      </div>

      {open && (
        <div className="px-4 sm:px-5 pb-5 border-t border-slate-100">
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <div className="inline-flex bg-slate-100 rounded-full p-1 flex-wrap" data-testid={`status-group-${note.wr}`}>
              <button onClick={() => setStatus("espletato")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold inline-flex items-center gap-1.5 transition ${isDone ? "bg-emerald-500 text-white shadow" : "text-emerald-700 hover:bg-emerald-50"}`}
                data-testid={`status-espletato-${note.wr}`}>
                <CheckCircle2 size={14} /> Espletato
              </button>
              <button onClick={() => setStatus("sospeso")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold inline-flex items-center gap-1.5 transition ${isSuspended ? "bg-amber-500 text-white shadow" : "text-amber-700 hover:bg-amber-50"}`}
                data-testid={`status-sospeso-${note.wr}`}>
                <PauseCircle size={14} /> Sospeso{isSuspended && note.suspend_reason ? ` · "${note.suspend_reason.substring(0, 18)}${note.suspend_reason.length > 18 ? '…' : ''}"` : ""}
              </button>
              <button onClick={() => setStatus("guasto")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold inline-flex items-center gap-1.5 transition ${isFault ? "bg-red-500 text-white shadow" : "text-red-700 hover:bg-red-50"}`}
                data-testid={`status-guasto-${note.wr}`}>
                <Zap size={14} /> Guasto
              </button>
              <button onClick={() => setStatus("migrazione")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold inline-flex items-center gap-1.5 transition ${isMigration ? "bg-indigo-500 text-white shadow" : "text-indigo-700 hover:bg-indigo-50"}`}
                data-testid={`status-migrazione-${note.wr}`}>
                <RefreshCw size={14} /> Migrazione
              </button>
            </div>
            {isDone && (
              <button onClick={undoEspletato} className="rounded-full px-3 py-2 text-xs font-semibold bg-amber-100 text-amber-800 hover:bg-amber-200 inline-flex items-center gap-2" data-testid={`undo-espletato-${note.wr}`}>
                <RotateCcw size={14} /> Annulla espletato
              </button>
            )}
            {isSuspended && (
              <button onClick={sendSuspendMail} className="rounded-full px-3 py-2 text-xs font-semibold bg-amber-100 text-amber-800 hover:bg-amber-200 inline-flex items-center gap-2" data-testid={`suspend-mail-${note.wr}`}>
                <Mail size={14} /> Mail sospensione
              </button>
            )}
            <button onClick={copy} className="rounded-full px-3 py-2 text-xs font-semibold bg-slate-900 text-white inline-flex items-center gap-2 hover:bg-slate-800" data-testid={`copy-note-button-${note.wr}`}>
              <Copy size={14} /> Copia nota
            </button>
            <button onClick={sendGmail} disabled={sending} className="btn-primary rounded-full px-3 py-2 text-xs font-semibold inline-flex items-center gap-2 disabled:opacity-60" data-testid={`send-gmail-button-${note.wr}`}>
              {sending ? <Loader2 className="animate-spin" size={14} /> : <Mail size={14} />} Invia tramite Gmail
            </button>
            <button onClick={syncNote} className="rounded-full px-3 py-2 text-xs font-semibold bg-emerald-100 text-emerald-800 hover:bg-emerald-200 inline-flex items-center gap-2" data-testid={`sync-note-${note.wr}`}>
              <RefreshCw size={14} /> Sincronizza magazzino
            </button>
            {note.pdf_storage_path ? (
              <a href={`${API}/files?path=${encodeURIComponent(note.pdf_storage_path)}`} target="_blank" rel="noopener noreferrer"
                className="rounded-full px-3 py-2 text-xs font-semibold bg-slate-100 text-slate-800 inline-flex items-center gap-2 hover:bg-slate-200">
                <FileText size={14} /> Apri PDF
              </a>
            ) : null}
            <button onClick={() => setEdit(!edit)} className="rounded-full px-3 py-2 text-xs font-semibold bg-slate-100 text-slate-800 inline-flex items-center gap-2 hover:bg-slate-200" data-testid={`edit-toggle-${note.wr}`}>
              {edit ? "Nascondi campi" : "Modifica campi"}
            </button>
            <button onClick={del} className="rounded-full px-3 py-2 text-xs font-semibold text-red-600 bg-red-50 inline-flex items-center gap-2 hover:bg-red-100 ml-auto" data-testid={`delete-note-${note.wr}`}>
              <Trash2 size={14} /> Elimina
            </button>
          </div>

          <div className="mt-2 text-[11px] text-slate-500 leading-relaxed">
            <strong>Suggerimento:</strong> "Espletato" sincronizza automaticamente i seriali (CPE/ONT) col magazzino. "Scatta foto" apre la fotocamera per allegare foto alla nota.
          </div>

          {/* Dati privati SEMPRE visibili e completamente leggibili (non finiscono nella nota) */}
          {/* Dati di lavoro — SEMPRE visibili, con editing inline per campi mancanti (non finiscono nella nota) */}
          <div className="mt-3 rounded-xl bg-slate-50 border border-slate-200 p-3" data-testid={`private-data-${note.wr}`}>
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2 flex items-center gap-1">
              🔒 Dati di lavoro (non nella nota) — tap sul valore per copiare, sul "+" per aggiungere
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                { k: "phone_client", label: "Telefono cliente", isTel: true, ph: "es. 328 1234567" },
                { k: "id_servizio", label: "ID SERVIZIO", ph: "AAA0001234" },
                { k: "id_risorsa", label: "ID RISORSA", ph: "es. 55 7528 6472…" },
                { k: "apparato_password", label: "Password", ph: "password apparato" },
              ].map((f) => {
                const v = (form[f.k] ?? note[f.k] ?? "").toString();
                const has = v.trim() !== "";
                const saveField = async (newVal) => {
                  const clean = (newVal ?? "").trim();
                  setForm({ ...form, [f.k]: clean });
                  try {
                    await axios.patch(`${API}/notes/${note.id}`, { [f.k]: clean });
                    toast.success(`${f.label} salvato`);
                    onChanged?.();
                  } catch (e) { toast.error(errorText(e)); }
                };
                return (
                  <div key={f.k} className="bg-white rounded-lg border border-slate-200 px-3 py-2" data-testid={`private-${f.k}-${note.wr}`}>
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">{f.label}</div>
                      {has ? (
                        <button onClick={() => { navigator.clipboard.writeText(v); toast.success(`${f.label} copiato`); }}
                          className="text-slate-400 hover:text-brand-pink brand-pink shrink-0 inline-flex items-center gap-1 text-[10px] font-semibold"
                          data-testid={`copy-${f.k}-${note.wr}`} title="Copia">
                          <Copy size={11} /> Copia
                        </button>
                      ) : null}
                    </div>
                    {has ? (
                      <PrivateFieldValue v={v} isTel={f.isTel} label={f.label} onEdit={(newV) => saveField(newV)} />
                    ) : (
                      <PrivateFieldEmpty placeholder={f.ph} label={f.label} testId={`add-${f.k}-${note.wr}`} onSave={saveField} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {edit && (
            <div className="mt-4 space-y-4" data-testid={`edit-form-${note.wr}`}>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <label className="text-xs font-medium text-slate-600">
                  Data lavoro
                  <input type="date" value={form.note_date || ""}
                    onChange={(e) => { setForm({ ...form, note_date: e.target.value }); setNoteDirty(false); }}
                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-pink"
                    data-testid={`field-note_date-${note.wr}`} />
                </label>
                <label className="text-xs font-medium text-slate-600 sm:col-span-2">
                  Tipo installazione
                  <select value={form.mono_type || ""}
                    onChange={(e) => { setForm({ ...form, mono_type: e.target.value }); setNoteDirty(false); }}
                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-pink"
                    data-testid={`field-mono_type-${note.wr}`}>
                    <option value="">— (usa MONO/INT sotto)</option>
                    <option value="MONO INT">MONO INT</option>
                    <option value="MONO EST">MONO EST</option>
                    <option value="SBR">SBR</option>
                    <option value="VRT STR SBR">VRT STR SBR</option>
                  </select>
                </label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { k: "cliente", label: "Cliente (D)" }, { k: "olo", label: "Descrizione OLO" },
                  { k: "splitter", label: "Porta uscita splitter PFS (BA_)" }, { k: "via", label: "VIA (dopo A662_)" },
                  { k: "pte_est", label: "PTE-EST" }, { k: "n_porta_perm", label: "PFS (N. porta perm.)" },
                  { k: "porta_pte", label: "PTE (Porta PTE)" },
                  { k: "ts", label: "TS" }, { k: "tc", label: "TC" }, { k: "d", label: "D" },
                  { k: "a", label: "A" },
                  ...((!form.mono_type) ? [{ k: "mono", label: "MONO" }, { k: "internal", label: "INT" }] : []),
                ].map((f) => (
                  <label key={f.k} className="text-xs font-medium text-slate-600">
                    {f.label}
                    <input type="text" value={form[f.k] ?? ""}
                      onChange={(e) => { setForm({ ...form, [f.k]: e.target.value }); setNoteDirty(false); }}
                      className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-pink focus:border-transparent"
                      data-testid={`field-${f.k}-${note.wr}`} />
                  </label>
                ))}
                <label className="text-xs font-medium text-slate-600 sm:col-span-2" onFocus={() => setLastField("cpe")}>
                  CPE (seriale modem)
                  <AssignedSerialInput value={form.cpe} tipoHint="CPE" noteId={note.id} onPhotoAttached={onChanged}
                    onPersist={async (v) => { await axios.patch(`${API}/notes/${note.id}`, { cpe: v }); }}
                    onChange={(v) => { setForm({ ...form, cpe: v }); setNoteDirty(false); setLastField("cpe"); }}
                    placeholder="Seleziona da assegnati o digita…" testId={`field-cpe-${note.wr}`} />
                </label>
                <label className="text-xs font-medium text-slate-600 sm:col-span-2" onFocus={() => setLastField("ont_sfp")}>
                  ONT / SFP
                  <AssignedSerialInput value={form.ont_sfp} tipoHint="ONT" noteId={note.id} onPhotoAttached={onChanged}
                    onPersist={async (v) => { await axios.patch(`${API}/notes/${note.id}`, { ont_sfp: v }); }}
                    onChange={(v) => { setForm({ ...form, ont_sfp: v }); setNoteDirty(false); setLastField("ont_sfp"); }}
                    placeholder="Seleziona da assegnati o digita…" testId={`field-ont_sfp-${note.wr}`} />
                </label>
              </div>

              {/* Materiali extra (EXT, ecc.) */}
              <div className="border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-semibold text-slate-700">Altri materiali</div>
                  <button type="button" onClick={() => { const m = form.materials || []; setForm({ ...form, materials: [...m, { tipo: "EXT", serial: "" }] }); setNoteDirty(false); }}
                    className="text-[11px] font-semibold text-brand-pink brand-pink hover:underline inline-flex items-center gap-1" data-testid={`add-material-${note.wr}`}>
                    + Aggiungi materiale
                  </button>
                </div>
                {(form.materials || []).length === 0 && <div className="text-[11px] text-slate-400 italic">Nessun materiale extra</div>}
                <div className="space-y-2">
                  {(form.materials || []).map((m, i) => (
                    <div key={i} className="grid grid-cols-1 sm:grid-cols-[7rem_1fr_auto] gap-2 items-start" data-testid={`material-row-${note.wr}-${i}`}>
                      <input type="text" placeholder="Tipo (es. EXT)" value={m.tipo || ""}
                        onChange={(e) => { const arr = [...(form.materials || [])]; arr[i] = { ...arr[i], tipo: e.target.value }; setForm({ ...form, materials: arr }); setNoteDirty(false); }}
                        className="rounded-lg border border-slate-200 px-2 py-2 text-xs font-semibold" />
                      <AssignedSerialInput value={m.serial} tipoHint={m.tipo} noteId={note.id} onPhotoAttached={onChanged}
                        onPersist={async (v) => {
                          const arr = [...(form.materials || [])];
                          arr[i] = { ...arr[i], serial: v };
                          await axios.patch(`${API}/notes/${note.id}`, { materials: arr });
                        }}
                        onChange={(v) => { const arr = [...(form.materials || [])]; arr[i] = { ...arr[i], serial: v }; setForm({ ...form, materials: arr }); setNoteDirty(false); }}
                        placeholder="Seriale" testId={`material-serial-${note.wr}-${i}`} />
                      <button type="button" onClick={() => { const arr = [...(form.materials || [])]; arr.splice(i, 1); setForm({ ...form, materials: arr }); setNoteDirty(false); }}
                        className="text-red-500 hover:bg-red-50 rounded-full p-1 self-center" data-testid={`remove-material-${note.wr}-${i}`}><X size={14} /></button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Dati di lavoro privati - NON entrano nella nota */}
              <details className="border-t border-slate-100 pt-3">
                <summary className="text-xs font-semibold text-slate-700 cursor-pointer">🔒 Dati di lavoro (non finiscono nella nota copiata)</summary>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
                  {[
                    { k: "phone_client", label: "Telefono cliente" },
                    { k: "apparato_password", label: "Password apparato" },
                    { k: "id_servizio", label: "ID SERVIZIO (AAA…)" },
                    { k: "id_risorsa", label: "ID RISORSA" },
                  ].map((f) => (
                    <label key={f.k} className="text-xs font-medium text-slate-600">
                      {f.label}
                      <input type="text" value={form[f.k] ?? ""}
                        onChange={(e) => { setForm({ ...form, [f.k]: e.target.value }); setNoteDirty(false); }}
                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-pink focus:border-transparent"
                        data-testid={`field-${f.k}-${note.wr}`} />
                    </label>
                  ))}
                </div>
              </details>
            </div>
          )}

          <div className="mt-4">
            <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
              <div className="text-xs font-medium text-slate-500">
                Nota (modificabile){noteDirty ? <span className="ml-2 brand-pink">• modificata manualmente</span> : null}
              </div>
              <button onClick={regenerate} className="text-[11px] font-semibold text-slate-600 hover:text-slate-900 inline-flex items-center gap-1" data-testid={`regenerate-note-${note.wr}`}>
                <RotateCcw size={12} /> Rigenera dai campi
              </button>
            </div>
            <textarea value={noteText} onChange={(e) => { setNoteDraft(e.target.value); setNoteDirty(true); }}
              rows={8} spellCheck={false}
              className="note-block w-full outline-none resize-y focus:ring-2 focus:ring-brand-pink/60"
              data-testid={`note-preview-${note.wr}`} />
            <div className="mt-2 flex flex-wrap gap-2">
              <button onClick={save} disabled={saving} className="btn-primary rounded-full px-4 py-2 text-xs font-semibold inline-flex items-center gap-2 disabled:opacity-60" data-testid={`save-note-${note.wr}`}>
                {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} Salva nota
              </button>
            </div>
          </div>

          <div className="mt-4">
            <PhotoManager note={note} onChanged={onChanged} />
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Stats Panel ----------
const DAILY_TARGET = 4;

const monthKeyOf = (iso) => localDateKey(iso).slice(0, 7);
const monthLabel = (mk) => {
  const [y, m] = mk.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleString("it-IT", { month: "long", year: "numeric" });
};

function localDateKey(iso) {
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  } catch { return "unknown"; }
}
function humanDate(key) {
  const [y, m, d] = key.split("-");
  const dt = new Date(Number(y), Number(m) - 1, Number(d));
  const days = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];
  return `${days[dt.getDay()]} ${d}/${m}`;
}
function downloadFile(name, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function StatsPanel({ notes, onReset }) {
  const now = new Date();
  const todayIso = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().slice(0, 10);
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const [from, setFrom] = useState(monthStart);
  const [to, setTo] = useState(todayIso);
  const [stats, setStats] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/notes/stats`, { params: { from, to } });
      setStats(r.data);
    } catch (_) { /* silent */ }
  }, [from, to]);

  useEffect(() => { fetchStats(); }, [fetchStats, notes.length]);

  const totals = stats?.totals || { limbo: 0, espletato: 0, sospeso: 0, guasto: 0, migrazione: 0 };
  const avgCompleted = stats?.avg_completed_per_working_day || 0;
  const avgFaults = stats?.avg_faults_per_working_day || 0;
  const workingDays = stats?.working_days_count || 0;
  const daily = stats?.daily || [];
  const maxDaily = Math.max(1, ...daily.map((d) => d.espletato + d.migrazione + d.sospeso + d.guasto));
  const todayEntry = daily.find((d) => d.date === todayIso);
  const todayDone = (todayEntry?.espletato || 0) + (todayEntry?.migrazione || 0);

  const exportAll = () => {
    const payload = { exported_at: new Date().toISOString(), from, to, stats, notes };
    downloadFile(`note-openfiber-${to}.json`, JSON.stringify(payload, null, 2), "application/json");
    toast.success("Esportazione completa avviata");
  };
  const exportOlo = () => {
    const lines = notes.map((n) => n.olo).filter(Boolean);
    downloadFile(`codici-olo-${to}.txt`, lines.join("\n"), "text/plain;charset=utf-8");
    toast.success("Esportazione OLO avviata");
  };
  const setThisMonth = () => { setFrom(monthStart); setTo(todayIso); };
  const setMidToMid = () => {
    // 15 del mese scorso → 15 di questo mese
    const t = new Date();
    const midCur = new Date(t.getFullYear(), t.getMonth(), 15);
    const midPrev = new Date(t.getFullYear(), t.getMonth() - 1, 15);
    setFrom(midPrev.toISOString().slice(0, 10));
    setTo(midCur.toISOString().slice(0, 10));
  };

  return (
    <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5" data-testid="stats-panel">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Report</div>
          <h2 className="text-lg sm:text-xl font-display font-bold text-slate-900 mt-0.5">Resoconto</h2>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs" data-testid="stats-from" />
          <span className="text-xs text-slate-400">→</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs" data-testid="stats-to" />
          <button onClick={setThisMonth} className="rounded-full px-2.5 py-1 text-[11px] font-semibold bg-slate-100 hover:bg-slate-200" data-testid="preset-month">Mese</button>
          <button onClick={setMidToMid} className="rounded-full px-2.5 py-1 text-[11px] font-semibold bg-slate-100 hover:bg-slate-200" data-testid="preset-15-15">15→15</button>
          <button onClick={exportOlo} disabled={!notes.length} className="rounded-full px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-900 inline-flex items-center gap-1 disabled:opacity-40" data-testid="export-olo-btn">
            <FileText size={14} /> OLO
          </button>
          <button onClick={exportAll} disabled={!notes.length} className="rounded-full px-3 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white inline-flex items-center gap-1 disabled:opacity-40" data-testid="export-all-btn">
            <FileText size={14} /> JSON
          </button>
          <button onClick={onReset} disabled={!notes.length} className="rounded-full px-3 py-1.5 text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 inline-flex items-center gap-1 disabled:opacity-40" data-testid="reset-month-btn">
            <RotateCcw size={14} /> Reset
          </button>
        </div>
      </div>

      {/* Top 4 counters replacing "totale note" */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
        <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-3" data-testid="stat-espletati">
          <div className="text-[11px] text-emerald-700 font-semibold uppercase tracking-wide">Impianti espletati</div>
          <div className="text-2xl font-display font-extrabold text-emerald-600 mt-0.5">{totals.espletato}</div>
        </div>
        <div className="rounded-xl bg-amber-50 border border-amber-100 p-3" data-testid="stat-sospesi">
          <div className="text-[11px] text-amber-700 font-semibold uppercase tracking-wide">Impianti sospesi</div>
          <div className="text-2xl font-display font-extrabold text-amber-600 mt-0.5">{totals.sospeso}</div>
        </div>
        <div className="rounded-xl bg-red-50 border border-red-100 p-3" data-testid="stat-guasti">
          <div className="text-[11px] text-red-700 font-semibold uppercase tracking-wide">Guasti eseguiti</div>
          <div className="text-2xl font-display font-extrabold text-red-600 mt-0.5">{totals.guasto}</div>
        </div>
        <div className="rounded-xl bg-indigo-50 border border-indigo-100 p-3" data-testid="stat-migrazioni">
          <div className="text-[11px] text-indigo-700 font-semibold uppercase tracking-wide">Migrazioni</div>
          <div className="text-2xl font-display font-extrabold text-indigo-600 mt-0.5">{totals.migrazione}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
        <div className="rounded-xl bg-slate-50 border border-slate-100 p-3" data-testid="stat-today">
          <div className="text-[11px] text-slate-500 font-semibold">Oggi (espl.+migr.)</div>
          <div className="text-2xl font-display font-extrabold text-slate-900 mt-0.5">{todayDone}</div>
        </div>
        <div className="rounded-xl bg-slate-50 border border-slate-100 p-3" data-testid="stat-daily-avg">
          <div className="text-[11px] text-slate-500 font-semibold">Media/giorno (escl. sabato)</div>
          <div className="text-2xl font-display font-extrabold text-slate-900 mt-0.5">{avgCompleted.toFixed(1)}</div>
          <div className="text-[10px] text-slate-500 mt-0.5">su {workingDays} giorni lavorati</div>
        </div>
        <div className="rounded-xl bg-slate-50 border border-slate-100 p-3" data-testid="stat-faults-avg">
          <div className="text-[11px] text-slate-500 font-semibold">Media guasti/giorno</div>
          <div className="text-2xl font-display font-extrabold text-red-500 mt-0.5">{avgFaults.toFixed(1)}</div>
          <div className="text-[10px] text-slate-500 mt-0.5">limbo: {totals.limbo}</div>
        </div>
      </div>

      {daily.length > 0 && (
        <div className="mt-5" data-testid="daily-chart">
          <div className="text-xs font-semibold text-slate-500 mb-2">Andamento giornaliero</div>
          <div className="flex items-end gap-[3px] h-24">
            {daily.map((d) => {
              const total = d.espletato + d.migrazione + d.sospeso + d.guasto;
              const h = Math.max(4, (total / maxDaily) * 96);
              const isToday = d.date === todayIso;
              return (
                <div key={d.date} title={`${d.date}: ${total} note${d.is_saturday ? ' (sabato escluso)' : ''}`}
                  className="flex-1 flex flex-col-reverse rounded overflow-hidden bg-slate-100 relative" style={{ height: 96, minWidth: 6 }}>
                  {total > 0 && (
                    <>
                      {d.espletato > 0 && <div className="w-full bg-emerald-500" style={{ height: `${(d.espletato / total) * h}px` }} />}
                      {d.migrazione > 0 && <div className="w-full bg-indigo-500" style={{ height: `${(d.migrazione / total) * h}px` }} />}
                      {d.sospeso > 0 && <div className="w-full bg-amber-400" style={{ height: `${(d.sospeso / total) * h}px` }} />}
                      {d.guasto > 0 && <div className="w-full bg-red-500" style={{ height: `${(d.guasto / total) * h}px` }} />}
                    </>
                  )}
                  {isToday && <div className="absolute inset-x-0 bottom-0 h-0.5 bg-slate-900" />}
                  {d.is_saturday && <div className="absolute inset-0 bg-slate-200/40 pointer-events-none" />}
                </div>
              );
            })}
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-slate-600">
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500"></span>espletati</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-indigo-500"></span>migrazioni</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400"></span>sospesi</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500"></span>guasti</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-300"></span>sabato (escluso)</span>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------- Team Picker (compagno di squadra giornaliero) ----------
function TeamPicker() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [partner, setPartner] = useState(null);
  const [partnerId, setPartnerId] = useState("");
  const [saving, setSaving] = useState(false);
  const isLeader = !!user?.is_team_leader;

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/team/today`);
      setPartner(r.data.partner);
      setPartnerId(r.data.partner?.id || "");
    } catch (_) {}
  }, []);

  useEffect(() => {
    (async () => {
      if (isLeader) {
        try { const r = await axios.get(`${API}/users/approved`); setUsers(r.data || []); } catch (_) {}
      }
      refresh();
    })();
  }, [refresh, isLeader]);

  const savePartner = async (uid) => {
    setSaving(true);
    try {
      await axios.post(`${API}/team/today`, { partner_user_id: uid || "" });
      toast.success(uid ? "Compagno di squadra impostato per oggi" : "Compagno rimosso");
      refresh();
    } catch (e) { toast.error(errorText(e)); }
    finally { setSaving(false); }
  };

  // Non-caposquadra: mostra solo lo stato in sola lettura
  if (!isLeader) {
    return (
      <div className="flex items-center gap-2" data-testid="team-picker-readonly">
        <Users size={14} className="text-slate-500" />
        {partner ? (
          <span className="text-[11px] font-semibold text-pink-800 bg-pink-50 border border-pink-200 rounded-full px-2 py-1" data-testid="team-partner-badge-readonly" title="Assegnato dal tuo caposquadra">
            👥 In squadra con {partner.name || partner.email}
          </span>
        ) : (
          <span className="text-[11px] font-medium text-slate-400 italic" title="Solo un caposquadra può creare la squadra">Nessuna squadra oggi</span>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2" data-testid="team-picker">
      <Users size={14} className="brand-pink" />
      <span className="text-[10px] font-bold text-pink-800 bg-pink-100 rounded-full px-1.5 py-0.5" title="Sei caposquadra: puoi scegliere il collega">⭐ CAPOSQUADRA</span>
      <select value={partnerId} onChange={(e) => { setPartnerId(e.target.value); savePartner(e.target.value); }}
        disabled={saving}
        className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-pink"
        data-testid="team-partner-select">
        <option value="">— Compagno di oggi —</option>
        {users.map((u) => <option key={u.id} value={u.id}>{u.name || u.email}</option>)}
      </select>
      {partner && <span className="text-[10px] font-bold text-pink-700 bg-pink-100 px-1.5 py-0.5 rounded" data-testid="team-partner-badge">👥 {partner.name || partner.email}</span>}
    </div>
  );
}

// ---------- Notifications Bell (polling every 15s) ----------
function NotificationsBell() {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const prevUnread = useRef(0);

  const fetchN = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/notifications`, { params: { limit: 30 } });
      setItems(r.data.items || []);
      const u = r.data.unread || 0;
      if (u > prevUnread.current) {
        try { if (navigator.vibrate) navigator.vibrate(50); } catch (_) {}
        const newest = (r.data.items || []).find((x) => !x.read);
        if (newest) toast.message("🔔 " + newest.message);
      }
      prevUnread.current = u;
      setUnread(u);
    } catch (_) { /* silent */ }
  }, []);

  useEffect(() => {
    fetchN();
    const t = setInterval(fetchN, 15000);
    return () => clearInterval(t);
  }, [fetchN]);

  const markRead = async (id) => {
    try { await axios.post(`${API}/notifications/${id}/read`); fetchN(); } catch (_) {}
  };
  const markAll = async () => {
    try { await axios.post(`${API}/notifications/read-all`); fetchN(); } catch (_) {}
  };

  return (
    <div className="relative" data-testid="notifications-bell-container">
      <button onClick={() => setOpen(!open)}
        className="btn-ghost relative text-xs font-semibold text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-full p-2"
        data-testid="notifications-bell">
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 bg-brand-pink text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] px-1 flex items-center justify-center brand-pink-bg" data-testid="notifications-badge">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white rounded-2xl border border-slate-200 shadow-xl z-50 max-h-[70vh] overflow-y-auto" data-testid="notifications-panel">
            <div className="sticky top-0 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-2">
              <Bell size={14} className="brand-pink" />
              <h3 className="text-sm font-semibold">Notifiche</h3>
              {unread > 0 && <button onClick={markAll} className="ml-auto text-[11px] font-semibold text-slate-600 hover:text-slate-900" data-testid="mark-all-read">Segna tutto letto</button>}
            </div>
            {items.length === 0 ? (
              <div className="p-6 text-center text-sm text-slate-400">Nessuna notifica</div>
            ) : (
              <div>
                {items.map((n) => (
                  <div key={n.id} onClick={() => !n.read && markRead(n.id)}
                    className={`px-4 py-3 border-b border-slate-100 last:border-0 cursor-pointer hover:bg-slate-50 ${!n.read ? "bg-pink-50/40" : ""}`}
                    data-testid={`notif-${n.id}`}>
                    <div className="flex items-start gap-2">
                      {!n.read && <span className="w-2 h-2 rounded-full bg-brand-pink brand-pink-bg mt-1.5 shrink-0" />}
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-slate-900">{n.message}</div>
                        {n.serials?.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {n.serials.map((s) => <span key={s} className="text-[10px] font-mono bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded">{s}</span>)}
                          </div>
                        )}
                        <div className="text-[10px] text-slate-400 mt-1">{new Date(n.created_at).toLocaleString("it-IT")}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ---------- Serial History Modal ----------
function SerialHistoryModal({ serialItem, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");  // all | returned
  useEffect(() => {
    (async () => {
      try { const r = await axios.get(`${API}/inventory/serials/${serialItem.id}/history`); setData(r.data); }
      catch (e) { toast.error(errorText(e)); }
      finally { setLoading(false); }
    })();
  }, [serialItem.id]);

  const isReturn = (e) => e.event_type === "unassigned" && e.extra?.reason === "returned_to_warehouse";

  const labelForEvent = (e) => {
    if (isReturn(e)) return { icon: <RotateCcw size={14} />, color: "bg-amber-100 text-amber-800", title: `Restituito da ${e.extra?.from_user_name || "tecnico"}` };
    switch (e.event_type) {
      case "created": return { icon: <Package size={14} />, color: "bg-emerald-100 text-emerald-800", title: e.extra?.auto_from_sync ? "Ingresso automatico (da sync nota)" : "Ingresso in magazzino" };
      case "assigned": return { icon: <UserCheck size={14} />, color: "bg-amber-100 text-amber-800", title: `Assegnato a ${e.extra?.to_user_name || "utente"}` };
      case "unassigned": return { icon: <UserX size={14} />, color: "bg-slate-100 text-slate-700", title: "Rimossa assegnazione" };
      case "downloaded": return { icon: <RefreshCw size={14} />, color: "bg-pink-100 text-pink-800", title: `Scaricato${e.note_wr ? ` su WR ${e.note_wr}` : ""}` };
      case "manual_update": return { icon: <Save size={14} />, color: "bg-slate-100 text-slate-700", title: "Aggiornamento manuale" };
      case "deleted": return { icon: <Trash2 size={14} />, color: "bg-red-100 text-red-800", title: "Eliminato dal magazzino" };
      default: return { icon: <History size={14} />, color: "bg-slate-100 text-slate-700", title: e.event_type };
    }
  };

  const events = (data?.events || []).filter((e) => filter === "all" || (filter === "returned" && isReturn(e)));
  const returnedCount = (data?.events || []).filter(isReturn).length;

  return (
    <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-start sm:items-center justify-center p-3 overflow-y-auto" onClick={onClose} data-testid="serial-history-modal">
      <div className="bg-white rounded-2xl max-w-lg w-full my-4 max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center gap-3 z-10">
          <History size={18} className="brand-pink" />
          <div className="min-w-0">
            <h2 className="text-base font-display font-bold">Storico seriale</h2>
            <div className="text-xs text-slate-500 font-mono truncate">{serialItem.serial}</div>
          </div>
          <button onClick={onClose} className="ml-auto btn-ghost rounded-full p-1.5 hover:bg-slate-100" data-testid="close-history"><X size={18} /></button>
        </div>
        <div className="p-5">
          <div className="flex gap-1 bg-slate-100 rounded-full p-1 mb-4 w-fit" data-testid="history-filter-tabs">
            <button onClick={() => setFilter("all")} className={`px-3 py-1 rounded-full text-xs font-semibold transition ${filter === "all" ? "bg-white text-slate-900 shadow" : "text-slate-500 hover:text-slate-800"}`} data-testid="history-filter-all">Tutti · {data?.events?.length || 0}</button>
            <button onClick={() => setFilter("returned")} className={`px-3 py-1 rounded-full text-xs font-semibold transition inline-flex items-center gap-1 ${filter === "returned" ? "bg-white text-amber-700 shadow" : "text-slate-500 hover:text-slate-800"}`} data-testid="history-filter-returned">
              <RotateCcw size={12} /> Restituzioni · {returnedCount}
            </button>
          </div>
          {loading ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm"><Loader2 className="animate-spin" size={16} /> Caricamento…</div>
          ) : !events.length ? (
            <div className="text-sm text-slate-400 text-center p-6">{filter === "returned" ? "Nessuna restituzione registrata" : "Nessun evento registrato"}</div>
          ) : (
            <ol className="relative border-l-2 border-slate-200 ml-2 space-y-4" data-testid="serial-timeline">
              {events.map((ev, i) => {
                const { icon, color, title } = labelForEvent(ev);
                return (
                  <li key={ev.id} className="ml-4">
                    <div className={`absolute -left-[9px] w-4 h-4 rounded-full ${color} flex items-center justify-center border-2 border-white`}>
                      <span className="w-2 h-2 rounded-full bg-current opacity-70" />
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                      <div className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold ${color}`}>
                        {icon} {title}
                      </div>
                      <div className="text-xs text-slate-500 mt-1.5">
                        {new Date(ev.created_at).toLocaleString("it-IT")}
                        {ev.actor_name ? ` · ${ev.actor_name}` : ""}
                      </div>
                      {ev.note_wr && (
                        <div className="text-[11px] text-slate-600 mt-1">Nota <span className="font-mono font-semibold">WR {ev.note_wr}</span></div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------- Warehouse Page ----------
function WarehousePage({ onOpenAdmin, showAdminBtn }) {
  const [serials, setSerials] = useState([]);
  const [users, setUsers] = useState([]);
  const [tags, setTags] = useState([]);
  const [tagStats, setTagStats] = useState({ total: 0, by_tag: [] });
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("in_stock");  // default: home = liberi
  const [tipoFilter, setTipoFilter] = useState("");
  const [bulkSearchOpen, setBulkSearchOpen] = useState(false);
  const [bulkSearchText, setBulkSearchText] = useState("");
  const [bulkSearchResults, setBulkSearchResults] = useState(null);
  const [bulkAssignUser, setBulkAssignUser] = useState("");
  const [bulkSearching, setBulkSearching] = useState(false);
  const [inputSerial, setInputSerial] = useState("");
  const [inputTipo, setInputTipo] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyItem, setHistoryItem] = useState(null);
  const [editingTipoId, setEditingTipoId] = useState(null);
  const [editingTipoVal, setEditingTipoVal] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set());
  const scanRef = useRef(null);
  const [thresholds, setThresholds] = useState([]);

  const fetchSerials = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/inventory/serials`, { params: { search: filter, status: statusFilter, tipo: tipoFilter } });
      setSerials(r.data || []);
    } catch (e) { toast.error(errorText(e)); }
    finally { setLoading(false); }
  }, [filter, statusFilter, tipoFilter]);

  const fetchTags = useCallback(async () => {
    try { const r = await axios.get(`${API}/inventory/tags`); setTags(r.data.tags || []); } catch (_) {}
    try { const r = await axios.get(`${API}/inventory/stats`); setTagStats(r.data || { total: 0, by_tag: [] }); } catch (_) {}
    try { const r = await axios.get(`${API}/inventory/thresholds`); setThresholds(r.data || []); } catch (_) {}
  }, []);

  const setTagThreshold = async (tag, threshold) => {
    try {
      await axios.post(`${API}/inventory/thresholds`, { tag, threshold: parseInt(threshold, 10) || 0 });
      toast.success(threshold > 0 ? `Soglia "${tag}" = ${threshold}` : `Soglia "${tag}" disattivata`);
      fetchTags();
    } catch (e) { toast.error(errorText(e)); }
  };

  const thresholdFor = (tag) => thresholds.find((t) => t.tag === tag)?.threshold || 0;

  useEffect(() => { const t = setTimeout(fetchSerials, 200); return () => clearTimeout(t); }, [fetchSerials]);
  useEffect(() => { axios.get(`${API}/inventory/users`).then((r) => setUsers(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { fetchTags(); }, [fetchTags]);
  useEffect(() => { if (scanRef.current) scanRef.current.focus(); }, []);

  const addSerial = async (s) => {
    const val = (s || inputSerial || "").trim();
    if (!val) return;
    try {
      await axios.post(`${API}/inventory/serials`, { serial: val, tipo: inputTipo.trim(), note: "" });
      toast.success(`Aggiunto ${val}${inputTipo.trim() ? ` (${inputTipo.trim()})` : ""}`);
      setInputSerial("");
      fetchSerials(); fetchTags();
    } catch (e) { toast.error(errorText(e)); }
    finally { setTimeout(() => scanRef.current?.focus(), 50); }
  };

  const bulkAdd = async () => {
    const list = bulkText.split(/[\n,;\s]+/).map((s) => s.trim()).filter(Boolean);
    if (!list.length) return;
    try {
      const r = await axios.post(`${API}/inventory/serials/bulk`, { serials: list, tipo: inputTipo.trim() });
      toast.success(`${r.data.created} aggiunti, ${r.data.skipped.length} già presenti`);
      setBulkText(""); fetchSerials(); fetchTags();
    } catch (e) { toast.error(errorText(e)); }
  };

  const assign = async (id, userId) => {
    try { await axios.patch(`${API}/inventory/serials/${id}`, { assigned_to_user_id: userId }); toast.success("Assegnazione aggiornata"); fetchSerials(); }
    catch (e) { toast.error(errorText(e)); }
  };

  const saveTipo = async (id) => {
    const v = editingTipoVal.trim();
    try {
      await axios.patch(`${API}/inventory/serials/${id}`, { tipo: v });
      setEditingTipoId(null); setEditingTipoVal("");
      fetchSerials(); fetchTags();
    } catch (e) { toast.error(errorText(e)); }
  };

  const returnToWarehouse = async (id, s) => {
    if (!window.confirm(`Restituire il modem ${s} al magazzino?`)) return;
    try {
      await axios.post(`${API}/inventory/serials/${id}/return`);
      toast.success(`${s} tornato in magazzino`);
      fetchSerials(); fetchTags();
    } catch (e) { toast.error(errorText(e)); }
  };

  const del = async (id, s) => {
    if (!window.confirm(`Eliminare seriale ${s}?`)) return;
    try { await axios.delete(`${API}/inventory/serials/${id}`); toast.success("Eliminato"); fetchSerials(); fetchTags(); }
    catch (e) { toast.error(errorText(e)); }
  };

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const selectAllVisible = () => {
    const ids = serials.map((s) => s.id);
    setSelectedIds((prev) => prev.size === ids.length ? new Set() : new Set(ids));
  };
  const selectByTag = () => {
    if (!tipoFilter) return;
    const ids = serials.filter((s) => (s.tipo || "") === tipoFilter).map((s) => s.id);
    setSelectedIds(new Set(ids));
    toast.success(`${ids.length} seriale/i "${tipoFilter}" selezionati`);
  };
  const runBulkSearch = async () => {
    const list = bulkSearchText.split(/[\n,;\s]+/).map((s) => s.trim()).filter(Boolean);
    if (!list.length) { toast.error("Incolla almeno un seriale"); return; }
    setBulkSearching(true);
    try {
      const r = await axios.post(`${API}/inventory/serials/search-bulk`, { serials: list });
      const ids = r.data.found.map((s) => s.id);
      setSelectedIds(new Set(ids));
      toast.success(`${ids.length} seriale/i trovati e selezionati`);
      if (r.data.not_found.length) toast.message(`Non trovati: ${r.data.not_found.join(", ")}`);
      setBulkSearchOpen(false); setBulkSearchText("");
    } catch (e) { toast.error(errorText(e)); }
    finally { setBulkSearching(false); }
  };
  const [bulkTag, setBulkTag] = useState("");
  const [bulkAssignee, setBulkAssignee] = useState("");
  const bulkDelete = async () => {
    if (!selectedIds.size) return;
    if (!window.confirm(`Eliminare ${selectedIds.size} seriale/i selezionato/i?`)) return;
    try {
      const r = await axios.post(`${API}/inventory/serials/bulk-delete`, { ids: Array.from(selectedIds) });
      toast.success(`${r.data.deleted} seriale/i eliminati`);
      setSelectedIds(new Set());
      fetchSerials(); fetchTags();
    } catch (e) { toast.error(errorText(e)); }
  };
  const bulkSetTag = async () => {
    if (!selectedIds.size) return;
    try {
      const r = await axios.post(`${API}/inventory/serials/bulk-update`, { ids: Array.from(selectedIds), tipo: bulkTag.trim() });
      toast.success(`${r.data.updated} seriale/i aggiornati (tag)`);
      setBulkTag(""); fetchSerials(); fetchTags();
    } catch (e) { toast.error(errorText(e)); }
  };
  const bulkAssign = async () => {
    if (!selectedIds.size || !bulkAssignee) return;
    const assignVal = bulkAssignee === "__none__" ? "" : bulkAssignee;
    try {
      const r = await axios.post(`${API}/inventory/serials/bulk-update`, { ids: Array.from(selectedIds), assigned_to_user_id: assignVal });
      toast.success(`${r.data.updated} seriale/i aggiornati (assegnazione)`);
      setBulkAssignee(""); fetchSerials();
    } catch (e) { toast.error(errorText(e)); }
  };
  const deleteTag = async (tag) => {
    if (!window.confirm(`Eliminare il tag "${tag}"? I seriali resteranno ma senza tag.`)) return;
    try {
      const r = await axios.post(`${API}/inventory/tags/delete`, { tag });
      toast.success(`Tag "${tag}" rimosso da ${r.data.updated} seriale/i`);
      fetchSerials(); fetchTags();
    } catch (e) { toast.error(errorText(e)); }
  };

  const exportCSV = async () => {
    try {
      const r = await axios.get(`${API}/inventory/export.csv`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const today = new Date().toISOString().slice(0, 10);
      const a = document.createElement("a"); a.href = url; a.download = `magazzino_${today}.csv`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Export CSV avviato");
    } catch (e) { toast.error(errorText(e)); }
  };

  const stats = {
    total: serials.length,
    in_stock: serials.filter((s) => s.status === "in_stock").length,
    assegnato: serials.filter((s) => s.status === "assegnato").length,
    scaricato: serials.filter((s) => s.status === "scaricato").length,
  };

  return (
    <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6" data-testid="warehouse-content">
      <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5" data-testid="warehouse-add">
        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Aggiungi seriale</div>
        <h2 className="text-lg font-display font-bold mt-0.5 mb-3">Aggiungi al magazzino</h2>
        <div className="text-xs text-slate-500 mb-3">Punta il campo qui sotto e usa la pistola scanner USB/wireless — legge il seriale e invia Enter. Puoi anche digitare a mano.</div>
        <form onSubmit={(e) => { e.preventDefault(); addSerial(); }} className="flex flex-wrap gap-2 items-center">
          <input list="wh-tags-datalist" value={inputTipo} onChange={(e) => setInputTipo(e.target.value)}
            placeholder="Tag (es. CPE, ONT, SFP, Router…)"
            className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-brand-pink"
            data-testid="add-tipo" />
          <datalist id="wh-tags-datalist">
            {tags.map((t) => <option key={t} value={t} />)}
          </datalist>
          <input ref={scanRef} value={inputSerial} onChange={(e) => setInputSerial(e.target.value)} placeholder="Scansiona o digita seriale, poi Enter"
            className="flex-1 min-w-[220px] rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-pink"
            data-testid="add-serial-input" autoFocus />
          <button type="submit" className="btn-primary rounded-full px-4 py-2 text-sm font-semibold inline-flex items-center gap-2" data-testid="add-serial-btn">
            <Package size={14} /> Aggiungi
          </button>
        </form>
        <div className="text-[11px] text-slate-400 mt-1">Il tag è libero. Puoi lasciarlo vuoto e assegnarlo dopo cliccando sul tag nella tabella.</div>
        <details className="mt-3">
          <summary className="text-xs font-semibold text-slate-600 cursor-pointer">Inserimento massivo (una riga per seriale)</summary>
          <textarea value={bulkText} onChange={(e) => setBulkText(e.target.value)} rows={4} placeholder="ABC123&#10;DEF456"
            className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-pink"
            data-testid="bulk-serial-textarea" />
          <button onClick={bulkAdd} className="mt-2 rounded-full px-3 py-2 text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 inline-flex items-center gap-2" data-testid="bulk-serial-btn">
            <Package size={14} /> Aggiungi tutti{inputTipo.trim() ? ` come ${inputTipo.trim()}` : ""}
          </button>
        </details>
      </section>

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="warehouse-stats">
        <div className="rounded-xl bg-white border border-slate-200 p-3"><div className="text-[11px] text-slate-500 font-semibold">Totale</div><div className="text-2xl font-display font-extrabold">{stats.total}</div></div>
        <div className="rounded-xl bg-white border border-slate-200 p-3"><div className="text-[11px] text-slate-500 font-semibold">In stock</div><div className="text-2xl font-display font-extrabold text-emerald-600">{stats.in_stock}</div></div>
        <div className="rounded-xl bg-white border border-slate-200 p-3"><div className="text-[11px] text-slate-500 font-semibold">Assegnati</div><div className="text-2xl font-display font-extrabold text-amber-600">{stats.assegnato}</div></div>
        <div className="rounded-xl bg-white border border-slate-200 p-3"><div className="text-[11px] text-slate-500 font-semibold">Scaricati</div><div className="text-2xl font-display font-extrabold text-slate-500">{stats.scaricato}</div></div>
      </section>

      {tagStats.by_tag.length > 0 && (
        <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5" data-testid="warehouse-tag-stats">
          <div className="flex items-center gap-2 mb-3">
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Statistiche per Tag</div>
              <h2 className="text-lg font-display font-bold mt-0.5">Ripartizione magazzino</h2>
            </div>
            <div className="ml-auto text-[11px] text-slate-500">{tagStats.by_tag.length} tag distinti · {tagStats.total} seriali</div>
          </div>
          <div className="space-y-2.5">
            {tagStats.by_tag.map((row) => {
              const max = Math.max(...tagStats.by_tag.map((x) => x.total));
              const pct = max ? (row.total / max) * 100 : 0;
              const inPct = row.total ? (row.in_stock / row.total) * 100 : 0;
              const asPct = row.total ? (row.assegnato / row.total) * 100 : 0;
              const dwPct = row.total ? (row.scaricato / row.total) * 100 : 0;
              return (
                <div key={row.tag || "__empty__"}
                  className={`w-full rounded-xl border transition p-3 ${tipoFilter === row.tag ? "border-brand-pink bg-pink-50" : "border-slate-200 hover:border-brand-pink hover:bg-pink-50/40"}`}
                  data-testid={`tag-stat-${row.tag || "empty"}`}>
                  <button onClick={() => setTipoFilter(row.tag)} className="w-full text-left" title="Clicca per filtrare la lista">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${row.tag ? "bg-pink-100 text-pink-800" : "bg-slate-100 text-slate-400 italic"}`}>
                        {row.tag || "— senza tag —"}
                      </span>
                      {row.tag && thresholdFor(row.tag) > 0 && row.in_stock <= thresholdFor(row.tag) && (
                        <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded animate-pulse" data-testid={`threshold-alert-${row.tag}`}>⚠️ SOTTO SOGLIA</span>
                      )}
                      <span className="text-lg font-display font-extrabold text-slate-900 ml-auto">{row.total}</span>
                    </div>
                    <div className="mt-2 h-2.5 bg-slate-100 rounded-full overflow-hidden relative" style={{ width: `${Math.max(pct, 8)}%`, minWidth: 60 }}>
                      <div className="absolute inset-y-0 left-0 bg-emerald-400" style={{ width: `${inPct}%` }} />
                      <div className="absolute inset-y-0 bg-amber-400" style={{ left: `${inPct}%`, width: `${asPct}%` }} />
                      <div className="absolute inset-y-0 bg-slate-400" style={{ left: `${inPct + asPct}%`, width: `${dwPct}%` }} />
                    </div>
                    <div className="flex gap-3 mt-1.5 text-[11px] text-slate-600">
                      <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400"></span> {row.in_stock} in stock</span>
                      <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400"></span> {row.assegnato} assegnati</span>
                      <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-400"></span> {row.scaricato} scaricati</span>
                    </div>
                  </button>
                  {row.tag && (
                    <div className="mt-2 pt-2 border-t border-slate-100 flex items-center gap-2">
                      <label className="text-[11px] font-semibold text-slate-500 inline-flex items-center gap-1">
                        <Zap size={10} /> Avvisa se in stock ≤
                      </label>
                      <input type="number" min="0" defaultValue={thresholdFor(row.tag) || ""} placeholder="0"
                        onBlur={(e) => setTagThreshold(row.tag, e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.target.blur(); } }}
                        className="w-16 rounded-full border border-slate-200 px-2 py-0.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-brand-pink"
                        data-testid={`threshold-input-${row.tag}`} />
                      {thresholdFor(row.tag) > 0 && (
                        <span className="text-[10px] text-slate-400">soglia attiva: {thresholdFor(row.tag)}</span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {tipoFilter && (
            <button onClick={() => setTipoFilter("")} className="mt-3 text-[11px] font-semibold text-slate-600 hover:text-slate-900 inline-flex items-center gap-1" data-testid="clear-tag-filter">
              <X size={12} /> Rimuovi filtro tag "{tipoFilter}"
            </button>
          )}
        </section>
      )}

      <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5" data-testid="warehouse-list">
        <div className="flex gap-1 bg-slate-100 rounded-full p-1 mb-3 w-fit" data-testid="warehouse-tabs">
          <button onClick={() => setStatusFilter("in_stock")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${statusFilter === "in_stock" ? "bg-white text-emerald-700 shadow" : "text-slate-500 hover:text-slate-800"}`}
            data-testid="wh-tab-in_stock">
            <Package size={12} /> In stock
          </button>
          <button onClick={() => setStatusFilter("assegnato")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${statusFilter === "assegnato" ? "bg-white text-amber-700 shadow" : "text-slate-500 hover:text-slate-800"}`}
            data-testid="wh-tab-assegnato">
            <UserCheck size={12} /> Assegnati
          </button>
          <button onClick={() => setStatusFilter("scaricato")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${statusFilter === "scaricato" ? "bg-white text-slate-700 shadow" : "text-slate-500 hover:text-slate-800"}`}
            data-testid="wh-tab-scaricato">
            <RefreshCw size={12} /> Scaricati
          </button>
          <button onClick={() => setStatusFilter("")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold inline-flex items-center gap-1 transition ${statusFilter === "" ? "bg-white text-slate-700 shadow" : "text-slate-500 hover:text-slate-800"}`}
            data-testid="wh-tab-all">
            Tutti
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Cerca seriale/utente"
              className="w-full pl-9 pr-3 py-2 rounded-full border border-slate-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid="warehouse-search" />
          </div>
          <select value={tipoFilter} onChange={(e) => setTipoFilter(e.target.value)} className="rounded-full border border-slate-200 px-3 py-2 text-sm" data-testid="warehouse-tipo-filter">
            <option value="">Tutti i tag</option>
            {tags.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          {tipoFilter && (
            <button onClick={selectByTag} className="rounded-full px-3 py-2 text-xs font-semibold bg-brand-pink/10 text-brand-pink brand-pink hover:bg-brand-pink/20 inline-flex items-center gap-1.5" data-testid="wh-select-tag">
              <CheckCircle2 size={14} /> Seleziona tutti "{tipoFilter}"
            </button>
          )}
          {tipoFilter && (
            <button onClick={() => deleteTag(tipoFilter)} className="rounded-full px-3 py-2 text-xs font-semibold bg-red-50 text-red-700 hover:bg-red-100 inline-flex items-center gap-1.5" data-testid="warehouse-delete-tag">
              <Trash2 size={14} /> Elimina tag "{tipoFilter}"
            </button>
          )}
          <button onClick={exportCSV} className="rounded-full px-3 py-2 text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 inline-flex items-center gap-1.5" data-testid="warehouse-export-csv">
            <Download size={14} /> Export CSV
          </button>
        </div>
        {selectedIds.size > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2 bg-pink-50 border border-pink-200 rounded-xl px-3 py-2" data-testid="wh-bulk-bar">
            <span className="text-xs font-semibold text-pink-800">{selectedIds.size} selezionati</span>
            <div className="inline-flex items-center gap-1">
              <input list="wh-bulk-tags" value={bulkTag} onChange={(e) => setBulkTag(e.target.value)} placeholder="Tag…"
                className="rounded-full border border-slate-200 px-3 py-1.5 text-xs w-28" data-testid="wh-bulk-tag-input" />
              <datalist id="wh-bulk-tags">{tags.map((t) => <option key={t} value={t} />)}</datalist>
              <button onClick={bulkSetTag} className="rounded-full px-3 py-1.5 text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800" data-testid="wh-bulk-apply-tag">Applica tag</button>
            </div>
            <div className="inline-flex items-center gap-1">
              <select value={bulkAssignee} onChange={(e) => setBulkAssignee(e.target.value)} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs" data-testid="wh-bulk-assignee">
                <option value="">— Assegnatario —</option>
                <option value="__none__">Rimuovi assegnazione</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.name || u.email}</option>)}
              </select>
              <button onClick={bulkAssign} className="rounded-full px-3 py-1.5 text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700" data-testid="wh-bulk-apply-assign">Assegna</button>
            </div>
            <button onClick={bulkDelete} className="ml-auto rounded-full px-3 py-1.5 text-xs font-semibold bg-red-600 text-white hover:bg-red-700 inline-flex items-center gap-1.5" data-testid="warehouse-bulk-delete">
              <Trash2 size={14} /> Elimina {selectedIds.size}
            </button>
          </div>
        )}
        {loading ? (
          <div className="flex items-center gap-2 text-slate-500 text-sm p-4"><Loader2 className="animate-spin" size={16} /> Caricamento…</div>
        ) : serials.length === 0 ? (
          <div className="border border-dashed border-slate-200 rounded-2xl p-8 text-center text-slate-500 text-sm">Nessun seriale in magazzino</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 font-semibold border-b border-slate-200">
                  <th className="py-2 pr-1 w-8">
                    <input type="checkbox" checked={selectedIds.size > 0 && selectedIds.size === serials.length}
                      onChange={selectAllVisible}
                      className="h-4 w-4 rounded border-slate-300 accent-pink-600 cursor-pointer" data-testid="wh-select-all" />
                  </th>
                  <th className="py-2 pr-2">Seriale</th>
                  <th className="py-2 pr-2">OLO / WR</th>
                  <th className="py-2 pr-2">Tag</th>
                  <th className="py-2 pr-2">Stato</th>
                  <th className="py-2 pr-2">Assegnato a</th>
                  <th className="py-2 pr-2">Scaricato da</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {serials.map((s) => (
                  <tr key={s.id} className={`border-b border-slate-100 last:border-0 ${selectedIds.has(s.id) ? "bg-pink-50" : ""}`} data-testid={`serial-row-${s.serial}`}>
                    <td className="py-2 pr-1">
                      <input type="checkbox" checked={selectedIds.has(s.id)} onChange={() => toggleSelect(s.id)}
                        className="h-4 w-4 rounded border-slate-300 accent-pink-600 cursor-pointer" data-testid={`wh-select-${s.serial}`} />
                    </td>
                    <td className="py-2 pr-2 font-mono text-slate-900">
                      <button onClick={() => setHistoryItem(s)} className="inline-flex items-center gap-1.5 hover:brand-pink hover:underline decoration-dotted underline-offset-2" data-testid={`serial-history-${s.serial}`} title="Vedi storico">
                        <History size={12} className="text-slate-400" /> {s.serial}
                      </button>
                    </td>
                    <td className="py-2 pr-2 text-xs" data-testid={`serial-olo-${s.serial}`}>
                      {s.downloaded_olo || s.downloaded_note_wr ? (
                        <div className="flex flex-col gap-0.5">
                          {s.downloaded_olo && (
                            <span onClick={() => { navigator.clipboard.writeText(s.downloaded_olo); toast.success("OLO copiato"); }}
                              className="font-mono font-semibold text-pink-800 bg-pink-50 border border-pink-200 rounded px-1.5 py-0.5 inline-block cursor-pointer hover:bg-pink-100 break-all"
                              title="Tap per copiare l'OLO">
                              {s.downloaded_olo}
                            </span>
                          )}
                          {s.downloaded_note_wr && (
                            <span className="text-[10px] text-slate-500 font-mono">WR {s.downloaded_note_wr}</span>
                          )}
                        </div>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="py-2 pr-2 text-slate-600">
                      {editingTipoId === s.id ? (
                        <div className="inline-flex items-center gap-1">
                          <input list="wh-tags-datalist" value={editingTipoVal} onChange={(e) => setEditingTipoVal(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") saveTipo(s.id); if (e.key === "Escape") { setEditingTipoId(null); setEditingTipoVal(""); } }}
                            autoFocus placeholder="tag…"
                            className="rounded-full border border-slate-300 px-2 py-1 text-xs w-28 focus:outline-none focus:ring-2 focus:ring-brand-pink"
                            data-testid={`edit-tipo-input-${s.serial}`} />
                          <button onClick={() => saveTipo(s.id)} className="text-emerald-600 hover:bg-emerald-50 rounded-full p-1" data-testid={`save-tipo-${s.serial}`}><Save size={12} /></button>
                          <button onClick={() => { setEditingTipoId(null); setEditingTipoVal(""); }} className="text-slate-400 hover:bg-slate-100 rounded-full p-1"><X size={12} /></button>
                        </div>
                      ) : (
                        <button onClick={() => { setEditingTipoId(s.id); setEditingTipoVal(s.tipo || ""); }}
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold transition ${s.tipo ? "bg-pink-100 text-pink-800 hover:bg-pink-200" : "bg-slate-100 text-slate-400 hover:bg-slate-200 italic"}`}
                          data-testid={`tipo-chip-${s.serial}`} title="Clicca per modificare">
                          {s.tipo || "+ tag"}
                        </button>
                      )}
                    </td>
                    <td className="py-2 pr-2">
                      {s.status === "in_stock" && <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">IN STOCK</span>}
                      {s.status === "assegnato" && <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded">ASSEGNATO</span>}
                      {s.status === "scaricato" && <span className="text-[10px] font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">SCARICATO</span>}
                    </td>
                    <td className="py-2 pr-2">
                      <select value={s.assigned_to_user_id || ""} onChange={(e) => assign(s.id, e.target.value)} disabled={s.status === "scaricato"}
                        className="text-xs rounded-full border border-slate-200 bg-white px-2 py-1 disabled:opacity-50 max-w-[180px]"
                        data-testid={`assign-${s.serial}`}>
                        <option value="">— Non assegnato —</option>
                        {users.map((u) => <option key={u.id} value={u.id}>{u.name || u.email}</option>)}
                      </select>
                    </td>
                    <td className="py-2 pr-2 text-xs text-slate-600">
                      {s.downloaded_by_name ? (
                        <span>{s.downloaded_by_name}<br /><span className="text-[10px] text-slate-400">{s.downloaded_at ? new Date(s.downloaded_at).toLocaleString("it-IT") : ""}</span></span>
                      ) : "—"}
                    </td>
                    <td className="py-2 text-right">
                      {s.status === "assegnato" && (
                        <button onClick={() => returnToWarehouse(s.id, s.serial)} className="text-amber-700 hover:bg-amber-50 rounded-full p-1.5 mr-1" data-testid={`return-serial-${s.serial}`} title="Restituisci a magazzino">
                          <RotateCcw size={14} />
                        </button>
                      )}
                      <button onClick={() => del(s.id, s.serial)} className="text-red-600 hover:bg-red-50 rounded-full p-1.5" data-testid={`delete-serial-${s.serial}`}><Trash2 size={14} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {historyItem && <SerialHistoryModal serialItem={historyItem} onClose={() => setHistoryItem(null)} />}
    </main>
  );
}

// ---------- Vacations Page (ferie) ----------
// Hash helper: derive a stable hue per user_id for color-coded calendar
const userColor = (uid) => {
  if (!uid) return { bg: "#e2e8f0", fg: "#475569" };
  let h = 0;
  for (let i = 0; i < uid.length; i++) h = (h * 31 + uid.charCodeAt(i)) & 0xffffffff;
  const hue = Math.abs(h) % 360;
  return { bg: `hsl(${hue}, 70%, 60%)`, fg: "#ffffff", light: `hsl(${hue}, 90%, 92%)`, dark: `hsl(${hue}, 60%, 30%)` };
};

function VacationsCalendar({ items }) {
  const [ym, setYm] = useState(() => {
    const n = new Date(); return { y: n.getFullYear(), m: n.getMonth() };
  });
  const { y, m } = ym;
  const first = new Date(y, m, 1);
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const startWeekday = (first.getDay() + 6) % 7; // Monday = 0
  const cells = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(y, m, d));
  while (cells.length % 7 !== 0) cells.push(null);

  const isoOf = (date) => {
    const dd = String(date.getDate()).padStart(2, "0");
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    return `${date.getFullYear()}-${mm}-${dd}`;
  };
  const vacsOn = (date) => {
    const iso = isoOf(date);
    return items.filter((v) => v.from_date <= iso && iso <= v.to_date && v.status !== "rejected");
  };

  // Distinct users for legend
  const legendMap = new Map();
  items.forEach((v) => { if (!legendMap.has(v.user_id)) legendMap.set(v.user_id, v.user_name || v.user_email); });
  const legend = Array.from(legendMap.entries());

  const monthName = new Date(y, m, 1).toLocaleString("it-IT", { month: "long", year: "numeric" });
  const prev = () => { const d = new Date(y, m - 1, 1); setYm({ y: d.getFullYear(), m: d.getMonth() }); };
  const next = () => { const d = new Date(y, m + 1, 1); setYm({ y: d.getFullYear(), m: d.getMonth() }); };
  const today = () => { const n = new Date(); setYm({ y: n.getFullYear(), m: n.getMonth() }); };
  const todayIso = isoOf(new Date());

  return (
    <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5" data-testid="vacations-calendar">
      <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
        <div>
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Calendario</div>
          <h2 className="text-lg font-display font-bold capitalize">{monthName}</h2>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={prev} className="rounded-full px-3 py-1 text-xs font-semibold bg-slate-100 hover:bg-slate-200" data-testid="cal-prev">‹</button>
          <button onClick={today} className="rounded-full px-3 py-1 text-xs font-semibold bg-slate-100 hover:bg-slate-200" data-testid="cal-today">Oggi</button>
          <button onClick={next} className="rounded-full px-3 py-1 text-xs font-semibold bg-slate-100 hover:bg-slate-200" data-testid="cal-next">›</button>
        </div>
      </div>
      <div className="grid grid-cols-7 gap-1 text-[10px] font-semibold text-slate-500 mb-1">
        {["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map((d) => <div key={d} className="text-center py-1">{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((c, i) => {
          if (!c) return <div key={`e${i}`} className="h-16 sm:h-20" />;
          const iso = isoOf(c);
          const vacs = vacsOn(c);
          const isToday = iso === todayIso;
          const isSat = c.getDay() === 6;
          const isSun = c.getDay() === 0;
          return (
            <div key={iso} className={`h-16 sm:h-20 rounded-lg border p-1 relative overflow-hidden ${isToday ? "border-brand-pink ring-1 ring-brand-pink" : "border-slate-200"} ${isSat || isSun ? "bg-slate-50" : "bg-white"}`}
              data-testid={`cal-cell-${iso}`}>
              <div className={`text-[10px] font-bold ${isToday ? "text-brand-pink" : "text-slate-500"}`}>{c.getDate()}</div>
              <div className="mt-0.5 space-y-0.5">
                {vacs.slice(0, 3).map((v) => {
                  const col = userColor(v.user_id);
                  return (
                    <div key={v.id} title={`${v.user_name} · ${v.from_date}→${v.to_date}${v.status === "pending" ? " (in attesa)" : ""}`}
                      className="truncate text-[9px] font-semibold px-1 py-0.5 rounded"
                      style={{ background: v.status === "pending" ? col.light : col.bg, color: v.status === "pending" ? col.dark : col.fg, border: v.status === "pending" ? `1px dashed ${col.bg}` : "none" }}
                      data-testid={`cal-vac-${v.id}-${iso}`}>
                      {v.user_name}
                    </div>
                  );
                })}
                {vacs.length > 3 && <div className="text-[9px] text-slate-500">+{vacs.length - 3}</div>}
              </div>
            </div>
          );
        })}
      </div>

      {legend.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-100">
          <div className="text-[11px] font-semibold text-slate-500 uppercase mb-2">Legenda</div>
          <div className="flex flex-wrap gap-2">
            {legend.map(([uid, name]) => {
              const col = userColor(uid);
              return (
                <div key={uid} className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full" style={{ background: col.light, color: col.dark }} data-testid={`legend-${uid}`}>
                  <span className="w-3 h-3 rounded-full" style={{ background: col.bg }} />
                  {name}
                </div>
              );
            })}
            <div className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-slate-100 text-slate-600">
              <span className="w-3 h-3 rounded-full border-2 border-dashed border-slate-400" /> In attesa
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function VacationsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canView = isAdmin || user?.role === "magazzino";  // magazzino can see full plan
  const isMagazzino = user?.role === "magazzino";
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");

  const fetchList = useCallback(async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/vacations`); setList(r.data || []); }
    catch (e) { toast.error(errorText(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchList(); }, [fetchList]);

  const submit = async (e) => {
    e.preventDefault();
    if (!from || !to) { toast.error("Compila entrambe le date"); return; }
    try {
      await axios.post(`${API}/vacations`, { from_date: from, to_date: to, reason });
      toast.success("Richiesta inviata all'admin");
      setFrom(""); setTo(""); setReason(""); fetchList();
    } catch (e) { toast.error(errorText(e)); }
  };

  const decide = async (vid, decision) => {
    const note = decision === "rejected" ? window.prompt("Nota (opzionale) motivo rifiuto:", "") : window.prompt("Nota opzionale:", "");
    try {
      await axios.post(`${API}/vacations/${vid}/decision`, { decision, admin_note: note || "" });
      toast.success(decision === "approved" ? "Ferie approvate" : "Ferie rifiutate");
      fetchList();
    } catch (e) { toast.error(errorText(e)); }
  };
  const cancel = async (vid) => {
    if (!window.confirm("Annullare questa richiesta?")) return;
    try { await axios.delete(`${API}/vacations/${vid}`); toast.success("Annullata"); fetchList(); }
    catch (e) { toast.error(errorText(e)); }
  };

  const badgeColor = (s) => s === "approved" ? "bg-emerald-100 text-emerald-800"
    : s === "rejected" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800";
  const badgeLabel = (s) => s === "approved" ? "Approvata" : s === "rejected" ? "Rifiutata" : "In attesa";

  return (
    <main className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6" data-testid="vacations-page">
      {!isAdmin && !isMagazzino && (
        <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5">
          <div className="flex items-center gap-2 mb-3">
            <Calendar size={18} className="brand-pink" />
            <h2 className="text-lg font-display font-bold">Nuova richiesta ferie</h2>
          </div>
          <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
            <label className="text-xs font-medium text-slate-600">
              Dal
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} required
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid="vacation-from" />
            </label>
            <label className="text-xs font-medium text-slate-600">
              Al
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} required
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid="vacation-to" />
            </label>
            <button type="submit" className="btn-primary rounded-full px-4 py-2 text-sm font-semibold inline-flex items-center justify-center gap-2" data-testid="vacation-submit">
              <UserCheck size={14} /> Invia richiesta
            </button>
            <label className="text-xs font-medium text-slate-600 sm:col-span-3">
              Motivo (opzionale)
              <input type="text" value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="Es. matrimonio, medico, ferie estive…"
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid="vacation-reason" />
            </label>
          </form>
        </section>
      )}

      {canView && list.length > 0 && <VacationsCalendar items={list} />}

      <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5">
        <div className="flex items-center gap-2 mb-3">
          <Calendar size={16} />
          <h2 className="text-base font-display font-bold">{canView ? "Tutte le richieste ferie" : "Le tue richieste"}</h2>
          <span className="ml-auto text-xs text-slate-500">{list.length}</span>
        </div>
        {loading ? (
          <div className="flex items-center gap-2 text-slate-500 text-sm p-4"><Loader2 className="animate-spin" size={16} /> Caricamento…</div>
        ) : list.length === 0 ? (
          <div className="border border-dashed border-slate-200 rounded-xl p-6 text-center text-sm text-slate-400">Nessuna richiesta</div>
        ) : (
          <div className="space-y-2">
            {list.map((v) => (
              <div key={v.id} className="border border-slate-200 rounded-xl p-3 flex flex-wrap items-center gap-3" data-testid={`vacation-row-${v.id}`}>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-slate-900 flex items-center gap-2 flex-wrap">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${badgeColor(v.status)}`}>{badgeLabel(v.status)}</span>
                    <span>{v.from_date} → {v.to_date}</span>
                    {v.has_overlap && <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded animate-pulse" title="Sovrapposizione con altre ferie" data-testid={`vac-overlap-${v.id}`}>⚠️ SOVRAPPOSTA</span>}
                    {canView && <span className="text-xs text-slate-500 font-normal">· {v.user_name || v.user_email}</span>}
                  </div>
                  {v.reason && <div className="text-xs text-slate-600 mt-0.5">💬 {v.reason}</div>}
                  {v.admin_note && <div className="text-[11px] text-slate-500 mt-0.5">Nota admin: {v.admin_note}</div>}
                </div>
                <div className="flex gap-1.5">
                  {isAdmin && v.status === "pending" && (
                    <>
                      <button onClick={() => decide(v.id, "approved")} className="text-xs font-semibold bg-emerald-500 text-white rounded-full px-3 py-1.5 hover:bg-emerald-600" data-testid={`vac-approve-${v.id}`}>Approva</button>
                      <button onClick={() => decide(v.id, "rejected")} className="text-xs font-semibold bg-red-500 text-white rounded-full px-3 py-1.5 hover:bg-red-600" data-testid={`vac-reject-${v.id}`}>Rifiuta</button>
                    </>
                  )}
                  {(v.status === "pending" || isAdmin) && (
                    <button onClick={() => cancel(v.id)} className="text-xs font-semibold text-red-600 bg-red-50 rounded-full px-3 py-1.5 hover:bg-red-100" data-testid={`vac-cancel-${v.id}`}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

// ---------- Admin Dashboard (media giornaliera + giacenza per tecnico) ----------
function AdminDashboard() {
  const now = new Date();
  const todayIso = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().slice(0, 10);
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const [from, setFrom] = useState(monthStart);
  const [to, setTo] = useState(todayIso);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/admin/dashboard`, { params: { from, to } }); setData(r.data); }
    catch (e) { toast.error(errorText(e)); }
    finally { setLoading(false); }
  }, [from, to]);
  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6" data-testid="admin-dashboard">
      <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Panoramica</div>
            <h2 className="text-lg sm:text-xl font-display font-bold text-slate-900 mt-0.5">Dashboard Admin</h2>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs" data-testid="dashboard-from" />
            <span className="text-xs text-slate-400">→</span>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs" data-testid="dashboard-to" />
          </div>
        </div>
        <div className="mt-3 text-[11px] text-slate-500">Sabati esclusi dal calcolo · Media = espletati+migrazioni / giorni lavorati</div>
      </section>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm p-4"><Loader2 className="animate-spin" size={16} /> Caricamento…</div>
      ) : !data ? null : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {data.users.map((u) => {
            const maxAvg = Math.max(1, ...data.users.map((x) => x.avg_completed));
            const pct = (u.avg_completed / maxAvg) * 100;
            return (
              <div key={u.id} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`user-stat-${u.id}`}>
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <div className="w-8 h-8 rounded-full bg-brand-pink brand-pink-bg text-white font-bold flex items-center justify-center text-xs">
                    {(u.name || u.email || "?").charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-slate-900 truncate">{u.name || u.email}</div>
                    <div className="text-[11px] text-slate-500 truncate">{u.email} · {u.role}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-display font-extrabold text-slate-900">{u.avg_completed.toFixed(1)}</div>
                    <div className="text-[10px] text-slate-500">media/g</div>
                  </div>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-emerald-400 to-brand-pink brand-pink-bg" style={{ width: `${Math.max(pct, 4)}%` }} />
                </div>
                <div className="grid grid-cols-4 gap-2 mt-3 text-center">
                  <div className="rounded-lg bg-emerald-50 p-2"><div className="text-[10px] text-emerald-700 font-semibold">Espletati</div><div className="text-sm font-bold text-emerald-700">{u.totals.espletato}</div></div>
                  <div className="rounded-lg bg-amber-50 p-2"><div className="text-[10px] text-amber-700 font-semibold">Sospesi</div><div className="text-sm font-bold text-amber-700">{u.totals.sospeso}</div></div>
                  <div className="rounded-lg bg-red-50 p-2"><div className="text-[10px] text-red-700 font-semibold">Guasti</div><div className="text-sm font-bold text-red-700">{u.totals.guasto}</div></div>
                  <div className="rounded-lg bg-indigo-50 p-2"><div className="text-[10px] text-indigo-700 font-semibold">Migraz.</div><div className="text-sm font-bold text-indigo-700">{u.totals.migrazione}</div></div>
                </div>
                <div className="mt-3 pt-3 border-t border-slate-100">
                  <div className="text-[11px] font-semibold text-slate-500 mb-1">Giacenza personale</div>
                  <div className="flex flex-wrap gap-2 text-[11px]">
                    <span className="inline-flex items-center gap-1 bg-emerald-100 text-emerald-800 rounded-full px-2 py-0.5"><Package size={10} /> {u.stock.in_stock} in stock</span>
                    <span className="inline-flex items-center gap-1 bg-amber-100 text-amber-800 rounded-full px-2 py-0.5"><UserCheck size={10} /> {u.stock.assegnato} assegnati</span>
                    <span className="inline-flex items-center gap-1 bg-slate-100 text-slate-700 rounded-full px-2 py-0.5"><RefreshCw size={10} /> {u.stock.scaricato} scaricati</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
// ---------- Destinatari email editabili (#4) ----------
function RecipientsEditor() {
  const { recipients, saveRecipients } = useRecipients();
  const [items, setItems] = useState(recipients);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newAddr, setNewAddr] = useState("");
  useEffect(() => { setItems(recipients); }, [recipients]);

  const add = () => {
    const e = newAddr.trim();
    if (!e) return;
    if (items.includes(e)) { toast.error("Indirizzo già presente"); return; }
    setItems((p) => [...p, e]); setNewAddr("");
  };
  const remove = (idx) => setItems((p) => p.filter((_, i) => i !== idx));
  const update = (idx, val) => setItems((p) => p.map((x, i) => (i === idx ? val : x)));
  const save = async () => {
    setSaving(true);
    try { await saveRecipients(items.map((s) => s.trim()).filter(Boolean)); toast.success("Destinatari salvati"); setEditing(false); setNewAddr(""); }
    catch (e) { toast.error(errorText(e)); }
    finally { setSaving(false); }
  };
  const cancel = () => { setItems(recipients); setEditing(false); setNewAddr(""); };

  return (
    <section className="bg-white border border-slate-200 rounded-2xl card-shadow p-4 sm:p-5" data-testid="recipients-section">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-900">Destinatari email preimpostati</div>
          <div className="text-xs text-slate-500 mt-0.5">Precompilati come destinatari nell'invio Gmail</div>
        </div>
        {!editing ? (
          <button onClick={() => setEditing(true)} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-full px-3 py-1.5" data-testid="recipients-edit-btn"><Edit3 size={13} /> Modifica</button>
        ) : (
          <div className="flex gap-2">
            <button onClick={save} disabled={saving} className="inline-flex items-center gap-1 text-xs font-semibold text-white btn-primary rounded-full px-3 py-1.5 disabled:opacity-60" data-testid="recipients-save-btn">{saving ? <Loader2 className="animate-spin" size={13} /> : <Save size={13} />} Salva</button>
            <button onClick={cancel} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-full px-3 py-1.5" data-testid="recipients-cancel-btn"><X size={13} /> Annulla</button>
          </div>
        )}
      </div>
      {!editing ? (
        <div className="mt-3 flex flex-wrap gap-2" data-testid="recipients-list">
          {items.length === 0 ? <span className="text-xs text-slate-400 italic">Nessun destinatario</span> :
            items.map((r) => (<span key={r} className="text-[11px] font-mono bg-slate-100 text-slate-800 px-2 py-1 rounded-md border border-slate-200">{r}</span>))}
        </div>
      ) : (
        <div className="mt-3 space-y-2" data-testid="recipients-editor">
          {items.map((r, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input value={r} onChange={(e) => update(idx, e.target.value)} type="email"
                className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-brand-pink"
                data-testid={`recipient-input-${idx}`} />
              <button onClick={() => remove(idx)} className="text-red-500 hover:text-red-700 p-1" data-testid={`recipient-remove-${idx}`}><Trash2 size={14} /></button>
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <input value={newAddr} onChange={(e) => setNewAddr(e.target.value)} type="email"
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
              placeholder="aggiungi indirizzo email…"
              className="flex-1 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-brand-pink"
              data-testid="recipient-new-input" />
            <button onClick={add} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-full px-3 py-1.5" data-testid="recipient-add-btn"><Plus size={13} /> Aggiungi</button>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------- Pagina Istruzioni Configurazioni (#6) ----------
function InstructionsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", description: "" });
  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({ title: "", description: "" });
  const [dragIndex, setDragIndex] = useState(null);
  const [uploadingId, setUploadingId] = useState(null);
  const [uploadingFileId, setUploadingFileId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/instructions`); setItems(r.data || []); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.title.trim()) { toast.error("Inserisci un titolo"); return; }
    try { await axios.post(`${API}/instructions`, form); toast.success("Riquadro aggiunto"); setForm({ title: "", description: "" }); setCreating(false); load(); }
    catch (e) { toast.error(errorText(e)); }
  };
  const startEdit = (it) => { setEditId(it.id); setEditForm({ title: it.title, description: it.description || "" }); };
  const saveEdit = async () => {
    if (!editForm.title.trim()) { toast.error("Inserisci un titolo"); return; }
    try { await axios.patch(`${API}/instructions/${editId}`, editForm); toast.success("Riquadro aggiornato"); setEditId(null); load(); }
    catch (e) { toast.error(errorText(e)); }
  };
  const del = async (id) => {
    if (!window.confirm("Eliminare questo riquadro?")) return;
    try { await axios.delete(`${API}/instructions/${id}`); toast.success("Riquadro eliminato"); load(); }
    catch (e) { toast.error(errorText(e)); }
  };
  const uploadImage = async (id, file) => {
    if (!file) return;
    setUploadingId(id);
    try {
      const fd = new FormData(); fd.append("file", file);
      await axios.post(`${API}/instructions/${id}/image`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Immagine aggiunta"); load();
    } catch (e) { toast.error(errorText(e)); }
    finally { setUploadingId(null); }
  };
  const removeImage = async (id, imgId) => {
    try { await axios.delete(`${API}/instructions/${id}/image/${imgId}`); load(); }
    catch (e) { toast.error(errorText(e)); }
  };
  const uploadFile = async (id, file) => {
    if (!file) return;
    setUploadingFileId(id);
    try {
      const fd = new FormData(); fd.append("file", file);
      await axios.post(`${API}/instructions/${id}/file`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("File allegato"); load();
    } catch (e) { toast.error(errorText(e)); }
    finally { setUploadingFileId(null); }
  };
  const removeFile = async (id, fileId) => {
    try { await axios.delete(`${API}/instructions/${id}/file/${fileId}`); load(); }
    catch (e) { toast.error(errorText(e)); }
  };
  const onDrop = async (targetIdx) => {
    if (dragIndex === null || dragIndex === targetIdx) { setDragIndex(null); return; }
    const reordered = [...items];
    const [moved] = reordered.splice(dragIndex, 1);
    reordered.splice(targetIdx, 0, moved);
    setItems(reordered); setDragIndex(null);
    try { await axios.post(`${API}/instructions/reorder`, { ids: reordered.map((x) => x.id) }); toast.success("Ordine aggiornato"); }
    catch (e) { toast.error(errorText(e)); load(); }
  };

  return (
    <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6" data-testid="instructions-page">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-lg sm:text-xl font-display font-bold text-slate-900">Istruzioni Configurazioni</h2>
          <p className="text-xs text-slate-500 mt-0.5">Guide e configurazioni utili{isAdmin ? " — modificabili solo dagli amministratori" : ""}</p>
        </div>
        {isAdmin && !creating && (
          <button onClick={() => setCreating(true)} className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-white btn-primary rounded-full px-3 py-2" data-testid="instruction-add-btn"><Plus size={14} /> Nuovo riquadro</button>
        )}
      </div>

      {isAdmin && creating && (
        <section className="bg-white border border-brand-pink/40 rounded-2xl card-shadow p-4 sm:p-5 space-y-3" data-testid="instruction-create-form">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Titolo" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid="instruction-title-input" />
          <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Descrizione" rows={4} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid="instruction-desc-input" />
          <div className="flex gap-2">
            <button onClick={create} className="inline-flex items-center gap-1 text-xs font-semibold text-white btn-primary rounded-full px-3 py-2" data-testid="instruction-save-btn"><Save size={14} /> Salva</button>
            <button onClick={() => { setCreating(false); setForm({ title: "", description: "" }); }} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 bg-slate-100 rounded-full px-3 py-2"><X size={14} /> Annulla</button>
          </div>
        </section>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm p-6"><Loader2 className="animate-spin" size={16} /> Caricamento…</div>
      ) : items.length === 0 ? (
        <div className="border border-dashed border-slate-200 rounded-2xl p-8 text-center text-slate-500 text-sm bg-white" data-testid="instructions-empty">Nessuna istruzione disponibile.</div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-4" data-testid="instructions-grid">
          {items.map((it, idx) => (
            <section key={it.id}
              draggable={isAdmin && editId !== it.id}
              onDragStart={() => setDragIndex(idx)}
              onDragOver={(e) => { if (isAdmin) e.preventDefault(); }}
              onDrop={() => onDrop(idx)}
              className={`bg-white border rounded-2xl card-shadow p-4 sm:p-5 ${dragIndex === idx ? "border-brand-pink ring-2 ring-brand-pink/30" : "border-slate-200"} ${isAdmin && editId !== it.id ? "cursor-move" : ""}`}
              data-testid={`instruction-card-${it.id}`}>
              {editId === it.id ? (
                <div className="space-y-3">
                  <input value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid={`instruction-edit-title-${it.id}`} />
                  <textarea value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={4} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-pink" data-testid={`instruction-edit-desc-${it.id}`} />
                  <div className="flex gap-2">
                    <button onClick={saveEdit} className="inline-flex items-center gap-1 text-xs font-semibold text-white btn-primary rounded-full px-3 py-1.5" data-testid={`instruction-edit-save-${it.id}`}><Save size={13} /> Salva</button>
                    <button onClick={() => setEditId(null)} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 bg-slate-100 rounded-full px-3 py-1.5"><X size={13} /> Annulla</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-base font-display font-bold text-slate-900 inline-flex items-center gap-2">
                      {isAdmin && <GripVertical size={15} className="text-slate-300 shrink-0" title="Trascina per riordinare" />}
                      <span>{it.title}</span>
                    </h3>
                    {isAdmin && (
                      <div className="flex gap-1 shrink-0">
                        <button onClick={() => startEdit(it)} className="text-slate-500 hover:text-brand-pink p-1" data-testid={`instruction-edit-${it.id}`}><Edit3 size={15} /></button>
                        <button onClick={() => del(it.id)} className="text-red-500 hover:text-red-700 p-1" data-testid={`instruction-delete-${it.id}`}><Trash2 size={15} /></button>
                      </div>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-slate-600 whitespace-pre-wrap">{it.description || <span className="text-slate-400 italic">Nessuna descrizione</span>}</p>
                  {(it.images?.length > 0) && (
                    <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2" data-testid={`instruction-images-${it.id}`}>
                      {it.images.map((img) => (
                        <div key={img.id} className="relative group">
                          <a href={`${API}/files?path=${encodeURIComponent(img.storage_path)}`} target="_blank" rel="noopener noreferrer">
                            <img src={`${API}/files?path=${encodeURIComponent(img.storage_path)}`} alt={img.filename || "immagine"} className="w-full h-24 object-cover rounded-lg border border-slate-200" />
                          </a>
                          {isAdmin && (
                            <button onClick={() => removeImage(it.id, img.id)} className="absolute top-1 right-1 bg-white/90 text-red-600 rounded-full p-1 shadow opacity-0 group-hover:opacity-100 transition" data-testid={`instruction-img-remove-${img.id}`}><X size={12} /></button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {isAdmin && (
                    <label className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-full px-3 py-1.5 cursor-pointer" data-testid={`instruction-img-add-${it.id}`}>
                      {uploadingId === it.id ? <Loader2 className="animate-spin" size={13} /> : <ImageIcon size={13} />} Aggiungi immagine
                      <input type="file" accept="image/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; uploadImage(it.id, f); }} />
                    </label>
                  )}
                  {(it.files?.length > 0) && (
                    <div className="mt-3 space-y-1.5" data-testid={`instruction-files-${it.id}`}>
                      {it.files.map((f) => (
                        <div key={f.id} className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                          <FileText size={14} className="text-slate-500 shrink-0" />
                          <a href={`${API}/files?path=${encodeURIComponent(f.storage_path)}`} download={f.filename} target="_blank" rel="noopener noreferrer"
                            className="text-xs font-medium text-slate-700 hover:text-brand-pink truncate flex-1" data-testid={`instruction-file-download-${f.id}`}>{f.filename}</a>
                          <a href={`${API}/files?path=${encodeURIComponent(f.storage_path)}`} download={f.filename} className="text-slate-500 hover:text-brand-pink shrink-0" title="Scarica"><Download size={14} /></a>
                          {isAdmin && (
                            <button onClick={() => removeFile(it.id, f.id)} className="text-red-500 hover:text-red-700 shrink-0" data-testid={`instruction-file-remove-${f.id}`}><X size={13} /></button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {isAdmin && (
                    <label className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-full px-3 py-1.5 cursor-pointer" data-testid={`instruction-file-add-${it.id}`}>
                      {uploadingFileId === it.id ? <Loader2 className="animate-spin" size={13} /> : <Upload size={13} />} Allega file
                      <input type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; uploadFile(it.id, f); }} />
                    </label>
                  )}
                </>
              )}
            </section>
          ))}
        </div>
      )}
    </main>
  );
}

function AppContent() {
  const { user } = useAuth();
  const [notes, setNotes] = useState([]);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastCreatedIds, setLastCreatedIds] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [deleting, setDeleting] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [scanner, setScanner] = useState(null); // { onScan }
  const [scanTarget, setScanTarget] = useState(null);
  const [page, setPage] = useState(user?.role === "magazzino" ? "warehouse" : "notes");
  const [openMonths, setOpenMonths] = useState(null); // Set of open month keys; null => default (current month only)
  const [closedDays, setClosedDays] = useState(() => new Set()); // day keys explicitly collapsed
  const [recipients, setRecipients] = useState(RECIPIENTS);
  const initialLoad = useRef(true);

  const filteredNotes = notes.filter((n) => {
    if (!dateFrom && !dateTo) return true;
    const k = localDateKey(n.created_at);
    if (dateFrom && k < dateFrom) return false;
    if (dateTo && k > dateTo) return false;
    return true;
  });
  const isEspletato = (n) => (n.note_type || n.status || "limbo") === "espletato";

  const currentMonthKey = new Date().toISOString().slice(0, 7);
  const isMonthOpen = (mk) => (openMonths ? openMonths.has(mk) : mk === currentMonthKey);
  const toggleMonth = (mk) => setOpenMonths((prev) => {
    const base = new Set(prev ? prev : [currentMonthKey]);
    if (base.has(mk)) base.delete(mk); else base.add(mk);
    return base;
  });
  const isDayOpen = (dk) => !closedDays.has(dk);
  const toggleDay = (dk) => setClosedDays((prev) => {
    const s = new Set(prev);
    if (s.has(dk)) s.delete(dk); else s.add(dk);
    return s;
  });

  // Fix #3: don't unmount the list on background refetch (preserves scroll & card state)
  const fetchNotes = useCallback(async () => {
    if (initialLoad.current) setLoading(true);
    try { const r = await axios.get(`${API}/notes`, { params: { search } }); setNotes(r.data || []); }
    catch (e) { console.error(e); }
    finally { setLoading(false); initialLoad.current = false; }
  }, [search]);

  const saveRecipients = useCallback(async (list) => {
    const r = await axios.put(`${API}/email-recipients`, { recipients: list });
    setRecipients(r.data.recipients || []);
  }, []);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/email-recipients`).then((r) => setRecipients(r.data.recipients || RECIPIENTS)).catch(() => {});
  }, [user]);

  useEffect(() => {
    const t = setTimeout(fetchNotes, 200);
    return () => clearTimeout(t);
  }, [fetchNotes]);

  const handleParsed = async () => {
    const r = await axios.get(`${API}/notes`);
    setNotes(r.data || []);
    setLastCreatedIds((r.data || []).slice(0, 8).map((n) => n.id));
  };

  const toggleSelect = (id) => setSelectedIds((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);
  const allSelected = notes.length > 0 && notes.every((n) => selectedIds.includes(n.id));
  const toggleSelectAll = () => setSelectedIds(allSelected ? [] : notes.map((n) => n.id));

  const bulkDelete = async () => {
    if (!selectedIds.length) return;
    if (!window.confirm(`Eliminare ${selectedIds.length} nota/note?`)) return;
    setDeleting(true);
    try { const r = await axios.post(`${API}/notes/bulk-delete`, { ids: selectedIds }); toast.success(`${r.data.deleted} eliminate`); setSelectedIds([]); fetchNotes(); }
    catch (e) { toast.error(errorText(e)); }
    finally { setDeleting(false); }
  };

  const resetMonth = async () => {
    if (!notes.length) return;
    if (!window.confirm(`ATTENZIONE: verranno eliminate tutte le ${notes.length} note. Assicurati di aver esportato i dati prima.\n\nProcedere con il reset?`)) return;
    try {
      const r = await axios.post(`${API}/notes/bulk-delete`, { ids: notes.map((n) => n.id) });
      toast.success(`Reset completato: ${r.data.deleted} note eliminate`);
      setSelectedIds([]);
      fetchNotes();
    } catch (e) { toast.error(errorText(e)); }
  };

  const openScanner = (onScan, hintTarget) => { setScanner({ onScan }); setScanTarget(hintTarget || null); };
  const closeScanner = () => { setScanner(null); setScanTarget(null); };
  const handleScan = (value, target, snapshot) => {
    scanner?.onScan?.(value, target, snapshot);
    closeScanner();
  };

  const canSwitchPage = user?.role === "admin" || user?.role === "user" || user?.role === "magazzino";
  const effectivePage = canSwitchPage ? (page || (user?.role === "magazzino" ? "warehouse" : "notes")) : "notes";

  return (
    <RecipientsContext.Provider value={{ recipients, saveRecipients }}>
    <div className="min-h-screen">
      <Header showAdminBtn={user?.role === "admin"} onAdmin={() => setAdminOpen(true)}
        page={effectivePage} onPageChange={setPage} canSwitchPage={canSwitchPage} />
      <Toaster richColors position="top-center" />
      {effectivePage === "warehouse" ? (
        <WarehousePage onOpenAdmin={() => setAdminOpen(true)} showAdminBtn={user?.role === "admin"} />
      ) : effectivePage === "vacations" ? (
        <VacationsPage />
      ) : effectivePage === "instructions" ? (
        <InstructionsPage />
      ) : effectivePage === "dashboard" && user?.role === "admin" ? (
        <AdminDashboard />
      ) : (
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6" data-testid="main-content">
        <PdfUploader onParsed={handleParsed} />

        <StatsPanel notes={filteredNotes} onReset={resetMonth} />

        <RecipientsEditor />

        <section>
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <h2 className="text-lg sm:text-xl font-display font-bold text-slate-900">Note</h2>
            <span className="text-xs text-slate-500">{filteredNotes.length} note</span>
            <div className="ml-auto flex gap-2 flex-wrap items-center">
              <div className="inline-flex items-center gap-1 text-xs text-slate-500">
                <Calendar size={14} />
                <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="rounded-full border border-slate-200 px-2 py-1.5 text-xs" data-testid="date-from" />
                <span>–</span>
                <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="rounded-full border border-slate-200 px-2 py-1.5 text-xs" data-testid="date-to" />
                {(dateFrom || dateTo) && (
                  <button onClick={() => { setDateFrom(""); setDateTo(""); }} className="text-slate-500 hover:text-slate-900 p-1" data-testid="clear-date"><X size={12} /></button>
                )}
              </div>
              <div className="relative w-full sm:w-64">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Cerca WR, cliente o OLO"
                  className="w-full pl-9 pr-3 py-2 rounded-full border border-slate-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-pink focus:border-transparent"
                  data-testid="search-archive-input" />
              </div>
            </div>
          </div>

          {filteredNotes.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2">
              <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
                <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} className="h-4 w-4 rounded border-slate-300 accent-pink-600" data-testid="select-all-checkbox" />
                {allSelected ? "Deseleziona tutto" : "Seleziona tutto"}
              </label>
              <span className="text-xs text-slate-500" data-testid="selection-count">{selectedIds.length} selezionate</span>
              <button onClick={bulkDelete} disabled={!selectedIds.length || deleting}
                className="ml-auto rounded-full px-3 py-1.5 text-xs font-semibold text-red-600 bg-red-50 inline-flex items-center gap-2 hover:bg-red-100 disabled:opacity-40 disabled:cursor-not-allowed"
                data-testid="bulk-delete-button">
                {deleting ? <Loader2 className="animate-spin" size={14} /> : <Trash2 size={14} />} Elimina selezionate
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm p-6"><Loader2 className="animate-spin" size={16} /> Caricamento…</div>
          ) : filteredNotes.length === 0 ? (
            <div className="border border-dashed border-slate-200 rounded-2xl p-8 text-center text-slate-500 text-sm bg-white" data-testid="empty-state">
              {notes.length === 0 ? "Nessuna nota. Carica un PDF Open Fiber per iniziare." : "Nessuna nota nel range selezionato."}
            </div>
          ) : (
            <div className="space-y-4" data-testid="notes-groups">
              {(() => {
                const months = {};
                filteredNotes.forEach((n) => {
                  const mk = monthKeyOf(n.created_at);
                  (months[mk] = months[mk] || []).push(n);
                });
                const mkeys = Object.keys(months).sort().reverse();
                return mkeys.map((mk) => {
                  const monthNotes = months[mk];
                  const mopen = isMonthOpen(mk);
                  const days = {};
                  monthNotes.forEach((n) => {
                    const dk = localDateKey(n.created_at);
                    (days[dk] = days[dk] || []).push(n);
                  });
                  const dkeys = Object.keys(days).sort().reverse();
                  return (
                    <div key={mk} className="border border-slate-200 rounded-2xl bg-white overflow-hidden" data-testid={`month-folder-${mk}`}>
                      <button onClick={() => toggleMonth(mk)} className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition" data-testid={`month-toggle-${mk}`}>
                        <Folder size={18} className="text-brand-pink brand-pink" />
                        <span className="text-sm font-display font-bold text-slate-900 capitalize">{monthLabel(mk)}</span>
                        <span className="text-xs font-semibold text-slate-500 bg-slate-100 rounded-full px-2 py-0.5">{monthNotes.length}</span>
                        <span className="ml-auto text-slate-400">{mopen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
                      </button>
                      {mopen && (
                        <div className="px-3 sm:px-4 pb-4 space-y-4 border-t border-slate-100 pt-3">
                          {dkeys.map((dk) => {
                            const dayNotes = [...days[dk]].sort((a, b) => (isEspletato(a) ? 1 : 0) - (isEspletato(b) ? 1 : 0));
                            const dopen = isDayOpen(dk);
                            return (
                              <div key={dk} data-testid={`day-group-${dk}`}>
                                <button onClick={() => toggleDay(dk)} className="w-full flex items-center gap-2 mb-2 group" data-testid={`day-toggle-${dk}`}>
                                  <span className="text-slate-400 group-hover:text-slate-700">{dopen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
                                  <div className="text-xs font-mono font-semibold text-slate-700 bg-slate-100 border border-slate-200 rounded-full px-3 py-1">{humanDate(dk)}</div>
                                  <div className={`text-xs font-semibold ${days[dk].length >= DAILY_TARGET ? "text-emerald-600" : "text-slate-500"}`}>{days[dk].length} note</div>
                                  <div className="flex-1 h-px bg-slate-100" />
                                </button>
                                {dopen && (
                                  <div className="space-y-3">
                                    {dayNotes.map((n) => (
                                      <NoteCard key={n.id} note={n} defaultOpen={lastCreatedIds.includes(n.id)}
                                        onChanged={fetchNotes} selected={selectedIds.includes(n.id)} onToggleSelect={toggleSelect}
                                        onOpenScanner={openScanner} />
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </section>
      </main>
      )}
      <footer className="max-w-6xl mx-auto px-4 sm:px-6 py-6 text-center text-xs text-slate-400">
        creato e amministrato da <span className="text-slate-600 font-semibold">Giuseppe Belviso</span>
      </footer>
      {adminOpen && <AdminPanel onClose={() => setAdminOpen(false)} />}
      {scanner && <ScannerModal onClose={closeScanner} onScan={handleScan} target={scanTarget} setTarget={setScanTarget} />}
    </div>
    </RecipientsContext.Provider>
  );
}

// ---------- Root ----------
function AppRoot() {
  const { user } = useAuth();
  if (user === null) return <div className="min-h-screen flex items-center justify-center text-slate-500 text-sm"><Loader2 className="animate-spin mr-2" size={16} /> Caricamento…</div>;
  if (!user) return (<><Toaster richColors position="top-center" /><AuthScreen /></>);
  return <AppContent />;
}

export default function App() {
  return <AuthProvider><AppRoot /></AuthProvider>;
}
