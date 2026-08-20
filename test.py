#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 BUFFETT ANALYZER — Progetto completo in UN SINGOLO FILE
================================================================================
 Analizza automaticamente un report aziendale (PDF/TXT) secondo il metodo
 di Warren Buffett & Charlie Munger:

   • 40 CRITERI QUANTITATIVI  (Core Buffett 1-21 + Complementari 22-40)
   • 12 CRITERI QUALITATIVI   (con spie matematiche/formule)
   • VALUTAZIONE DCF          (su Owner Earnings + Margine di Sicurezza)

 FUNZIONAMENTO 100% AUTOMATICO: nessun inserimento manuale di dati.
 Il file crea da solo l'intero progetto (cartelle, sample, output).

 USO:
   python buffett_analyzer.py                 -> apre la GUI
   python buffett_analyzer.py bilancio.pdf    -> analisi automatica all'avvio

 DIPENDENZE: solo libreria standard (tkinter).
 Opzionale per un miglior parsing dei PDF:  pip install pypdf
================================================================================
"""

import os
import re
import sys
import math
import zlib
import datetime
import threading
import webbrowser
from dataclasses import dataclass
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("ERRORE: tkinter non disponibile. Installa Python con supporto GUI.")
    sys.exit(1)

# PDF reader opzionali (fallback puro integrato se assenti)
PdfReader = None
try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None

# ============================================================================
# COSTANTI GRAFICHE (tema dark moderno)
# ============================================================================
BG      = "#0b0e14"
PANEL   = "#11151f"
CARD    = "#161c28"
CARD2   = "#1b2333"
BORDER  = "#232c3f"
FG      = "#e8ecf4"
MUTED   = "#8a94ab"
GOLD    = "#f2b632"
GREEN   = "#2ecc71"
AMBER   = "#f39c12"
RED     = "#ff5c5c"
GRAY    = "#5a6478"
BLUE    = "#4da3ff"

F_TITLE  = ("Segoe UI", 20, "bold")
F_SUB    = ("Segoe UI", 9)
F_H2     = ("Segoe UI", 13, "bold")
F_BODY   = ("Segoe UI", 10)
F_SMALL  = ("Segoe UI", 9)
F_TINY   = ("Segoe UI", 8)
F_CARD_T = ("Segoe UI", 10, "bold")
F_MONO   = ("Consolas", 9)

STATUS_META = {
    "pass": (GREEN, "✔ OK"),
    "warn": (AMBER, "◑ PARZIALE"),
    "partial": (AMBER, "◑ PARZIALE"),
    "fail": (RED,   "✘ CRITICO"),
    "nd":   (GRAY,  "… N/D"),
}
QSTATUS_META = {
    "pass":    (GREEN, "✔ SUPERATO"),
    "partial": (AMBER, "◑ PARZIALE"),
    "fail":    (RED,   "✘ NON SUPERATO"),
    "nd":      (GRAY,  "… N/D"),
}

APP_TITLE = "BUFFETT ANALYZER"
VERSION   = "1.0.0"

# ============================================================================
# SETUP PROGETTO — il file crea da solo tutta la struttura
# ============================================================================
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
OUTPUT_DIR  = os.path.join(BASE_DIR, "outputs")
SAMPLE_FILE = os.path.join(SAMPLES_DIR, "sample_report.txt")

SAMPLE_REPORT = """AURELIA S.P.A. — RELAZIONE FINANZIARIA ANNUALE 2025
Valori espressi in milioni di Euro

=== CONTO ECONOMICO ===
Ricavi: 2023 4.820, 2024 5.240, 2025 5.710
Costo del venduto: 2023 2.650, 2024 2.860, 2025 3.080
Margine operativo lordo (EBITDA): 1.500
Spese SG&A: 2025 690
Risultato operativo (EBIT): 2023 1.010, 2024 1.150, 2025 1.290
Oneri finanziari (interessi passivi): 45
Utile netto: 2023 720, 2024 830, 2025 940
Ammortamenti: 210
Spese ricerca e sviluppo (R&D): 85
Aliquota fiscale effettiva: 24%

=== STATO PATRIMONIALE ===
Attività correnti: 2.900
Rimanenze di magazzino: 480
Crediti verso clienti: 860
Cassa e equivalenti: 1.150
Totale attivo: 8.400
Passività correnti: 1.350
Debito a lungo termine: 1.600
Debito totale: 2.050
Patrimonio netto: 4.300

=== RENDICONTO FINANZIARIO ===
Flusso di cassa operativo: 1.180
Spese in conto capitale (CapEx): 260
Free cash flow: 920

=== DATI DI MERCATO ===
Azioni in circolazione: 250 milioni
Prezzo azione: 62,40 Euro
Capitalizzazione di mercato: 15.600 milioni
Dividendi distribuiti: 230
"""


def ensure_project():
    """Crea l'intera struttura del progetto al primo avvio."""
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(SAMPLE_FILE):
        with open(SAMPLE_FILE, "w", encoding="utf-8") as f:
            f.write(SAMPLE_REPORT)


# ============================================================================
# ESTRAZIONE TESTO DA PDF / TXT
# ============================================================================
def _pure_pdf_text(data: bytes) -> str:
    """Estrattore PDF minimale con sola libreria standard (FlateDecode + Tj/TJ)."""
    chunks = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        raw = data[start:end]
        try:
            dec = zlib.decompress(raw)
        except Exception:
            dec = raw
        for t in re.findall(rb"\((?:\\.|[^\\()])*\)", dec):
            s = t[1:-1]
            s = s.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
            try:
                chunks.append(s.decode("latin-1"))
            except Exception:
                pass
        chunks.append("\n")
    return "\n".join(chunks)


def extract_text_from_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        text = ""
        if PdfReader is not None:
            try:
                reader = PdfReader(path)
                text = "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception:
                text = ""
        if not text.strip():
            with open(path, "rb") as f:
                text = _pure_pdf_text(f.read())
        return text
    # file di testo
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    raise ValueError("Formato file non leggibile")


# ============================================================================
# PARSER FINANZIARIO AUTOMATICO (keyword IT/EN + numeri)
# ============================================================================
ACCENTS = str.maketrans(
    "àáâäèéêëìíîïòóôöùúûüçÀÁÂÄÈÉÊËÌÍÎÏÒÓÔÖÙÚÛÜÇ",
    "aaaaeeeeiiiioooouuuucAAAAEEEEIIIIOOOOUUUUC",
)

NUM_RE = re.compile(r"""
      \(\s*[€$]?\s*\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?\s*\)     # (1.234,56)
    | [-−]\s*[€$]?\s*\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?        # -1.234,5
    | \d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?                        # 1.234,56
    | \d+(?:[.,]\d{1,2})?\s?%?                                 # 940 / 62,40 / 16,5%
""", re.X)


def parse_number_token(tok: str) -> Optional[float]:
    t = tok.strip()
    if not t:
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1].strip()
    if t and t[0] in "-−":
        neg, t = True, t[1:].strip()
    t = t.replace("€", "").replace("$", "").replace(" ", "").rstrip("%")
    if not re.search(r"\d", t):
        return None
    dots, commas = t.count("."), t.count(",")
    if dots and commas:
        if t.rfind(".") > t.rfind(","):
            t = t.replace(",", "")
        else:
            t = t.replace(".", "").replace(",", ".")
    elif commas:
        if commas >= 2:
            t = t.replace(",", "")
        else:
            head, _, tail = t.partition(",")
            if tail.isdigit() and len(tail) == 3 and head not in ("", "0"):
                t = t.replace(",", "")
            else:
                t = t.replace(",", ".")
    elif dots:
        if dots >= 2:
            t = t.replace(".", "")
        else:
            head, _, tail = t.partition(".")
            if tail.isdigit() and len(tail) == 3 and head not in ("", "0"):
                t = t.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def norm_line(line: str) -> str:
    return line.lower().translate(ACCENTS).replace("\u00a0", " ")


def strip_years(line: str) -> str:
    years = re.findall(r"\b(?:19|20)\d{2}\b", line)
    if len(years) >= 2:
        return re.sub(r"\b(?:19|20)\d{2}\b", " ", line)
    return re.sub(r"\b(?:19|20)\d{2}\b(?=\s*[€$]?\s*\d)", " ", line)


def extract_numbers_from_line(line: str, allow_percent=False):
    """Restituisce la lista dei valori numerici trovati nella riga."""
    clean = strip_years(line)
    out = []
    for m in NUM_RE.finditer(clean):
        tok = m.group(0)
        is_pct = tok.rstrip().endswith("%")
        if is_pct and not allow_percent:
            continue
        v = parse_number_token(tok)
        if v is None:
            continue
        if not is_pct:
            nxt = clean[m.end(): m.end() + 16].lower()
            if re.match(r"\s*(miliard|mld|bn|billion)", nxt):
                v *= 1000.0
        out.append((v, is_pct))
    if len(out) > 1:  # rimuove eventuali anni residui (1900-2099)
        out = [x for x in out if not (x[1] is False and x[0] == int(x[0]) and 1900 <= x[0] <= 2099)]
    return out


