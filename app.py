import os, sys
from datetime import datetime, timedelta
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json as _json
import secrets as _secrets
import hashlib as _hashlib

try:
    import tkinter
except Exception:
    import types, sys as _sys2
    class _StubBase:
        def __init__(self, *a, **k): pass
        def __getattr__(self, k): return _StubBase()
        def __call__(self, *a, **k): return _StubBase()
    tk = types.ModuleType("tkinter")
    for n in ("Frame","Tk","Toplevel","Canvas","Scrollbar","Label","Button","Entry","Text",
              "Listbox","Checkbutton","Radiobutton","Menu","Message","Scale","Spinbox",
              "StringVar","IntVar","DoubleVar","BooleanVar"):
        setattr(tk, n, type(n, (_StubBase,), {}))
    tk.__getattr__ = lambda k: _StubBase()
    _sys2.modules["tkinter"] = tk
    ttk = types.ModuleType("tkinter.ttk")
    for n in ("Frame","Treeview","Notebook","Button","Label","Entry"):
        setattr(ttk, n, type(n, (_StubBase,), {}))
    ttk.__getattr__ = lambda k: _StubBase()
    _sys2.modules["tkinter.ttk"] = ttk
    for nm in ("tkinter.filedialog","tkinter.messagebox","tkinter.scrolledtext"):
        m = types.ModuleType(nm)
        m.__getattr__ = lambda k: _StubBase()
        _sys2.modules[nm] = m

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import test1 as engine

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key")
_dbu = os.environ.get("DATABASE_URL", "sqlite:///users.db")
if _dbu.startswith("postgres://"):
    _dbu = _dbu.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _dbu
app.config["UPLOAD_FOLDER"] = os.path.join(BASE, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(BASE, "outputs"), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

def send_email(to, subject, body):
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        print(f"[email-sim] -> {to}: {subject}")
        return
    try:
        import requests as _rq
        _rq.post("https://api.resend.com/emails",
                 headers={"Authorization": "Bearer " + key},
                 json={"from": "AUGET <noreply@sibilla.cc>", "to": [to], "subject": subject, "html": body}, timeout=10)
    except Exception as e:
        print("[email-err]", e)

STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY")
stripe = None
if STRIPE_KEY:
    try:
        import stripe as _st
        _st.api_key = STRIPE_KEY
        stripe = _st
    except Exception:
        stripe = None
STRIPE_PRICES = {"basic": os.environ.get("STRIPE_PRICE_BASIC"),
                 "pro": os.environ.get("STRIPE_PRICE_PRO"),
                 "enterprise": os.environ.get("STRIPE_PRICE_ENTERPRISE")}

PLAN_LIMITS = {"basic": 10, "trial": 3, "pro": None, "enterprise": None, "demo": None, "admin": None}

def _used_this_month(uid):
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return Report.query.filter(Report.user_id == uid, Report.created_at >= start).count()

def _gen_codes(n=10):
    return [f"{_secrets.token_hex(2).upper()}-{_secrets.token_hex(2).upper()}" for _ in range(n)]

def _hash_code(c):
    return _hashlib.sha256((c or "").strip().upper().encode()).hexdigest()

def send_sms(to, body):
    sid = os.environ.get("TWILIO_SID"); tok = os.environ.get("TWILIO_TOKEN"); frm = os.environ.get("TWILIO_FROM")
    if not (sid and tok and frm):
        print(f"[sms-sim] -> {to}: {body}")
        return False
    try:
        from twilio.rest import Client
        Client(sid, tok).messages.create(body=body, from_=frm, to=to)
        return True
    except Exception as e:
        print("[sms-err]", e)
        return False

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    subscription_tier = db.Column(db.String(20), default="none")
    subscription_expires = db.Column(db.DateTime)
    stripe_customer_id = db.Column(db.String(120))
    stripe_subscription_id = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    recovery_hash = db.Column(db.Text)
    otp_hash = db.Column(db.String(120))
    otp_expires = db.Column(db.DateTime)
    reset_token = db.Column(db.String(120))
    reset_expires = db.Column(db.DateTime)
    
    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)
    
    @property
    def subscription_active(self):
        if self.subscription_tier in ("demo", "admin"):
            return True
        if not self.subscription_expires:
            return False
        return datetime.utcnow() < self.subscription_expires

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default="aperto")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    rating = db.Column(db.Integer)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CollabRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    kind = db.Column(db.String(120))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    filename = db.Column(db.String(200))
    company = db.Column(db.String(120))
    score = db.Column(db.Float)
    html = db.Column(db.Text)
    metrics_json = db.Column(db.Text)
    notes = db.Column(db.Text)
    sector = db.Column(db.String(80))
    is_favorite = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WatchItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    ticker = db.Column(db.String(20))
    name = db.Column(db.String(120))
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SiteConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_open = db.Column(db.Boolean, default=True)
    demo_enabled = db.Column(db.Boolean, default=True)
    contact_email = db.Column(db.String(120), default="info@sibilla.cc")
    contact_telegram = db.Column(db.String(120), default="@sibilla_finance")
    contact_linkedin = db.Column(db.String(200), default="linkedin.com/in/matteo-zanoni")

def get_cfg():
    c = SiteConfig.query.first()
    if not c:
        c = SiteConfig(); db.session.add(c); db.session.commit()
    return c

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if not current_user.subscription_active:
            flash("Abbonamento scaduto.", "error")
            return redirect(url_for("pricing"))
        return f(*args, **kwargs)
    return decorated