# (chiave, pattern inclusi, pattern esclusi, accetta_percentuali)
SPECS = [
    ("ricavi",       [r"ricav", r"revenue", r"fatturato", r"\bsales\b", r"turnover"],
                     [r"margine", r"costo", r"crescita", r"growth", r"variazione"], False),
    ("cogs",         [r"costo del venduto", r"cost of goods sold", r"\bcogs\b", r"cost of sales",
                      r"cost of revenue", r"costo dei ricavi"], [], False),
    ("ebitda",       [r"ebitda", r"margine operativo lordo"], [], False),
    ("ebit",         [r"ebit(?!da)", r"risultato operativo", r"operating income",
                      r"operating profit", r"utile operativo", r"reddito operativo"],
                     [r"ebitda", r"margine operativo lordo"], False),
    ("net_income",   [r"utile netto", r"net income", r"net profit", r"risultato netto",
                      r"profit for the (?:year|period)", r"utile del gruppo"],
                     [r"per azione", r"per share", r"\beps\b"], False),
    ("depreciation", [r"ammortament", r"depreciation"], [], False),
    ("capex",        [r"capex", r"conto capitale", r"capital expenditure",
                      r"investimenti in immobilizzazioni"], [], False),
    ("cfo",          [r"flusso di cassa operativo", r"flusso di cassa da attivit",
                      r"cash flow operativo", r"cash flow from operat",
                      r"operating cash flow"], [r"free", r"libero"], False),
    ("fcf",          [r"free cash flow", r"flusso di cassa libero", r"\bfcf\b"], [], False),
    ("equity",       [r"patrimonio netto", r"shareholders? equity", r"stockholders? equity",
                      r"net equity", r"capitale proprio"], [r"vincolato"], False),
    ("total_debt",   [r"debito totale", r"total debt", r"debiti totali",
                      r"indebitamento totale", r"debito finanziario lordo"], [], False),
    ("net_debt",     [r"posizione finanziaria netta", r"net debt", r"indebitamento netto"], [], False),
    ("lt_debt",      [r"(?:debito|finanziamenti).{0,20}lungo termine", r"long[- ]term debt"], [], False),
    ("cassa",        [r"cassa e (?:mezzi )?equivalenti", r"cash and (?:cash )?equivalents",
                      r"disponibilit liquide", r"cassa e banche"], [], False),
    ("total_assets", [r"totale attiv", r"total assets", r"attivo totale",
                      r"totale dell.attivo"], [], False),
    ("current_assets",[r"attivit correnti", r"attivo corrente", r"current assets"], [], False),
    ("current_liab", [r"passivit correnti", r"passivo corrente", r"current liabilities"], [], False),
    ("inventory",    [r"rimanenze", r"inventor"], [], False),
    ("crediti",      [r"crediti (?:commerciali|verso clienti)", r"accounts receivable",
                      r"trade receivables"], [], False),
    ("interessi",    [r"interessi passivi", r"interest expense", r"oneri finanziari"], [], False),
    ("sga",          [r"sg&a", r"\bsga\b", r"spese generali", r"selling,? general",
                      r"administrative expenses", r"costi commerciali"], [], False),
    ("rnd",          [r"ricerca e sviluppo", r"r&d", r"research and development"], [], False),
    ("shares",       [r"azioni in circolazione", r"shares outstanding",
                      r"numero (?:di )?azioni", r"number of shares"], [], False),
    ("price",        [r"prezzo (?:per )?azione", r"share price", r"stock price",
                      r"prezzo di chiusura"], [], False),
    ("market_cap",   [r"capitalizzazione", r"market cap"], [], False),
    ("dividendi",    [r"dividendi (?:distribuiti|pagati|totali)", r"dividends (?:paid|declared|total)",
                      r"\bdividendi\b", r"\bdividends\b"], [r"payout"], False),
    ("tax_rate",     [r"aliquota fiscale", r"tax rate", r"aliquota effettiva"], [], True),
]


def extract_financials(text: str):
    """Estrazione automatica delle grandezze finanziarie dal testo del report."""
    D, S, log = {}, {}, []
    lines = [ln.strip() for ln in re.split(r"[\n\r]+", text) if ln.strip()]
    for key, inc_pats, exc_pats, allow_pct in SPECS:
        found = False
        for idx, raw in enumerate(lines):
            line = norm_line(raw)
            if any(re.search(p, line) for p in exc_pats):
                continue
            if not any(re.search(p, line) for p in inc_pats):
                continue
            nums = extract_numbers_from_line(raw, allow_percent=allow_pct)
            vals = [v for v, pct in nums if (pct == bool(allow_pct)) or (not allow_pct and not pct)]
            if allow_pct:
                pcts = [v for v, pct in nums if pct]
                if pcts:
                    D[key] = pcts[-1] / 100.0
                    S[key] = [v / 100.0 for v in pcts]
                    log.append(("ok", f"{key:14s} = {D[key]*100:.1f}%  (riga {idx+1})"))
                    found = True
                    break
                continue
            if vals:
                D[key] = vals[-1]          # ultimo valore = anno più recente
                S[key] = vals
                serie = " → ".join(fmt(v, 0) for v in vals) if len(vals) > 1 else ""
                log.append(("ok", f"{key:14s} = {fmt(vals[-1])}  {serie}  (riga {idx+1})"))
                found = True
                break
        if not found:
            log.append(("nd", f"{key:14s} = non trovato nel documento"))

    # ---- fallback / derivazioni automatiche ----
    if "total_debt" not in D and "net_debt" in D and "cassa" in D:
        D["total_debt"] = D["net_debt"] + D["cassa"]
        log.append(("ok", "total_debt    = derivato da posizione finanziaria netta + cassa"))
    if "lt_debt" not in D and "total_debt" in D:
        D["lt_debt"] = D["total_debt"]
    if "fcf" not in D and "cfo" in D and "capex" in D:
        D["fcf"] = D["cfo"] - D["capex"]
        log.append(("ok", "fcf           = derivato da CFO − CapEx"))
    if "capex" not in D and "cfo" in D and "fcf" in D:
        D["capex"] = D["cfo"] - D["fcf"]
        log.append(("ok", "capex         = derivato da CFO − FCF"))
    if "ebit" not in D and "ebitda" in D and "depreciation" in D:
        D["ebit"] = D["ebitda"] - D["depreciation"]
        log.append(("ok", "ebit          = derivato da EBITDA − Ammortamenti"))
    if "ricavi" in D and "cogs" in D:
        D["gross_profit"] = D["ricavi"] - D["cogs"]
    return D, S, log


# ============================================================================
# UTILITÀ DI CALCOLO
# ============================================================================
def safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def cagr_of(series):
    if not series or len(series) < 2 or series[0] <= 0 or series[-1] <= 0:
        return None
    return (series[-1] / series[0]) ** (1.0 / (len(series) - 1)) - 1.0


def fmt(v, dec=1):
    if v is None:
        return "N/D"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_pct(v, dec=1):
    return "N/D" if v is None else f"{fmt(v, dec)}%"


def status_from(value, pass_cond, warn_cond):
    if value is None:
        return "nd"
    if pass_cond:
        return "pass"
    if warn_cond:
        return "warn"
    return "fail"


# ============================================================================
# MOTORE DCF — VALORE INTRINSECO SU OWNER EARNINGS
# ============================================================================
def compute_dcf(D, S):
    cfo, capex = D.get("cfo"), D.get("capex")
    oe = (cfo - capex) if (cfo is not None and capex is not None) else None
    base = oe if (oe is not None and oe > 0) else D.get("fcf")
    if base is None or base <= 0:
        base = D.get("net_income")
    if base is None or base <= 0:
        return {"ok": False}

    cagr_e = cagr_of(S.get("net_income"))
    if cagr_e is not None:
        g1 = max(0.0, min(cagr_e, 0.08))       # crescita fase 1 (prudenziale, max 8%)
    else:
        g1 = 0.04
    r, g, n = 0.10, 0.025, 10                  # sconto 10%, crescita perpetua 2,5%, 10 anni

    flows, pv_sum = [], 0.0
    for t in range(1, n + 1):
        f = base * (1 + g1) ** t
        flows.append(f)
        pv_sum += f / (1 + r) ** t
    tv = flows[-1] * (1 + g) / (r - g)
    pv_tv = tv / (1 + r) ** n
    iv = pv_sum + pv_tv

    shares, price = D.get("shares"), D.get("price")
    mcap = D.get("market_cap")
    if mcap is None and price and shares:
        mcap = price * shares
    iv_share = iv / shares if shares else None
    mos = ((iv - mcap) / iv * 100.0) if mcap else None
    return {"ok": True, "base": base, "base_is_oe": oe is not None and oe > 0,
            "g1": g1, "r": r, "g": g, "n": n, "flows": flows, "tv": tv,
            "iv": iv, "iv_share": iv_share, "mcap": mcap, "mos": mos,
            "price": price, "cagr_used": cagr_e}


# ============================================================================
# 40 CRITERI QUANTITATIVI
# ============================================================================
@dataclass
class Metric:
    code: str
    name: str
    tag: str
    value: Optional[float]
    value_text: str
    threshold: str
    status: str
    core: bool
    detail: str = ""


def build_quant(D, S, dcf):
    Q = []
    add = lambda *a, **k: Q.append(Metric(*a, **k))

    ric  = D.get("ricavi");  cogs = D.get("cogs");  ni = D.get("net_income")
    gp   = D.get("gross_profit")
    ebit = D.get("ebit");    eq = D.get("equity");  td = D.get("total_debt")
    cash = D.get("cassa");   ltd = D.get("lt_debt")
    cfo  = D.get("cfo");     capex = D.get("capex"); fcf = D.get("fcf")
    oe   = (cfo - capex) if (cfo is not None and capex is not None) else None
    tax  = D.get("tax_rate", 0.24)
    shares, price, mcap = D.get("shares"), D.get("price"), D.get("market_cap")
    if mcap is None and price and shares:
        mcap = price * shares
    ta, ca, cl = D.get("total_assets"), D.get("current_assets"), D.get("current_liab")
    cred, intx = D.get("crediti"), D.get("interessi")
    sga, rnd, div = D.get("sga"), D.get("rnd"), (D.get("dividendi") or 0.0)
    nopat = ebit * (1 - tax) if ebit is not None else None
    ic = (eq + td - (cash or 0.0)) if (eq is not None and td is not None) else None

    # ---- 1. Owner Earnings ----
    st = status_from(oe, oe is not None and ni is not None and oe >= ni, oe is not None and oe > 0)
    add("Q01", "Owner Earnings", "Pilastro fondamentale · Cassa reale",
        oe, "N/D" if oe is None else fmt(oe, 0), "Crescente e ≥ Utile Netto", st, True,
        f"CFO {fmt(cfo,0)} − CapEx {fmt(capex,0)}")

    # ---- 2. ROIC ----
    roic = safe_div(nopat, ic)
    roic_v = roic * 100 if roic is not None else None
    add("Q02", "ROIC", "Efficienza del capitale",
        roic_v, fmt_pct(roic_v), "> 15% costante (Economic Moat)",
        status_from(roic_v, roic_v is not None and roic_v > 15, roic_v is not None and roic_v >= 10), True,
        f"NOPAT {fmt(nopat,0)} / Capitale investito {fmt(ic,0)}")

    # ---- 3. ROE ----
    roe = safe_div(ni, eq)
    roe_v = roe * 100 if roe is not None else None
    add("Q03", "ROE", "Redditività dell'equity",
        roe_v, fmt_pct(roe_v), "> 15% costante (basso debito)",
        status_from(roe_v, roe_v is not None and roe_v > 15, roe_v is not None and roe_v >= 10), True,
        f"Utile {fmt(ni,0)} / Patrimonio Netto {fmt(eq,0)}")

    # ---- 4. Anni per estinguere il debito ----
    yrs = safe_div(ltd, ni)
    add("Q04", "Anni per estinguere il debito", "Solvibilità",
        yrs, "N/D" if yrs is None else f"{fmt(yrs,2)} anni", "< 3–4 anni",
        status_from(yrs, yrs is not None and yrs < 3, yrs is not None and yrs <= 4), True,
        f"Debito LT {fmt(ltd,0)} / Utile {fmt(ni,0)}")

    # ---- 5. Debt/Equity ----
    de = safe_div(td, eq)
    add("Q05", "Debt / Equity", "Leva finanziaria",
        de, fmt(de, 2), "< 0,5",
        status_from(de, de is not None and de < 0.5, de is not None and de <= 1.0), True,
        f"Debito {fmt(td,0)} / Equity {fmt(eq,0)}")

    # ---- 6. Margine Lordo ----
    gm = safe_div(gp, ric)
    gm_v = gm * 100 if gm is not None else None
    add("Q06", "Margine Lordo", "Pricing power",
        gm_v, fmt_pct(gm_v), "> 40% (vantaggio competitivo)",
        status_from(gm_v, gm_v is not None and gm_v > 40, gm_v is not None and gm_v >= 30), True,
        f"(Ricavi {fmt(ric,0)} − COGS {fmt(cogs,0)}) / Ricavi")

    # ---- 7. Margine Netto ----
    nm = safe_div(ni, ric)
    nm_v = nm * 100 if nm is not None else None
    add("Q07", "Margine Netto", "Efficienza finale",
        nm_v, fmt_pct(nm_v), "> 15%–20%",
        status_from(nm_v, nm_v is not None and nm_v >= 15, nm_v is not None and nm_v >= 10), True,
        f"Utile {fmt(ni,0)} / Ricavi {fmt(ric,0)}")

    # ---- 8. Valore Intrinseco (DCF) ----
    iv = dcf.get("iv") if dcf.get("ok") else None
    add("Q08", "Valore Intrinseco (DCF Owner Earnings)", "Valutazione",
        iv, "N/D" if iv is None else fmt(iv, 0),
        "Tasso sconto prudente 9–10%, g perpetua 2–3%",
        "pass" if iv else "nd", True,
        "" if iv is None else f"Base {fmt(dcf['base'],0)} · r=10% · g=2,5% · n=10")

    # ---- 9. Margine di Sicurezza ----
    mos = dcf.get("mos") if dcf.get("ok") else None
    add("Q09", "Margine di Sicurezza", "Protezione dal rischio",
        mos, fmt_pct(mos), "Sconto 20%–30% sul valore intrinseco",
        status_from(mos, mos is not None and mos >= 30, mos is not None and mos >= 20), True,
        "" if mos is None else f"(VI {fmt(iv,0)} − Market Cap {fmt(dcf.get('mcap'),0)}) / VI")

    # ---- 10. Test del $1 trattenuto ----
    proxy = safe_div(mcap, eq)
    if proxy is not None:
        st, det = ("pass" if proxy >= 1.5 else "partial"), f"Proxy statico Market Cap/Equity = {fmt(proxy,2)} (test completo richiede serie storica)"
    else:
        st, det = "nd", "Richiede serie storica pluriennale"
    add("Q10", "Test del $1 di utile trattenuto", "Qualità del management",
        proxy, "N/D" if proxy is None else fmt(proxy, 2), "> $1,00 di valore per $1 trattenuto", st, True, det)

    # ---- 11. CapEx Ratio ----
    cxr = safe_div(capex, ni)
    cxr_v = cxr * 100 if cxr is not None else None
    add("Q11", "CapEx Ratio", "Business asset-light",
        cxr_v, fmt_pct(cxr_v), "< 25%–30%",
        status_from(cxr_v, cxr_v is not None and cxr_v <= 30, cxr_v is not None and cxr_v <= 50), True,
        f"CapEx {fmt(capex,0)} / Utile {fmt(ni,0)}")

    # ---- 12. Buyback rate ----
    add("Q12", "Share Buyback Rate", "Allocazione capitale", None, "N/D",
        "Riduzione azioni 1%–3% annuo", "nd", True, "Richiede serie storica azioni")

    # ---- 13. SGA / Utile Lordo ----
    den13 = gp if gp else ric
    sgar = safe_div(sga, den13)
    sgar_v = sgar * 100 if sgar is not None else None
    add("Q13", "Spese SG&A / Utile Lordo", "Costi strutturali",
        sgar_v, fmt_pct(sgar_v), "< 30%",
        status_from(sgar_v, sgar_v is not None and sgar_v < 30, sgar_v is not None and sgar_v <= 40), True,
        f"SGA {fmt(sga,0)} / {'Margine Lordo' if gp else 'Ricavi'} {fmt(den13,0)}")

    # ---- 14. R&D / Utile Lordo ----
    den14 = gp if gp else ric
    rdr = safe_div(rnd, den14)
    rdr_v = (rdr * 100) if rdr is not None else (0.0 if ric else None)
    add("Q14", "Spese R&D / Utile Lordo", "Rischio obsolescenza",
        rdr_v, fmt_pct(rdr_v), "< 15%",
        status_from(rdr_v, rdr_v is not None and rdr_v <= 15, rdr_v is not None and rdr_v <= 25), True,
        "R&D non dichiarata → incidenza nulla" if rnd is None else f"R&D {fmt(rnd,0)}")

    # ---- 15. Cash Conversion ----
    cc = safe_div(fcf, ni)
    add("Q15", "Cash Conversion Rate", "Qualità del bilancio",
        cc, fmt(cc, 2), "≥ 1,0 (assenza di artifici contabili)",
        status_from(cc, cc is not None and cc >= 1.0, cc is not None and cc >= 0.8), True,
        f"FCF {fmt(fcf,0)} / Utile {fmt(ni,0)}")

    # ---- 16. Earnings Yield ----
    eps = safe_div(ni, shares)
    ey = safe_div(eps, price)
    ey_v = ey * 100 if ey is not None else None
    add("Q16", "Earnings Yield", "Rendimento azionario",
        ey_v, fmt_pct(ey_v), "Premio netto rispetto al risk-free",
        status_from(ey_v, ey_v is not None and ey_v > 5, ey_v is not None and ey_v >= 3.5), True,
        f"EPS {fmt(eps,2)} / Prezzo {fmt(price,2)}")

    # ---- 17. FCF Yield ----
    ev = (mcap + td - (cash or 0.0)) if (mcap and td is not None) else None
    fy = safe_div(fcf, ev)
    fy_v = fy * 100 if fy is not None else None
    add("Q17", "Free Cash Flow Yield", "Rendimento di cassa",
        fy_v, fmt_pct(fy_v), "> 6%–7%",
        status_from(fy_v, fy_v is not None and fy_v > 7, fy_v is not None and fy_v >= 6), True,
        f"FCF {fmt(fcf,0)} / EV {fmt(ev,0)}")

    # ---- 18. SGR ----
    payout = safe_div(div, ni) or 0.0
    sgr = roe_v * (1 - payout) if roe_v is not None else None
    add("Q18", "Sustainable Growth Rate", "Crescita interna",
        sgr, fmt_pct(sgr), "Elevato e coerente con lo storico",
        status_from(sgr, sgr is not None and sgr >= 10, sgr is not None and sgr >= 5), True,
        f"ROE {fmt_pct(roe_v)} × (1 − payout {fmt(payout*100,1)}%)")

    # ---- 19. Retention Rate ----
    rr = (1 - payout) * 100
    add("Q19", "Retention Rate", "Reinvestimento utili",
        rr, fmt_pct(rr), "Dipende dalle opportunità ad alto ROIC",
        "warn" if payout > 0.8 else "pass", True, f"Payout {fmt(payout*100,1)}%")

    # ---- 20. Compounding ----
    if sgr is not None:
        fv = 10000 * (1 + sgr / 100) ** 10
        add("Q20", "Crescita Composta (FV 10 anni)", "Effetto compounding",
            fv, fmt(fv, 0), "Focus sulla capitalizzazione di lungo periodo",
            "pass" if sgr >= 10 else "warn", True,
            f"10.000 al tasso SGR {fmt(sgr,1)}% per 10 anni")
    else:
        add("Q20", "Crescita Composta (FV 10 anni)", "Effetto compounding",
            None, "N/D", "Focus sulla capitalizzazione di lungo periodo", "nd", True)

    # ---- 21. Buffett Indicator ----
    add("Q21", "Buffett Indicator", "Macro valutazione di mercato", None, "N/D",
        "< 80% acquisto · > 120% sopravvalutato", "nd", True,
        "Dato macro (Market Cap/GDP) non presente nel report")

    # ---- 22. Margine Operativo ----
    om = safe_div(ebit, ric)
    om_v = om * 100 if om is not None else None
    add("Q22", "Margine Operativo", "Gestione caratteristica",
        om_v, fmt_pct(om_v), "> 20%",
        status_from(om_v, om_v is not None and om_v > 20, om_v is not None and om_v >= 10), False,
        f"EBIT {fmt(ebit,0)} / Ricavi {fmt(ric,0)}")

    # ---- 23. CAGR ----
    c_ric, c_ni = cagr_of(S.get("ricavi")), cagr_of(S.get("net_income"))
    best = c_ni if c_ni is not None else c_ric
    best_v = best * 100 if best is not None else None
    parti = []
    if c_ric is not None:
        parti.append("Ricavi " + fmt_pct(c_ric * 100))
    if c_ni is not None:
        parti.append("Utili " + fmt_pct(c_ni * 100))
    txt23 = " · ".join(parti) if parti else "N/D"
    add("Q23", "CAGR Utili / Ricavi", "Crescita storica composta",
        best_v, txt23, "> 5% annuo",
        status_from(best_v, best_v is not None and best_v > 5, best_v is not None and best_v >= 0), False,
        "Serie storica estratta dal report" if best is not None else "Serve serie pluriennale")

    # ---- 24. FCF ----
    add("Q24", "Free Cash Flow", "Liquidità",
        fcf, fmt(fcf, 0), "> 0",
        status_from(fcf, fcf is not None and fcf > 0, fcf is not None and fcf >= 0), False,
        f"CFO {fmt(cfo,0)} − CapEx {fmt(capex,0)}")

    # ---- 25. FCF Margin ----
    fm = safe_div(fcf, ric)
    fm_v = fm * 100 if fm is not None else None
    add("Q25", "FCF Margin", "Efficienza di cassa",
        fm_v, fmt_pct(fm_v), "> 10%",
        status_from(fm_v, fm_v is not None and fm_v > 10, fm_v is not None and fm_v >= 5), False)

    # ---- 26. EPS ----
    add("Q26", "EPS (Utile per Azione)", "Redditività azionaria",
        eps, fmt(eps, 2), "> 0 e crescente",
        status_from(eps, eps is not None and eps > 0, eps is not None and eps >= 0), False,
        f"Utile {fmt(ni,0)} / Azioni {fmt(shares,0)}")

    # ---- 27. Interest Coverage ----
    if intx is not None and intx > 0 and ebit is not None:
        icr = ebit / intx
    elif intx == 0 and ebit is not None:
        icr = float("inf")
    else:
        icr = None
    add("Q27", "Interest Coverage", "Solvibilità interessi",
        icr if icr != float("inf") else 999, "N/D" if icr is None else ("∞" if icr == float("inf") else fmt(icr, 1) + "×"),
        "> 5 (ideale > 10)",
        status_from(icr, icr is not None and icr > 10, icr is not None and icr >= 5), False,
        f"EBIT {fmt(ebit,0)} / Interessi {fmt(intx,0)}")

    # ---- 28. Current Ratio ----
    cr = safe_div(ca, cl)
    add("Q28", "Current Ratio", "Liquidità breve",
        cr, fmt(cr, 2), "> 1,5",
        status_from(cr, cr is not None and cr > 1.5, cr is not None and cr >= 1.0), False,
        f"Attività correnti {fmt(ca,0)} / Passività correnti {fmt(cl,0)}")

    # ---- 29. Quick Ratio ----
    qr = safe_div(((cash or 0) + (cred or 0)), cl)
    add("Q29", "Quick Ratio", "Liquidità immediata",
        qr, fmt(qr, 2), "≥ 1,0",
        status_from(qr, qr is not None and qr >= 1.0, qr is not None and qr >= 0.7), False,
        f"(Cassa {fmt(cash,0)} + Crediti {fmt(cred,0)}) / Pass. correnti {fmt(cl,0)}")

    # ---- 30. ROA ----
    roa = safe_div(ni, ta)
    roa_v = roa * 100 if roa is not None else None
    add("Q30", "ROA", "Efficienza sugli asset",
        roa_v, fmt_pct(roa_v), "> 10%",
        status_from(roa_v, roa_v is not None and roa_v > 10, roa_v is not None and roa_v >= 5), False)

    # ---- 31. ROCE ----
    roce = safe_div(ebit, (ta - cl) if (ta is not None and cl is not None) else None)
    roce_v = roce * 100 if roce is not None else None
    add("Q31", "ROCE", "Capitale impiegato",
        roce_v, fmt_pct(roce_v), "> 15%",
        status_from(roce_v, roce_v is not None and roce_v > 15, roce_v is not None and roce_v >= 10), False,
        f"EBIT / (Totale attivo {fmt(ta,0)} − Pass. corr. {fmt(cl,0)})")

    # ---- 32. P/E ----
    pe = safe_div(price, eps)
    add("Q32", "P/E", "Multiplo di mercato",
        pe, fmt(pe, 1), "< 15 interessante",
        status_from(pe, pe is not None and pe < 15, pe is not None and pe <= 25), False,
        f"Prezzo {fmt(price,2)} / EPS {fmt(eps,2)}")

    # ---- 33. PEG ----
    g_peg = (c_ni * 100) if c_ni is not None else None
    peg = (pe / g_peg) if (pe is not None and g_peg and g_peg > 0) else None
    add("Q33", "PEG Ratio", "Multiplo corretto per crescita",
        peg, fmt(peg, 2), "< 1,0 sottovalutazione relativa",
        status_from(peg, peg is not None and peg < 1, peg is not None and peg <= 1.5), False,
        f"P/E {fmt(pe,1)} / crescita utili {fmt_pct(g_peg)}")

    # ---- 34. P/B ----
    bvps = safe_div(eq, shares)
    pb = safe_div(price, bvps)
    add("Q34", "Price / Book Value", "Multiplo contabile",
        pb, fmt(pb, 2), "< 3 (contesto ROE elevato)",
        status_from(pb, pb is not None and pb < 3, pb is not None and pb <= 6), False,
        f"Prezzo {fmt(price,2)} / BVPS {fmt(bvps,2)}")

    # ---- 35. EV/EBIT ----
    eve = safe_div(ev, ebit)
    add("Q35", "EV / EBIT", "Valutazione globale",
        eve, fmt(eve, 1), "< 12",
        status_from(eve, eve is not None and eve < 12, eve is not None and eve <= 18), False,
        f"EV {fmt(ev,0)} / EBIT {fmt(ebit,0)}")

    # ---- 36. EV/FCF ----
    evf = safe_div(ev, fcf)
    add("Q36", "EV / FCF", "Valutazione su cassa",
        evf, fmt(evf, 1), "< 15",
        status_from(evf, evf is not None and evf < 15, evf is not None and evf <= 25), False,
        f"EV {fmt(ev,0)} / FCF {fmt(fcf,0)}")

    # ---- 37. Payout Ratio ----
    po = payout * 100
    add("Q37", "Dividend Payout Ratio", "Politica dividendi",
        po, fmt_pct(po), "< 60% sostenibile",
        status_from(po, po <= 60, po <= 80), False)

    # ---- 38. Debt Ratio ----
    dr = safe_div(td, ta)
    dr_v = dr * 100 if dr is not None else None
    add("Q38", "Debt Ratio", "Struttura patrimoniale",
        dr_v, fmt_pct(dr_v), "< 40%",
        status_from(dr_v, dr_v is not None and dr_v < 40, dr_v is not None and dr_v <= 60), False)

    # ---- 39. Interest-Bearing Debt Ratio ----
    ibd = safe_div(td, eq)
    add("Q39", "Debito Oneroso / Equity", "Peso del debito finanziario",
        ibd, fmt(ibd, 2), "< 0,5",
        status_from(ibd, ibd is not None and ibd < 0.5, ibd is not None and ibd <= 1.0), False)

    # ---- 40. CAGR Book Value ----
    add("Q40", "CAGR Book Value per Azione", "Storico patrimonio", None, "N/D",
        "Crescita composta del BVPS", "nd", False, "Richiede serie storica pluriennale")
    return Q