BASE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{{ title }}</title>
<style>
:root{--bg:#0b1220;--card:#121c30;--line:#233250;--gold:#f0b429;--teal:#2dd4a7;--blue:#4cc3ff;--text:#e8eef7;--muted:#93a4bd}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;margin:0;min-height:100vh}
.nav{background:#0e1728;padding:.8rem 2rem;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem}
.brand{color:var(--gold);font-weight:800;font-size:1.25rem;letter-spacing:3px}
.nav a{text-decoration:none;margin-left:1rem}
.tools a{color:var(--teal);font-weight:600}
.admin a{color:var(--muted)}
.container{max-width:960px;margin:2rem auto;padding:0 2rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:2rem;margin:1rem 0}
.hero{background:linear-gradient(135deg,#13223d,#0e1728);text-align:center}
h1{color:var(--gold)}h2{color:var(--teal)}
input,select,textarea{width:100%;padding:10px;background:#0b1220;border:1px solid var(--line);border-radius:8px;color:var(--text);margin:8px 0;box-sizing:border-box}
button{background:var(--gold);color:#0b1220;border:0;padding:12px 28px;border-radius:10px;font-weight:700;cursor:pointer;font-size:15px;width:100%}
.btn2{background:var(--teal);color:#0b1220}
.alert{padding:12px;border-radius:8px;margin:1rem 0}
.error{background:#da3633;color:white}
.success{background:#238636;color:white}
.tier{border:2px solid var(--line);border-radius:14px;padding:1.5rem;margin:1rem 0;text-align:center}
.tier.active{border-color:var(--gold)}
.tier h3{color:var(--gold);font-size:1.5rem;margin:0}
.price{font-size:2rem;color:var(--teal);margin:1rem 0}
table{width:100%;border-collapse:collapse;background:var(--card);margin:1rem 0}
td,th{border:1px solid var(--line);padding:8px;text-align:left}
.pill{display:inline-block;padding:4px 14px;border-radius:20px;font-size:.85rem;margin:4px}
.pill-teal{background:rgba(45,212,167,.15);color:var(--teal);border:1px solid var(--teal)}
.pill-blue{background:rgba(76,195,255,.12);color:var(--blue);border:1px solid var(--blue)}
.pill-gold{background:rgba(240,180,41,.12);color:var(--gold);border:1px solid var(--gold)}
</style></head>
<body>
<div class="nav">
  <div class="brand">AUGET</div>
  <div class="tools">
    {% if current_user.is_authenticated %}
      <a href="/analyze">Analizza</a><a href="/reports">Report</a><a href="/watchlist">Watchlist</a><a href="/compare">Confronta</a><a href="/cronologia">Cronologia</a><a href="/simula">Simula</a>
    {% else %}
      <a href="/">Home</a>
    {% endif %}
  </div>
  <div class="admin">
    <a href="/guida">Guida</a><a href="/contatti">Contatti</a><a href="/collabora">Collabora</a>
    {% if current_user.is_authenticated %}
      <a href="/assistenza">Assistenza</a><a href="/feedback">Feedback</a><a href="/pricing">Piani</a>
      {% if current_user.subscription_tier == "admin" %}<a href="/admin" style="color:var(--gold);font-weight:700">Admin</a>{% endif %}
      <a href="/account" style="color:var(--muted)">{{ current_user.email }}</a><a href="/logout">Esci</a>
    {% else %}
      <a href="/login">Accedi</a><a href="/register" style="color:var(--gold);font-weight:700">Registrati</a>
    {% endif %}
  </div>
</div>
<div class="container">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, message in messages %}
        <div class="alert {{ category }}">{{ message }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}
  {{ content|safe }}
</div>

<script>
(function() {
  var form = document.querySelector('form[action="/do_analyze"]');
  var btn = document.getElementById('analyze-btn');
  var container = document.getElementById('progress-container');
  var bar = document.getElementById('progress-bar');
  var text = document.getElementById('progress-text');
  var progress = 0;
  var interval;
  var timeout;
  
  if (form && btn) {
    form.addEventListener('submit', function(e) {
      var fileInput = form.querySelector('input[type="file"]');
      if (fileInput && fileInput.files.length > 0) {
        btn.disabled = true;
        btn.textContent = "Analisi in corso...";
        container.style.display = 'block';
        
        // Fase 1: va fino al 90% in 45 secondi
        interval = setInterval(function() {
          progress += 2;
          if (progress > 90) progress = 90;
          bar.style.width = progress + '%';
          bar.textContent = progress + '%';
          
          if (progress < 20) text.textContent = "📄 Estrazione testo dal PDF...";
          else if (progress < 40) text.textContent = "📊 Analisi metriche finanziarie...";
          else if (progress < 60) text.textContent = "🧮 Calcolo indicatori e score...";
          else if (progress < 80) text.textContent = " Verifica coerenza dati...";
          else text.textContent = "⏳ Analisi quasi completata, attendi i risultati...";
        }, 1000); // 2% ogni secondo = 45 secondi per arrivare al 90%
        
        // Fase 2: dopo 50 secondi, arriva al 100% e mostra messaggio
        timeout = setTimeout(function() {
          clearInterval(interval);
          progress = 100;
          bar.style.width = '100%';
          bar.textContent = '100%';
          bar.style.background = '#10b981';
          text.innerHTML = '✅ Analisi completata! Se non vedi i risultati, <a href="/simula" style="color:var(--teal);text-decoration:underline">clicca qui per ricaricare</a>.';
          
          // Aggiungi pulsante di ricarica dopo 120 secondi totali
          setTimeout(function() {
            var reloadBtn = document.createElement('div');
            reloadBtn.style.cssText = 'margin-top:1rem;text-align:center';
            reloadBtn.innerHTML = '<a href="/simula" class="btn2" style="background:var(--teal)">🔄 Vai ai Risultati</a>';
            text.parentNode.appendChild(reloadBtn);
          }, 70000); // Dopo 70 secondi aggiuntivi (120 totali)
        }, 50000); // 50 secondi
      }
    });
  }
})();
</script>
</body></html>"""

@app.route("/favicon.ico")
def favicon():
    return ("", 204)

@app.route("/")
def index():
    if current_user.is_authenticated:
        report_count = Report.query.filter_by(user_id=current_user.id).count()
        if report_count == 0:
            welcome_msg = "Benvenuto in AUGET!"
            welcome_sub = "Inizia la tua prova gratuita di 7 giorni. Nessun impegno."
        else:
            name = current_user.email.split('@')[0]
            welcome_msg = "Bentornato, " + name + "!"
            welcome_sub = "Come vuoi procedere oggi?"
        content = "<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:4rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center'>"
        content += "<h1 style='color:#fbbf24;margin:0;font-size:3rem'>" + welcome_msg + "</h1>"
        content += "<p style='color:#e2e8f0;font-size:1.3rem;margin:1rem 0 0 0'>" + welcome_sub + "</p>"
        content += "</div>"
        content += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:1.5rem;margin-bottom:2rem'>"
        content += "<div class='card' style='border:2px solid var(--teal);padding:2rem;text-align:center'><h2 style='color:var(--teal);margin-top:0'>Analizza un Nuovo Bilancio</h2><p style='color:var(--muted)'>Carica un bilancio aziendale e ottieni lo score AUGET in pochi secondi.</p><a href='/analyze' class='btn2' style='margin-top:1rem;display:inline-block'>Analizza Ora</a></div>"
        content += "<div class='card' style='border:2px solid var(--gold);padding:2rem;text-align:center'><h2 style='color:var(--gold);margin-top:0'>La Tua Cronologia</h2><p style='color:var(--muted)'>Visualizza e gestisci tutte le analisi salvate automaticamente.</p><a href='/cronologia' class='btn2' style='margin-top:1rem;display:inline-block;background:var(--gold);color:#0b1220'>Vedi Cronologia</a></div>"
        content += "<div class='card' style='border:2px solid var(--blue);padding:2rem;text-align:center'><h2 style='color:var(--blue);margin-top:0'>Stress Test</h2><p style='color:var(--muted)'>Simula scenari macroeconomici e valuta la resilienza aziendale.</p><a href='/simula' class='btn2' style='margin-top:1rem;display:inline-block;background:var(--blue)'>Simula</a></div>"
        content += "</div>"
        content += "<div class='card' style='background:var(--bg);padding:2rem;text-align:center'><h3 style='color:var(--gold);margin-top:0'>Cosa puoi fare con AUGET:</h3><ul style='list-style:none;padding:0;margin:1.5rem 0;line-height:2'><li>Punteggio 0-100 con verdetto immediato</li><li>40 indicatori su redditivita, cassa, crescita e valutazione</li><li>Simulazioni macro con scenari Bear/Base/Bull</li><li>Confronto tra aziende dello stesso settore</li></ul><p style='color:var(--muted);margin:1rem 0 0 0'>Hai gia analizzato <strong>" + str(report_count) + "</strong> " + ("azienda" if report_count == 1 else "aziende") + ".</p></div>"
    else:
        content = '<div class="card"><h1 style="font-size:2.8rem;margin:0;letter-spacing:4px">AUGET</h1>'
        content += "<p style=\"font-size:1.2rem;color:var(--teal)\">Capire se un'azienda e solida, quanto vale e se il prezzo e giusto.</p>"
        content += '<p><a href="/register"><button style="width:auto;margin:0 6px">Inizia gratis</button></a>'
        content += '<a href="/login"><button class="btn2" style="width:auto;margin:0 6px">Accedi</button></a></p></div>'
        content += '<div class="card"><h2>Cosa fa</h2><ul>'
        content += '<li><strong style="color:var(--gold)">Punteggio 0-100</strong> con verdetto immediato</li>'
        content += '<li><strong style="color:var(--gold)">40 indicatori</strong> su redditivita, cassa, crescita e valutazione</li>'
        content += '<li><strong style="color:var(--gold)">20 indicatori bancari</strong> (ROE, ROA, CET1, NPL, Cost/Income)</li>'
        content += '<li><strong style="color:var(--gold)">Simulazioni macro</strong> con scenari Bear/Base/Bull</li>'
        content += '<li><strong style="color:var(--gold)">Classifica e confronto</strong> tra aziende</li>'
        content += '</ul></div>'
        content += '<div class="card" style="text-align:center"><h2 style="color:var(--teal)">Prova ora</h2>'
        content += '<p style="color:var(--muted)">7 giorni gratis, senza carta di credito.</p>'
        content += '<a href="/register"><button class="btn2" style="width:auto">Crea il tuo account</button></a></div>'
    return render_template_string(BASE_TEMPLATE, title="AUGET", content=content)


@app.route("/guida")
def guida():
    content = """<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:3rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center'>
    <h1 style='color:#fbbf24;margin:0;font-size:2.5rem'>Guida ai Criteri di Analisi</h1>
    <p style='color:#e2e8f0;font-size:1.2rem;margin:1rem 0 0 0'>Impara a interpretare i risultati di AUGET</p>
    </div>"""
    
    content += '<div class="card" style="margin-bottom:2rem">'
    content += '<h2 style="color:var(--gold);margin-top:0">Score AUGET (0-100)</h2>'
    content += '<p style="font-size:1.05rem;line-height:1.8">Lo <strong>Score AUGET</strong> è una sintesi da 0 a 100 della qualità complessiva dell\'azienda.</p>'
    content += '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;margin:1.5rem 0">'
    content += '<div style="background:rgba(16,185,129,0.1);padding:1rem;border-radius:8px;border-left:4px solid #10b981"><h3 style="color:#10b981;margin:0 0 0.5rem 0">85-100: Eccellente</h3><p style="margin:0;font-size:0.95rem">Azienda solida, bilanci sani, ottima redditività.</p></div>'
    content += '<div style="background:rgba(251,191,36,0.1);padding:1rem;border-radius:8px;border-left:4px solid #fbbf24"><h3 style="color:#fbbf24;margin:0 0 0.5rem 0">60-84: Buona</h3><p style="margin:0;font-size:0.95rem">Azienda affidabile con alcuni punti di attenzione.</p></div>'
    content += '<div style="background:rgba(239,68,68,0.1);padding:1rem;border-radius:8px;border-left:4px solid #ef4444"><h3 style="color:#ef4444;margin:0 0 0.5rem 0">0-59: Da Cautela</h3><p style="margin:0;font-size:0.95rem">Azienda con criticità significative.</p></div>'
    content += '</div></div>'
    
    content += '<div class="card" style="margin-bottom:2rem"><h2 style="color:var(--gold);margin-top:0">Valore Intrinseco</h2>'
    content += '<p style="font-size:1.05rem;line-height:1.8">Il <strong>Valore Intrinseco</strong> è il prezzo "giusto" dell\'azione basato sul flusso di cassa scontato (DCF).</p>'
    content += '<div style="background:var(--bg);padding:1.5rem;border-radius:8px;margin:1rem 0"><h4 style="margin-top:0">Come si calcola:</h4><ol style="margin:0;padding-left:1.5rem;line-height:1.8"><li>Stima dei flussi di cassa liberi (FCF) per 10 anni</li><li>Applicazione di un tasso di sconto</li><li>Calcolo del valore terminale</li><li>Divisione per il numero di azioni</li></ol></div></div>'
    
    content += '<div class="card" style="margin-bottom:2rem"><h2 style="color:var(--gold);margin-top:0">Margine di Sicurezza</h2>'
    content += '<p style="font-size:1.05rem;line-height:1.8">Lo sconto (o premio) del prezzo di mercato rispetto al valore intrinseco.</p>'
    content += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.5rem 0">'
    content += '<div style="background:rgba(16,185,129,0.1);padding:1rem;border-radius:8px"><h3 style="color:#10b981;margin:0 0 0.5rem 0">Margine Positivo (>20%)</h3><p style="margin:0;font-size:0.95rem">Azione sottovalutata. Opportunità di acquisto.</p></div>'
    content += '<div style="background:rgba(239,68,68,0.1);padding:1rem;border-radius:8px"><h3 style="color:#ef4444;margin:0 0 0.5rem 0">Margine Negativo</h3><p style="margin:0;font-size:0.95rem">Azione sopravvalutata. Meglio aspettare.</p></div>'
    content += '</div></div>'
    
    content += '<div class="card" style="margin-bottom:2rem"><h2 style="color:var(--gold);margin-top:0">ROE (Return on Equity)</h2>'
    content += '<p style="font-size:1.05rem;line-height:1.8">Il <strong>ROE</strong> (Utile Netto / Patrimonio Netto) misura la redditività del capitale.</p>'
    content += '<ul style="line-height:2"><li><strong style="color:#10b981">ROE > 20%</strong> - Eccellente</li><li><strong style="color:#fbbf24">ROE 15-20%</strong> - Ottimo</li><li><strong style="color:#3b82f6">ROE 10-15%</strong> - Buono</li><li><strong style="color:#ef4444">ROE < 10%</strong> - Scarso</li></ul></div>'
    
    content += '<div style="background:rgba(45,212,167,0.1);padding:2rem;border-radius:12px;margin:2rem 0;border:2px solid var(--teal)">'
    content += '<h2 style="color:var(--teal);margin-top:0">Come Usare Questi Dati</h2>'
    content += '<ol style="margin:0;padding-left:1.5rem;line-height:2;font-size:1.05rem">'
    content += '<li><strong>Non basarti su un solo indicatore</strong></li>'
    content += '<li><strong>Confronta con i competitor</strong></li>'
    content += '<li><strong>Guarda il trend storico</strong></li>'
    content += '<li><strong>Considera il contesto macro</strong></li>'
    content += '<li><strong>Applica il margine di sicurezza</strong></li>'
    content += '</ol></div>'
    
    content += '<div style="text-align:center;margin-top:2rem;padding:2rem;background:var(--bg);border-radius:12px">'
    content += '<h3 style="color:var(--gold);margin-top:0">Pronto a iniziare?</h3>'
    content += '<p style="margin:1rem 0">Carica il primo bilancio e scopri lo score AUGET.</p>'
    content += '<a href="/analyze" class="btn2" style="padding:1rem 2rem;font-size:1.1rem">Analizza un Bilancio</a>'
    content += '</div>'
    
    return render_template_string(BASE_TEMPLATE, title="Guida Completa", content=content)

    items = [("Score AUGET", "Sintesi da 0 a 100 della qualita aziendale."),
             ("Valore intrinseco", "Quanto vale un'azione secondo il flusso di cassa scontato."),
             ("Margine di sicurezza", "Sconto del prezzo rispetto al valore intrinseco."),
             ("ROE", "Utile diviso patrimonio: redditivita del capitale. Sopra 12-15% e ottimo."),
             ("ROA", "Utile diviso totale attivo: efficienza della banca."),
             ("CET1", "Capitale primario rispetto ai rischi: solidita patrimoniale.")]
    rows = "".join(f"<div class='card'><h2>{k}</h2><p>{v}</p></div>" for k, v in items)
    content = "<h1>Guida ai criteri</h1>" + rows
    return render_template_string(BASE_TEMPLATE, title="Guida", content=content)

@app.route("/contatti")
def contatti():
    cfg = get_cfg()
    content = f"""<div class="card"><h1>Contatti</h1>
    <p><strong>Email:</strong> {cfg.contact_email}</p>
    <p><strong>Telegram:</strong> {cfg.contact_telegram}</p>
    <p><strong>LinkedIn:</strong> {cfg.contact_linkedin}</p></div>"""
    return render_template_string(BASE_TEMPLATE, title="Contatti", content=content)

@app.route("/collabora", methods=["GET", "POST"])
def collabora():
    if request.method == "POST":
        c = CollabRequest(name=request.form.get("name"), email=request.form.get("email"),
                          kind=request.form.get("kind"), message=request.form.get("message"))
        db.session.add(c); db.session.commit()
        flash("Proposta inviata!", "success")
        return redirect("/collabora")
    content = """<div class="card"><h1>Collabora con noi</h1>
    <form method="post"><input name="name" placeholder="Nome" required>
      <input type="email" name="email" placeholder="Email" required>
      <textarea name="message" rows="5" placeholder="La tua proposta" required></textarea>
      <button type="submit" style="margin-top:1rem">Invia</button></form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Collabora", content=content)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not get_cfg().site_open:
            flash("Registrazioni sospese.", "error")
            return redirect(url_for("index"))
        email = request.form.get("email")
        password = request.form.get("password")
        if User.query.filter_by(email=email).first():
            flash("Email gia registrata", "error")
            return redirect(url_for("register"))
        user = User(email=email, subscription_tier="trial", subscription_expires=datetime.utcnow() + timedelta(days=7))
        user.set_password(password)
        user.phone = (request.form.get("phone") or "").strip() or None
        codes = _gen_codes()
        user.recovery_hash = _json.dumps([_hash_code(c) for c in codes])
        db.session.add(user)
        db.session.commit()
        session["new_codes"] = codes
        login_user(user, remember=request.form.get("remember") == "on")
        send_email(email, "Benvenuto in AUGET", "<p>Il tuo account e pronto.</p>")
        flash("Registrazione completata!", "success")
        return redirect("/codes")
    content = """<div class="card"><h1>Registrati</h1>
    <form method="post"><input type="email" name="email" placeholder="Email" required>
      <input type="password" name="password" placeholder="Password" required>
      <input name="phone" placeholder="Telefono (facoltativo)">
      <button type="submit">Crea account</button></form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Registrazione", content=content)


@app.route("/assistenza")
def assistenza():
    content = "<div class='card'><h1>Assistenza</h1>"
    content += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:2rem;margin:2rem 0'>"
    content += "<div class='card'><h2 style='color:var(--teal)'>📚 Documentazione</h2><p>Guide e tutorial su come usare AUGET.</p><a href='/guida' class='btn2' style='display:inline-block;margin-top:1rem'>Vai alla Guida</a></div>"
    content += "<div class='card'><h2 style='color:var(--gold)'>📧 Email Support</h2><p>Rispondiamo entro 24 ore.</p><a href='mailto:support@sibilla.cc' class='btn2' style='display:inline-block;margin-top:1rem;background:var(--gold);color:#0b1220'>Scrivici</a></div>"
    content += "<div class='card'><h2 style='color:var(--blue)'>💬 FAQ</h2><p>Domande frequenti e piani.</p><a href='/prezzi' class='btn2' style='display:inline-block;margin-top:1rem'>Vedi Prezzi</a></div>"
    content += "</div>"
    content += "<div class='card' style='background:linear-gradient(135deg, rgba(45,212,167,0.1), rgba(240,180,41,0.1));border:2px solid var(--teal);padding:2rem;text-align:center'>"
    content += "<h2 style='color:var(--teal);margin-top:0'>Demo Personalizzata?</h2>"
    content += "<p style='font-size:1.1rem'>Prenota una demo gratuita di 30 minuti.</p>"
    content += "<a href='mailto:support@sibilla.cc?subject=Demo AUGET' class='btn2' style='padding:1rem 2rem;font-size:1.1rem'>Prenota Demo</a>"
    content += "</div></div>"
    return render_template_string(BASE_TEMPLATE, title="Assistenza", content=content)

@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        msg = request.form.get("message", "")
        rating = request.form.get("rating", "5")
        flash(f"Grazie per il feedback! Valutazione: {rating}/5", "success")
        return redirect("/feedback")
    
    content = "<div class='card'><h1>Feedback</h1>"
    content += "<p style='color:var(--muted)'>Aiutaci a migliorare AUGET! Il tuo parere è fondamentale.</p>"
    content += "<form method='post' style='margin-top:2rem'>"
    content += "<label style='display:block;margin-bottom:0.5rem;font-weight:600'>Come valuti AUGET?</label>"
    content += "<div style='display:flex;gap:1rem;margin-bottom:1.5rem'>"
    for i in range(5, 0, -1):
        content += f"<label style='cursor:pointer'><input type='radio' name='rating' value='{i}' style='margin-right:5px'> {'⭐' * i}</label>"
    content += "</div>"
    content += "<label style='display:block;margin-bottom:0.5rem;font-weight:600'>Cosa ne pensi?</label>"
    content += "<textarea name='message' placeholder='Cosa ti è piaciuto? Cosa vorresti migliorare?' style='width:100%;height:200px;margin-bottom:1rem;padding:1rem;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--text)'></textarea>"
    content += "<button type='submit' class='btn2'>Invia Feedback</button>"
    content += "</form>"
    content += "<p style='color:var(--muted);margin-top:1rem'>Oppure scrivici a <a href='mailto:support@sibilla.cc' style='color:var(--teal)'>support@sibilla.cc</a></p>"
    content += "</div>"
    return render_template_string(BASE_TEMPLATE, title="Feedback", content=content)



@app.route("/cronologia", methods=["GET", "POST"])
@login_required
def cronologia():
    """Cronologia analisi con filtri e rinomina"""
    # Gestione rinomina
    if request.method == "POST":
        if "rename_id" in request.form:
            report_id = request.form.get("rename_id")
            new_name = request.form.get("new_name", "").strip()
            if new_name and report_id:
                report = Report.query.get(report_id)
                if report and report.user_id == current_user.id:
                    report.company = new_name
                    db.session.commit()
                    flash("Report rinominato!", "success")
                else:
                    flash("Errore nella rinomina", "error")
            return redirect("/cronologia")
        
        if "delete_id" in request.form:
            report_id = request.form.get("delete_id")
            report = Report.query.get(report_id)
            if report and report.user_id == current_user.id:
                db.session.delete(report)
                db.session.commit()
                flash("Report eliminato", "success")
            return redirect("/cronologia")
    
    # Filtri
    search_query = request.args.get("search", "").strip()
    date_filter = request.args.get("date_filter", "").strip()
    sort_by = request.args.get("sort", "created_at")
    sort_order = request.args.get("order", "desc")
    
    # Query base
    query = Report.query.filter_by(user_id=current_user.id)
    
    # Applica filtri
    if search_query:
        query = query.filter(
            db.or_(
                Report.company.ilike(f"%{search_query}%"),
                Report.filename.ilike(f"%{search_query}%")
            )
        )
    
    if date_filter:
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_filter, "%Y-%m-%d")
            query = query.filter(db.func.date(Report.created_at) == date_obj.date())
        except:
            pass
    
    # Ordinamento
    if sort_by == "created_at":
        query = query.order_by(Report.created_at.desc() if sort_order == "desc" else Report.created_at.asc())
    elif sort_by == "score":
        query = query.order_by(Report.score.desc() if sort_order == "desc" else Report.score.asc())
    elif sort_by == "company":
        query = query.order_by(Report.company.asc() if sort_order == "desc" else Report.company.desc())
    
    reports = query.all()
    
    # HTML
    html = """<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:3rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center'>
    <h1 style='color:#fbbf24;margin:0;font-size:2.5rem'>📚 Cronologia Analisi</h1>
    <p style='color:#e2e8f0;font-size:1.2rem;margin:1rem 0 0 0'>Tutte le tue analisi salvate automaticamente</p>
    </div>"""
    
    # Filtri e ricerca
    html += '<div class="card" style="margin-bottom:2rem">'
    html += '<form method="get" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;align-items:end">'
    
    html += '<div><label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Cerca per nome o file</label>'
    html += '<input type="text" name="search" value="' + (search_query or "") + '" placeholder="Es. Generali, bilancio 2023..." style="width:100%;padding:0.8rem;border-radius:8px;border:2px solid var(--line);background:var(--bg);color:var(--text)">'
    html += '</div>'
    
    html += '<div><label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Filtra per data</label>'
    html += '<input type="date" name="date_filter" value="' + (date_filter or "") + '" style="width:100%;padding:0.8rem;border-radius:8px;border:2px solid var(--line);background:var(--bg);color:var(--text)">'
    html += '</div>'
    
    html += '<div><label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Ordina per</label>'
    html += '<select name="sort" style="width:100%;padding:0.8rem;border-radius:8px;border:2px solid var(--line);background:var(--bg);color:var(--text)">'
    html += '<option value="created_at"' + (' selected' if sort_by == "created_at" else "") + '>Data analisi</option>'
    html += '<option value="score"' + (' selected' if sort_by == "score" else "") + '>Score</option>'
    html += '<option value="company"' + (' selected' if sort_by == "company" else "") + '>Nome azienda</option>'
    html += '</select>'
    html += '</div>'
    
    html += '<div><button type="submit" class="btn2" style="width:100%">Applica Filtri</button></div>'
    html += '<div><a href="/cronologia" class="btn2" style="width:100%;background:var(--blue)">Reset</a></div>'
    
    html += '</form></div>'
    
    # Lista report
    if reports:
        html += f'<p style="color:var(--muted);margin-bottom:1rem">{len(reports)} analisi trovate</p>'
        html += '<div style="display:grid;gap:1rem">'
        
        for rep in reports:
            score_color = "#10b981" if (rep.score or 0) >= 70 else ("#fbbf24" if (rep.score or 0) >= 45 else "#ef4444")
            date_str = rep.created_at.strftime("%d/%m/%Y %H:%M") if rep.created_at else "N/D"
            
            html += '<div class="card" style="display:grid;grid-template-columns:1fr auto auto auto;gap:1rem;align-items:center;padding:1.5rem">'
            
            # Info principali
            html += '<div>'
            html += '<h3 style="margin:0 0 0.5rem 0;color:var(--gold)">' + (rep.company or rep.filename) + '</h3>'
            html += '<p style="margin:0;color:var(--muted);font-size:0.9rem">' + (rep.sector or "Settore non specificato") + '</p>'
            html += '<p style="margin:0.3rem 0 0 0;color:var(--muted);font-size:0.85rem">Analizzato il: ' + date_str + '</p>'
            html += '</div>'
            
            # Score
            html += '<div style="text-align:center;padding:1rem;background:rgba(0,0,0,0.2);border-radius:8px;min-width:100px">'
            html += '<div style="font-size:2rem;font-weight:800;color:' + score_color + '">' + str(rep.score or "N/D") + '</div>'
            html += '<div style="font-size:0.8rem;color:var(--muted)">Score</div>'
            html += '</div>'
            
            # Azioni
            html += '<div style="display:flex;gap:0.5rem">'
            html += '<form method="post" style="display:inline">'
            html += '<input type="hidden" name="rename_id" value="' + str(rep.id) + '">'
            html += '<input type="text" name="new_name" placeholder="Nuovo nome" value="' + (rep.company or "") + '" style="padding:0.5rem;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--text);width:150px">'
            html += '<button type="submit" class="btn2" style="padding:0.5rem 1rem;font-size:0.9rem">Rinomina</button>'
            html += '</form>'
            html += '</div>'
            
            html += '<div style="display:flex;gap:0.5rem">'
            html += '<a href="/simula/' + str(rep.id) + '" class="btn2" style="padding:0.5rem 1rem;background:var(--teal)">Vedi</a>'
            html += '<a href="/simula/' + str(rep.id) + '/export" class="btn2" style="padding:0.5rem 1rem;background:var(--gold);color:#0b1220">PDF</a>'
            html += """<form method="post" style="display:inline" onsubmit="return confirm(\'Eliminare questo report?\')">""" + "\n"
            html += '<input type="hidden" name="delete_id" value="' + str(rep.id) + '">'
            html += '<button type="submit" class="btn2" style="padding:0.5rem 1rem;background:#ef4444">Elimina</button>'
            html += '</form>'
            html += '</div>'
            
            html += '</div>'
        
        html += '</div>'
    else:
        html += '<div class="card" style="text-align:center;padding:3rem">'
        html += '<h3 style="color:var(--muted);margin:0 0 1rem 0">Nessuna analisi trovata</h3>'
        html += '<p style="color:var(--muted);margin:0 0 1.5rem 0">Carica il primo bilancio per iniziare</p>'
        html += '<a href="/analyze" class="btn2" style="padding:1rem 2rem">Analizza Bilancio</a>'
        html += '</div>'
    
    return render_template_string(BASE_TEMPLATE, title="Cronologia", content=html)

@app.route("/watchlist", methods=["GET", "POST"])
@login_required
def watchlist():
    """Watchlist semplice per salvare ticker"""
    
    if "watchlist" not in session:
        session["watchlist"] = []
    
    if request.method == "POST":
        action = request.form.get("action")
        ticker = request.form.get("ticker", "").upper().strip()
        
        if ticker and action == "add":
            if ticker not in session["watchlist"]:
                session["watchlist"].append(ticker)
                session.modified = True
                flash(f"{ticker} aggiunto alla watchlist!", "success")
            else:
                flash(f"{ticker} è già nella watchlist", "info")
        elif ticker and action == "remove":
            if ticker in session["watchlist"]:
                session["watchlist"].remove(ticker)
                session.modified = True
                flash(f"{ticker} rimosso dalla watchlist", "success")
    
    popular_tickers = {
        "AAPL": {"name": "Apple Inc.", "sector": "Tecnologia", "desc": "iPhone, Mac, iPad, servizi digitali"},
        "MSFT": {"name": "Microsoft", "sector": "Tecnologia", "desc": "Software, Cloud Azure, Office 365"},
        "TSLA": {"name": "Tesla", "sector": "Automotive", "desc": "Auto elettriche, batterie, energia solare"},
        "AMZN": {"name": "Amazon", "sector": "E-commerce/Cloud", "desc": "Retail online, AWS, streaming"},
        "GOOGL": {"name": "Alphabet", "sector": "Tecnologia", "desc": "Google, YouTube, pubblicità online"},
        "NVDA": {"name": "NVIDIA", "sector": "Semiconduttori", "desc": "GPU, AI, chip per gaming e data center"},
        "META": {"name": "Meta Platforms", "sector": "Tecnologia", "desc": "Facebook, Instagram, metaverso"},
        "BRK.B": {"name": "Berkshire Hathaway", "sector": "Finanza", "desc": "Conglomerato di Warren Buffett"},
    }
    
    html = "<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:3rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center'>"
    html += "<h1 style='color:#fbbf24;margin:0;font-size:2.5rem'>📊 Watchlist</h1>"
    html += "<p style='color:#e2e8f0;font-size:1.2rem;margin:1rem 0 0 0'>Salva i ticker che vuoi monitorare e analizzarli</p>"
    html += "</div>"
    
    html += '<div class="card" style="margin-bottom:2rem">'
    html += '<h2 style="color:var(--gold);margin-top:0">Aggiungi Ticker</h2>'
    html += '<form method="post" style="display:flex;gap:1rem;align-items:end;flex-wrap:wrap">'
    html += '<div style="flex:1;min-width:200px">'
    html += '<label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Ticker (es. AAPL, MSFT, TSLA)</label>'
    html += '<input type="text" name="ticker" placeholder="Inserisci ticker..." required style="width:100%;padding:1rem;border-radius:8px;border:2px solid var(--line);background:var(--bg);color:var(--text);font-size:1.1rem;font-weight:600" autofocus>'
    html += '<input type="hidden" name="action" value="add">'
    html += '</div>'
    html += '<button type="submit" class="btn2" style="padding:1rem 2rem;font-size:1.1rem;background:var(--teal)">Aggiungi</button>'
    html += '</form>'
    html += '</div>'
    
    if session["watchlist"]:
        html += '<div class="card" style="margin-bottom:2rem;border:2px solid var(--teal)">'
        html += '<h2 style="color:var(--teal);margin-top:0">I Tuoi Ticker Salvati</h2>'
        html += '<div style="display:grid;gap:1rem;margin:1.5rem 0">'
        
        for ticker in session["watchlist"]:
            info = popular_tickers.get(ticker, {"name": "N/D", "sector": "N/D", "desc": "N/D"})
            html += '<div style="background:var(--bg);padding:1.5rem;border-radius:8px;display:grid;grid-template-columns:1fr auto;gap:1rem;align-items:center">'
            html += '<div>'
            html += '<h3 style="color:var(--gold);margin:0 0 0.3rem 0;font-size:1.5rem">' + ticker + '</h3>'
            html += '<p style="font-weight:600;margin:0 0 0.3rem 0">' + info["name"] + '</p>'
            html += '<p style="color:var(--muted);margin:0;font-size:0.9rem">' + info["desc"] + '</p>'
            html += '</div>'
            html += '<div style="display:flex;gap:0.5rem">'
            html += '<a href="https://finance.yahoo.com/quote/' + ticker + '" target="_blank" class="btn2" style="background:var(--blue)">Vedi Prezzo</a>'
            html += '<form method="post" style="display:inline"><input type="hidden" name="ticker" value="' + ticker + '"><input type="hidden" name="action" value="remove"><button type="submit" class="btn2" style="background:#ef4444">Rimuovi</button></form>'
            html += '</div></div>'
        html += '</div></div>'
    else:
        html += '<div class="card" style="margin-bottom:2rem;text-align:center;padding:2rem">'
        html += '<p style="color:var(--muted);margin:0">Nessun ticker salvato. Aggiungi il primo ticker sopra!</p>'
        html += '</div>'
    
    html += '<div class="card"><h2 style="color:var(--gold);margin-top:0">Ticker Popolari</h2>'
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:1.5rem;margin:1.5rem 0">'
    for ticker, info in popular_tickers.items():
        in_watchlist = ticker in session["watchlist"]
        html += '<div class="card" style="border-left:4px solid var(--teal);padding:1.5rem">'
        html += '<h3 style="color:var(--teal);margin:0 0 0.5rem 0;font-size:1.5rem">' + ticker + '</h3>'
        html += '<p style="font-weight:600;margin:0 0 0.3rem 0">' + info["name"] + '</p>'
        html += '<p style="color:var(--muted);margin:0 0 0.3rem 0;font-size:0.9rem"><strong>Settore:</strong> ' + info["sector"] + '</p>'
        html += '<p style="color:var(--muted);margin:0 0 1rem 0;font-size:0.9rem">' + info["desc"] + '</p>'
        if not in_watchlist:
            html += '<form method="post" style="display:inline"><input type="hidden" name="ticker" value="' + ticker + '"><input type="hidden" name="action" value="add"><button type="submit" class="btn2" style="display:inline-block;padding:0.5rem 1rem;font-size:0.9rem">Aggiungi</button></form> '
        html += '<a href="https://finance.yahoo.com/quote/' + ticker + '" target="_blank" class="btn2" style="display:inline-block;padding:0.5rem 1rem;font-size:0.9rem;background:var(--blue)">Yahoo Finance</a>'
        html += '</div>'
    html += '</div></div>'
    
    return render_template_string(BASE_TEMPLATE, title="Watchlist", content=html)

def watchlist():
    """Gestione watchlist ticker con dati yfinance"""
    ticker_data = None
    error_msg = None
    
    if request.method == "POST":
        ticker = request.form.get("ticker", "").upper().strip()
        if ticker:
            try:
                import yfinance as yf
                import requests
                
                # Tentativo 1: yfinance
                stock = yf.Ticker(ticker)
                info = stock.info
                
                # Verifichiamo se abbiamo dati validi
                if not info or info.get("currentPrice") is None:
                    # Tentativo 2: API diretta di Yahoo Finance
                    try:
                        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
                        params = {"modules": "price,summaryProfile,financialData", "corsDomain": "finance.yahoo.com"}
                        resp = requests.get(url, params=params, timeout=10)
                        data = resp.json()
                        
                        if "quoteSummary" in data and "result" in data["quoteSummary"] and data["quoteSummary"]["result"]:
                            result = data["quoteSummary"]["result"][0]
                            price_info = result.get("price", {})
                            profile = result.get("summaryProfile", {})
                            
                            ticker_data = {
                                "ticker": ticker,
                                "name": price_info.get("longName", profile.get("longBusinessSummary", ticker)),
                                "price": price_info.get("regularMarketPrice", {}).get("raw", "N/D"),
                                "currency": price_info.get("currency", "USD"),
                                "sector": profile.get("sector", "N/D"),
                                "industry": profile.get("industry", "N/D"),
                                "description": (profile.get("longBusinessSummary", "Nessuna descrizione disponibile.") or "Nessuna descrizione disponibile.")[:300] + "...",
                                "marketCap": price_info.get("marketCap", {}).get("raw", 0),
                                "peRatio": "N/D",
                                "dividendYield": 0
                            }
                            
                            if ticker_data["marketCap"]:
                                if ticker_data["marketCap"] >= 1e9:
                                    ticker_data["marketCap_str"] = f"${ticker_data['marketCap']/1e9:.2f}B"
                                elif ticker_data["marketCap"] >= 1e6:
                                    ticker_data["marketCap_str"] = f"${ticker_data['marketCap']/1e6:.2f}M"
                                else:
                                    ticker_data["marketCap_str"] = f"${ticker_data['marketCap']}"
                            else:
                                ticker_data["marketCap_str"] = "N/D"
                            
                            flash(f"{ticker} trovato!", "success")
                        else:
                            error_msg = f"Ticker {ticker} non trovato. Verifica il simbolo."
                    except:
                        error_msg = f"Impossibile recuperare dati per {ticker}. Riprova più tardi."
                else:
                    # yfinance ha funzionato
                    ticker_data = {
                        "ticker": ticker,
                        "name": info.get("shortName", info.get("longName", "N/D")),
                        "price": info.get("currentPrice", "N/D"),
                        "currency": info.get("currency", "USD"),
                        "sector": info.get("sector", "N/D"),
                        "industry": info.get("industry", "N/D"),
                        "description": (info.get("longBusinessSummary") or "Nessuna descrizione disponibile.")[:300] + "...",
                        "marketCap": info.get("marketCap", 0),
                        "peRatio": info.get("trailingPE", "N/D"),
                        "dividendYield": info.get("dividendYield", 0)
                    }
                    
                    if ticker_data["marketCap"]:
                        if ticker_data["marketCap"] >= 1e9:
                            ticker_data["marketCap_str"] = f"${ticker_data['marketCap']/1e9:.2f}B"
                        elif ticker_data["marketCap"] >= 1e6:
                            ticker_data["marketCap_str"] = f"${ticker_data['marketCap']/1e6:.2f}M"
                        else:
                            ticker_data["marketCap_str"] = f"${ticker_data['marketCap']}"
                    else:
                        ticker_data["marketCap_str"] = "N/D"
                    
                    flash(f"{ticker} trovato!", "success")
            except Exception as e:
                error_msg = f"Servizio temporaneamente non disponibile. Riprova più tardi."
    
    popular_tickers = [
        ("AAPL", "Apple Inc.", "Tech leader - iPhone, Mac, iPad"),
        ("MSFT", "Microsoft", "Cloud & Software - Azure, Office 365"),
        ("TSLA", "Tesla", "EV & Energia - Auto elettriche, batterie"),
        ("AMZN", "Amazon", "E-commerce & Cloud - AWS, retail"),
        ("NVDA", "NVIDIA", "AI & Chip - GPU, intelligenza artificiale"),
    ]
    
    html = "<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:3rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center'>"
    html += "<h1 style='color:#fbbf24;margin:0;font-size:2.5rem'>Watchlist</h1>"
    html += "<p style='color:#e2e8f0;font-size:1.2rem;margin:1rem 0 0 0'>Monitora i ticker e ottieni informazioni in tempo reale</p>"
    html += "</div>"
    
    html += '<div class="card" style="margin-bottom:2rem">'
    html += '<h2 style="color:var(--gold);margin-top:0">Cerca un Ticker</h2>'
    html += '<form method="post" style="display:flex;gap:1rem;align-items:end;flex-wrap:wrap">'
    html += '<div style="flex:1;min-width:200px">'
    html += '<label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Ticker (es. AAPL, MSFT, TSLA)</label>'
    html += '<input type="text" name="ticker" placeholder="Inserisci ticker..." required style="width:100%;padding:1rem;border-radius:8px;border:2px solid var(--line);background:var(--bg);color:var(--text);font-size:1.1rem;font-weight:600" autofocus>'
    html += '</div>'
    html += '<button type="submit" class="btn2" style="padding:1rem 2rem;font-size:1.1rem;background:var(--teal)">Cerca</button>'
    html += '</form>'
    html += '</div>'
    
    if error_msg:
        html += '<div class="card" style="border:2px solid #ef4444;background:rgba(239,68,68,0.1);margin-bottom:2rem">'
        html += '<p style="color:#ef4444;margin:0;font-weight:600">⚠️ ' + error_msg + '</p>'
        html += '</div>'
    
    if ticker_data:
        html += '<div class="card" style="border:2px solid var(--teal);margin-bottom:2rem;padding:2rem">'
        html += '<h2 style="color:var(--gold);margin:0 0 1rem 0">' + ticker_data["ticker"] + ' - ' + ticker_data["name"] + '</h2>'
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;margin:1.5rem 0">'
        html += '<div style="background:var(--bg);padding:1rem;border-radius:8px"><h3 style="color:var(--teal);margin:0 0 0.5rem 0">Prezzo</h3><p style="font-size:2rem;font-weight:800;margin:0">' + str(ticker_data["price"]) + ' ' + ticker_data["currency"] + '</p></div>'
        html += '<div style="background:var(--bg);padding:1rem;border-radius:8px"><h3 style="color:var(--teal);margin:0 0 0.5rem 0">Settore</h3><p style="font-size:1.2rem;margin:0">' + ticker_data["sector"] + '</p></div>'
        html += '<div style="background:var(--bg);padding:1rem;border-radius:8px"><h3 style="color:var(--teal);margin:0 0 0.5rem 0">Market Cap</h3><p style="font-size:1.3rem;margin:0">' + ticker_data["marketCap_str"] + '</p></div>'
        html += '</div>'
        html += '<div style="background:var(--bg);padding:1.5rem;border-radius:8px;margin:1.5rem 0">'
        html += '<h3 style="color:var(--gold);margin:0 0 0.5rem 0">Descrizione Azienda</h3>'
        html += '<p style="line-height:1.8;color:var(--muted)">' + ticker_data["description"] + '</p>'
        html += '</div>'
        html += '<div style="margin-top:1.5rem;display:flex;gap:1rem">'
        html += '<a href="/analyze" class="btn2" style="background:var(--teal)">Analizza Bilancio</a>'
        html += '<a href="https://finance.yahoo.com/quote/' + ticker_data["ticker"] + '" target="_blank" class="btn2" style="background:var(--blue)">Vedi su Yahoo Finance</a>'
        html += '</div></div>'
    
    html += '<div class="card"><h2 style="color:var(--gold);margin-top:0">Ticker Popolari</h2>'
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:1.5rem;margin:1.5rem 0">'
    for ticker, name, desc in popular_tickers:
        html += '<div class="card" style="border-left:4px solid var(--teal);padding:1.5rem">'
        html += '<h3 style="color:var(--teal);margin:0 0 0.5rem 0;font-size:1.5rem">' + ticker + '</h3>'
        html += '<p style="font-weight:600;margin:0 0 0.3rem 0">' + name + '</p>'
        html += '<p style="color:var(--muted);margin:0 0 1rem 0;font-size:0.9rem">' + desc + '</p>'
        html += '<a href="/analyze" class="btn2" style="display:inline-block;padding:0.5rem 1rem;font-size:0.9rem">Analizza</a>'
        html += '</div>'
    html += '</div></div>'
    
    return render_template_string(BASE_TEMPLATE, title="Watchlist", content=html)


@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    rs = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    if request.method == "POST":
        ids = request.form.getlist("ids")[:3]
        reps = [r for r in rs if str(r.id) in ids]
        if len(reps) < 2:
            flash("Seleziona almeno 2 report", "error")
            return redirect("/compare")
        
        html = "<div class='card'><h1>�� Confronto Aziende</h1>"
        html += "<table style='width:100%;border-collapse:collapse;margin-top:1.5rem'><tr style='background:var(--bg)'>"
        html += "<th style='padding:1rem;text-align:left;border-bottom:2px solid var(--line)'>Metrica</th>"
        for r in reps:
            html += f"<th style='padding:1rem;border-bottom:2px solid var(--line)'>{r.company or r.filename}</th>"
        html += "</tr>"
        
        metrics = [("score", "Score AUGET", "var(--gold)"), ("sector", "Settore", "var(--teal)")]
        for m, label, color in metrics:
            html += f"<tr><td style='padding:0.8rem;color:var(--muted)'>{label}</td>"
            for r in reps:
                val = getattr(r, m, "N/D")
                html += f"<td style='padding:0.8rem;font-weight:600;color:{color}'>{val}</td>"
            html += "</tr>"
        
        html += "</table></div>"
        return render_template_string(BASE_TEMPLATE, title="Confronto", content=html)
    
    boxes = ""
    for r in rs:
        boxes += f"<label style='display:block;margin:0.8rem 0;padding:1rem;background:var(--bg);border-radius:8px;cursor:pointer;border:2px solid transparent;transition:all 0.3s'><input type='checkbox' name='ids' value='{r.id}' style='margin-right:10px;width:18px;height:18px'> <strong>{r.company or r.filename}</strong><br><span style='color:var(--muted);font-size:0.9rem'>{r.sector or 'Altro'} • Score: {r.score or 'N/D'}</span></label>"
    
    no_reports_msg = '<p style="color:var(--muted)">Nessun report disponibile. Carica prima un bilancio.</p>'
    content_compare = f"<div class='card'><h1>🔍 Confronta Report</h1><p style='color:var(--muted)'>Seleziona 2 o 3 aziende da confrontare</p><form method='post'>{(boxes or no_reports_msg)}<button type='submit' class='btn2' style='margin-top:1.5rem'>Confronta Selezionati</button></form></div>"
    return render_template_string(BASE_TEMPLATE, title="Confronta", content=content_compare)

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user
    total_reports = Report.query.filter_by(user_id=user.id).count()
    total_simulations = SavedSimulation.query.filter_by(user_id=user.id).count() if 'SavedSimulation' in globals() else 0
    recent_reports = Report.query.filter_by(user_id=user.id).order_by(Report.created_at.desc()).limit(5).all()
    
    content = "<div class='card'><h1> Dashboard</h1>"
    content += f"<p style='color:var(--muted);font-size:1.1rem'>Benvenuto, {user.email}</p>"
    
    # Stats
    content += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1.5rem;margin:2rem 0'>"
    content += f"<div class='card' style='text-align:center;background:linear-gradient(135deg, rgba(45,212,167,0.1), transparent);border:2px solid var(--teal)'><h3 style='color:var(--teal);font-size:2.5rem;margin:0.5rem 0'>{total_reports}</h3><p style='color:var(--muted);margin:0'>Report Analizzati</p></div>"
    content += f"<div class='card' style='text-align:center;background:linear-gradient(135deg, rgba(240,180,41,0.1), transparent);border:2px solid var(--gold)'><h3 style='color:var(--gold);font-size:2.5rem;margin:0.5rem 0'>{total_simulations}</h3><p style='color:var(--muted);margin:0'>Simulazioni</p></div>"
    content += f"<div class='card' style='text-align:center;background:linear-gradient(135deg, rgba(59,130,246,0.1), transparent);border:2px solid var(--blue)'><h3 style='color:var(--blue);font-size:1.5rem;margin:0.5rem 0'>{(user.subscription_tier or 'free').upper()}</h3><p style='color:var(--muted);margin:0'>Piano Attivo</p></div>"
    content += "</div>"
    
    # Recent reports
    if recent_reports:
        content += "<h2 style='margin-top:2rem'>📈 Report Recenti</h2><div style='display:grid;gap:1rem;margin-top:1rem'>"
        for r in recent_reports:
            score_color = "#10b981" if (r.score or 0) >= 70 else ("#fbbf24" if (r.score or 0) >= 45 else "#ef4444")
            content += f"<div class='card' style='display:flex;justify-content:space-between;align-items:center;padding:1rem'><div><h3 style='margin:0'>{r.company or r.filename}</h3><p style='color:var(--muted);margin:0.3rem 0 0 0'>{r.sector or 'Altro'} • {r.created_at.strftime('%d/%m/%Y')}</p></div><div style='font-size:2rem;font-weight:800;color:{score_color}'>{r.score or 'N/D'}/100</div></div>"
        content += "</div>"
    
    content += "<div style='margin-top:2rem;text-align:center'><a href='/simula' class='btn2' style='padding:1rem 2rem;font-size:1.1rem'>Nuova Simulazione</a> <a href='/reports' class='btn2' style='padding:1rem 2rem;font-size:1.1rem;background:var(--blue)'>Tutti i Report</a></div>"
    content += "</div>"
    return render_template_string(BASE_TEMPLATE, title="Dashboard", content=content)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            cfg = get_cfg()
            t = user.subscription_tier
            if not cfg.site_open and t != "admin" and not (t == "demo" and cfg.demo_enabled):
                flash("Sito in manutenzione.", "error")
                return redirect(url_for("index"))
            login_user(user, remember=request.form.get("remember") == "on")
            if not user.subscription_active:
                return redirect(url_for("pricing"))
            return redirect(url_for("analyze_page"))
        flash("Credenziali non valide", "error")
    content = """<div class="card"><h1>Accedi</h1>
    <form method="post"><input type="email" name="email" placeholder="Email" required>
      <input type="password" name="password" placeholder="Password" required>
      <button type="submit">Accedi</button></form>
    <p style="text-align:center;margin-top:1rem"><a href="/recover" style="color:var(--blue)">Hai problemi ad accedere?</a></p></div>"""
    return render_template_string(BASE_TEMPLATE, title="Login", content=content)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/pricing")
@login_required
def pricing():
    content = """<h1>Scegli il tuo piano</h1>
    <div class="tier"><h3>Basic</h3><div class="price">9€/mese</div><p>10 analisi/mese</p>
      <form method="post" action="/checkout/basic"><button type="submit">Scegli</button></form></div>
    <div class="tier"><h3>Professional</h3><div class="price">29€/mese</div><p>Illimitate</p>
      <form method="post" action="/checkout/pro"><button type="submit">Scegli</button></form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Piani", content=content)

@app.route("/checkout/<tier>", methods=["POST"])
@login_required
def checkout(tier):
    current_user.subscription_tier = tier
    current_user.subscription_expires = datetime.utcnow() + timedelta(days=30)
    db.session.commit()
    flash(f"Piano {tier} attivato!", "success")
    return redirect(url_for("analyze_page"))

@app.route("/analyze")
@login_required
@subscription_required
def analyze_page():
    lim = PLAN_LIMITS.get(current_user.subscription_tier)
    used = _used_this_month(current_user.id)
    counter = f"<p style='color:var(--muted)'>Analisi questo mese: {used}" + (f" / {lim}" if lim else " (illimitate)") + "</p>"
    content = f"""<div class="card"><h1>Analizza Bilancio</h1>{counter}
    <form method="post" enctype="multipart/form-data" action="/do_analyze">
      <input type="file" name="report" accept=".pdf,.docx,.txt,.html,.htm" required>
      <button type="submit" id="analyze-btn" style="margin-top:1rem">Analizza</button>
      <div id="progress-container" style="display:none;margin-top:1rem">
        <div style="background:var(--bg);border-radius:8px;overflow:hidden;height:30px;border:2px solid var(--line)">
          <div id="progress-bar" style="width:0%;height:100%;background:linear-gradient(90deg, #10b981, #059669);transition:width 0.3s ease;display:flex;align-items:center;justify-content:center;color:white;font-weight:700;font-size:0.9rem">0%</div>
        </div>
        <p id="progress-text" style="text-align:center;margin-top:0.5rem;color:var(--muted);font-size:0.95rem">Inizio analisi...</p>
      </div></form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Analizza", content=content)

@app.route("/do_analyze", methods=["POST"])
@login_required
@subscription_required
def do_analyze():
    f = request.files.get("report")
    if not f or not f.filename:
        flash("Nessun file", "error")
        return redirect(url_for("analyze_page"))
    lim = PLAN_LIMITS.get(current_user.subscription_tier)
    if lim is not None and _used_this_month(current_user.id) >= lim:
        flash(f"Limite raggiunto ({lim}/mese).", "error")
        return redirect(url_for("pricing"))
    path = os.path.join(app.config["UPLOAD_FOLDER"], f.filename)
    f.save(path)
    try:
        res = engine.analyze_document(path)
        html_path = engine.export_html(res)
        html = open(html_path, encoding="utf-8").read()
        sel = {"score": res.get("scores", {}).get("total")}
        for m in res.get("quant", []):
            if m.code in ("Q08", "Q09", "Q16", "Q18", "Q32", "Q34", "B1", "B2", "B4", "B5"):
                sel[m.code] = m.value
        _D = res.get("D", {})
        sel.update({"oe": _D.get("oe") or _D.get("fcf"), "fcf": _D.get("fcf"),
                    "shares": _D.get("shares"), "price": _D.get("price"),
                    "revenue": _D.get("revenue"), "ebit": _D.get("ebit"),
                    "interest": _D.get("interest") or _D.get("interest_expense"),
                    "total_debt": _D.get("total_debt"), "cassa": _D.get("cassa"),
                    "equity": _D.get("equity"), "payout": _D.get("payout"),
                    "capex": _D.get("capex"), "net_income": _D.get("net_income")})
        rep = Report(user_id=current_user.id, filename=f.filename, company=res.get("company", ""),
                     score=sel["score"], html=html, metrics_json=_json.dumps(sel))
        db.session.add(rep); db.session.commit()
        return redirect(f"/reports/{rep.id}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"Errore: {str(e)}", "error")
        return redirect(url_for("analyze_page"))

@app.route("/reports")
@login_required
def reports():
    sec = request.args.get("sector", "")
    allr = Report.query.filter_by(user_id=current_user.id).all()
    sectors = sorted({r.sector for r in allr if r.sector})
    rs = [r for r in allr if (not sec or r.sector == sec)]
    rs.sort(key=lambda r: (r.score is None, -(r.score or 0)))
    sec_links = "".join(f"<a href='/reports?sector={x}' class='pill pill-blue'>{x}</a>" for x in sectors)
    rows = ""
    for r in rs:
        rows += f"""<div class='card'><h2>{r.company or r.filename}</h2>
        <p>Score: <strong style='color:var(--gold)'>{r.score if r.score is not None else 'N/D'}</strong> · Settore: {r.sector or 'non impostato'} · {r.created_at.strftime('%d/%m/%Y')}</p>
        <p><a href='/reports/{r.id}' style='color:var(--teal)'>Apri report</a></p>
        <form method='post' action='/reports/{r.id}/edit'>
          <input name='sector' placeholder='Settore' value='{r.sector or ''}'>
          <textarea name='notes' rows='2' placeholder='Note personali'>{r.notes or ''}</textarea>
          <button class='btn2' style='width:auto' type='submit'>Salva</button></form></div>"""
    content = "<h1>I tuoi report (dal migliore al peggiore)</h1><p>Filtra: " + (sec_links or "nessuno") + "</p>" + (rows or "<p>Nessun report.</p>")
    return render_template_string(BASE_TEMPLATE, title="Report", content=content)

@app.route("/reports/<int:rid>")
@login_required
def report_view(rid):
    r = Report.query.get_or_404(rid)
    if r.user_id != current_user.id and current_user.subscription_tier not in ("demo", "admin"):
        return ("non autorizzato", 403)
    
    # Calcolo navigazione
    all_reports = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    idx = next((i for i, rep in enumerate(all_reports) if rep.id == rid), -1)
    prev_rep = all_reports[idx - 1] if idx > 0 else None
    next_rep = all_reports[idx + 1] if idx >= 0 and idx < len(all_reports) - 1 else None
    
    # Toggle favorite
    if request.method == "POST":
        r.is_favorite = not r.is_favorite
        db.session.commit()
        return redirect(f"/reports/{rid}")
    
    # HTML del report con navigazione
    nav_html = f"""
    <div style="background:var(--card);border-bottom:1px solid var(--line);padding:1rem;margin:-2rem -2rem 2rem -2rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem">
      <div style="display:flex;gap:0.5rem;align-items:center">
        <a href="/reports" style="background:var(--teal);color:#0b1220;padding:0.5rem 1rem;border-radius:8px;text-decoration:none;font-weight:600">← Tutti i report</a>
        {f'<a href="/reports/{prev_rep.id}" style="background:#233250;color:var(--text);padding:0.5rem 1rem;border-radius:8px;text-decoration:none;font-weight:600" title="{prev_rep.company or prev_rep.filename}">← Prec</a>' if prev_rep else '<span style="opacity:0.3;padding:0.5rem 1rem">← Prec</span>'}
        {f'<a href="/reports/{next_rep.id}" style="background:#233250;color:var(--text);padding:0.5rem 1rem;border-radius:8px;text-decoration:none;font-weight:600" title="{next_rep.company or next_rep.filename}">Succ →</a>' if next_rep else '<span style="opacity:0.3;padding:0.5rem 1rem">Succ →</span>'}
      </div>
      <form method="post" style="margin:0">
        <button type="submit" style="width:auto;padding:0.5rem 1rem;background:{'var(--gold)' if r.is_favorite else '#233250'};color:{'#0b1220' if r.is_favorite else 'var(--text)'};border-radius:8px;font-weight:600">
          {'★ Rimuovi dai preferiti' if r.is_favorite else '☆ Aggiungi ai preferiti'}
        </button>
      </form>
    </div>
    """
    
    html_content = r.html.replace('<div class="card">', nav_html + '<div class="card">', 1)
    return (html_content, 200, {"Content-Type": "text/html; charset=utf-8"})

@app.route("/reports/<int:rid>/edit", methods=["POST"])
@login_required
def report_edit(rid):
    r = Report.query.get_or_404(rid)
    if r.user_id != current_user.id:
        return ("non autorizzato", 403)
    r.sector = (request.form.get("sector") or "").strip() or None
    r.notes = request.form.get("notes") or ""
    db.session.commit()
    flash("Report aggiornato.", "success")
    return redirect("/reports")

@app.route("/ranking")
@login_required
def ranking():
    rs = Report.query.filter_by(user_id=current_user.id).all()
    rs.sort(key=lambda r: (r.score is None, -(r.score or 0)))
    rows = ""
    for i, r in enumerate(rs, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        rows += f"<tr><td>{medal}</td><td>{r.company or r.filename}</td><td style='color:var(--gold)'>{r.score if r.score is not None else 'N/D'}</td><td>{r.sector or '-'}</td><td><a href='/reports/{r.id}' style='color:var(--teal)'>Apri</a></td></tr>"
    content = f"<h1>Classifica (migliore → peggiore)</h1><table><tr><th>#</th><th>Azienda</th><th>Score</th><th>Settore</th><th></th></tr>{rows}</table>" if rs else "<h1>Classifica</h1><p>Nessun report.</p>"
    return render_template_string(BASE_TEMPLATE, title="Classifica", content=content)

def _sim_dcf(oe, g, r, years=10, tg=0.02):
    if r <= tg:
        r = tg + 0.01
    iv = 0.0; cf = oe
    for t in range(1, years + 1):
        cf *= (1 + g)
        iv += cf / (1 + r) ** t
    iv += cf * (1 + tg) / (r - tg) / (1 + r) ** years
    return iv


def _fmtv(x):
    """Formatta valore numerico"""
    try:
        return f"{float(x):.1f}" if x is not None else "N/D"
    except Exception:
        return "N/D"

def _get_metric(report_obj, key):
    """Estrae metrica dal metrics_json del report"""
    if key == "score":
        return report_obj.score
    try:
        data = _json.loads(report_obj.metrics_json or "{}")
        return data.get(key)
    except Exception:
        return None


# ===== FINANCIAL INTELLIGENCE ENGINE =====

# LIVELLO 1: Scenari Macro con shock specifici
MACRO_SCENARIOS = {
    "Soft landing": {
        "prob": 0.35,
        "gdp": -0.5, "infl": -0.8, "rates": -0.5, "unemp": 0.2,
        "consumption": -0.3, "energy": 0.0, "spread": 0.0,
        "desc": "PIL stabile, inflazione in calo, tassi in riduzione graduale"
    },
    "Boom economico": {
        "prob": 0.08,
        "gdp": 2.5, "infl": 0.5, "rates": 0.5, "unemp": -0.5,
        "consumption": 2.0, "energy": 0.3, "spread": -0.3,
        "desc": "Crescita forte, consumi in aumento, ottimismo"
    },
    "Recessione moderata": {
        "prob": 0.28,
        "gdp": -2.0, "infl": -1.0, "rates": -1.0, "unemp": 1.5,
        "consumption": -2.0, "energy": -0.5, "spread": 1.5,
        "desc": "PIL in calo, disoccupazione in aumento, consumi deboli"
    },
    "Recessione severa": {
        "prob": 0.12,
        "gdp": -5.0, "infl": -1.5, "rates": -2.0, "unemp": 3.0,
        "consumption": -5.0, "energy": -1.0, "spread": 3.5,
        "desc": "Crisi profonda, crollo consumi, liquidità scarsa"
    },
    "Stagflazione": {
        "prob": 0.10,
        "gdp": -2.0, "infl": 3.0, "rates": 2.0, "unemp": 1.5,
        "consumption": -3.0, "energy": 2.0, "spread": 2.0,
        "desc": "Inflazione alta con PIL in calo, tassi in aumento"
    },
    "Crisi finanziaria": {
        "prob": 0.07,
        "gdp": -4.0, "infl": -0.5, "rates": 1.5, "unemp": 2.5,
        "consumption": -4.0, "energy": 0.0, "spread": 5.0,
        "desc": "Spread in esplosione, costo debito altissimo, mercato azionario in crollo"
    },
}

# LIVELLO 2: Matrice sensibilità settoriale
SECTOR_SENS = {
    "Banca": {"rev_gdp": 0.8, "pricing_power": 0.2, "rate_sens": 1.0, "energy_sens": 0.3, "margin_adj": -0.02},
    "Tech": {"rev_gdp": 1.2, "pricing_power": 0.6, "rate_sens": -0.8, "energy_sens": 0.4, "margin_adj": -0.03},
    "Retail": {"rev_gdp": 1.8, "pricing_power": 0.3, "rate_sens": -0.5, "energy_sens": 0.5, "margin_adj": -0.04},
    "Consumer": {"rev_gdp": 0.6, "pricing_power": 0.8, "rate_sens": -0.2, "energy_sens": 0.6, "margin_adj": -0.01},
    "Pharma": {"rev_gdp": 0.5, "pricing_power": 0.9, "rate_sens": -0.3, "energy_sens": 0.3, "margin_adj": -0.01},
    "Utilities": {"rev_gdp": 0.3, "pricing_power": 0.7, "rate_sens": -0.7, "energy_sens": 0.9, "margin_adj": -0.02},
    "Energy": {"rev_gdp": 0.4, "pricing_power": 0.8, "rate_sens": -0.2, "energy_sens": -1.5, "margin_adj": 0.01},
    "Auto": {"rev_gdp": 2.0, "pricing_power": 0.2, "rate_sens": -0.9, "energy_sens": 0.7, "margin_adj": -0.05},
    "Industria": {"rev_gdp": 1.5, "pricing_power": 0.4, "rate_sens": -0.5, "energy_sens": 0.8, "margin_adj": -0.03},
    "Immobiliare": {"rev_gdp": 1.3, "pricing_power": 0.3, "rate_sens": -1.0, "energy_sens": 0.6, "margin_adj": -0.04},
    "Altro": {"rev_gdp": 1.0, "pricing_power": 0.4, "rate_sens": -0.4, "energy_sens": 0.5, "margin_adj": -0.02},
}

def _get_sector_sens(sector):
    s = (sector or "").strip()
    for k, v in SECTOR_SENS.items():
        if k.lower() in s.lower():
            return v
    return SECTOR_SENS["Altro"]

# LIVELLO 3+4: Stress test con catena causale
def _stress_company(m, scenario):
    sector = (m.get("sector") or "Altro")
    sens = _get_sector_sens(sector)
    sc = MACRO_SCENARIOS[scenario]
    
    # Dati aziendali (con fallback a stime)
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    fcf = float(m.get("fcf") or m.get("oe") or 0)
    debt = float(m.get("total_debt") or 0)
    interest = float(m.get("interest") or 0) or 0.01
    cassa = float(m.get("cassa") or 0)
    equity = float(m.get("equity") or 1)
    
    # Stime se mancano dati
    if not rev and ebit:
        rev = ebit / 0.15
    if not ebit and rev:
        ebit = rev * 0.15
    if not fcf and ebit:
        fcf = ebit * 0.7
    
    margin = ebit / rev if rev else 0.15
    
    # CATENA CAUSALE: Macro → Settore → Azienda
    
    # 1. Shock PIL → consumi → volumi → ricavi
    vol_shock = sc["gdp"] * sens["rev_gdp"] / 100
    
    # 2. Pricing power compensa inflazione
    price_shock = sc["infl"] * sens["pricing_power"] / 100
    
    # 3. Ricavi finali
    rev_shock = vol_shock + price_shock
    new_rev = rev * (1 + rev_shock)
    
    # 4. Margini: peggiorano in crisi, migliorano in boom
    margin_shock = sens["margin_adj"] * (1 + abs(sc["gdp"]) / 5)
    new_margin = max(margin + margin_shock, 0.02)
    new_ebit = new_rev * new_margin
    
    # 5. Interessi: aumentano con spread e tassi
    int_mult = 1 + (sc["rates"] + sc["spread"] * 0.3) / 100
    new_interest = interest * max(int_mult, 0.3)
    
    # 6. FCF: segue EBIT con leverage operativo
    ebit_ratio = new_ebit / ebit if ebit else 1
    new_fcf = fcf * max(ebit_ratio, 0.2)
    
    # 7. Indicatori finanziari
    debt_ebitda = debt / new_ebit if new_ebit > 0 else 99
    int_coverage = new_ebit / new_interest if new_interest > 0 else 99
    cash_runway = cassa / abs(new_fcf) if new_fcf < 0 else 999
    
    # 8. Probabilità di distress (4 fattori)
    distress = 0
    if debt_ebitda > 4: distress += 0.25
    if int_coverage < 2: distress += 0.30
    if new_fcf < 0 and cassa < abs(new_fcf): distress += 0.35
    if cash_runway < 1: distress += 0.10
    
    # 9. Resilience Score (0-100)
    resilience = 100 - distress * 100
    if new_fcf > 0 and debt_ebitda < 3: resilience = min(100, resilience + 10)
    if cassa > debt * 0.3: resilience = min(100, resilience + 8)
    if margin > 0.15: resilience = min(100, resilience + 5)
    
    return {
        "rev_chg": rev_shock * 100,
        "ebitda_chg": (new_ebit - ebit) / ebit * 100 if ebit else 0,
        "fcf_chg": (new_fcf - fcf) / fcf * 100 if fcf else 0,
        "debt_ebitda": debt_ebitda,
        "int_cov": int_coverage,
        "dividendo_ok": new_fcf > 0,
        "liquidity": "Adeguata" if cash_runway > 2 else ("Tesa" if cash_runway > 1 else "Critica"),
        "distress_prob": distress,
        "resilience": max(0, min(100, resilience)),
    }


    # Benchmark settoriali per confronto
    sector_benchmarks = {
        "Tech": {"avg_score": 72, "avg_margin": 0.25, "avg_debt_ebitda": 1.5},
        "Finance": {"avg_score": 68, "avg_margin": 0.30, "avg_debt_ebitda": 8.0},
        "Energy": {"avg_score": 65, "avg_margin": 0.15, "avg_debt_ebitda": 2.5},
        "Healthcare": {"avg_score": 70, "avg_margin": 0.20, "avg_debt_ebitda": 2.0},
        "Consumer": {"avg_score": 67, "avg_margin": 0.12, "avg_debt_ebitda": 2.2},
        "Industrial": {"avg_score": 64, "avg_margin": 0.10, "avg_debt_ebitda": 2.8},
        "Altro": {"avg_score": 66, "avg_margin": 0.15, "avg_debt_ebitda": 2.5}
    }
@app.route("/simula", methods=["GET", "POST"])
@login_required
def simula():
    """Stress Test con modifica manuale dei dati per simulare scenari"""
    
    rep = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).first()
    
    if not rep:
        return render_template_string(BASE_TEMPLATE, title="Simula", 
            content="<div class='card'><h2>🛡️ Stress Test Avanzato</h2>"
            "<p>Carica prima un bilancio in /analyze.</p>"
            "<a href='/analyze' class='btn2'>Analizza Bilancio</a></div>")
    
    m = _json.loads(rep.metrics_json or "{}")
    
    # Dati originali dal PDF
    orig_revenue = float(m.get("revenue") or 0)
    orig_ebit = float(m.get("ebit") or 0)
    orig_debt = float(m.get("total_debt") or 0)
    orig_cash = float(m.get("cassa") or 0)
    orig_interest = float(m.get("interest") or 0)
    orig_ebitda = float(m.get("ebitda") or orig_ebit * 1.2)
    
    # Se l'utente ha modificato i dati via POST, usiamo quelli
    if request.method == "POST":
        revenue = float(request.form.get("revenue") or orig_revenue)
        ebit = float(request.form.get("ebit") or orig_ebit)
        total_debt = float(request.form.get("total_debt") or orig_debt)
        cash = float(request.form.get("cassa") or orig_cash)
        interest = float(request.form.get("interest") or orig_interest)
        scenario_name = request.form.get("scenario_name", "Scenario personalizzato")
    else:
        revenue = orig_revenue
        ebit = orig_ebit
        total_debt = orig_debt
        cash = orig_cash
        interest = orig_interest
        scenario_name = "Scenario Base (dati originali)"
    
    # Benchmark di settore
    sector_benchmarks = {
        "Tech": 45, "Software": 50, "Services": 35,
        "Manufacturing": 25, "Industrial": 25, "Automotive": 20,
        "Retail": 15, "Consumer": 20, "Food": 30,
        "Finance": 30, "Banking": 35, "Insurance": 40,
        "Healthcare": 35, "Pharma": 40, "Energy": 20,
        "Utilities": 30, "Telecom": 25, "Real Estate": 20,
        "Altro": 30
    }
    sector = rep.sector or "Altro"
    benchmark = sector_benchmarks.get(sector, 30)
    
    # Calcolo Breaking Point
    if interest > 0 and ebit > 0:
        interest_coverage = ebit / interest
        min_ebit_to_survive = interest
        if ebit > min_ebit_to_survive:
            breaking_point = ((ebit - min_ebit_to_survive) / ebit) * 100
        else:
            breaking_point = 0
    elif interest == 0:
        interest_coverage = 999
        breaking_point = 100
    else:
        interest_coverage = 0
        breaking_point = 0
    
    # Cash Runway
    monthly_burn = max((revenue - orig_ebitda) / 12, revenue / 24)
    cash_runway = cash / monthly_burn if monthly_burn > 0 else 999
    
    # Status e colore
    if breaking_point >= 40:
        status = "FORTEZZA FINANZIARIA"
        status_color = "#10b981"
    elif breaking_point >= 20:
        status = "RESILIENTE"
        status_color = "#fbbf24"
    elif breaking_point >= 5:
        status = "FRAGILE"
        status_color = "#f97316"
    else:
        status = "A RISCHIO DEFAULT"
        status_color = "#ef4444"
    
    # Confronto con benchmark
    bp_diff = breaking_point - benchmark
    if bp_diff > 5:
        bench_text = "SUPERIORE alla media di +" + str(int(bp_diff)) + "%"
        bench_color = "#10b981"
    elif bp_diff < -5:
        bench_text = "INFERIORE alla media di " + str(int(abs(bp_diff))) + "%"
        bench_color = "#ef4444"
    else:
        bench_text = "IN LINEA con la media"
        bench_color = "#fbbf24"
    
    # Cash Runway display
    runway_display = min(int(cash_runway), 99) if cash_runway < 999 else "99+"
    if cash_runway >= 12:
        runway_color = "#10b981"
        runway_text = "Ottima autonomia finanziaria"
    elif cash_runway >= 6:
        runway_color = "#fbbf24"
        runway_text = "Autonomia sufficiente, ma da monitorare"
    else:
        runway_color = "#ef4444"
        runway_text = "Autonomia critica - Serve aumentare la liquidità"
    
    # HTML
    html = "<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:3rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center'>"
    html += "<h1 style='color:#fbbf24;margin:0;font-size:2.5rem'>🛡️ Stress Test Avanzato</h1>"
    html += "<p style='color:#e2e8f0;font-size:1.2rem;margin:1rem 0 0 0'>Modifica i dati per simulare scenari</p>"
    html += "</div>"
    
    # FORM con dati modificabili
    html += '<form method="post" class="card" style="margin-bottom:2rem;padding:2rem">'
    html += '<h2 style="color:var(--gold);margin-top:0">📝 Modifica i Dati per Simulare</h2>'
    html += '<p style="color:var(--muted);margin-bottom:1.5rem">I valori precompilati sono quelli estratti dal PDF. Modificali per vedere come cambierebbe la resilienza.</p>'
    
    html += '<input type="hidden" name="scenario_name" value="Scenario modificato">'
    
    # Griglia input
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;margin:1.5rem 0">'
    
    # Ricavi
    html += '<div style="background:var(--bg);padding:1rem;border-radius:8px">'
    html += '<label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Ricavi (M€)</label>'
    html += '<input type="number" name="revenue" value="' + str(revenue) + '" step="0.1" style="width:100%;padding:0.8rem;border-radius:6px;border:2px solid var(--line);background:var(--surface);color:var(--text);font-size:1.1rem;font-weight:600">'
    html += '<p style="font-size:0.8rem;color:var(--muted);margin:0.3rem 0 0 0">Originale: ' + str(orig_revenue) + ' M€</p>'
    html += '</div>'
    
    # EBIT
    html += '<div style="background:var(--bg);padding:1rem;border-radius:8px">'
    html += '<label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">EBIT (M€)</label>'
    html += '<input type="number" name="ebit" value="' + str(ebit) + '" step="0.1" style="width:100%;padding:0.8rem;border-radius:6px;border:2px solid var(--line);background:var(--surface);color:var(--text);font-size:1.1rem;font-weight:600">'
    html += '<p style="font-size:0.8rem;color:var(--muted);margin:0.3rem 0 0 0">Originale: ' + str(orig_ebit) + ' M€</p>'
    html += '</div>'
    
    # Debito
    html += '<div style="background:var(--bg);padding:1rem;border-radius:8px">'
    html += '<label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Debito Totale (M€)</label>'
    html += '<input type="number" name="total_debt" value="' + str(total_debt) + '" step="0.1" style="width:100%;padding:0.8rem;border-radius:6px;border:2px solid var(--line);background:var(--surface);color:var(--text);font-size:1.1rem;font-weight:600">'
    html += '<p style="font-size:0.8rem;color:var(--muted);margin:0.3rem 0 0 0">Originale: ' + str(orig_debt) + ' M€</p>'
    html += '</div>'
    
    # Cassa
    html += '<div style="background:var(--bg);padding:1rem;border-radius:8px">'
    html += '<label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Cassa (M€)</label>'
    html += '<input type="number" name="cassa" value="' + str(cash) + '" step="0.1" style="width:100%;padding:0.8rem;border-radius:6px;border:2px solid var(--line);background:var(--surface);color:var(--text);font-size:1.1rem;font-weight:600">'
    html += '<p style="font-size:0.8rem;color:var(--muted);margin:0.3rem 0 0 0">Originale: ' + str(orig_cash) + ' M€</p>'
    html += '</div>'
    
    # Interessi
    html += '<div style="background:var(--bg);padding:1rem;border-radius:8px">'
    html += '<label style="display:block;margin-bottom:0.5rem;color:var(--muted);font-size:0.9rem">Interessi Passivi (M€)</label>'
    html += '<input type="number" name="interest" value="' + str(interest) + '" step="0.1" style="width:100%;padding:0.8rem;border-radius:6px;border:2px solid var(--line);background:var(--surface);color:var(--text);font-size:1.1rem;font-weight:600">'
    html += '<p style="font-size:0.8rem;color:var(--muted);margin:0.3rem 0 0 0">Originale: ' + str(orig_interest) + ' M€</p>'
    html += '</div>'
    
    html += '</div>'  # Fine griglia
    
    # Pulsante ricalcola
    html += '<button type="submit" class="btn2" style="width:100%;padding:1rem;font-size:1.1rem;background:var(--teal)">🔄 Ricalcola Stress Test con questi valori</button>'
    html += '</form>'
    
    # RISULTATI
    html += '<div class="card" style="border:3px solid ' + status_color + ';padding:2rem;margin-bottom:2rem;background:linear-gradient(135deg, rgba(' + str(int(status_color[1:3], 16)) + ',' + str(int(status_color[3:5], 16)) + ',' + str(int(status_color[5:7], 16)) + ',0.1), transparent)">'
    
    html += '<div style="text-align:center;margin-bottom:2rem">'
    html += '<h2 style="color:' + status_color + ';margin:0 0 1rem 0;font-size:2rem">' + status + '</h2>'
    
    if breaking_point > 0 and breaking_point < 100:
        html += '<div style="font-size:5rem;font-weight:800;color:' + status_color + ';margin:1rem 0">-' + str(int(breaking_point)) + '%</div>'
        html += '<p style="font-size:1.2rem;color:var(--muted);margin:0">Crollo ricavi sopportabile</p>'
    else:
        html += '<div style="font-size:2.5rem;font-weight:700;color:' + status_color + ';margin:1rem 0">Nessun limite critico</div>'
    
    html += '</div>'
    
    # Barra visiva
    if breaking_point > 0 and breaking_point <= 100:
        html += '<div style="margin:2rem 0">'
        html += '<div style="background:var(--bg);border-radius:12px;overflow:hidden;height:40px">'
        bar_width = min(breaking_point, 100)
        html += '<div style="width:' + str(bar_width) + '%;height:100%;background:' + status_color + ';display:flex;align-items:center;justify-content:center;color:white;font-weight:700;font-size:1.1rem">' + str(int(breaking_point)) + '%</div>'
        html += '</div>'
        html += '<div style="display:flex;justify-content:space-between;margin-top:0.5rem;font-size:0.85rem;color:var(--muted)">'
        html += '<span>Crollo 0%</span><span>Crollo 50%</span><span>Crollo 100%</span>'
        html += '</div></div>'
    
    # Spiegazione
    if interest > 0 and ebit > 0:
        explanation = "Con EBIT di " + str(ebit) + "M e interessi di " + str(interest) + "M, l'azienda può resistere a un crollo dei ricavi del " + str(int(breaking_point)) + "% prima di non riuscire più a pagare gli interessi."
    elif interest == 0:
        explanation = "L'azienda non ha debiti finanziari. È immune al rischio di default da tassi di interesse."
    else:
        explanation = "Dati insufficienti per calcolare il punto di rottura."
    
    html += '<div style="background:var(--bg);padding:1.5rem;border-radius:8px;margin:1.5rem 0">'
    html += '<p style="font-size:1.1rem;line-height:1.8;margin:0">' + explanation + '</p>'
    html += '</div>'
    
    # Benchmark
    html += '<div style="background:var(--bg);padding:1.5rem;border-radius:8px;margin:1.5rem 0">'
    html += '<h3 style="color:var(--gold);margin:0 0 0.5rem 0">📊 Benchmark di Settore (' + sector + ')</h3>'
    html += '<p style="margin:0 0 0.5rem 0">Media del settore: <strong style="color:var(--teal)">' + str(benchmark) + '%</strong></p>'
    html += '<p style="color:' + bench_color + ';margin:0;font-weight:600">' + bench_text + '</p>'
    html += '</div>'
    
    # Cash Runway
    html += '<div style="background:var(--bg);padding:1.5rem;border-radius:8px;margin:1.5rem 0">'
    html += '<h3 style="color:var(--gold);margin:0 0 0.5rem 0">⏱️ Cash Runway (Autonomia)</h3>'
    html += '<div style="font-size:3rem;font-weight:800;color:' + runway_color + ';margin:1rem 0">' + str(runway_display) + ' <span style="font-size:1.5rem">mesi</span></div>'
    html += '<p style="color:' + runway_color + ';margin:0">' + runway_text + '</p>'
    html += '</div>'
    
    # Interest Coverage
    if interest > 0:
        cov_color = "#10b981" if interest_coverage >= 3 else ("#fbbf24" if interest_coverage >= 1.5 else "#ef4444")
        html += '<div style="text-align:center;padding:1rem;background:rgba(0,0,0,0.2);border-radius:8px;margin:1rem 0">'
        html += '<h3 style="color:var(--muted);margin:0 0 0.5rem 0;font-size:0.95rem">Interest Coverage Ratio</h3>'
        html += '<p style="font-size:2.5rem;font-weight:800;color:' + cov_color + ';margin:0">' + str(round(interest_coverage, 1)) + 'x</p>'
        html += '<p style="color:var(--muted);margin:0.5rem 0 0 0;font-size:0.9rem">EBIT / Interessi Passivi</p>'
        html += '</div>'
    
    html += '</div>'  # Fine card risultati
    
    # Pulsanti azione
    html += '<div style="display:flex;gap:1rem;justify-content:center;flex-wrap:wrap">'
    html += '<button onclick="window.print()" class="btn2" style="background:var(--blue)">📥 Scarica Report PDF</button>'
    html += '<a href="/cronologia" class="btn2" style="background:var(--gold);color:#0b1220">📚 Vedi Cronologia</a>'
    html += '</div>'
    
    html += '<p style="text-align:center;color:var(--muted);margin-top:2rem">Analisi basata su: <strong>' + str(rep.company or rep.filename) + '</strong></p>'
    
    return render_template_string(BASE_TEMPLATE, title="Stress Test Avanzato", content=html)

def simula():
    """Stress Test di Sopravvivenza - Calcola il punto di rottura aziendale"""
    
    rep = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).first()
    
    if not rep:
        return render_template_string(BASE_TEMPLATE, title="Simula", 
            content="<div class='card'><h2>📊 Stress Test di Sopravvivenza</h2>"
            "<p>Carica prima un bilancio in /analyze per vedere quanto è resiliente l'azienda.</p>"
            "<a href='/analyze' class='btn2'>Analizza Bilancio</a></div>")
    
    m = _json.loads(rep.metrics_json or "{}")
    
    revenue = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    total_debt = float(m.get("total_debt") or 0)
    cash = float(m.get("cassa") or 0)
    interest = float(m.get("interest") or 0)
    
    breaking_point_ebit = 0
    status = ""
    status_color = ""
    explanation = ""
    advice = ""
    
    if interest > 0 and ebit > 0:
        interest_coverage = ebit / interest
        min_ebit_to_survive = interest
        
        if ebit > min_ebit_to_survive:
            max_ebit_drop = ebit - min_ebit_to_survive
            breaking_point_ebit = (max_ebit_drop / ebit) * 100
        else:
            breaking_point_ebit = 0
        
        if breaking_point_ebit >= 40:
            status = "FORTEZZA FINANZIARIA"
            status_color = "#10b981"
            explanation = f"L'azienda può resistere a un crollo dei ricavi del {breaking_point_ebit:.0f}% prima di non riuscire più a pagare gli interessi con l'EBIT operativo."
            advice = f"Con un Interest Coverage di {interest_coverage:.1f}x e cassa netta di €{cash - total_debt:.0f}M, è un'azienda difensiva eccellente per periodi di crisi."
        elif breaking_point_ebit >= 20:
            status = "RESILIENTE"
            status_color = "#fbbf24"
            explanation = f"L'azienda può sopportare una recessione moderata (-{breaking_point_ebit:.0f}% ricavi) prima di entrare in zona di pericolo."
            advice = f"Interest Coverage di {interest_coverage:.1f}x. Monitorare il debito e la generazione di cassa nei prossimi trimestri."
        elif breaking_point_ebit >= 5:
            status = "FRAGILE"
            status_color = "#f97316"
            explanation = f"Basta un piccolo calo dei ricavi (-{breaking_point_ebit:.0f}%) per mettere a rischio la copertura degli interessi."
            advice = f"Interest Coverage basso ({interest_coverage:.1f}x). L'azienda è vulnerabile a shock economici anche moderati."
        else:
            status = "A RISCHIO DEFAULT"
            status_color = "#ef4444"
            explanation = f"L'EBIT attuale ({ebit:.1f}M) copre a malapena gli interessi ({interest:.1f}M). Un ulteriore calo dei ricavi porterebbe al default tecnico."
            advice = "Situazione critica. L'azienda deve ridurre il debito o aumentare urgentemente la redditività operativa."
    
    elif interest == 0:
        status = "DEBITO ZERO"
        status_color = "#10b981"
        breaking_point_ebit = 100
        explanation = "L'azienda non ha debiti finanziari e quindi non paga interessi. È immune al rischio di default da tassi di interesse."
        advice = f"Con €{cash:.0f}M di cassa e zero debiti, l'azienda è una fortezza finanziaria pronta a cogliere opportunità di crescita."
    
    else:
        status = "DATI INSUFFICIENTI"
        status_color = "#6b7280"
        breaking_point_ebit = 0
        explanation = "Impossibile calcolare il punto di rottura con i dati disponibili nel bilancio."
        advice = "Verificare che il PDF contenga Stato Patrimoniale e Conto Economico completi."
    
    html = "<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:3rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center'>"
    html += "<h1 style='color:#fbbf24;margin:0;font-size:2.5rem'>️ Stress Test di Sopravvivenza</h1>"
    html += "<p style='color:#e2e8f0;font-size:1.2rem;margin:1rem 0 0 0'>Quanto può crollare l'azienda prima di andare in crisi?</p>"
    html += "</div>"
    
    html += f"<div class='card' style='border:3px solid {status_color};padding:2.5rem;margin-bottom:2rem;background:linear-gradient(135deg, rgba({int(status_color[1:3], 16)}, {int(status_color[3:5], 16)}, {int(status_color[5:7], 16)}, 0.1), transparent)'>"
    
    html += "<div style='text-align:center;margin-bottom:2rem'>"
    html += f"<h2 style='color:{status_color};margin:0 0 1rem 0;font-size:2rem'>{status}</h2>"
    
    if breaking_point_ebit > 0 and breaking_point_ebit < 100:
        html += f"<div style='font-size:4rem;font-weight:800;color:{status_color};margin:1rem 0'>-{breaking_point_ebit:.0f}%</div>"
        html += "<p style='font-size:1.2rem;color:var(--muted);margin:0'>Crollo ricavi sopportabile</p>"
    else:
        html += f"<div style='font-size:2.5rem;font-weight:700;color:{status_color};margin:1rem 0'>Nessun limite critico</div>"
    
    html += "</div>"
    
    if breaking_point_ebit > 0 and breaking_point_ebit <= 100:
        html += "<div style='margin:2rem 0'>"
        html += "<div style='background:var(--bg);border-radius:12px;overflow:hidden;height:40px;position:relative'>"
        bar_color = status_color
        bar_width = min(breaking_point_ebit, 100)
        html += f"<div style='width:{bar_width}%;height:100%;background:{bar_color};transition:width 1s ease;display:flex;align-items:center;justify-content:center;color:white;font-weight:700;font-size:1.1rem'>{breaking_point_ebit:.0f}%</div>"
        html += "</div>"
        html += "<div style='display:flex;justify-content:space-between;margin-top:0.5rem;font-size:0.85rem;color:var(--muted)'>"
        html += "<span>Crollo 0%</span>"
        html += "<span>Crollo 50%</span>"
        html += "<span>Crollo 100%</span>"
        html += "</div>"
        html += "</div>"
    
    html += f"<div style='background:var(--bg);padding:1.5rem;border-radius:8px;margin:1.5rem 0'>"
    html += f"<p style='font-size:1.1rem;line-height:1.8;margin:0;color:var(--text)'>{explanation}</p>"
    html += "</div>"
    
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(150px, 1fr));gap:1rem;margin:1.5rem 0'>"
    html += f"<div style='background:var(--bg);padding:1rem;border-radius:8px;text-align:center'><h3 style='color:var(--muted);margin:0 0 0.5rem 0;font-size:0.9rem'>Ricavi</h3><p style='font-size:1.5rem;font-weight:700;margin:0'>€{revenue:.0f}M</p></div>"
    html += f"<div style='background:var(--bg);padding:1rem;border-radius:8px;text-align:center'><h3 style='color:var(--muted);margin:0 0 0.5rem 0;font-size:0.9rem'>EBIT</h3><p style='font-size:1.5rem;font-weight:700;margin:0'>€{ebit:.0f}M</p></div>"
    html += f"<div style='background:var(--bg);padding:1rem;border-radius:8px;text-align:center'><h3 style='color:var(--muted);margin:0 0 0.5rem 0;font-size:0.9rem'>Interessi</h3><p style='font-size:1.5rem;font-weight:700;margin:0'>€{interest:.0f}M</p></div>"
    html += f"<div style='background:var(--bg);padding:1rem;border-radius:8px;text-align:center'><h3 style='color:var(--muted);margin:0 0 0.5rem 0;font-size:0.9rem'>Debito Netto</h3><p style='font-size:1.5rem;font-weight:700;margin:0'>€{total_debt - cash:.0f}M</p></div>"
    html += "</div>"
    
    if interest > 0:
        coverage = ebit / interest if interest > 0 else 0
        coverage_color = "#10b981" if coverage >= 3 else ("#fbbf24" if coverage >= 1.5 else "#ef4444")
        html += f"<div style='text-align:center;padding:1rem;background:rgba(0,0,0,0.2);border-radius:8px;margin:1rem 0'>"
        html += f"<h3 style='color:var(--muted);margin:0 0 0.5rem 0;font-size:0.95rem'>Interest Coverage Ratio</h3>"
        html += f"<p style='font-size:2.5rem;font-weight:800;color:{coverage_color};margin:0'>{coverage:.1f}x</p>"
        html += f"<p style='color:var(--muted);margin:0.5rem 0 0 0;font-size:0.9rem'>EBIT / Interessi Passivi</p>"
        html += "</div>"
    
    html += f"<div style='background:linear-gradient(135deg, rgba({int(status_color[1:3], 16)}, {int(status_color[3:5], 16)}, {int(status_color[5:7], 16)}, 0.1), transparent);border:2px solid {status_color};padding:1.5rem;border-radius:8px;margin:1.5rem 0'>"
    html += f"<h3 style='color:{status_color};margin:0 0 0.5rem 0'>💡 Analisi Strategica</h3>"
    html += f"<p style='margin:0;line-height:1.8'>{advice}</p>"
    html += "</div>"
    
    html += "</div>"
    
    html += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap'>"
    html += "<a href='/analyze' class='btn2' style='background:var(--teal)'>📄 Analizza Altro Bilancio</a>"
    html += "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'>📚 Vedi Cronologia</a>"
    html += "</div>"
    
    html += f"<p style='text-align:center;color:var(--muted);margin-top:2rem'>Analisi basata su: <strong>{rep.company or rep.filename}</strong></p>"
    
    return render_template_string(BASE_TEMPLATE, title="Stress Test", content=html)

def simula():
    rs = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    
    if request.method == "POST":
        # Upload nuovo report o selezione esistente
        if "report_file" in request.files:
            f = request.files["report_file"]
            if f and f.filename:
                path = os.path.join(app.config["UPLOAD_FOLDER"], f.filename)
                f.save(path)
                try:
                    res = engine.analyze_document(path)
                    html_path = engine.export_html(res)
                    html = open(html_path, encoding="utf-8").read()
                    sel = {"score": res.get("scores", {}).get("total")}
                    for m in res.get("quant", []):
                        if m.code in ("Q08", "Q09", "Q16", "Q18", "Q32", "Q34", "B1", "B2", "B4", "B5"):
                            sel[m.code] = m.value
                    _D = res.get("D", {})
                    sel.update({"oe": _D.get("oe") or _D.get("fcf"), "fcf": _D.get("fcf"),
                                "shares": _D.get("shares"), "price": _D.get("price"),
                                "revenue": _D.get("revenue"), "ebit": _D.get("ebit"),
                                "interest": _D.get("interest"), "total_debt": _D.get("total_debt"),
                                "cassa": _D.get("cassa"), "equity": _D.get("equity")})
                    rep = Report(user_id=current_user.id, filename=f.filename,
                                 company=res.get("company", ""), score=sel["score"],
                                 html=html, metrics_json=_json.dumps(sel))
                    db.session.add(rep); db.session.commit()
                    rs.insert(0, rep)
                except Exception as e:
                    flash(f"Errore analisi: {str(e)}", "error")
        
        rid = request.form.get("rid")
        if rid:
            rep = next((r for r in rs if str(r.id) == str(rid)), rs[0] if rs else None)
        else:
            rep = rs[0] if rs else None
    else:
        rep = rs[0] if rs else None
    
    if not rep:
        return render_template_string(BASE_TEMPLATE, title="Simula",
            content="<div class='card'><h1>Financial Intelligence Engine</h1><p>Nessun report disponibile. Carica un bilancio per iniziare lo stress test.</p></div>")
    
    m = _json.loads(rep.metrics_json or "{}")
    m["sector"] = rep.sector or "Altro"
    
    # Calcola tutti gli scenari
    rows = ""
    exp_impact = 0; w_res = 0
    for name, sc in MACRO_SCENARIOS.items():
        r = _stress_company(m, name)
        color = "var(--teal)" if r["resilience"] >= 70 else ("var(--gold)" if r["resilience"] >= 45 else "#da3633")
        icon = "🟢" if r["resilience"] >= 70 else ("🟡" if r["resilience"] >= 45 else "🔴")
        div_txt = "✓" if r["dividendo_ok"] else "⚠"
        rows += f"<tr><td>{icon} {name}</td><td>{sc['prob']*100:.0f}%</td>"
        rows += f"<td>{r['rev_chg']:+.1f}%</td>"
        rows += f"<td>{r['ebitda_chg']:+.1f}%</td>"
        rows += f"<td>{r['fcf_chg']:+.1f}%</td>"
        rows += f"<td>{r['debt_ebitda']:.1f}x</td>"
        rows += f"<td>{r['int_cov']:.1f}x</td>"
        rows += f"<td>{div_txt}</td>"
        rows += f"<td>{r['liquidity']}</td>"
        rows += f"<td style='color:{color};font-weight:700'>{r['resilience']:.0f}</td></tr>"
        exp_impact += r["rev_chg"] * sc["prob"]
        w_res += r["resilience"] * sc["prob"]
    
    res_color = "var(--teal)" if w_res >= 70 else ("var(--gold)" if w_res >= 45 else "#da3633")
    
    opts = "".join(f"<option value='{r.id}' {'selected' if r.id == rep.id else ''}>{r.company or r.filename} ({r.sector or 'Altro'})</option>" for r in rs)
    
    content = f"""<div class='card'><h1>Financial Intelligence Engine</h1>
    <p style='color:var(--muted)'>Stress test multi-scenario con catena causale Macro → Settore → Azienda</p>
    <form method='post' enctype='multipart/form-data'>
      <select name='rid'>{opts}</select>
      <input type='file' name='report_file' accept='.pdf,.docx,.txt'>
      <button type='submit' class='btn2' style='width:auto;margin-left:8px'>Carica o seleziona</button>
    </form></div>
    
    <div class='card' style='text-align:center;border:2px solid {res_color}'>
      <h2 style='color:{res_color}'>Resilience Score: {w_res:.0f}/100</h2>
      <p>Expected Impact: <strong>{exp_impact:+.1f}%</strong> ricavi (media ponderata)</p>
      <p style='color:var(--muted);font-size:.9rem'>Probabilità di sopravvivere a 6 scenari macro mantenendo FCF positivo e debito sostenibile</p>
    </div>
    
    <div class='card'><h2>Matrice scenari</h2>
    <table><tr><th>Scenario</th><th>Prob.</th><th>Ricavi</th><th>EBITDA</th><th>FCF</th><th>Debt/EBITDA</th><th>Int.Cov.</th><th>Div.</th><th>Liquidità</th><th>Resilienza</th></tr>
    {rows}</table></div>
    
    <div class='card'><h2>Come funziona</h2>
    <p style='color:var(--muted);font-size:.9rem'>
    <strong>Livello 1 — Macro:</strong> shock su PIL, inflazione, tassi, disoccupazione, consumi, energia, spread.<br>
    <strong>Livello 2 — Settore:</strong> sensibilità specifica (banche beneficiano di tassi alti, tech soffre, consumer resilienti).<br>
    <strong>Livello 3 — Azienda:</strong> pricing power, margini, leverage, copertura interessi.<br>
    <strong>Livello 4 — Output:</strong> bilancio futuro + probabilità distress + resilienza.<br>
    <strong>Resilience Score:</strong> quanto è probabile che l'azienda sopravviva e continui a generare FCF durante una crisi.</p></div>"""
    return render_template_string(BASE_TEMPLATE, title="Simula", content=content)

@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "change_password":
            old_pw = request.form.get("old_password", "")
            new_pw = request.form.get("new_password", "")
            if not current_user.check_password(old_pw):
                flash("Password attuale non corretta", "error")
            elif len(new_pw) < 6:
                flash("Min 6 caratteri", "error")
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash("Password aggiornata", "success")
        elif action == "change_email":
            new_email = (request.form.get("new_email") or "").strip().lower()
            if User.query.filter_by(email=new_email).first():
                flash("Email gia in uso", "error")
            else:
                current_user.email = new_email
                db.session.commit()
                flash("Email aggiornata", "success")
        return redirect("/account")
    content = f"""<div class="card"><h1>Gestione account</h1>
    <p>Email: <strong>{current_user.email}</strong></p>
    <h2>Cambia password</h2>
    <form method="post"><input type="hidden" name="action" value="change_password">
      <input type="password" name="old_password" placeholder="Password attuale" required>
      <input type="password" name="new_password" placeholder="Nuova password" required>
      <button class="btn2" style="margin-top:1rem">Cambia</button></form>
    <h2>Cambia email</h2>
    <form method="post"><input type="hidden" name="action" value="change_email">
      <input type="email" name="new_email" placeholder="Nuova email" required>
      <button class="btn2" style="margin-top:1rem">Aggiorna</button></form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Account", content=content)

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if current_user.subscription_tier != "admin":
        return ("non autorizzato", 403)
    cfg = get_cfg()
    if request.method == "POST":
        act = request.form.get("action")
        if act == "toggle_site":
            cfg.site_open = not cfg.site_open
        elif act == "toggle_demo":
            cfg.demo_enabled = not cfg.demo_enabled
        elif act == "save_contacts":
            cfg.contact_email = request.form.get("contact_email") or cfg.contact_email
            cfg.contact_telegram = request.form.get("contact_telegram") or cfg.contact_telegram
            cfg.contact_linkedin = request.form.get("contact_linkedin") or cfg.contact_linkedin
        db.session.commit()
        flash("Salvato.", "success")
        return redirect("/admin")
    stato = "APERTO" if cfg.site_open else "CHIUSO"
    content = f"""<div class="card"><h1>Pannello Admin</h1>
    <p>Stato: <strong style="color:{'var(--teal)' if cfg.site_open else '#da3633'}">{stato}</strong></p>
    <form method="post"><input type="hidden" name="action" value="toggle_site">
      <button type="submit" style="width:auto;background:{'#da3633' if cfg.site_open else 'var(--teal)'};color:white">{'Chiudi' if cfg.site_open else 'Apri'} sito</button></form>
    <p style="margin-top:1.5rem">Demo: {'ATTIVO' if cfg.demo_enabled else 'DISATTIVATO'}</p>
    <form method="post"><input type="hidden" name="action" value="toggle_demo">
      <button type="submit" class="btn2" style="width:auto">{'Disabilita' if cfg.demo_enabled else 'Abilita'} demo</button></form></div>
    <div class="card"><h2>Contatti</h2>
    <form method="post"><input type="hidden" name="action" value="save_contacts">
      <input name="contact_email" value="{cfg.contact_email}">
      <input name="contact_telegram" value="{cfg.contact_telegram}">
      <input name="contact_linkedin" value="{cfg.contact_linkedin}">
      <button type="submit" class="btn2" style="width:auto">Salva</button></form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Admin", content=content)

@app.route("/force-setup")
def force_setup():
    with app.app_context():
        if not User.query.filter_by(email="demo@demo.com").first():
            d = User(email="demo@demo.com", subscription_tier="demo", subscription_expires=datetime.utcnow()+timedelta(days=3650))
            d.set_password("demo123"); db.session.add(d)
        if not User.query.filter_by(email="admin@sibilla.cc").first():
            a = User(email="admin@sibilla.cc", subscription_tier="admin", subscription_expires=datetime.utcnow()+timedelta(days=36500))
            a.set_password("AugetAdmin!2026"); db.session.add(a)
        db.session.commit()
        return "<h1>Fatto</h1><p>demo@demo.com / demo123</p><p>admin@sibilla.cc / AugetAdmin!2026</p>"

@app.before_request
def _site_gate():
    if request.endpoint in (None, "login", "register", "recover", "favicon", "static", "admin", "force_setup"):
        return None
    cfg = get_cfg()
    if cfg.site_open:
        return None
    if current_user.is_authenticated:
        t = current_user.subscription_tier
        if t == "admin" or (t == "demo" and cfg.demo_enabled):
            return None
    return render_template_string(BASE_TEMPLATE, title="Manutenzione",
        content="<div class='card'><h1>Sito in manutenzione</h1><p>Tornera disponibile a breve.</p></div>"), 503

with app.app_context():
    from sqlalchemy import inspect, text as sa_text
    try:
        inspector = inspect(db.engine)
        for cls in [User, Report, WatchItem, Ticket, Feedback, CollabRequest, SiteConfig]:
            tn = cls.__tablename__
            if tn in inspector.get_table_names():
                exist = {c['name'] for c in inspector.get_columns(tn)}
                for col in cls.__table__.columns:
                    if col.name not in exist and col.name != 'id':
                        try:
                            ctype = str(col.type.compile(db.engine.dialect))
                            db.session.execute(sa_text(f'ALTER TABLE "{tn}" ADD COLUMN IF NOT EXISTS {col.name} {ctype}'))
                            print(f"  + colonna {tn}.{col.name}")
                        except Exception as e:
                            print(f"  ! skip {col.name}: {e}")
            db.session.commit()
        db.create_all()
        print("DB pronto")
    except Exception as e:
        print(f"Auto-migrazione err: {e}")
        db.create_all()
    
    if not User.query.filter_by(email="demo@demo.com").first():
        d = User(email="demo@demo.com", subscription_tier="demo", subscription_expires=datetime.utcnow() + timedelta(days=3650))
        d.set_password("demo123"); db.session.add(d); db.session.commit()
        print("Account demo creato")
    if not User.query.filter_by(email="admin@sibilla.cc").first():
        adm = User(email="admin@sibilla.cc", subscription_tier="admin", subscription_expires=datetime.utcnow() + timedelta(days=36500))
        adm.set_password("AugetAdmin!2026"); db.session.add(adm); db.session.commit()
        print("Account admin creato: admin@sibilla.cc / AugetAdmin!2026")

if __name__ == "__main__":
    print("AUGET WEB con login: http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False, threaded=True)