# ============================================================================
# 12 CRITERI QUALITATIVI (con spie matematiche)
# ============================================================================
def build_qual(D, S, dcf):
    K = []
    ric, cogs, ni, ebit = D.get("ricavi"), D.get("cogs"), D.get("net_income"), D.get("ebit")
    gp = D.get("gross_profit")
    eq, ltd, ta = D.get("equity"), D.get("lt_debt"), D.get("total_assets")
    cfo, capex, fcf = D.get("cfo"), D.get("capex"), D.get("fcf")
    sga, rnd = D.get("sga"), D.get("rnd")
    mcap = D.get("market_cap") or ((D.get("price") or 0) * (D.get("shares") or 0) or None)
    tax = D.get("tax_rate", 0.24)

    gm = safe_div(gp, ric)
    gm_v = gm * 100 if gm is not None else None
    roic = safe_div(ebit * (1 - tax) if ebit is not None else None,
                    (eq + (D.get("total_debt") or 0) - (D.get("cassa") or 0)) if eq is not None else None)
    roic_v = roic * 100 if roic is not None else None

    def add(n, title, desc, formula, status, note):
        K.append({"n": n, "title": title, "desc": desc, "formula": formula,
                  "status": status, "note": note})

    # 1. Moat
    if gm_v is None and roic_v is None:
        st = "nd"; note = "Dati insufficienti"
    else:
        ok = (gm_v is not None and gm_v > 40) and (roic_v is not None and roic_v > 15)
        part = (gm_v is not None and gm_v > 40) or (roic_v is not None and roic_v > 15)
        st = "pass" if ok else ("partial" if part else "fail")
        note = f"Margine Lordo {fmt_pct(gm_v)} · ROIC {fmt_pct(roic_v)}"
    add(1, "Vantaggio competitivo durevole (Economic Moat)",
        "Fossato protettivo (brand, network effect, switching cost, vantaggio di costo) che impedisce ai concorrenti di erodere i profitti.",
        "Margine Lordo > 40% · ROIC > 15%", st, note)

    # 2. Pricing power (stabilità margine operativo)
    sr, se = S.get("ricavi"), S.get("ebit")
    if sr and se and len(sr) >= 2 and len(se) >= 2 and len(sr) == len(se):
        margins = [e / r * 100 for r, e in zip(sr, se) if r]
        mean = sum(margins) / len(margins)
        std = math.sqrt(sum((x - mean) ** 2 for x in margins) / len(margins))
        st = "pass" if (std < 2 and mean > 20) else ("partial" if mean > 15 else "fail")
        note = f"Margini operativi {len(margins)} anni: media {fmt(mean,1)}%, deviazione std {fmt(std,2)} pp"
    else:
        om = safe_div(ebit, ric)
        om_v = om * 100 if om is not None else None
        st = "partial" if (om_v is not None and om_v > 20) else ("fail" if om_v is not None else "nd")
        note = f"Margine operativo {fmt_pct(om_v)} (stabilità pluriennale non verificabile senza serie storica)"
    add(2, "Potere di prezzo (Pricing Power)",
        "Capacità di alzare i prezzi senza perdere clienti a favore della concorrenza.",
        "Margine Operativo = EBIT / Ricavi, stabile nel tempo (σ ≈ 0)", st, note)

    # 3. Cerchio di competenza / prevedibilità
    sni = S.get("net_income")
    if sni and len(sni) >= 2:
        neg = sum(1 for x in sni if x < 0)
        st = "pass" if neg == 0 else "fail"
        note = f"Serie utili {len(sni)} anni: {neg} esercizi in perdita"
    elif ni is not None:
        st = "partial"; note = f"Utile corrente positivo ({fmt(ni,0)}), ma serve serie storica per la continuità"
    else:
        st = "nd"; note = "Dato non disponibile"
    add(3, "Cerchio di competenza e prevedibilità",
        "Business semplice, domanda costante, futuro prevedibile a 10–20 anni.",
        "Anni in perdita negli ultimi 10 = 0", st, note)

    # 4. Capital-light
    cx = safe_div(capex, cfo)
    cx_v = cx * 100 if cx is not None else None
    add(4, "Modello capital-light",
        "Il business cresce senza reinvestire continuamente ingenti capitali in impianti e magazzino.",
        "CapEx / Cash Flow Operativo < 25%–30%",
        status_from(cx_v, cx_v is not None and cx_v <= 30, cx_v is not None and cx_v <= 50),
        f"CapEx {fmt(capex,0)} / CFO {fmt(cfo,0)} = {fmt_pct(cx_v)}")

    # 5. Owner earnings reali
    oe = (cfo - capex) if (cfo is not None and capex is not None) else None
    cc = safe_div(fcf, ni)
    if oe is not None and cc is not None:
        st = "pass" if (oe > 0 and cc >= 1.0) else ("partial" if oe > 0 else "fail")
    else:
        st = "nd"
    add(5, "Generazione reale di cassa (Owner Earnings)",
        "Gli utili contabili devono trasformarsi in denaro reale e liquido per gli azionisti.",
        "Owner Earnings = CFO − CapEx · Cash Conversion ≥ 100%", st,
        f"Owner Earnings {fmt(oe,0)} · Conversione cassa {fmt(cc,2)}")

    # 6. Allocazione capitale / test del dollaro
    proxy = safe_div(mcap, eq)
    if proxy is not None:
        st = "pass" if proxy >= 1.5 else "partial"
        note = f"Proxy Market Cap/Equity = {fmt(proxy,2)} (il test completo richiede la serie storica a 10 anni)"
    else:
        st = "nd"; note = "Richiede serie storica di market cap e utili trattenuti"
    add(6, "Allocazione razionale del capitale",
        "Management che reinveste ad alto rendimento, buyback a sconto, dividendi sostenibili.",
        "Test del $1: Δ Market Cap / Utili trattenuti > 1,0", st, note)

    # 7. Frugalità
    den = gp if gp else ric
    sg = safe_div(sga, den)
    sg_v = sg * 100 if sg is not None else None
    add(7, "Frugalità e controllo dei costi",
        "Cultura aziendale orientata all'efficienza e al contenimento delle spese generali.",
        "SG&A / Utile Lordo < 30%",
        status_from(sg_v, sg_v is not None and sg_v < 30, sg_v is not None and sg_v <= 40),
        f"SGA {fmt(sga,0)} / {'Margine Lordo' if gp else 'Ricavi'} {fmt(den,0)} = {fmt_pct(sg_v)}")

    # 8. Idiot test
    roa = safe_div(ni, ta)
    roa_v = roa * 100 if roa is not None else None
    add(8, "Criterio dell'idiot test",
        "Business così forte da generare profitti anche se gestito da un incompetente.",
        "ROA = Utile Netto / Totale Attività > 10%",
        status_from(roa_v, roa_v is not None and roa_v > 10, roa_v is not None and roa_v >= 5),
        f"ROA = {fmt_pct(roa_v)}")

    # 9. Indipendenza dal debito
    yrs = safe_div(ltd, ni)
    add(9, "Indipendenza e avversione al debito",
        "Capacità di superare recessioni e tassi alti senza debito rischioso.",
        "Debito LT / Utile Netto < 3–4 anni",
        status_from(yrs, yrs is not None and yrs < 3, yrs is not None and yrs <= 4),
        f"{fmt(yrs,2)} anni di utili per estinguere il debito LT")

    # 10. Franchise vs commodity
    nm = safe_div(ni, ric)
    nm_v = nm * 100 if nm is not None else None
    add(10, "Modello franchise vs commodity",
        "Prodotto unico e insostituibile, non merce indifferenziata da guerra di prezzo.",
        "Margine Netto > 15%",
        status_from(nm_v, nm_v is not None and nm_v > 15, nm_v is not None and nm_v >= 10),
        f"Margine netto = {fmt_pct(nm_v)}")

    # 11. Resistenza alla disruption
    rr = safe_div(rnd, ric)
    rr_v = rr * 100 if rr is not None else (0.0 if ric else None)
    if rr is None and ric:
        st, note = "partial", "R&D non dichiarata nel report"
    else:
        st = status_from(rr_v, rr_v is not None and rr_v <= 3, rr_v is not None and rr_v <= 8)
        note = f"R&D {fmt(rnd,0)} / Ricavi {fmt(ric,0)} = {fmt_pct(rr_v)}"
    add(11, "Resistenza a disruption e obsolescenza",
        "Bisogno umano primario, basso rischio di obsolescenza tecnologica.",
        "R&D / Ricavi molto bassa o assente", st, note)

    # 12. Candore e onestà contabile
    ratio = safe_div(cfo, ebit)
    add(12, "Candore, trasparenza e onestà contabile",
        "Management senza ego, niente artifizi contabili o EBITDA adjusted fantasiosi.",
        "CFO / EBIT ≈ 1,0",
        status_from(ratio, ratio is not None and 0.8 <= ratio <= 1.3, ratio is not None and 0.6 <= ratio <= 1.5),
        f"CFO {fmt(cfo,0)} / EBIT {fmt(ebit,0)} = {fmt(ratio,2)}")
    return K


# ============================================================================
# PUNTEGGI E VERDETTO
# ============================================================================
def compute_scores(quant, qual):
    qv = [m for m in quant if m.status != "nd"]
    q_pts = sum(1.0 if m.status == "pass" else 0.5 if m.status == "warn" else 0.0 for m in qv)
    quant_score = (100.0 * q_pts / len(qv)) if qv else 0.0
    ka = [q for q in qual if q["status"] != "nd"]
    k_pts = sum(1.0 if q["status"] == "pass" else 0.5 if q["status"] == "partial" else 0.0 for q in ka)
    qual_score = (100.0 * k_pts / len(ka)) if ka else 0.0
    final = 0.45 * qual_score + 0.55 * quant_score
    return {"quant": quant_score, "qual": qual_score, "final": final,
            "quant_n": len(qv), "qual_n": len(ka),
            "qual_pass": sum(1 for q in ka if q["status"] == "pass")}


def verdict_for(scores, dcf):
    f = scores["final"]
    if f >= 85:
        t = "🏆 ECCELLENTE — Qualità da cassaforte Berkshire"
    elif f >= 70:
        t = "✅ BUONO — Azienda solida, da approfondire"
    elif f >= 55:
        t = "⚠️ MEDIOCRE — Non supera pienamente i filtri di Buffett"
    else:
        t = "❌ SCARTARE — Non compatibile con il metodo"
    mos = dcf.get("mos") if dcf.get("ok") else None
    if mos is None:
        sub = "Prezzo di mercato non disponibile: impossibile valutare il margine di sicurezza."
    elif mos >= 30:
        sub = f"Margine di sicurezza {fmt(mos,1)}%: prezzo interessante, sconto adeguato (≥ 30%)."
    elif mos >= 20:
        sub = f"Margine di sicurezza {fmt(mos,1)}%: sconto borderline (20–30%), serve prudenza."
    elif mos >= 0:
        sub = f"Margine di sicurezza {fmt(mos,1)}%: prezzo vicino al valore intrinseco. Buffett attenderebbe uno sconto maggiore."
    else:
        sub = f"Prezzo SOPRA il valore intrinseco ({fmt(mos,1)}%): attendere una correzione."
    return t, sub


# ============================================================================
# PIPELINE DI ANALISI
# ============================================================================
def analyze_document(path, cb=None):
    def step(p, msg):
        if cb:
            cb(p, msg)

    step(5, "Lettura del documento…")
    text = extract_text_from_file(path)
    if not text.strip():
        raise ValueError("Impossibile estrarre testo dal documento (PDF scannerizzato? Usa un PDF testuale o un TXT).")

    step(25, "Estrazione automatica dei dati finanziari…")
    D, S, log = extract_financials(text)
    found = sum(1 for k in D)
    if found < 3:
        raise ValueError("Nessun dato finanziario significativo riconosciuto nel documento.")

    step(55, "Calcolo dei 40 criteri quantitativi…")
    dcf = compute_dcf(D, S)
    quant = build_quant(D, S, dcf)

    step(75, "Analisi dei 12 criteri qualitativi…")
    qual = build_qual(D, S, dcf)

    step(90, "Punteggi e verdetto finale…")
    scores = compute_scores(quant, qual)
    vt, vs = verdict_for(scores, dcf)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    company = lines[0][:90] if lines else os.path.basename(path)
    step(100, "Completato.")
    return {"source": os.path.basename(path), "company": company,
            "text_len": len(text), "D": D, "S": S, "quant": quant, "qual": qual,
            "dcf": dcf, "scores": scores, "verdict": vt, "verdict_sub": vs, "log": log}


# ============================================================================
# GUI — WIDGET HELPER
# ============================================================================
class ScrollableFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120 or (-1 if event.num == 4 else 1))), "units")

    def _bind_wheel(self, _):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", self._wheel)
        self.canvas.bind_all("<Button-5>", self._wheel)

    def _unbind_wheel(self, _):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")


def clear(frame):
    for w in frame.winfo_children():
        w.destroy()


def pill(parent, status, meta=None):
    meta = meta or STATUS_META
    col, lab = meta[status]
    return tk.Label(parent, text=lab, bg=col, fg="#0a0f16",
                    font=("Segoe UI", 8, "bold"), padx=8, pady=2)


def metric_card(parent, m):
    card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
    col = STATUS_META[m.status][0]
    bar = tk.Frame(card, bg=col, width=4)
    bar.grid(row=0, column=0, rowspan=5, sticky="ns")
    head = tk.Frame(card, bg=CARD)
    head.grid(row=0, column=1, sticky="ew", padx=(12, 10), pady=(10, 0))
    tk.Label(head, text=f"{m.code} · {m.name}", bg=CARD, fg=FG, font=F_CARD_T, anchor="w").pack(side="left")
    tk.Label(head, text="CORE BUFFETT" if m.core else "COMPLEMENTARE", bg=CARD,
             fg=GOLD if m.core else MUTED, font=F_TINY).pack(side="right")
    tk.Label(card, text=m.tag, bg=CARD, fg=MUTED, font=F_TINY, anchor="w").grid(
        row=1, column=1, sticky="ew", padx=(12, 10))
    vrow = tk.Frame(card, bg=CARD)
    vrow.grid(row=2, column=1, sticky="ew", padx=(12, 10), pady=(4, 0))
    tk.Label(vrow, text=m.value_text, bg=CARD, fg=FG, font=("Segoe UI", 15, "bold"), anchor="w").pack(side="left")
    pill(vrow, m.status).pack(side="right")
    if m.detail:
        tk.Label(card, text=m.detail, bg=CARD, fg=BLUE, font=F_TINY, anchor="w").grid(
            row=3, column=1, sticky="ew", padx=(12, 10), pady=(2, 0))
    tk.Label(card, text=f"Soglia Buffett: {m.threshold}", bg=CARD, fg=MUTED, font=F_TINY, anchor="w").grid(
        row=4, column=1, sticky="ew", padx=(12, 10), pady=(2, 10))
    return card


def qual_card(parent, q):
    card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1, padx=16, pady=12)
    col, lab = QSTATUS_META[q["status"]]
    top = tk.Frame(card, bg=CARD)
    top.pack(fill="x")
    tk.Label(top, text=f"{q['n']:02d} · {q['title']}", bg=CARD, fg=FG, font=("Segoe UI", 11, "bold"),
             anchor="w").pack(side="left")
    pill(top, q["status"], QSTATUS_META).pack(side="right")
    tk.Label(card, text=q["desc"], bg=CARD, fg=MUTED, font=F_SMALL, anchor="w",
             justify="left", wraplength=620).pack(fill="x", pady=(6, 4))
    tk.Label(card, text="📐 " + q["formula"], bg=CARD, fg=GOLD, font=F_SMALL, anchor="w").pack(fill="x")
    tk.Label(card, text="→ " + q["note"], bg=CARD, fg=col, font=F_SMALL, anchor="w",
             justify="left", wraplength=620).pack(fill="x", pady=(4, 0))
    return card


def kpi_card(parent, label, value, sub="", color=FG):
    c = tk.Frame(parent, bg=CARD2, highlightbackground=BORDER, highlightthickness=1, padx=14, pady=10)
    tk.Label(c, text=label, bg=CARD2, fg=MUTED, font=F_TINY, anchor="w").pack(fill="x")
    tk.Label(c, text=value, bg=CARD2, fg=color, font=("Segoe UI", 16, "bold"), anchor="w").pack(fill="x")
    if sub:
        tk.Label(c, text=sub, bg=CARD2, fg=MUTED, font=F_TINY, anchor="w").pack(fill="x")
    return c


def draw_gauge(cv, score, size=230):
    cv.delete("all")
    cx = cy = size // 2
    r = size // 2 - 20
    cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=240, extent=-240,
                  style="arc", outline=BORDER, width=16)
    color = GREEN if score >= 80 else (GOLD if score >= 65 else (AMBER if score >= 50 else RED))
    ext = -240 * max(0.0, min(score, 100.0)) / 100.0
    if ext < -1:
        cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=240, extent=ext,
                      style="arc", outline=color, width=16)
    cv.create_text(cx, cy - 12, text=f"{score:.0f}", font=("Segoe UI", 40, "bold"), fill=FG)
    cv.create_text(cx, cy + 26, text="/ 100", font=("Segoe UI", 11), fill=MUTED)
    cv.create_text(cx, cy + 48, text="BUFFETT SCORE", font=("Segoe UI", 8, "bold"), fill=GOLD)


# ============================================================================
# GUI — APPLICAZIONE PRINCIPALE
# ============================================================================
class BuffettApp:
    def __init__(self, root):
        self.root = root
        self.result = None
        root.title(f"{APP_TITLE} v{VERSION}")
        root.configure(bg=BG)
        root.geometry("1280x820")
        root.minsize(1000, 640)

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=[12, 8, 12, 0])
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        padding=[20, 9], font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", CARD2)],
                  foreground=[("selected", GOLD)])
        style.configure("Vertical.TScrollbar", background=CARD2, troughcolor=BG,
                        borderwidth=0, arrowcolor=MUTED)
        style.configure("gold.Horizontal.TProgressbar", troughcolor=PANEL,
                        background=GOLD, borderwidth=0, thickness=6)

        self._build_header()
        self._build_toolbar()
        self._build_notebook()
        self._build_statusbar()
        self._show_welcome()

    # ---------------- layout ----------------
    def _build_header(self):
        h = tk.Frame(self.root, bg=PANEL)
        h.pack(fill="x")
        tk.Label(h, text="⚖  BUFFETT ANALYZER", bg=PANEL, fg=GOLD, font=F_TITLE).pack(side="left", padx=20, pady=12)
        tk.Label(h, text="40 criteri quantitativi  •  12 criteri qualitativi  •  DCF Owner Earnings  •  100% automatico",
                 bg=PANEL, fg=MUTED, font=F_SUB).pack(side="left", padx=8, pady=20)

    def _build_toolbar(self):
        t = tk.Frame(self.root, bg=BG)
        t.pack(fill="x", padx=16, pady=(12, 4))
        self.btn_load = tk.Button(t, text="📂  Carica Report (PDF/TXT)", command=self.on_load,
                                  bg=GOLD, fg="#14100a", font=("Segoe UI", 10, "bold"),
                                  bd=0, padx=18, pady=8, cursor="hand2", activebackground="#ffd066")
        self.btn_load.pack(side="left")
        self.btn_demo = tk.Button(t, text="▶  Demo", command=self.on_demo,
                                  bg=CARD2, fg=FG, font=("Segoe UI", 10, "bold"),
                                  bd=0, padx=16, pady=8, cursor="hand2", activebackground=BORDER)
        self.btn_demo.pack(side="left", padx=10)
        self.btn_html = tk.Button(t, text="🌐  Esporta HTML", command=self.on_export, state="disabled",
                                  bg=CARD2, fg=FG, font=("Segoe UI", 10, "bold"),
                                  bd=0, padx=16, pady=8, cursor="hand2", activebackground=BORDER)
        self.btn_html.pack(side="left")
        self.status_lbl = tk.Label(t, text="In attesa di un report…", bg=BG, fg=MUTED, font=F_SMALL)
        self.status_lbl.pack(side="right")
        self.prog = ttk.Progressbar(t, style="gold.Horizontal.TProgressbar", length=220, maximum=100)
        self.prog.pack(side="right", padx=12)

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=16, pady=8)
        self.tabs = {}
        for key, label in [("dash", "◈  DASHBOARD"), ("qual", "⑫  CRITERI QUALITATIVI"),
                           ("quant", "40  CRITERI QUANTITATIVI"), ("dcf", "∑  DCF & VALUTAZIONE"),
                           ("log", "≡  LOG ESTRAZIONE")]:
            sf = ScrollableFrame(self.nb)
            self.nb.add(sf, text=label)
            self.tabs[key] = sf.inner

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg=PANEL)
        sb.pack(fill="x", side="bottom")
        tk.Label(sb, text=f"Progetto: {BASE_DIR}   ·   v{VERSION}   ·   {datetime.date.today().strftime('%d/%m/%Y')}",
                 bg=PANEL, fg=MUTED, font=F_TINY, padx=14, pady=5).pack(side="left")

    # ---------------- azioni ----------------
    def on_load(self):
        path = filedialog.askopenfilename(
            title="Seleziona il report aziendale",
            filetypes=[("Report", "*.pdf *.txt"), ("PDF", "*.pdf"), ("Testo", "*.txt"), ("Tutti", "*.*")])
        if path:
            self.load_file(path)

    def on_demo(self):
        ensure_project()
        self.load_file(SAMPLE_FILE)

    def on_export(self):
        if not self.result:
            return
        path = export_html(self.result)
        if messagebox.askyesno("Report esportato", f"Dashboard HTML salvata in:\n{path}\n\nAprirla nel browser?"):
            webbrowser.open("file:///" + path.replace("\\", "/"))

    def load_file(self, path):
        self.btn_load.config(state="disabled")
        self.btn_demo.config(state="disabled")
        self.prog["value"] = 0
        threading.Thread(target=self._worker, args=(path,), daemon=True).start()

    def _worker(self, path):
        def cb(p, msg):
            self.root.after(0, lambda p=p, msg=msg: self._progress(p, msg))
        try:
            res = analyze_document(path, cb)
            self.root.after(0, lambda r=res: self._show_result(r))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda err=e: self._on_error(err))

    def _progress(self, p, msg):
        self.prog["value"] = p
        self.status_lbl.config(text=msg)

    def _on_error(self, err):
        self.btn_load.config(state="normal")
        self.btn_demo.config(state="normal")
        self.status_lbl.config(text="Errore durante l'analisi")
        messagebox.showerror("Errore analisi", str(err))

    # ---------------- rendering ----------------
    def _show_welcome(self):
        f = self.tabs["dash"]
        clear(f)
        box = tk.Frame(f, bg=BG)
        box.pack(pady=60, padx=40)
        tk.Label(box, text="🏛", bg=BG, fg=GOLD, font=("Segoe UI", 54)).pack()
        tk.Label(box, text="Benvenuto nel Buffett Analyzer", bg=BG, fg=FG, font=("Segoe UI", 18, "bold")).pack(pady=(10, 6))
        tk.Label(box, text=("1. Carica un report aziendale (bilancio PDF o TXT) oppure premi ▶ Demo.\n"
                            "2. L'estrazione dei dati è completamente automatica: nessun inserimento manuale.\n"
                            "3. Ottieni i 40 criteri quantitativi, i 12 criteri qualitativi, il DCF\n"
                            "    su Owner Earnings e il verdetto finale in stile Berkshire Hathaway."),
                 bg=BG, fg=MUTED, font=F_BODY, justify="left").pack()

    def _show_result(self, res):
        self.result = res
        self.btn_load.config(state="normal")
        self.btn_demo.config(state="normal")
        self.btn_html.config(state="normal")
        self._build_dashboard(res)
        self._build_qual_tab(res)
        self._build_quant_tab(res)
        self._build_dcf_tab(res)
        self._build_log_tab(res)
        self.nb.select(0)

    def _build_dashboard(self, res):
        f = self.tabs["dash"]
        clear(f)
        s, dcf = res["scores"], res["dcf"]

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=24, pady=(20, 8))
        gframe = tk.Frame(top, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        gframe.pack(side="left", padx=(0, 20))
        cv = tk.Canvas(gframe, width=240, height=240, bg=CARD, highlightthickness=0)
        cv.pack(padx=10, pady=10)
        draw_gauge(cv, s["final"])

        right = tk.Frame(top, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text=res["company"], bg=BG, fg=FG, font=("Segoe UI", 15, "bold"),
                 anchor="w", wraplength=700, justify="left").pack(fill="x")
        tk.Label(right, text=f"Fonte: {res['source']}   ·   {res['text_len']:,} caratteri analizzati",
                 bg=BG, fg=MUTED, font=F_TINY, anchor="w").pack(fill="x", pady=(2, 10))
        tk.Label(right, text=res["verdict"], bg=BG, fg=GOLD, font=("Segoe UI", 16, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(right, text=res["verdict_sub"], bg=BG, fg=FG, font=F_BODY, anchor="w",
                 justify="left", wraplength=700).pack(fill="x", pady=(6, 12))
        chips = tk.Frame(right, bg=BG)
        chips.pack(fill="x")
        kpi_card(chips, "PUNTEGGIO QUALITATIVO", f"{s['qual']:.0f}/100",
                 f"{s['qual_pass']} criteri superati su {s['qual_n']}").pack(side="left", padx=(0, 10))
        kpi_card(chips, "PUNTEGGIO QUANTITATIVO", f"{s['quant']:.0f}/100",
                 f"{s['quant_n']} metriche valutate").pack(side="left", padx=(0, 10))
        mos = dcf.get("mos") if dcf.get("ok") else None
        mos_col = GREEN if (mos or -99) >= 30 else (AMBER if (mos or -99) >= 20 else RED)
        kpi_card(chips, "MARGINE DI SICUREZZA", fmt_pct(mos), "sconto richiesto 20–30%", mos_col).pack(side="left")

        D = res["D"]
        grid = tk.Frame(f, bg=BG)
        grid.pack(fill="x", padx=24, pady=12)
        items = [
            ("RICAVI", fmt(D.get("ricavi"), 0)),
            ("UTILE NETTO", fmt(D.get("net_income"), 0)),
            ("OWNER EARNINGS", fmt((D.get("cfo") - D.get("capex")) if (D.get("cfo") is not None and D.get("capex") is not None) else None, 0)),
            ("ROIC", fmt_pct((safe_div(D.get("ebit"), 1) and None) if False else None, 0) if False else next((m.value_text for m in res["quant"] if m.code == "Q02"), "N/D")),
            ("ROE", next((m.value_text for m in res["quant"] if m.code == "Q03"), "N/D")),
            ("DEBT/EQUITY", next((m.value_text for m in res["quant"] if m.code == "Q05"), "N/D")),
        ]
        for i, (lab, val) in enumerate(items):
            kpi_card(grid, lab, val).grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="a")

        if dcf.get("ok"):
            box = tk.Frame(f, bg=GOLD, padx=2, pady=2)
            box.pack(fill="x", padx=24, pady=(8, 24))
            inner = tk.Frame(box, bg=CARD)
            inner.pack(fill="x")
            txt = (f"VALORE INTRINSECO (DCF Owner Earnings):  {fmt(dcf['iv'],0)}"
                   + (f"   ·   per azione {fmt(dcf['iv_share'],2)}" if dcf.get("iv_share") else "")
                   + (f"   ·   prezzo di mercato {fmt(dcf['price'],2)}" if dcf.get("price") else ""))
            tk.Label(inner, text="💰 " + txt, bg=CARD, fg=GOLD, font=("Segoe UI", 11, "bold"),
                     anchor="w", padx=14, pady=12, wraplength=900, justify="left").pack(fill="x")

    def _build_qual_tab(self, res):
        f = self.tabs["qual"]
        clear(f)
        tk.Label(f, text="I 12 CRITERI QUALITATIVI DI WARREN BUFFETT", bg=BG, fg=GOLD,
                 font=F_H2, anchor="w").pack(fill="x", padx=24, pady=(18, 4))
        tk.Label(f, text="Approvazione qualitativa: ogni criterio è verificato tramite la propria spia matematica.",
                 bg=BG, fg=MUTED, font=F_SMALL, anchor="w").pack(fill="x", padx=24, pady=(0, 12))
        for q in res["qual"]:
            qual_card(f, q).pack(fill="x", padx=24, pady=6)
        tk.Frame(f, bg=BG, height=20).pack()

    def _build_quant_tab(self, res):
        f = self.tabs["quant"]
        clear(f)
        tk.Label(f, text="I 40 CRITERI QUANTITATIVI — CORE BUFFETT (1–21) + COMPLEMENTARI (22–40)",
                 bg=BG, fg=GOLD, font=F_H2, anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(18, 12))
        f.columnconfigure(0, weight=1, uniform="a")
        f.columnconfigure(1, weight=1, uniform="a")
        for i, m in enumerate(res["quant"]):
            metric_card(f, m).grid(row=1 + i // 2, column=i % 2, sticky="nsew", padx=(24 if i % 2 == 0 else 8, 24 if i % 2 else 8), pady=6)

    def _build_dcf_tab(self, res):
        f = self.tabs["dcf"]
        clear(f)
        dcf = res["dcf"]
        tk.Label(f, text="VALUTAZIONE DCF SU OWNER EARNINGS + MARGINE DI SICUREZZA",
                 bg=BG, fg=GOLD, font=F_H2, anchor="w").pack(fill="x", padx=24, pady=(18, 8))
        if not dcf.get("ok"):
            tk.Label(f, text="Dati insufficienti per il DCF (serve un flusso di cassa o un utile positivo).",
                     bg=BG, fg=RED, font=F_BODY, anchor="w").pack(fill="x", padx=24)
            return
        par = tk.Frame(f, bg=BG)
        par.pack(fill="x", padx=24, pady=6)
        kpi_card(par, "FLUSSO BASE", fmt(dcf["base"], 0),
                 "Owner Earnings (CFO − CapEx)" if dcf["base_is_oe"] else "FCF / Utile (fallback)").grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        kpi_card(par, "CRESCITA FASE 1", fmt_pct(dcf["g1"] * 100), "prudenziale, max 8%").grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        kpi_card(par, "TASSO DI SCONTO", fmt_pct(dcf["r"] * 100), "conservativo").grid(row=0, column=2, sticky="nsew", padx=6, pady=6)
        kpi_card(par, "CRESCITA PERPETUA", fmt_pct(dcf["g"] * 100), "terminal value").grid(row=0, column=3, sticky="nsew", padx=6, pady=6)
        for c in range(4):
            par.columnconfigure(c, weight=1, uniform="a")

        rows = tk.Frame(f, bg=BG)
        rows.pack(fill="x", padx=24, pady=10)
        tk.Label(rows, text="Flussi attualizzati (10 anni):", bg=BG, fg=MUTED, font=F_SMALL, anchor="w").pack(fill="x")
        flow_txt = "   ".join(f"Anno {i+1}: {fmt(v,0)}" for i, v in enumerate(dcf["flows"][:5]))
        flow_txt2 = "   ".join(f"Anno {i+6}: {fmt(v,0)}" for i, v in enumerate(dcf["flows"][5:]))
        tk.Label(rows, text=flow_txt, bg=BG, fg=FG, font=F_MONO, anchor="w").pack(fill="x", pady=(4, 0))
        tk.Label(rows, text=flow_txt2, bg=BG, fg=FG, font=F_MONO, anchor="w").pack(fill="x")
        tk.Label(rows, text=f"Terminal Value attualizzato: {fmt(dcf['tv'] / (1 + dcf['r']) ** dcf['n'], 0)}",
                 bg=BG, fg=FG, font=F_MONO, anchor="w").pack(fill="x", pady=(4, 0))

        summ = tk.Frame(f, bg=BG)
        summ.pack(fill="x", padx=24, pady=12)
        kpi_card(summ, "VALORE INTRINSECO", fmt(dcf["iv"], 0),
                 f"per azione: {fmt(dcf.get('iv_share'),2)}" if dcf.get("iv_share") else "", GOLD).grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        kpi_card(summ, "PREZZO / MARKET CAP", fmt(dcf.get("price"), 2) if dcf.get("price") else fmt(dcf.get("mcap"), 0),
                 "valore di mercato" if dcf.get("mcap") else "").grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        mos = dcf.get("mos")
        mos_col = GREEN if (mos or -99) >= 30 else (AMBER if (mos or -99) >= 20 else RED)
        kpi_card(summ, "MARGINE DI SICUREZZA", fmt_pct(mos),
                 "Buffett richiede ≥ 20–30%", mos_col).grid(row=0, column=2, sticky="nsew", padx=6, pady=6)
        for c in range(3):
            summ.columnconfigure(c, weight=1, uniform="a")

        tk.Label(f, text=res["verdict_sub"], bg=BG, fg=FG, font=F_BODY, anchor="w",
                 wraplength=860, justify="left").pack(fill="x", padx=30, pady=(4, 24))

    def _build_log_tab(self, res):
        f = self.tabs["log"]
        clear(f)
        t = tk.Text(f, bg=CARD, fg=FG, font=F_MONO, bd=0, padx=14, pady=12, wrap="none")
        t.tag_configure("ok", foreground=GREEN)
        t.tag_configure("nd", foreground=GRAY)
        t.insert("end", f"ANALISI AUTOMATICA — {res['source']}\n", "ok")
        t.insert("end", f"Azienda: {res['company']}\n")
        t.insert("end", f"Caratteri estratti: {res['text_len']:,}\n")
        t.insert("end", f"Grandezze trovate: {len(res['D'])}\n\n")
        for lvl, msg in res["log"]:
            t.insert("end", ("✔ " if lvl == "ok" else "· ") + msg + "\n", lvl)
        t.config(state="disabled")
        t.pack(fill="both", expand=True, padx=24, pady=18)


# ============================================================================
# EXPORT HTML (dashboard moderna auto-contenuta)
# ============================================================================
HTML_CSS = """
:root{--bg:#0b0e14;--card:#161c28;--border:#232c3f;--fg:#e8ecf4;--muted:#8a94ab;
--gold:#f2b632;--green:#2ecc71;--amber:#f39c12;--red:#ff5c5c;--gray:#5a6478;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font-family:'Segoe UI',Arial,sans-serif;padding:32px}
.hero{background:linear-gradient(135deg,#161c28,#1b2333);border:1px solid var(--border);
border-radius:16px;padding:32px;margin-bottom:24px}
.hero h1{color:var(--gold);font-size:26px;margin-bottom:6px}
.hero .sub{color:var(--muted);font-size:13px}
.score{font-size:52px;font-weight:800;color:var(--gold);margin-top:12px}
.verdict{font-size:18px;margin-top:8px;font-weight:600}
.verdict-sub{color:var(--muted);margin-top:6px;max-width:900px}
h2{color:var(--gold);margin:28px 0 14px;font-size:18px;letter-spacing:.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 18px;
border-left:4px solid var(--gray)}
.card.pass{border-left-color:var(--green)} .card.warn,.card.partial{border-left-color:var(--amber)}
.card.fail{border-left-color:var(--red)}
.card .name{font-weight:700;font-size:14px}
.card .tag{color:var(--muted);font-size:11px;margin:2px 0 8px}
.card .value{font-size:22px;font-weight:800}
.card .thr{color:var(--muted);font-size:11px;margin-top:6px}
.card .det{color:#4da3ff;font-size:11px;margin-top:4px}
.card .note{color:var(--muted);font-size:12px;margin-top:6px}
.pill{display:inline-block;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;
color:#0a0f16;float:right}
.pill.pass{background:var(--green)} .pill.warn,.pill.partial{background:var(--amber)}
.pill.fail{background:var(--red)} .pill.nd{background:var(--gray);color:#dfe4ee}
footer{color:var(--muted);font-size:11px;margin-top:36px;text-align:center}
"""


def export_html(res):
    s, dcf = res["scores"], res["dcf"]
    cards_q = []
    for m in res["quant"]:
        _, lab = STATUS_META[m.status]
        cards_q.append(
            f'<div class="card {m.status}"><span class="pill {m.status}">{lab}</span>'
            f'<div class="name">{m.code} · {m.name}</div><div class="tag">{m.tag}'
            f'{" · CORE BUFFETT" if m.core else ""}</div>'
            f'<div class="value">{m.value_text}</div>'
            f'<div class="thr">Soglia: {m.threshold}</div>'
            + (f'<div class="det">{m.detail}</div>' if m.detail else "") + "</div>")
    cards_k = []
    for q in res["qual"]:
        _, lab = QSTATUS_META[q["status"]]
        cards_k.append(
            f'<div class="card {q["status"]}"><span class="pill {q["status"]}">{lab}</span>'
            f'<div class="name">{q["n"]:02d} · {q["title"]}</div>'
            f'<div class="note">{q["desc"]}</div>'
            f'<div class="det">📐 {q["formula"]}</div>'
            f'<div class="thr">→ {q["note"]}</div></div>')
    mos_txt = fmt_pct(dcf.get("mos")) if dcf.get("ok") else "N/D"
    html = ("<!DOCTYPE html><html lang='it'><head><meta charset='utf-8'>"
            f"<title>Buffett Analyzer — {res['company']}</title><style>{HTML_CSS}</style></head><body>"
            f"<div class='hero'><h1>⚖ BUFFETT ANALYZER</h1>"
            f"<div class='sub'>{res['company']} · Fonte: {res['source']} · "
            f"{datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</div>"
            f"<div class='score'>{s['final']:.0f} / 100</div>"
            f"<div class='verdict'>{res['verdict']}</div>"
            f"<div class='verdict-sub'>{res['verdict_sub']}</div>"
            f"<div class='sub' style='margin-top:12px'>Qualitativo {s['qual']:.0f}/100 · "
            f"Quantitativo {s['quant']:.0f}/100 · Margine di sicurezza {mos_txt}</div></div>"
            "<h2>⑫ CRITERI QUALITATIVI</h2><div class='grid'>" + "".join(cards_k) + "</div>"
            "<h2>40 CRITERI QUANTITATIVI</h2><div class='grid'>" + "".join(cards_q) + "</div>"
            "<footer>Generato automaticamente da Buffett Analyzer · Metodo Berkshire Hathaway"
            " · Nessuna consulenza finanziaria</footer></body></html>")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", res["company"])[:40] or "report"
    path = os.path.join(OUTPUT_DIR, f"{slug}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ============================================================================
# MAIN
# ============================================================================
def main():
    ensure_project()
    root = tk.Tk()
    app = BuffettApp(root)
    # analisi automatica se il file viene passato come argomento da riga di comando
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        root.after(400, lambda: app.load_file(os.path.abspath(sys.argv[1])))
    root.mainloop()


if __name__ == "__main__":
    main() 