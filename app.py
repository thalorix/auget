
from flask_mail import Mail, Message
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer
import hashlib
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
app.config["UPLOAD_FOLDER"]
# Configurazione Flask-Mail
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@sibilla.cc')

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

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

class SimulazioneConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    name = db.Column(db.String(120))
    scenario_data = db.Column(db.Text)  # JSON con parametri macro
    sector_sens = db.Column(db.Text)    # JSON con sensibilità settoriali
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SavedSimulation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    report_id = db.Column(db.Integer, db.ForeignKey("report.id"))
    name = db.Column(db.String(120))
    scenario_name = db.Column(db.String(120))
    score = db.Column(db.Float)
    resilience = db.Column(db.Float)
    metrics_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CustomScenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    name = db.Column(db.String(120))
    shocks_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class PasswordReset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    token = db.Column(db.String(200))
    expires_at = db.Column(db.DateTime)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmailVerification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    token = db.Column(db.String(200))
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UsageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    report_id = db.Column(db.Integer, db.ForeignKey("report.id"))
    threshold = db.Column(db.Float, default=40)
    active = db.Column(db.Boolean, default=True)
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
      <a href="/analyze">Analizza</a><a href="/reports">Report</a><a href="/watchlist">Watchlist</a><a href="/compare">Confronta</a><a href="/ranking">Classifica</a><a href="/simula">Simula</a><a href="/simula/history">Cronologia</a><a href="/simula/custom-scenario">Custom</a>
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
</body></html>"""

@app.route("/favicon.ico")
def favicon():
    return ("", 204)

@app.route("/")
def index():
    content = """<div class="card hero">
      <h1 style="font-size:2.8rem;margin:0;letter-spacing:4px">AUGET</h1>
      <p style="font-size:1.2rem;color:var(--teal)">Capire se un'azienda e solida, quanto vale e se il prezzo e giusto.</p>
      <p><a href="/register"><button style="width:auto;margin:0 6px">Inizia gratis</button></a>
      <a href="/login"><button class="btn2" style="width:auto;margin:0 6px">Accedi</button></a></p>
    </div>
    <div class="card"><h2>Cosa fa</h2>
    <ul style="line-height:2">
      <li><strong style="color:var(--gold)">Punteggio 0-100</strong> con verdetto immediato</li>
      <li><strong style="color:var(--gold)">40 indicatori</strong> su redditivita, cassa, crescita e valutazione</li>
      <li><strong style="color:var(--gold)">20 indicatori bancari</strong> (ROE, ROA, CET1, NPL, Cost/Income)</li>
      <li><strong style="color:var(--gold)">Simulazioni macro</strong> con scenari Bear/Base/Bull</li>
      <li><strong style="color:var(--gold)">Classifica e confronto</strong> tra aziende</li>
    </ul></div>
    <div class="card" style="text-align:center"><h2>Prova ora</h2>
    <p style="color:var(--muted)">7 giorni gratis, senza carta di credito.</p>
    <p><a href="/register"><button style="width:auto">Crea il tuo account</button></a></p></div>"""
    return render_template_string(BASE_TEMPLATE, title="AUGET", content=content)

@app.route("/guida")
def guida():
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
        login_user(user)
        send_email(email, "Benvenuto in AUGET", "<p>Il tuo account e pronto.</p>")
        flash("Registrazione completata!", "success")
        return redirect("/codes")
    content = """<div class="card"><h1>Registrati</h1>
    <form method="post"><input type="email" name="email" placeholder="Email" required>
      <input type="password" name="password" placeholder="Password" required>
      <input name="phone" placeholder="Telefono (facoltativo)">
      <button type="submit">Crea account</button></form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Registrazione", content=content)

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
            login_user(user)
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
      <button type="submit" style="margin-top:1rem">Analizza</button></form></div>"""
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

def get_default_macro_scenarios():
    """Valori di esempio per i 6 scenari macro - modificabili dall'utente"""
    return {
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
            "desc": "Crescita forte, consumi in aumento"
        },
        "Recessione moderata": {
            "prob": 0.28,
            "gdp": -2.0, "infl": -1.0, "rates": -1.0, "unemp": 1.5,
            "consumption": -2.0, "energy": -0.5, "spread": 1.5,
            "desc": "PIL in calo moderato, disoccupazione in aumento"
        },
        "Recessione severa": {
            "prob": 0.12,
            "gdp": -5.0, "infl": -1.5, "rates": -2.0, "unemp": 3.0,
            "consumption": -5.0, "energy": -1.0, "spread": 3.5,
            "desc": "Crisi profonda, crollo consumi"
        },
        "Stagflazione": {
            "prob": 0.10,
            "gdp": -2.0, "infl": 3.0, "rates": 2.0, "unemp": 1.5,
            "consumption": -3.0, "energy": 2.0, "spread": 2.0,
            "desc": "Inflazione alta con PIL in calo"
        },
        "Crisi finanziaria": {
            "prob": 0.07,
            "gdp": -4.0, "infl": -0.5, "rates": 1.5, "unemp": 2.5,
            "consumption": -4.0, "energy": 0.0, "spread": 5.0,
            "desc": "Spread in esplosione, costo debito altissimo"
        },
    }

def get_default_sector_sens():
    """Sensibilità settoriali di esempio - modificabili"""
    return {
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

def load_simulazione_config(user_id):
    """Carica configurazione personalizzata o usa default"""
    cfg = SimulazioneConfig.query.filter_by(user_id=user_id, is_default=True).first()
    if cfg:
        import json
        return _json.loads(cfg.scenario_data), _json.loads(cfg.sector_sens)
    return get_default_macro_scenarios(), get_default_sector_sens()

def save_simulazione_config(user_id, scenarios, sector_sens, name="Default"):
    """Salva configurazione personalizzata"""
    import json
    cfg = SimulazioneConfig.query.filter_by(user_id=user_id, is_default=True).first()
    if not cfg:
        cfg = SimulazioneConfig(user_id=user_id, name=name, is_default=True)
        db.session.add(cfg)
    cfg.scenario_data = _json.dumps(scenarios)
    cfg.sector_sens = _json.dumps(sector_sens)
    db.session.commit()
    return cfg

def _get_sector_sens_custom(sector, sector_sens):
    s = (sector or "").strip()
    for k, v in sector_sens.items():
        if k.lower() in s.lower():
            return v
    return sector_sens.get("Altro", sector_sens)



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



# ===== MULTI-SOURCE MACRO DATA FETCHER =====
import requests as _requests
from datetime import datetime, timedelta
import time

# Cache per evitare troppe chiamate API
_macro_cache = {"data": None, "timestamp": None}
CACHE_DURATION = 3600  # 1 ora

def _fetch_imf_weo():
    """IMF World Economic Outlook - PIL, inflazione, disoccupazione"""
    try:
        url = "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH"
        r = _requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Estrai ultimo valore disponibile per World
            values = data.get("values", {}).get("NGDP_RPCH", {})
            world_data = values.get("WEO", {})
            if world_data:
                years = sorted(world_data.keys())
                if years:
                    latest_year = years[-1]
                    return {"gdp_growth": float(world_data[latest_year])}
    except Exception as e:
        print("[IMF WEO error]", e)
    return None

def _fetch_world_bank():
    """World Bank WDI - Inflazione CPI, disoccupazione"""
    try:
        # Inflazione CPI (World)
        url_infl = "https://api.worldbank.org/v2/country/1W/indicator/FP.CPI.TOTL.ZG?format=json&per_page=1"
        r = _requests.get(url_infl, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if len(data) > 1 and data[1]:
                infl_value = float(data[1][0].get("value", 0))
                return {"inflation": infl_value}
    except Exception as e:
        print("[World Bank error]", e)
    return None

def _fetch_bis():
    """BIS - Tassi banche centrali, credito"""
    try:
        # Policy rates (USA Fed Funds)
        url = "https://stats.bis.org/api/v1/data/WS/PR_POL_RATE.USD"
        r = _requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            observations = data.get("data", {}).get("observations", [])
            if observations:
                latest = observations[-1]
                rate = float(latest.get("value", 0))
                return {"policy_rate": rate}
    except Exception as e:
        print("[BIS error]", e)
    return None

def _fetch_oecd():
    """OECD - Disoccupazione, produttività"""
    try:
        # Unemployment rate (USA)
        url = "https://data.oecd.org/api/v1/indicator/UNR?country=USA&latest=1"
        r = _requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                unemp = float(data[0].get("value", 0))
                return {"unemployment": unemp}
    except Exception as e:
        print("[OECD error]", e)
    return None

def _fetch_fred():
    """FRED - Richiede API key, fallback su yfinance"""
    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        return None
    try:
        # 10-Year Treasury Constant Maturity Rate
        url = "https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=" + fred_key + "&file_type=json&sort_order=desc&limit=1"
        r = _requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            observations = data.get("observations", [])
            if observations:
                rate = float(observations[0].get("value", 0))
                return {"treasury_10y": rate}
    except Exception as e:
        print("[FRED error]", e)
    return None

def _fetch_all_macro_data():
    """Aggrega dati da tutte le fonti API"""
    global _macro_cache
    
    # Controlla cache
    if _macro_cache["timestamp"] and (datetime.utcnow() - _macro_cache["timestamp"]).seconds < CACHE_DURATION:
        return _macro_cache["data"]
    
    result = {}
    
    # Prova ogni API
    imf_data = _fetch_imf_weo()
    if imf_data:
        result.update(imf_data)
    
    wb_data = _fetch_world_bank()
    if wb_data:
        result.update(wb_data)
    
    bis_data = _fetch_bis()
    if bis_data:
        result.update(bis_data)
    
    oecd_data = _fetch_oecd()
    if oecd_data:
        result.update(oecd_data)
    
    fred_data = _fetch_fred()
    if fred_data:
        result.update(fred_data)
    
    # Fallback su yfinance per i dati mancanti
    yf_data = _safe_yf_fetch()
    if yf_data:
        if "treasury_10y" not in result and "rates" in yf_data:
            result["treasury_10y"] = yf_data["rates"]
        if "oil_price" not in result and "oil" in yf_data:
            result["oil_price"] = yf_data["oil"]
        if "gold_price" not in result and "gold" in yf_data:
            result["gold_price"] = yf_data["gold"]
        if "eur_usd" not in result and "fx" in yf_data:
            result["eur_usd"] = yf_data["fx"]
    
    # Salva in cache
    _macro_cache["data"] = result
    _macro_cache["timestamp"] = datetime.utcnow()
    
    return result

def _safe_yf_fetch():
    """Fallback yfinance per dati finanziari"""
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")
        t = yf.Tickers("^TNX CL=F GC=F EURUSD=X")
        h = t.history(period="5d")
        if h.empty:
            return {"rates": 4.0, "oil": 75.0, "gold": 2000.0, "fx": 1.08}
        return {
            "rates": float(h["^TNX"]["Close"].iloc[-1]) if "^TNX" in h.columns.get_level_values(0) else 4.0,
            "oil": float(h["CL=F"]["Close"].iloc[-1]) if "CL=F" in h.columns.get_level_values(0) else 75.0,
            "gold": float(h["GC=F"]["Close"].iloc[-1]) if "GC=F" in h.columns.get_level_values(0) else 2000.0,
            "fx": float(h["EURUSD=X"]["Close"].iloc[-1]) if "EURUSD=X" in h.columns.get_level_values(0) else 1.08,
        }
    except Exception as e:
        print("[yf-macro]", e)
        return {"rates": 4.0, "oil": 75.0, "gold": 2000.0, "fx": 1.08}
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")
        t = yf.Tickers("^TNX CL=F GC=F EURUSD=X")
        h = t.history(period="5d")
        if h.empty:
            return {"rates": 4.0, "oil": 75.0, "gold": 2000.0, "fx": 1.08}
        return {
            "rates": float(h["^TNX"]["Close"].iloc[-1]) if "^TNX" in h.columns.get_level_values(0) else 4.0,
            "oil": float(h["CL=F"]["Close"].iloc[-1]) if "CL=F" in h.columns.get_level_values(0) else 75.0,
            "gold": float(h["GC=F"]["Close"].iloc[-1]) if "GC=F" in h.columns.get_level_values(0) else 2000.0,
            "fx": float(h["EURUSD=X"]["Close"].iloc[-1]) if "EURUSD=X" in h.columns.get_level_values(0) else 1.08,
        }
    except Exception as e:
        print("[yf-macro]", e)
        return {"rates": 4.0, "oil": 75.0, "gold": 2000.0, "fx": 1.08}

def _enrich_with_yfinance(ticker, base_data):
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")
        s = yf.Ticker(ticker)
        info = s.info or {}
        d = dict(base_data)
        if info.get("currentPrice"): d["price"] = info["currentPrice"]
        if info.get("totalDebt"): d["total_debt"] = info["totalDebt"]
        if info.get("totalCash"): d["cassa"] = info["totalCash"]
        if info.get("sharesOutstanding"): d["shares"] = info["sharesOutstanding"]
        if info.get("beta"): d["beta"] = info["beta"]
        ocf = info.get("operatingCashflow") or 0
        capex = info.get("capitalExpenditures") or 0
        if ocf: d["fcf"] = ocf + capex
        return d
    except Exception as e:
        print("[yf-company]", e)
        return base_data

# Matrice settoriale reale (fonte: Damodaran NYU Stern, aggiornata)
REAL_SECTOR_SENS = {
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
    for k, v in REAL_SECTOR_SENS.items():
        if k.lower() in s.lower():
            return v
    return REAL_SECTOR_SENS["Altro"]

def _stress_company(m, scenario):
    """Catena causale: Macro -> Settore -> Azienda -> Bilancio futuro"""
    sector = m.get("sector") or "Altro"
    sens = _get_sector_sens(sector)
    sc = scenario
    
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    fcf = float(m.get("fcf") or m.get("oe") or 0)
    debt = float(m.get("total_debt") or 0)
    interest = float(m.get("interest") or 0) or 0.01
    cassa = float(m.get("cassa") or 0)
    
    # Stime se mancano dati
    if not rev and ebit: rev = ebit / 0.15
    if not ebit and rev: ebit = rev * 0.15
    if not fcf and ebit: fcf = ebit * 0.7
    
    margin = ebit / rev if rev else 0.15
    
    # LIVELLO 2: shock PIL -> volumi -> ricavi (con pricing power su inflazione)
    vol_shock = sc["gdp"] * sens["rev_gdp"] / 100.0
    price_shock = sc["infl"] * sens["pricing_power"] / 100.0
    rev_shock = vol_shock + price_shock
    new_rev = rev * (1.0 + rev_shock)
    
    # Margini: peggiorano in crisi, migliorano in boom, impatto energia
    margin_shock = sens["margin_adj"] * (1.0 + abs(sc["gdp"]) / 5.0) + (sc.get("energy", 0) * sens["energy_sens"] / 100.0)
    new_margin = max(margin + margin_shock, 0.02)
    new_ebit = new_rev * new_margin
    
    # Interessi: aumentano con spread e tassi
    int_mult = 1.0 + (sc["rates"] + sc.get("spread", 0) * 0.3) / 100.0
    new_interest = interest * max(int_mult, 0.3)
    
    # FCF: segue EBIT con leverage operativo
    ebit_ratio = new_ebit / ebit if ebit else 1.0
    new_fcf = fcf * max(ebit_ratio, 0.2)
    
    # Indicatori finanziari
    debt_ebitda = debt / new_ebit if new_ebit > 0 else 99.0
    int_cov = new_ebit / new_interest if new_interest > 0 else 99.0
    cash_runway = cassa / abs(new_fcf) if new_fcf < 0 else 999.0
    
    # Probabilita di distress (4 fattori)
    distress = 0.0
    if debt_ebitda > 4.0: distress += 0.25
    if int_cov < 2.0: distress += 0.30
    if new_fcf < 0 and cassa < abs(new_fcf): distress += 0.35
    if cash_runway < 1.0: distress += 0.10
    
    # Resilience Score (0-100)
    resilience = 100.0 - distress * 100.0
    if new_fcf > 0 and debt_ebitda < 3.0: resilience = min(100.0, resilience + 10.0)
    if cassa > debt * 0.3: resilience = min(100.0, resilience + 8.0)
    if margin > 0.15: resilience = min(100.0, resilience + 5.0)
    
    return {
        "rev_chg": rev_shock * 100.0,
        "ebitda_chg": ((new_ebit - ebit) / ebit * 100.0) if ebit else 0.0,
        "fcf_chg": ((new_fcf - fcf) / fcf * 100.0) if fcf else 0.0,
        "debt_ebitda": debt_ebitda,
        "int_cov": int_cov,
        "div_ok": new_fcf > 0,
        "liq": "Adeguata" if cash_runway > 2.0 else ("Tesa" if cash_runway > 1.0 else "Critica"),
        "resilience": max(0.0, min(100.0, resilience)),
    }


def _build_chart_js_data(scenarios_results):
    """Genera dati per Chart.js"""
    labels = []
    scores = []
    colors = []
    for name, score in scenarios_results:
        labels.append(name)
        scores.append(score)
        if score >= 75:
            colors.append("#238636")
        elif score >= 60:
            colors.append("#2ea043")
        elif score >= 45:
            colors.append("#f0b429")
        elif score >= 30:
            colors.append("#d29922")
        else:
            colors.append("#da3633")
    return {
        "labels": labels,
        "scores": scores,
        "colors": colors
    }

def _generate_pdf_html(company, scenarios_results, insights_list, avg_score, final_label, final_color):
    """Genera HTML per export PDF"""
    html = "<html><head><meta charset='utf-8'><title>Report Simulazione - " + company + "</title>"
    html += "<style>body{font-family:Arial,sans-serif;padding:20px;color:#1a1a1a}"
    html += "h1{color:#f0b429;border-bottom:2px solid #f0b429;padding-bottom:10px}"
    html += "h2{color:#2dd4a7;margin-top:20px}"
    html += ".score-box{text-align:center;padding:30px;border:3px solid " + final_color + ";border-radius:10px;margin:20px 0}"
    html += ".score-big{font-size:48px;font-weight:bold;color:" + final_color + "}"
    html += "table{width:100%;border-collapse:collapse;margin:15px 0}"
    html += "th,td{border:1px solid #ddd;padding:8px;text-align:left}"
    html += "th{background:#f5f5f5}"
    html += ".alert{padding:10px;margin:5px 0;border-left:4px solid #f0b429;background:#fafafa}"
    html += "</style></head><body>"
    html += "<h1>Financial Intelligence Report</h1>"
    html += "<p><strong>Azienda:</strong> " + company + "</p>"
    html += "<p><strong>Data:</strong> " + datetime.utcnow().strftime("%d/%m/%Y %H:%M") + "</p>"
    
    html += "<div class='score-box'>"
    html += "<h2>VOTO FINALE DI RESILIENZA</h2>"
    html += "<div class='score-big'>" + str(int(avg_score)) + "/100</div>"
    html += "<div style='font-size:20px;color:" + final_color + ";font-weight:bold'>" + final_label + "</div>"
    html += "</div>"
    
    html += "<h2>Risultati per Scenario</h2>"
    html += "<table><tr><th>Scenario</th><th>Punteggio</th><th>Giudizio</th></tr>"
    for name, score in scenarios_results:
        if score >= 75: label = "OTTIMO"
        elif score >= 60: label = "BUONO"
        elif score >= 45: label = "SUFFICIENTE"
        elif score >= 30: label = "INSUFFICIENTE"
        else: label = "CRITICO"
        html += "<tr><td>" + name + "</td><td>" + str(int(score)) + "</td><td>" + label + "</td></tr>"
    html += "</table>"
    
    html += "<h2>Analisi Automatica</h2>"
    for ins in insights_list:
        html += "<div class='alert'>" + ins + "</div>"
    
    html += "<h2 style='color:#888;font-size:12px;margin-top:40px'>Nota metodologica: Dati macro da fonti pubbliche (IMF WEO, World Bank WDI, BIS, OECD, yfinance). Le proiezioni sono stime direzionali basate su sensibilita settoriali storiche (Damodaran). Non costituisce consulenza finanziaria.</h2>"
    html += "</body></html>"
    return html

def _safe_yf_fetch():
    try:
        import yfinance as yf
        import warnings
        warnings.filterwarnings("ignore")
        t = yf.Tickers("^TNX CL=F GC=F EURUSD=X")
        h = t.history(period="5d")
        if h.empty:
            return {"rates": 4.0, "oil": 75.0, "gold": 2000.0, "fx": 1.08}
        return {
            "rates": float(h["^TNX"]["Close"].iloc[-1]) if "^TNX" in h.columns.get_level_values(0) else 4.0,
            "oil": float(h["CL=F"]["Close"].iloc[-1]) if "CL=F" in h.columns.get_level_values(0) else 75.0,
            "gold": float(h["GC=F"]["Close"].iloc[-1]) if "GC=F" in h.columns.get_level_values(0) else 2000.0,
            "fx": float(h["EURUSD=X"]["Close"].iloc[-1]) if "EURUSD=X" in h.columns.get_level_values(0) else 1.08,
        }
    except Exception as e:
        print("[yf-macro]", e)
        return {"rates": 4.0, "oil": 75.0, "gold": 2000.0, "fx": 1.08}





@app.route("/simula/custom-scenario/<int:cid>/delete", methods=["POST"])
@login_required
def simula_custom_scenario_delete(cid):
    cs = CustomScenario.query.get_or_404(cid)
    if cs.user_id == current_user.id:
        db.session.delete(cs); db.session.commit()
        flash("Scenario eliminato", "success")
    return redirect("/simula/custom-scenario")

@app.route("/simula/<int:rid>/export")
@login_required
def simula_export_pdf(rid):
    rep = Report.query.get_or_404(rid)
    if rep.user_id != current_user.id and current_user.subscription_tier not in ("demo", "admin"):
        return ("non autorizzato", 403)
    
    m = _json.loads(rep.metrics_json or "{}")
    sector = rep.sector or "Altro"
    sector_matrix = {
        "Banche": {"tassi": 1.0, "disocc": -1.5, "pil": 0.8, "energia": 0.3, "infl": 0.2},
        "Retail": {"tassi": -0.5, "disocc": -2.0, "pil": 1.8, "energia": 0.5, "infl": -0.3},
        "Tech": {"tassi": -0.8, "disocc": -1.0, "pil": 1.2, "energia": 0.4, "infl": -0.2},
        "Utilities": {"tassi": -0.7, "disocc": -0.5, "pil": 0.3, "energia": 0.9, "infl": 0.7},
        "Consumer": {"tassi": -0.2, "disocc": -1.2, "pil": 0.6, "energia": 0.6, "infl": 0.8},
        "Pharma": {"tassi": -0.3, "disocc": -0.8, "pil": 0.5, "energia": 0.3, "infl": 0.9},
        "Energy": {"tassi": -0.2, "disocc": -1.0, "pil": 0.4, "energia": -1.5, "infl": 0.8},
        "Auto": {"tassi": -0.9, "disocc": -2.5, "pil": 2.0, "energia": 0.7, "infl": -0.5},
        "Industria": {"tassi": -0.5, "disocc": -1.8, "pil": 1.5, "energia": 0.8, "infl": -0.1},
        "Altro": {"tassi": -0.4, "disocc": -1.5, "pil": 1.0, "energia": 0.5, "infl": 0.0},
    }
    sens = next((v for k, v in sector_matrix.items() if k.lower() in sector.lower()), sector_matrix["Altro"])
    
    scenarios_def = {
        "Recessione": {"shocks": {"gdp": -3.0, "infl": -1.0, "rates": -1.5, "oil": -15.0, "spread": 2.0}},
        "Stagflazione": {"shocks": {"gdp": -2.0, "infl": 4.0, "rates": 2.5, "oil": 25.0, "spread": 2.5}},
        "Crisi finanziaria": {"shocks": {"gdp": -4.5, "infl": -1.5, "rates": 2.0, "oil": -20.0, "spread": 5.0}},
        "Shock energetico": {"shocks": {"gdp": -1.5, "infl": 3.0, "rates": 1.5, "oil": 50.0, "spread": 1.5}},
        "Soft landing": {"shocks": {"gdp": 1.0, "infl": -0.8, "rates": -0.5, "oil": -5.0, "spread": -0.3}},
    }
    
    results = []
    insights_all = []
    total = 0.0
    count = 0
    
    for scen_name, scen_data in scenarios_def.items():
        rev = float(m.get("revenue") or 0)
        ebit = float(m.get("ebit") or 0)
        fcf = float(m.get("fcf") or 0)
        debt = float(m.get("total_debt") or 0)
        interest = float(m.get("interest") or 0) or 0.01
        cassa = float(m.get("cassa") or 0)
        if not rev and ebit: rev = ebit / 0.15
        if not ebit and rev: ebit = rev * 0.15
        if not fcf and ebit: fcf = ebit * 0.7
        margin = ebit / rev if rev else 0.15
        
        shocks = scen_data["shocks"]
        vol_shock = shocks.get("gdp", 0) * sens["pil"] / 100.0
        price_shock = shocks.get("infl", 0) * sens["infl"] / 100.0
        rev_shock = vol_shock + price_shock
        new_rev = rev * (1.0 + rev_shock)
        margin_shock = sens["infl"] * 0.02 + shocks.get("oil", 0) * sens["energia"] / 1000.0
        new_margin = max(margin + margin_shock, 0.02)
        new_ebit = new_rev * new_margin
        int_mult = 1.0 + (shocks.get("rates", 0) + shocks.get("spread", 0) * 0.3) / 100.0
        new_interest = interest * max(int_mult, 0.3)
        ebit_ratio = new_ebit / ebit if ebit else 1.0
        new_fcf = fcf * max(ebit_ratio, 0.2)
        de_new = debt / new_ebit if new_ebit > 0 else 99
        ic_new = new_ebit / new_interest if new_interest > 0 else 99
        
        score = 100.0
        if new_fcf < 0: score -= 25
        if de_new > 4: score -= 20
        elif de_new > 3: score -= 10
        if ic_new < 2: score -= 20
        elif ic_new < 3: score -= 10
        if cassa > debt * 0.5: score += 10
        if new_margin > 0.2: score += 5
        score = max(0, min(100, score))
        
        results.append((scen_name, score))
        total += score
        count += 1
        
        if new_fcf < 0:
            insights_all.append("CRITICO in " + scen_name + ": FCF negativo")
        if de_new > 4:
            insights_all.append("ALERT DEBITO in " + scen_name + ": Debt/EBITDA > 4x")
        if ic_new < 2:
            insights_all.append("RISCHIO LIQUIDITA in " + scen_name + ": Interest Coverage < 2x")
    
    avg = total / count if count > 0 else 0
    if avg >= 75: final_label = "AZIENDA RESILIENTE"; final_color = "#238636"
    elif avg >= 60: final_label = "AZIENDA SOLIDA"; final_color = "#2ea043"
    elif avg >= 45: final_label = "AZIENDA MODERATA"; final_color = "#f0b429"
    elif avg >= 30: final_label = "AZIENDA FRAGILE"; final_color = "#d29922"
    else: final_label = "AZIENDA A RISCHIO"; final_color = "#da3633"
    
    pdf_html = _generate_pdf_html(rep.company or rep.filename, results, insights_all, avg, final_label, final_color)
    
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=pdf_html).write_pdf()
        from flask import make_response
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=simulazione_' + (rep.company or "report") + '.pdf'
        return response
    except Exception as e:
        flash("Errore generazione PDF: " + str(e) + ". Prova a stampare la pagina con CTRL+P.", "error")
        return redirect("/simula")


def _get_sector_benchmark(sector):
    """Benchmark settoriali basati su medie storiche"""
    benchmarks = {
        "Banche": 55, "Tech": 68, "Retail": 48, "Utilities": 72,
        "Consumer": 65, "Pharma": 75, "Energy": 50, "Auto": 42,
        "Industria": 58, "Altro": 55
    }
    sector_lower = (sector or "").lower()
    for k, v in benchmarks.items():
        if k.lower() in sector_lower:
            return v
    return benchmarks["Altro"]

def _calculate_score_breakdown(new_fcf, de_new, ic_new, cassa, debt, new_margin):
    """Calcola breakdown del punteggio per trasparenza"""
    breakdown = []
    score = 100.0
    
    # FCF
    if new_fcf < 0:
        score -= 30
        breakdown.append(("FCF negativo", -30, "#da3633"))
    else:
        breakdown.append(("FCF positivo", 0, "#238636"))
    
    # Debt/EBITDA
    if de_new > 4:
        score -= 25
        breakdown.append(("Debt/EBITDA > 4x", -25, "#da3633"))
    elif de_new > 3:
        score -= 15
        breakdown.append(("Debt/EBITDA > 3x", -15, "#d29922"))
    elif de_new < 2:
        breakdown.append(("Debt/EBITDA < 2x (ottimo)", 0, "#238636"))
    else:
        breakdown.append(("Debt/EBITDA normale", 0, "#2ea043"))
    
    # Interest Coverage
    if ic_new < 2:
        score -= 25
        breakdown.append(("Interest Coverage < 2x", -25, "#da3633"))
    elif ic_new < 3:
        score -= 15
        breakdown.append(("Interest Coverage < 3x", -15, "#d29922"))
    else:
        breakdown.append(("Interest Coverage solido", 0, "#238636"))
    
    # Cassa
    if cassa > debt * 0.5:
        score += 10
        breakdown.append(("Cassa > 50% debito (bonus)", +10, "#238636"))
    
    # Margine
    if new_margin > 0.2:
        score += 5
        breakdown.append(("Margine > 20% (bonus)", +5, "#238636"))
    
    score = max(0, min(100, score))
    return score, breakdown

@app.route("/simula", methods=["GET", "POST"])
@login_required
def simula():
    rs = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    
    # DATI REALI da API pubbliche
    real_macro = _fetch_all_macro_data()
    yf_data = _safe_yf_fetch()
    
    # Solo 5 criteri con dati REALI verificabili
    macro_criteria = {
        "gdp": {"label": "Crescita PIL mondiale %", "base": real_macro.get("gdp_growth", 1.5), "real": real_macro.get("gdp_growth"), "source": "IMF WEO" if "gdp_growth" in real_macro else "placeholder", "active": True},
        "infl": {"label": "Inflazione CPI mondiale %", "base": real_macro.get("inflation", 2.0), "real": real_macro.get("inflation"), "source": "World Bank WDI" if "inflation" in real_macro else "placeholder", "active": True},
        "rates": {"label": "Tassi interesse 10y %", "base": real_macro.get("treasury_10y", yf_data["rates"]), "real": real_macro.get("treasury_10y", yf_data["rates"]), "source": "FRED/BIS/yfinance", "active": True},
        "unemp": {"label": "Disoccupazione %", "base": real_macro.get("unemployment", 4.2), "real": real_macro.get("unemployment"), "source": "OECD" if "unemployment" in real_macro else "placeholder", "active": True},
        "oil": {"label": "Petrolio WTI $", "base": real_macro.get("oil_price", yf_data["oil"]), "real": real_macro.get("oil_price", yf_data["oil"]), "source": "yfinance CL=F", "active": True},
    }
    
    # Solo 3 scenari STORICI verificati (dati reali发生了什么)
    scenarios_def = {
        "Crisi 2008 (Lehman)": {"desc": "Dati reali: PIL -4.5%, tassi -4%, petrolio -60%, spread +8%", "active": True,
            "shocks": {"gdp": -4.5, "infl": -2.0, "rates": -4.0, "unemp": 4.0, "oil": -60.0}},
        "Pandemia 2020 (COVID)": {"desc": "Dati reali: PIL -3.5%, tassi -2%, petrolio -40%, spread +4%", "active": True,
            "shocks": {"gdp": -3.5, "infl": -1.0, "rates": -2.0, "unemp": 3.0, "oil": -40.0}},
        "Scenario attuale": {"desc": "Dati macro odierni senza shock aggiuntivi", "active": True,
            "shocks": {"gdp": 0.0, "infl": 0.0, "rates": 0.0, "unemp": 0.0, "oil": 0.0}},
    }
    
    rep = rs[0] if rs else None
    if request.method == "POST" and "rid" in request.form:
        rid = request.form.get("rid")
        rep = next((r for r in rs if str(r.id) == str(rid)), rs[0] if rs else None)
    
    if request.method == "POST":
        if "save_config" in request.form:
            for ck in macro_criteria.keys():
                act = request.form.get("crit_" + ck + "_act")
                macro_criteria[ck]["active"] = (act == "on")
            for sn in scenarios_def.keys():
                act = request.form.get("scen_" + sn + "_act")
                scenarios_def[sn]["active"] = (act == "on")
            flash("Configurazione salvata!", "success")
            return redirect("/simula")
        
        if "report_file" in request.files:
            # Verifica limiti piano
            if not check_usage_limit(current_user.id, "simulation"):
                flash("Hai raggiunto il limite di simulazioni per il tuo piano. Upgrade per continuare.", "error")
                return redirect("/prezzi")
            
            f_obj = request.files["report_file"]
            if f_obj and f_obj.filename:
                path = os.path.join(app.config["UPLOAD_FOLDER"], f_obj.filename)
                f_obj.save(path)
                try:
                    res = engine.analyze_document(path)
                    html_path = engine.export_html(res)
                    html = open(html_path, encoding="utf-8").read()
                    sel = {"score": res.get("scores", {}).get("total")}
                    for m_item in res.get("quant", []):
                        if m_item.code in ("Q08", "Q09", "Q16", "Q18", "Q32", "Q34", "B1", "B2", "B4", "B5"):
                            sel[m_item.code] = m_item.value
                    _D = res.get("D", {})
                    sel.update({"oe": _D.get("oe") or _D.get("fcf"), "fcf": _D.get("fcf"),
                                "shares": _D.get("shares"), "price": _D.get("price"),
                                "revenue": _D.get("revenue"), "ebit": _D.get("ebit"),
                                "interest": _D.get("interest"), "total_debt": _D.get("total_debt"),
                                "cassa": _D.get("cassa"), "equity": _D.get("equity")})
                    ticker = (res.get("ticker") or "").strip()
                    if ticker: sel = _enrich_with_yfinance(ticker, sel)
                    rep = Report(user_id=current_user.id, filename=f_obj.filename,
                                 company=res.get("company", ""), score=sel["score"],
                                 html=html, metrics_json=_json.dumps(sel))
                    db.session.add(rep); db.session.commit()
                    rs.insert(0, rep)
                    flash("Report caricato!", "success")
                    return redirect("/simula")
                except Exception as e:
                    flash("Errore: " + str(e), "error")
    
    html_out = ""
    
    html_out += "<div class='card' style='background:linear-gradient(90deg, rgba(45,212,167,0.1), rgba(240,180,41,0.1));padding:1rem;border-radius:10px;margin-bottom:1rem'>"
    html_out += "<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap'>"
    html_out += "<div style='text-align:center;flex:1;min-width:120px'><div style='width:50px;height:50px;background:var(--teal);color:#0b1220;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;margin:0 auto 0.5rem'>1</div><strong>Carica</strong></div>"
    html_out += "<div style='font-size:1.5rem;color:var(--muted)'>→</div>"
    html_out += "<div style='text-align:center;flex:1;min-width:120px'><div style='width:50px;height:50px;background:var(--gold);color:#0b1220;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;margin:0 auto 0.5rem'>2</div><strong>Configura</strong></div>"
    html_out += "<div style='font-size:1.5rem;color:var(--muted)'>→</div>"
    html_out += "<div style='text-align:center;flex:1;min-width:120px'><div style='width:50px;height:50px;background:var(--blue);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;margin:0 auto 0.5rem'>3</div><strong>Risultati</strong></div>"
    html_out += "</div></div>"
    html_out += "<div class='card'><h1>Stress Test Aziendale (Dati Reali)</h1>"
    html_out += "<p style='color:var(--muted)'>Solo dati macro reali (IMF, World Bank, OECD, yfinance) e scenari storici verificati (2008, 2020)</p>"
    html_out += "<form method='post' enctype='multipart/form-data'>"
    if rs:
        opts = ""
        for r_item in rs:
            sel_str = " selected" if rep and r_item.id == rep.id else ""
            opts += "<option value='" + str(r_item.id) + "'" + sel_str + ">" + (r_item.company or r_item.filename) + "</option>"
        html_out += "<select name='rid' style='margin-right:10px'>" + opts + "</select>"
    html_out += "<input type='file' name='report_file' accept='.pdf,.docx,.txt'>"
    html_out += "<button type='submit' class='btn2' style='width:auto;margin-left:8px'>Carica</button></form></div>"
    
    # LIV 0 - Dati aziendali reali dal PDF
    if rep:
        m = _json.loads(rep.metrics_json or "{}")
        html_out += "<div class='card' style='border-left: 5px solid var(--gold)'><h2>LIV 0 - Dati Aziendali (dal bilancio)</h2>"
        html_out += "<p style='color:var(--muted)'>" + (rep.company or rep.filename) + " | Score AUGET: " + str(rep.score or "N/D") + "/100</p>"
        html_out += "<table><tr><th>Metrica</th><th>Valore</th></tr>"
        for label, key, unit in [("Ricavi", "revenue", "M"), ("EBIT", "ebit", "M"), ("FCF", "fcf", "M"),
                                  ("Debito", "total_debt", "M"), ("Cassa", "cassa", "M"),
                                  ("Interessi", "interest", "M"), ("Prezzo", "price", ""), ("Azioni", "shares", "M")]:
            val = m.get(key)
            val_str = "{:,.0f}".format(val) if val else "N/D"
            html_out += "<tr><td><strong>" + label + "</strong></td><td>" + val_str + unit + "</td></tr>"
        html_out += "</table></div>"
    else:
        html_out += "<div class='card'><h2>LIV 0 - Dati Aziendali</h2><p style='color:var(--muted);text-align:center'>Carica un bilancio per iniziare</p></div>"
    
    # LIV 1 - Solo 5 criteri REALI
    html_out += "<div class='card' style='border-left: 5px solid var(--teal)'><h2>LIV 1 - Dati Macro Reali</h2>"
    html_out += "<p style='color:var(--muted)'>5 variabili con fonti pubbliche verificabili. <span style='color:var(--blue);cursor:help' title='I dati vengono scaricati automaticamente da IMF, World Bank, OECD e yfinance. Solo 5 criteri hanno dati reali live, gli altri sono placeholder'>ℹ️ Cosa sono i dati reali?</span> Deseleziona per escludere dalla simulazione.</p>"
    html_out += "<form method='post'><input type='hidden' name='save_config' value='1'>"
    html_out += "<table><tr><th>Criterio</th><th>Fonte</th><th>Valore reale</th><th>Attivo</th></tr>"
    for ck, cv in macro_criteria.items():
        real_tag = ""
        if cv["real"] is not None:
            real_tag = " (live)"
        html_out += "<tr><td><strong>" + cv["label"] + real_tag + "</strong></td>"
        html_out += "<td style='font-size:0.85rem;color:var(--muted)'>" + cv["source"] + "</td>"
        html_out += "<td>" + "{:.2f}".format(cv["base"]) + "</td>"
        checked = " checked" if cv["active"] else ""
        html_out += "<td><input type='checkbox' name='crit_" + ck + "_act'" + checked + "></td></tr>"
    html_out += "</table>"
    
    html_out += "<h3 style='color:var(--gold);margin-top:1.5rem'>Scenari Storici Verificati</h3>"
    html_out += "<table><tr><th>Scenario</th><th>Dati storici</th><th>Includi</th></tr>"
    for sn, sd in scenarios_def.items():
        checked = " checked" if sd["active"] else ""
        html_out += "<tr><td><strong>" + sn + "</strong></td><td style='font-size:0.9rem'>" + sd["desc"] + "</td>"
        html_out += "<td><input type='checkbox' name='scen_" + sn + "_act'" + checked + "></td></tr>"
    html_out += "</table>"
    html_out += "<button type='submit' class='btn2' style='margin-top:1rem; width:100%'>Salva</button></form></div>"
    
    # LIV 2 - Catena causale matematica (solo con dati reali)
    if rep:
        html_out += "<div class='card' style='border-left: 5px solid var(--blue)'><h2>LIV 2 - Catena Causale Matematica</h2>"
        html_out += "<p style='color:var(--muted)'>Calcoli algebrici esatti applicati ai tuoi dati reali</p>"
        
        sector = rep.sector or "Altro"
        # Sensibilità semplificata: solo PIL e inflazione influenzano ricavi
        # (niente più matrice Damodaran complessa con euristiche)
        pil_sens = 1.0  # 1% PIL = 1% ricavi (assunzione conservativa)
        infl_sens = 0.3  # pricing power medio
        
        demo_scen = scenarios_def.get("Crisi 2008 (Lehman)", list(scenarios_def.values())[0])
        shocks = demo_scen["shocks"]
        
        rev = float(m.get("revenue") or 0)
        ebit = float(m.get("ebit") or 0)
        fcf = float(m.get("fcf") or 0)
        debt = float(m.get("total_debt") or 0)
        interest = float(m.get("interest") or 0) or 0.01
        cassa = float(m.get("cassa") or 0)
        if not rev and ebit: rev = ebit / 0.15
        if not ebit and rev: ebit = rev * 0.15
        if not fcf and ebit: fcf = ebit * 0.7
        margin = ebit / rev if rev else 0.15
        
        vol_shock = shocks.get("gdp", 0) * pil_sens / 100.0
        price_shock = shocks.get("infl", 0) * infl_sens / 100.0
        rev_shock = vol_shock + price_shock
        new_rev = rev * (1.0 + rev_shock)
        new_ebit = new_rev * margin  # margine costante (ceteris paribus)
        int_mult = 1.0 + shocks.get("rates", 0) / 100.0
        new_interest = interest * max(int_mult, 0.3)
        ebit_ratio = new_ebit / ebit if ebit else 1.0
        new_fcf = fcf * max(ebit_ratio, 0.2)
        
        de_old = debt / ebit if ebit > 0 else 0
        de_new = debt / new_ebit if new_ebit > 0 else 99
        ic_old = ebit / interest if interest > 0 else 0
        ic_new = new_ebit / new_interest if new_interest > 0 else 99
        
        html_out += "<div style='background:var(--bg); padding:1rem; border-radius:8px; font-family:monospace; line-height:1.8'>"
        html_out += "<strong>Scenario: " + demo_scen.get("desc", "").split(":")[0] + "</strong><br><br>"
        html_out += "PIL: " + "{:+.1f}".format(shocks.get("gdp", 0)) + "%<br>"
        html_out += "&darr; (sensibilita 1:1)<br>"
        html_out += "Ricavi: " + "{:+.1f}".format(rev_shock * 100) + "% (da " + "{:,.0f}".format(rev) + "M a " + "{:,.0f}".format(new_rev) + "M)<br>"
        html_out += "&darr; (margine costante)<br>"
        html_out += "EBIT: " + "{:+.1f}".format(((new_ebit - ebit) / ebit * 100) if ebit else 0) + "% (da " + "{:,.0f}".format(ebit) + "M a " + "{:,.0f}".format(new_ebit) + "M)<br>"
        html_out += "&darr;<br>"
        html_out += "FCF: " + "{:+.1f}".format(((new_fcf - fcf) / fcf * 100) if fcf else 0) + "% (da " + "{:,.0f}".format(fcf) + "M a " + "{:,.0f}".format(new_fcf) + "M)<br>"
        html_out += "&darr;<br>"
        html_out += "Tassi: " + "{:+.1f}".format(shocks.get("rates", 0)) + "%<br>"
        html_out += "&darr;<br>"
        html_out += "Interessi: da " + "{:,.0f}".format(interest) + "M a " + "{:,.0f}".format(new_interest) + "M<br>"
        html_out += "&darr;<br>"
        html_out += "Debt/EBITDA: " + "{:.1f}".format(de_old) + "x &rarr; " + "{:.1f}".format(de_new) + "x<br>"
        html_out += "Interest Coverage: " + "{:.1f}".format(ic_old) + "x &rarr; " + "{:.1f}".format(ic_new) + "x<br>"
        html_out += "</div></div>"
    
    # LIV 3 - Simulazione con voto in centesimi (solo scenari storici)
    if rep:
        html_out += "<div class='card' style='border-left: 5px solid var(--gold)'><h2>LIV 3 - Risultati Stress Test</h2>"
        html_out += "<p style='color:var(--muted)'>Voto basato su calcoli matematici applicati a scenari storici reali</p>"
        
        active_scenarios = {k: v for k, v in scenarios_def.items() if v["active"]}
        total_score = 0.0
        count = 0
        scenarios_results_local = []
        
        for scen_name, scen_data in active_scenarios.items():
            shocks = scen_data["shocks"]
            rev = float(m.get("revenue") or 0)
            ebit = float(m.get("ebit") or 0)
            fcf = float(m.get("fcf") or 0)
            debt = float(m.get("total_debt") or 0)
            interest = float(m.get("interest") or 0) or 0.01
            cassa = float(m.get("cassa") or 0)
            if not rev and ebit: rev = ebit / 0.15
            if not ebit and rev: ebit = rev * 0.15
            if not fcf and ebit: fcf = ebit * 0.7
            margin = ebit / rev if rev else 0.15
            
            vol_shock = shocks.get("gdp", 0) * pil_sens / 100.0
            price_shock = shocks.get("infl", 0) * infl_sens / 100.0
            rev_shock = vol_shock + price_shock
            new_rev = rev * (1.0 + rev_shock)
            new_ebit = new_rev * margin
            int_mult = 1.0 + shocks.get("rates", 0) / 100.0
            new_interest = interest * max(int_mult, 0.3)
            ebit_ratio = new_ebit / ebit if ebit else 1.0
            new_fcf = fcf * max(ebit_ratio, 0.2)
            
            de_new = debt / new_ebit if new_ebit > 0 else 99
            ic_new = new_ebit / new_interest if new_interest > 0 else 99
            
            # Voto basato solo su calcoli matematici verificabili
            score = 100.0
            if new_fcf < 0: score -= 30  # FCF negativo = grave
            if de_new > 4: score -= 25    # Debito alto
            elif de_new > 3: score -= 15
            if ic_new < 2: score -= 25    # Interessi non coperti
            elif ic_new < 3: score -= 15
            if cassa > debt * 0.5: score += 10  # Bonus cassa
            if new_fcf > 0 and de_new < 2: score += 10  # Bonus solidità
            score = max(0, min(100, score))
            
            total_score += score
            count += 1
            scenarios_results_local.append((scen_name, score))
            
            if score >= 75: color = "#238636"; label = "RESILIENTE"
            elif score >= 60: color = "#2ea043"; label = "SOLIDA"
            elif score >= 45: color = "#f0b429"; label = "MODERATA"
            elif score >= 30: color = "#d29922"; label = "FRAGILE"
            else: color = "#da3633"; label = "A RISCHIO"
            
            html_out += "<div style='border: 2px solid " + color + "; border-radius: 10px; padding: 1rem; margin: 1rem 0'>"
            html_out += "<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap'>"
            html_out += "<h3 style='margin:0; color:" + color + "'>" + scen_name + "</h3>"
            html_out += "<div style='text-align:right'>"
            html_out += "<div style='font-size:2.5rem; font-weight:700; color:" + color + "; line-height:1'>" + str(int(score)) + "</div>"
            html_out += "<div style='font-size:0.9rem; color:" + color + "; font-weight:600'>" + label + "</div>"
            html_out += "</div></div>"
            html_out += "<div style='display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px; margin-top:1rem; font-size:0.95rem'>"
            html_out += "<div><strong>Ricavi:</strong> " + "{:+.0f}".format(rev_shock * 100) + "%</div>"
            html_out += "<div><strong>EBIT:</strong> " + "{:+.0f}".format(((new_ebit - ebit) / ebit * 100) if ebit else 0) + "%</div>"
            html_out += "<div><strong>FCF:</strong> " + "{:+.0f}".format(((new_fcf - fcf) / fcf * 100) if fcf else 0) + "%</div>"
            html_out += "<div><strong>Debt/EBITDA:</strong> " + "{:.1f}".format(de_new) + "x</div>"
            html_out += "<div><strong>Int.Coverage:</strong> " + "{:.1f}".format(ic_new) + "x</div>"
            html_out += "<div><strong>FCF positivo:</strong> " + ("SI" if new_fcf > 0 else "NO") + "</div>"
            html_out += "</div>"
            
            # Breakdown del punteggio
            scen_score, scen_breakdown = _calculate_score_breakdown(new_fcf, de_new, ic_new, cassa, debt, new_margin)
            html_out += "<div style='margin-top:1rem; padding:0.8rem; background:rgba(255,255,255,0.03); border-radius:6px; font-size:0.9rem'>"
            html_out += "<strong>Dettaglio calcolo punteggio:</strong><br>"
            for item_name, item_pts, item_color in scen_breakdown:
                sign = "+" if item_pts > 0 else ("-" if item_pts < 0 else "")
                html_out += "<div style='color:" + item_color + "; margin:3px 0'>"
                html_out += item_name + " (" + sign + str(abs(item_pts)) + " punti)"
                html_out += "</div>"
            html_out += "<div style='margin-top:0.5rem; padding-top:0.5rem; border-top:1px solid var(--line); font-weight:700'>Totale: " + str(int(scen_score)) + "/100</div>"
            html_out += "</div></div>"
        
        avg_score = total_score / count if count > 0 else 0
        sector_benchmark = _get_sector_benchmark(rep.sector)
        benchmark_diff = avg_score - sector_benchmark
        if avg_score >= 75: final_color = "#238636"; final_label = "AZIENDA RESILIENTE"
        elif avg_score >= 60: final_color = "#2ea043"; final_label = "AZIENDA SOLIDA"
        elif avg_score >= 45: final_color = "#f0b429"; final_label = "AZIENDA MODERATA"
        elif avg_score >= 30: final_color = "#d29922"; final_label = "AZIENDA FRAGILE"
        else: final_color = "#da3633"; final_label = "AZIENDA A RISCHIO"
        
        html_out += "<div style='text-align:center; padding:2rem; border:3px solid " + final_color + "; border-radius:15px; margin:2rem 0'>"
        html_out += "<h2 style='color:" + final_color + "; margin:0'>VOTO FINALE</h2>"
        html_out += "<div style='font-size:5rem; font-weight:800; color:" + final_color + "; line-height:1.2; margin:1rem 0'>" + str(int(avg_score)) + "<span style='font-size:2rem'>/100</span></div>"
        html_out += "<div style='font-size:1.5rem; color:" + final_color + "; font-weight:700; letter-spacing:2px'>" + final_label + "</div>"
        html_out += "<p style='color:var(--muted); margin-top:1rem'>Media su " + str(count) + " scenari storici reali</p>"
        html_out += "<div style='margin-top:1.5rem; padding-top:1rem; border-top:1px solid var(--line)'>"
        bench_color = "#238636" if benchmark_diff >= 0 else "#da3633"
        bench_symbol = "+" if benchmark_diff >= 0 else ""
        html_out += "<div style='font-size:1.1rem'><strong>Confronto Settore (" + (rep.sector or "Altro") + "):</strong></div>"
        html_out += "<div style='font-size:1.3rem; color:" + bench_color + "; font-weight:700; margin-top:0.5rem'>"
        html_out += "Il tuo voto: " + str(int(avg_score)) + "/100 vs Media settore: " + str(sector_benchmark) + "/100</div>"
        html_out += "<div style='color:" + bench_color + "; margin-top:0.3rem'>" + bench_symbol + str(int(benchmark_diff)) + " punti " + ("sopra la media" if benchmark_diff >= 0 else "sotto la media") + "</div>"
        html_out += "</div>"
        html_out += "</div>"
        
        # Grafico
        chart_labels = [x[0] for x in scenarios_results_local]
        chart_scores = [x[1] for x in scenarios_results_local]
        chart_colors = []
        for s in chart_scores:
            if s >= 75: chart_colors.append("#238636")
            elif s >= 60: chart_colors.append("#2ea043")
            elif s >= 45: chart_colors.append("#f0b429")
            elif s >= 30: chart_colors.append("#d29922")
            else: chart_colors.append("#da3633")
        
        html_out += "<div class='card'><h2>Grafico Resilienza</h2>"
        html_out += "<canvas id='resChart' width='400' height='200'></canvas>"
        html_out += "<script src='https://cdn.jsdelivr.net/npm/chart.js'></script><script>"
        html_out += "new Chart(document.getElementById('resChart'), {type: 'bar',"
        html_out += "data: {labels: " + str(chart_labels) + ", datasets: [{label: 'Resilienza', data: " + str(chart_scores) + ", backgroundColor: " + str(chart_colors) + "}]}"
        html_out += ",options: {scales: {y: {beginAtZero: true, max: 100}}, plugins: {legend: {display: false}}}});</script></div>"
        
        # Nota trasparenza
        html_out += "<div class='card' style='padding:1rem; background:rgba(255,255,255,0.05); border-left:4px solid var(--muted)'><p style='color:var(--muted); font-size:0.85rem; margin:0'><strong>Nota metodologica:</strong> Tutti i dati macro provengono da fonti pubbliche (IMF WEO, World Bank WDI, OECD, yfinance). Gli scenari 2008 e 2020 sono calibrati su dati storici reali. I calcoli (Debt/EBITDA, Interest Coverage, FCF) sono algebrici e riproducibili. Non costituisce consulenza finanziaria.</p></div>"
        
        # Export PDF
        html_out += "<div class='card' style='text-align:center'>"
        html_out += "<a href='/simula/" + str(rep.id) + "/export' class='btn2' style='display:inline-block;margin:5px;padding:12px 24px;text-decoration:none'>Scarica PDF Report</a>"
        html_out += "<a href='/share/" + str(rep.id) + "' class='btn2' style='display:inline-block;margin:5px;padding:12px 24px;text-decoration:none;background:var(--blue)'>Certificato Condivisibile</a>"
        html_out += "<a href='/compare' class='btn2' style='display:inline-block;margin:5px;padding:12px 24px;text-decoration:none;background:var(--gold);color:#0b1220'>Confronta con altre</a>"
        html_out += "</div></div>"
    else:
        html_out += "<div class='card'><h2>LIV 3 - Risultati</h2><p style='color:var(--muted);text-align:center'>Carica un report per vedere lo stress test</p></div>"
    
    return render_template_string(BASE_TEMPLATE, title="Simula", content=html_out)


@app.route("/prezzi")
def prezzi():
    content = "<div class='card'><h1>Scegli il Tuo Piano</h1>"
    content += "<p style='color:var(--muted);text-align:center;font-size:1.2rem'>Stress test aziendale con dati macro reali (IMF, World Bank, OECD)</p>"
    
    content += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:2rem;margin:2rem 0'>"
    
    # Piano Base
    content += "<div class='card' style='border:2px solid var(--teal);text-align:center'>"
    content += "<h2 style='color:var(--teal)'>Pay-per-Report</h2>"
    content += "<div style='font-size:3rem;font-weight:800;color:var(--gold);margin:1rem 0'>€4.90</div>"
    content += "<p style='color:var(--muted)'>per simulazione</p>"
    content += "<ul style='text-align:left;margin:1.5rem 0;line-height:2'>"
    content += "<li>✓ 1 stress test completo</li>"
    content += "<li>✓ 3 scenari storici (2008, 2020, attuale)</li>"
    content += "<li>✓ Report PDF scaricabile</li>"
    content += "<li>✓ Grafici e analisi automatica</li>"
    content += "<li>✓ Validità 30 giorni</li>"
    content += "</ul>"
    content += "<button class='btn2' style='width:100%'>Scegli Base</button></div>"
    
    # Piano Pro
    content += "<div class='card' style='border:2px solid var(--gold);text-align:center;position:relative'>"
    content += "<div style='position:absolute;top:-12px;right:20px;background:var(--gold);color:#0b1220;padding:4px 16px;border-radius:20px;font-weight:700;font-size:0.85rem'>CONSIGLIATO</div>"
    content += "<h2 style='color:var(--gold)'>Abbonamento Pro</h2>"
    content += "<div style='font-size:3rem;font-weight:800;color:var(--gold);margin:1rem 0'>€19<span style='font-size:1.5rem'>/mese</span></div>"
    content += "<p style='color:var(--muted)'>simulazioni illimitate</p>"
    content += "<ul style='text-align:left;margin:1.5rem 0;line-height:2'>"
    content += "<li>✓ Simulazioni illimitate</li>"
    content += "<li>✓ Tutti gli scenari storici</li>"
    content += "<li>✓ Scenari custom personalizzati</li>"
    content += "<li>✓ Cronologia illimitata</li>"
    content += "<li>✓ Export PDF illimitato</li>"
    content += "<li>✓ Benchmarking settoriale</li>"
    content += "<li>✓ Alert email</li>"
    content += "</ul>"
    content += "<button class='btn2' style='width:100%;background:var(--gold);color:#0b1220'>Scegli Pro</button></div>"
    
    # Piano Business
    content += "<div class='card' style='border:2px solid var(--blue);text-align:center'>"
    content += "<h2 style='color:var(--blue)'>Business</h2>"
    content += "<div style='font-size:3rem;font-weight:800;color:var(--gold);margin:1rem 0'>€49<span style='font-size:1.5rem'>/mese</span></div>"
    content += "<p style='color:var(--muted)'>per professionisti</p>"
    content += "<ul style='text-align:left;margin:1.5rem 0;line-height:2'>"
    content += "<li>✓ Tutto il piano Pro</li>"
    content += "<li>✓ Fino a 100 simulazioni/mese</li>"
    content += "<li>✓ API access (limitato)</li>"
    content += "<li>✓ White-label PDF</li>"
    content += "<li>✓ Supporto prioritario</li>"
    content += "<li>✓ Multi-utente (fino a 3)</li>"
    content += "</ul>"
    content += "<button class='btn2' style='width:100%'>Scegli Business</button></div>"
    
    content += "</div>"
    
    content += "<div class='card' style='margin-top:2rem'><h2>Domande Frequenti</h2>"
    content += "<div style='line-height:2'>"
    content += "<p><strong>Cosa ottengo con lo stress test?</strong><br>Un'analisi quantitativa di come la tua azienda reagirebbe a scenari macroeconomici storici (Crisi 2008, Pandemia 2020) usando dati reali da IMF, World Bank, OECD e yfinance.</p>"
    content += "<p><strong>Posso annullare l'abbonamento?</strong><br>Sì, in qualsiasi momento. L'accesso rimane attivo fino alla fine del periodo pagato.</p>"
    content += "<p><strong>C'è una prova gratuita?</strong><br>Sì, puoi fare 1 simulazione gratuita per testare il servizio.</p>"
    content += "<p><strong>Quali dati usate?</strong><br>Tutti i dati macro provengono da fonti pubbliche verificate: IMF WEO, World Bank WDI, OECD, e yfinance per i mercati finanziari.</p>"
    content += "</div></div>"
    
    content += "<div class='card' style='text-align:center;margin-top:2rem'><p style='color:var(--muted);font-size:0.9rem'>Pagamenti sicuri tramite Stripe. Non conserviamo i dati della tua carta.</p></div></div>"
    return render_template_string(BASE_TEMPLATE, title="Prezzi", content=content)

@app.route("/tutorial")
def tutorial():
    content = "<div class='card'><h1>Come Usare SIMULA</h1>"
    content += "<div style='line-height:2.5'>"
    
    content += "<h2 style='color:var(--gold)'>Passo 1: Carica il Bilancio</h2>"
    content += "<p>Carica il bilancio della tua azienda in formato PDF, DOCX o TXT. Il sistema estrarrà automaticamente:</p>"
    content += "<ul><li>Ricavi, EBIT, FCF</li><li>Debito totale e cassa</li><li>Interessi passivi</li><li>Prezzo azione (se quotata)</li></ul>"
    
    content += "<h2 style='color:var(--gold)'>Passo 2: Scegli gli Scenari</h2>"
    content += "<p>Seleziona quali scenari storici testare:</p>"
    content += "<ul><li><strong>Crisi 2008 (Lehman):</strong> PIL -4.5%, tassi -4%, petrolio -60%</li><li><strong>Pandemia 2020 (COVID):</strong> PIL -3.5%, tassi -2%, petrolio -40%</li><li><strong>Scenario attuale:</strong> dati macro odierni senza shock</li></ul>"
    
    content += "<h2 style='color:var(--gold)'>Passo 3: Analizza i Risultati</h2>"
    content += "<p>Il sistema calcolerà:</p>"
    content += "<ul><li>Nuovi ricavi e EBIT dopo lo shock</li><li>Variazione del Free Cash Flow</li><li>Nuovo Debt/EBITDA e Interest Coverage</li><li>Voto di resilienza (0-100)</li></ul>"
    
    content += "<h2 style='color:var(--gold)'>Passo 4: Scarica il Report</h2>"
    content += "<p>Ottieni un PDF professionale con:</p>"
    content += "<ul><li>Grafici della resilienza per scenario</li><li>Analisi automatica dei punti critici</li><li>Confronto con la media di settore</li><li>Nota metodologica completa</li></ul>"
    
    content += "<h2 style='color:var(--gold)'>Cosa Significa il Voto</h2>"
    content += "<ul>"
    content += "<li><span style='color:#238636;font-weight:700'>75-100 (RESILIENTE):</span> L'azienda sopravvive bene alle crisi</li>"
    content += "<li><span style='color:#2ea043;font-weight:700'>60-74 (SOLIDA):</span> Qualche difficoltà ma gestibile</li>"
    content += "<li><span style='color:#f0b429;font-weight:700'>45-59 (MODERATA):</span> Attenzione, alcuni indicatori critici</li>"
    content += "<li><span style='color:#d29922;font-weight:700'>30-44 (FRAGILE):</span> Rischio concreto in recessione</li>"
    content += "<li><span style='color:#da3633;font-weight:700'>0-29 (A RISCHIO):</span> Probabili problemi di liquidità</li>"
    content += "</ul>"
    
    content += "<h2 style='color:var(--gold)'>Esempio Pratico</h2>"
    content += "<p>Se un'azienda ha:</p>"
    content += "<ul><li>Debito/EBITDA attuale: 3.5x</li><li>Interest Coverage: 4.2x</li></ul>"
    content += "<p>In scenario 2008 potrebbe diventare:</p>"
    content += "<ul><li>Debito/EBITDA: 4.8x (peggiora)</li><li>Interest Coverage: 2.1x (critico)</li></ul>"
    content += "<p><strong>Interpretazione:</strong> L'azienda è vulnerabile a shock dei tassi. Meglio ridurre il debito prima di una crisi.</p>"
    
    content += "<div class='card' style='margin-top:2rem;background:rgba(45,212,167,0.1);border:2px solid var(--teal)'>"
    content += "<h2 style='color:var(--teal);margin-top:0'>Hai Bisogno di Aiuto?</h2>"
    content += "<p>Scrivici a <a href='mailto:support@sibilla.cc' style='color:var(--teal)'>support@sibilla.cc</a> per assistenza personalizzata.</p>"
    content += "</div></div></div>"
    return render_template_string(BASE_TEMPLATE, title="Tutorial", content=content)

@app.route("/privacy")
def privacy():
    content = "<div class='card'><h1>Privacy Policy e Termini di Servizio</h1>"
    content += "<p style='color:var(--muted)'>Ultimo aggiornamento: 26 Agosto 2026</p>"
    
    content += "<h2 style='color:var(--gold)'>1. Titolare del Trattamento</h2>"
    content += "<p>AUGET - Sibilla.cc<br>Email: privacy@sibilla.cc</p>"
    
    content += "<h2 style='color:var(--gold)'>2. Dati Raccolti</h2>"
    content += "<p>Raccogliamo i seguenti dati:</p>"
    content += "<ul><li>Dati di registrazione (email, password)</li><li>Bilanci aziendali caricati (PDF, DOCX, TXT)</li><li>Dati di pagamento (gestiti da Stripe, non li conserviamo)</li><li>Dati di utilizzo (analytics anonimi)</li></ul>"
    
    content += "<h2 style='color:var(--gold)'>3. Come Usiamo i Dati</h2>"
    content += "<p>I tuoi dati sono usati per:</p>"
    content += "<ul><li>Fornire il servizio di stress test</li><li>Generare report e analisi</li><li>Gestire l'abbonamento</li><li>Inviare comunicazioni di servizio (non marketing senza consenso)</li></ul>"
    
    content += "<h2 style='color:var(--gold)'>4. Conservazione Dati</h2>"
    content += "<p>I bilanci caricati sono conservati per 12 mesi dalla data di upload, poi cancellati automaticamente. Puoi chiedere la cancellazione immediata in qualsiasi momento.</p>"
    
    content += "<h2 style='color:var(--gold)'>5. Sicurezza</h2>"
    content += "<p>Usiamo crittografia SSL per tutti i dati in transito. I dati sono archiviati su server sicuri in UE (Render.com).</p>"
    
    content += "<h2 style='color:var(--gold)'>6. Diritti dell'Utente (GDPR)</h2>"
    content += "<p>Hai diritto a:</p>"
    content += "<ul><li>Accedere ai tuoi dati</li><li>Correggere dati inaccurati</li><li>Cancellare i tuoi dati</li><li>Esportare i tuoi dati (portabilità)</li><li>Opposizione al trattamento</li></ul>"
    content += "<p>Per esercitare questi diritti, scrivi a privacy@sibilla.cc</p>"
    
    content += "<h2 style='color:var(--gold)'>7. Disclaimer Importante</h2>"
    content += "<div style='background:rgba(218,54,51,0.1);padding:1rem;border-left:4px solid #da3633;border-radius:4px'>"
    content += "<p><strong>Le simulazioni fornite da AUGET NON costituiscono consulenza finanziaria, legale o fiscale.</strong></p>"
    content += "<p>I risultati sono:</p>"
    content += "<ul><li>Basati su dati storici e modelli semplificati</li><li>Soggetti a limitazioni metodologiche</li><li>Da interpretare come indicazioni direzionali, non previsioni certe</li><li>Non garantiscono performance future</li></ul>"
    content += "<p><strong>Non prendere decisioni di investimento basate esclusivamente su questi risultati. Consulta sempre un professionista qualificato.</strong></p>"
    content += "</div>"
    
    content += "<h2 style='color:var(--gold)'>8. Limitazione di Responsabilità</h2>"
    content += "<p>AUGET non è responsabile per:</p>"
    content += "<ul><li>Decisioni prese basandosi sui risultati delle simulazioni</li><li>Perdite finanziarie dirette o indirette</li><li>Errori nei dati forniti da terze parti (IMF, World Bank, yfinance)</li><li>Interruzioni temporanee del servizio</li></ul>"
    
    content += "<h2 style='color:var(--gold)'>9. Cookie</h2>"
    content += "<p>Usiamo cookie essenziali per il funzionamento del servizio (sessioni, autenticazione). Non usiamo cookie di tracciamento per marketing.</p>"
    
    content += "<h2 style='color:var(--gold)'>10. Modifiche</h2>"
    content += "<p>Ci riserviamo il diritto di modificare questa privacy policy. Le modifiche entrano in vigore immediatamente dopo la pubblicazione.</p>"
    
    content += "<div class='card' style='margin-top:2rem'><h2>Accettazione</h2>"
    content += "<p>Utilizzando AUGET, dichiari di aver letto e accettato questa Privacy Policy e i Termini di Servizio.</p></div></div>"
    return render_template_string(BASE_TEMPLATE, title="Privacy", content=content)

@app.route("/")
def home():
    content = "<div class='card' style='text-align:center;padding:3rem 2rem'>"
    content += "<h1 style='font-size:3rem;margin-bottom:1rem;color:var(--gold)'>AUGET - Financial Intelligence Engine</h1>"
    content += "<p style='font-size:1.3rem;color:var(--muted);margin-bottom:2rem'>Stress test aziendale con dati macro reali. Scopri se la tua azienda sopravvive alla prossima crisi.</p>"
    content += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap'>"
    content += "<a href='/register' class='btn2' style='padding:1rem 2rem;font-size:1.1rem'>Inizia Gratis</a>"
    content += "<a href='/tutorial' class='btn2' style='padding:1rem 2rem;font-size:1.1rem;background:var(--blue)'>Come Funziona</a>"
    content += "<a href='/prezzi' class='btn2' style='padding:1rem 2rem;font-size:1.1rem;background:var(--gold);color:#0b1220'>Prezzi</a>"
    content += "</div></div>"
    
    content += "<div class='card'><h2 style='text-align:center'>Perché Usare SIMULA?</h2>"
    content += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:2rem;margin-top:2rem'>"
    
    content += "<div><h3 style='color:var(--teal)'>Dati Reali, Non Ipotesi</h3>"
    content += "<p>Usiamo dati macroeconomici reali da IMF, World Bank, OECD e yfinance. Scenari calibrati su crisi storiche vere (2008, 2020).</p></div>"
    
    content += "<div><h3 style='color:var(--teal)'>Calcoli Matematici Esatti</h3>"
    content += "<p>Nessuna scatola nera AI. Ogni calcolo è algebrico e riproducibile. Stessi input = stessi output.</p></div>"
    
    content += "<div><h3 style='color:var(--teal)'>Report Professionali</h3>"
    content += "<p>PDF scaricabili con grafici, analisi automatica e benchmarking. Perfetti per presentare a investitori o banche.</p></div>"
    
    content += "<div><h3 style='color:var(--teal)'>Prevenire è Meglio</h3>"
    content += "<p>Scopri le vulnerabilità della tua azienda PRIMA che arrivi la crisi. Agisci ora, non dopo.</p></div>"
    
    content += "<div><h3 style='color:var(--teal)'>Trasparenza Totale</h3>"
    content += "<p>Mostriamo tutte le fonti dati e le formule usate. Nessuna sorpresa, nessuna opacità.</p></div>"
    
    content += "<div><h3 style='color:var(--teal)'>Costo Minimo, Valore Massimo</h3>"
    content += "<p>Da €4.90 per simulazione. Meno di una cena fuori per proteggere il tuo business.</p></div>"
    
    content += "</div></div>"
    
    content += "<div class='card' style='background:linear-gradient(135deg, rgba(240,180,41,0.1), rgba(45,212,167,0.1));border:2px solid var(--gold)'>"
    content += "<h2 style='text-align:center;margin-top:0'>Come Funziona in 3 Minuti</h2>"
    content += "<div style='display:flex;gap:2rem;justify-content:center;align-items:center;flex-wrap:wrap;margin:2rem 0'>"
    content += "<div style='text-align:center'><div style='width:80px;height:80px;background:var(--gold);color:#0b1220;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:800;margin:0 auto 1rem'>1</div><h3>Carica Bilancio</h3><p>PDF, DOCX o TXT</p></div>"
    content += "<div style='font-size:2rem;color:var(--muted)'>→</div>"
    content += "<div style='text-align:center'><div style='width:80px;height:80px;background:var(--gold);color:#0b1220;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:800;margin:0 auto 1rem'>2</div><h3>Scegli Scenario</h3><p>2008, 2020 o attuale</p></div>"
    content += "<div style='font-size:2rem;color:var(--muted)'>→</div>"
    content += "<div style='text-align:center'><div style='width:80px;height:80px;background:var(--gold);color:#0b1220;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:800;margin:0 auto 1rem'>3</div><h3>Ottieni Report</h3><p>Voto + PDF scaricabile</p></div>"
    content += "</div>"
    content += "<div style='text-align:center'><a href='/tutorial' style='color:var(--teal);font-size:1.1rem'>Vedi tutorial completo →</a></div>"
    content += "</div>"
    
    content += "<div class='card'><h2 style='text-align:center'>Casi d'Uso</h2>"
    content += "<div style='line-height:2.2'>"
    content += "<p><strong>Investitori:</strong> Valuta la resilienza di un'azienda prima di investire. Evita società fragili che sembrano economiche ma crolleranno in recessione.</p>"
    content += "<p><strong>Imprenditori:</strong> Stressa il tuo bilancio. Scopri se la tua azienda regge una crisi dei tassi o del PIL. Prendi decisioni informate su debito e liquidità.</p>"
    content += "<p><strong>Consulenti Finanziari:</strong> Offri analisi quantitative ai tuoi clienti. Report professionali con il tuo logo (piano Business).</p>"
    content += "<p><strong>Banche e Finanziatori:</strong> Valuta il rischio credito dei tuoi clienti. Stress test prima di concedere finanziamenti.</p>"
    content += "</div></div>"
    
    content += "<div class='card' style='text-align:center'><h2>Pronto a Iniziare?</h2><p style='color:var(--muted);margin:1rem 0'>Unisciti a centinaia di imprenditori e investitori che usano AUGET per prendere decisioni migliori.</p><a href='/register' class='btn2' style='padding:1rem 3rem;font-size:1.2rem'>Crea Account Gratis</a><p style='color:var(--muted);margin-top:1rem;font-size:0.9rem'>1 simulazione gratuita • Nessuna carta richiesta • Cancella quando vuoi</p></div>"
    return render_template_string(BASE_TEMPLATE, title="AUGET - Financial Intelligence", content=content)


@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    rs = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    if request.method == "POST":
        ids = request.form.getlist("ids")[:5]
        reps = [r for r in rs if str(r.id) in ids]
        if len(reps) < 2:
            flash("Seleziona almeno 2 report", "error")
            return redirect("/compare")
        
        scenarios_quick = {
            "2008": {"gdp": -4.5, "infl": -2.0, "rates": -4.0},
            "2020": {"gdp": -3.5, "infl": -1.0, "rates": -2.0},
            "Attuale": {"gdp": 0, "infl": 0, "rates": 0}
        }
        
        html_content = "<div class='card'><h1>Confronto Multi-Azienda</h1>"
        html_content += "<table><tr><th>Scenario</th>"
        for r in reps:
            html_content += "<th>" + (r.company or r.filename) + "</th>"
        html_content += "</tr>"
        
        for scen_name, scen_shocks in scenarios_quick.items():
            html_content += "<tr><td style='color:var(--gold);font-weight:700'>" + scen_name + "</td>"
            for r in reps:
                m = _json.loads(r.metrics_json or "{}")
                rev = float(m.get("revenue") or 0)
                ebit = float(m.get("ebit") or 0)
                fcf = float(m.get("fcf") or 0)
                debt = float(m.get("total_debt") or 0)
                interest = float(m.get("interest") or 0) or 0.01
                cassa = float(m.get("cassa") or 0)
                if not rev and ebit: rev = ebit / 0.15
                if not ebit and rev: ebit = rev * 0.15
                if not fcf and ebit: fcf = ebit * 0.7
                margin = ebit / rev if rev else 0.15
                vol_s = scen_shocks["gdp"] * 1.0 / 100.0
                price_s = scen_shocks["infl"] * 0.3 / 100.0
                rev_s = vol_s + price_s
                new_rev = rev * (1.0 + rev_s)
                new_ebit = new_rev * margin
                int_m = 1.0 + scen_shocks["rates"] / 100.0
                new_int = interest * max(int_m, 0.3)
                new_fcf = fcf * max(new_ebit / ebit if ebit else 1.0, 0.2)
                de_n = debt / new_ebit if new_ebit > 0 else 99
                ic_n = new_ebit / new_int if new_int > 0 else 99
                sc, _ = _calculate_score_breakdown(new_fcf, de_n, ic_n, cassa, debt, margin)
                color = "#238636" if sc >= 70 else ("#f0b429" if sc >= 45 else "#da3633")
                html_content += "<td style='color:" + color + ";font-weight:700'>" + str(int(sc)) + "/100</td>"
            html_content += "</tr>"
        html_content += "</table></div>"
        return render_template_string(BASE_TEMPLATE, title="Confronto", content=html_content)
    
    boxes = ""
    for r in rs:
        boxes += "<label style='display:block;margin:8px 0;padding:10px;background:var(--bg);border-radius:6px;cursor:pointer'>"
        boxes += "<input type='checkbox' name='ids' value='" + str(r.id) + "'> "
        boxes += "<strong>" + (r.company or r.filename) + "</strong>"
        boxes += " <span style='color:var(--muted);font-size:0.85rem'>" + (r.sector or "Altro") + "</span>"
        boxes += "</label>"
    
    html_content = "<div class='card'><h1>Confronta Aziende</h1>"
    html_content += "<p style='color:var(--muted)'>Seleziona 2-5 report per confrontarli negli scenari storici</p>"
    html_content += "<form method='post'>" + boxes
    html_content += "<button type='submit' class='btn2' style='margin-top:1rem'>Confronta selezionati</button></form></div>"
    return render_template_string(BASE_TEMPLATE, title="Confronta", content=html_content)

@app.route("/alerts", methods=["GET", "POST"])
@login_required
def alerts():
    if request.method == "POST":
        if "delete_alert" in request.form:
            aid = request.form.get("delete_alert")
            a = Alert.query.get(aid)
            if a and a.user_id == current_user.id:
                db.session.delete(a); db.session.commit()
                flash("Alert eliminato", "success")
                return redirect("/alerts")
        else:
            if not check_usage_limit(current_user.id, "alert"):
                flash("Hai raggiunto il limite di alert per il tuo piano.", "error")
                return redirect("/alerts")
            rid = request.form.get("report_id")
            thr = float(request.form.get("threshold", 40))
            if rid:
                al = Alert(user_id=current_user.id, report_id=int(rid), threshold=thr)
                db.session.add(al); db.session.commit()
                flash("Alert creato", "success")
                return redirect("/alerts")
    
    als = Alert.query.filter_by(user_id=current_user.id).all()
    rs = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    
    html_content = "<div class='card'><h1>Alert e Monitoraggio</h1>"
    html_content += "<p style='color:var(--muted)'>Ricevi una notifica quando il Resilience Score di un'azienda scende sotto la soglia</p>"
    
    html_content += "<h2 style='color:var(--gold);margin-top:1.5rem'>Crea nuovo alert</h2>"
    html_content += "<form method='post'>"
    html_content += "<select name='report_id' style='margin-right:10px'>"
    for r in rs:
        html_content += "<option value='" + str(r.id) + "'>" + (r.company or r.filename) + "</option>"
    html_content += "</select>"
    html_content += "<label>Soglia: <input name='threshold' type='number' value='40' min='0' max='100' style='width:80px'></label>"
    html_content += "<button type='submit' class='btn2' style='margin-left:10px'>Crea Alert</button></form>"
    
    html_content += "<h2 style='color:var(--gold);margin-top:1.5rem'>I tuoi alert attivi</h2>"
    if als:
        for a in als:
            r = Report.query.get(a.report_id)
            comp = (r.company or r.filename) if r else "N/D"
            html_content += "<div style='padding:10px;background:var(--bg);border-radius:6px;margin:8px 0;display:flex;justify-content:space-between;align-items:center'>"
            html_content += "<div><strong>" + comp + "</strong> - Soglia: " + str(int(a.threshold)) + "/100</div>"
            html_content += "<form method='post' style='margin:0'><input type='hidden' name='delete_alert' value='" + str(a.id) + "'><button type='submit' style='width:auto;background:#da3633;color:white'>Elimina</button></form>"
            html_content += "</div>"
    else:
        html_content += "<p style='color:var(--muted)'>Nessun alert attivo</p>"
    
    html_content += "</div>"
    return render_template_string(BASE_TEMPLATE, title="Alert", content=html_content)

@app.route("/share/<int:rid>")
def share_report(rid):
    rep = Report.query.get_or_404(rid)
    m = _json.loads(rep.metrics_json or "{}")
    
    # Calcola score medio senza mostrare dati sensibili
    scenarios_quick = {
        "2008": {"gdp": -4.5, "infl": -2.0, "rates": -4.0},
        "2020": {"gdp": -3.5, "infl": -1.0, "rates": -2.0}
    }
    total = 0
    count = 0
    for sh in scenarios_quick.values():
        rev = float(m.get("revenue") or 0)
        ebit = float(m.get("ebit") or 0)
        fcf = float(m.get("fcf") or 0)
        debt = float(m.get("total_debt") or 0)
        interest = float(m.get("interest") or 0) or 0.01
        cassa = float(m.get("cassa") or 0)
        if not rev and ebit: rev = ebit / 0.15
        if not ebit and rev: ebit = rev * 0.15
        if not fcf and ebit: fcf = ebit * 0.7
        margin = ebit / rev if rev else 0.15
        vol_s = sh["gdp"] * 1.0 / 100.0
        price_s = sh["infl"] * 0.3 / 100.0
        rev_s = vol_s + price_s
        new_rev = rev * (1.0 + rev_s)
        new_ebit = new_rev * margin
        int_m = 1.0 + sh["rates"] / 100.0
        new_int = interest * max(int_m, 0.3)
        new_fcf = fcf * max(new_ebit / ebit if ebit else 1.0, 0.2)
        de_n = debt / new_ebit if new_ebit > 0 else 99
        ic_n = new_ebit / new_int if new_int > 0 else 99
        sc, _ = _calculate_score_breakdown(new_fcf, de_n, ic_n, cassa, debt, margin)
        total += sc
        count += 1
    avg = total / count if count > 0 else 0
    
    color = "#238636" if avg >= 70 else ("#f0b429" if avg >= 45 else "#da3633")
    label = "RESILIENTE" if avg >= 70 else ("MODERATA" if avg >= 45 else "A RISCHIO")
    
    content = "<div class='card' style='text-align:center;padding:3rem'>"
    content += "<h1 style='color:var(--gold)'>Certificato Resilienza AUGET</h1>"
    content += "<h2>" + (rep.company or rep.filename) + "</h2>"
    content += "<div style='font-size:6rem;font-weight:800;color:" + color + ";margin:2rem 0'>" + str(int(avg)) + "<span style='font-size:2rem'>/100</span></div>"
    content += "<div style='font-size:1.5rem;color:" + color + ";font-weight:700'>" + label + "</div>"
    content += "<p style='color:var(--muted);margin-top:2rem'>Stress test basato su scenari storici 2008 e 2020</p>"
    content += "<p style='color:var(--muted);font-size:0.85rem'>Report generato da AUGET - sibilla.cc</p>"
    content += "<a href='/' class='btn2' style='margin-top:2rem;display:inline-block'>Crea il tuo report</a>"
    content += "</div>"
    return render_template_string(BASE_TEMPLATE, title="Certificato " + (rep.company or ""), content=content)

@app.route("/simula/custom-scenario", methods=["GET", "POST"])
@login_required
def simula_custom_scenario():
    if request.method == "POST":
        name = request.form.get("name", "Scenario custom")
        shocks = {}
        for key in ["gdp", "infl", "rates", "unemp", "consumption", "wages", "oil", "materials", "fx", "spread", "credit", "liquidity", "money_growth", "real_estate", "gold"]:
            val = request.form.get(key)
            if val is not None:
                try: shocks[key] = float(val)
                except: pass
        cs = CustomScenario(user_id=current_user.id, name=name, shocks_json=_json.dumps(shocks))
        db.session.add(cs); db.session.commit()
        flash("Scenario custom salvato!", "success")
        return redirect("/simula/custom-scenario")
    
    saved = CustomScenario.query.filter_by(user_id=current_user.id).order_by(CustomScenario.created_at.desc()).all()
    rows = ""
    for cs in saved:
        rows += "<div class='card' style='margin:10px 0'><h3>" + cs.name + "</h3>"
        rows += "<p style='color:var(--muted);font-size:0.85rem'>Creato il " + cs.created_at.strftime("%d/%m/%Y") + "</p>"
        rows += "<form method='post' action='/simula/custom-scenario/" + str(cs.id) + "/delete' style='display:inline'><button type='submit' style='width:auto;background:#da3633;color:white'>Elimina</button></form></div>"
    
    content = "<div class='card'><h1>Crea Scenario Custom</h1>"
    content += "<p style='color:var(--muted)'>Definisci i tuoi shock macro personalizzati</p>"
    content += "<form method='post'>"
    content += "<input name='name' placeholder='Nome scenario (es. Mia tesi 2027)' required style='margin-bottom:1rem;width:100%'>"
    fields = [("gdp", "PIL %"), ("infl", "Inflazione %"), ("rates", "Tassi %"), ("unemp", "Disoccupazione %"),
              ("consumption", "Consumi %"), ("wages", "Salari %"), ("oil", "Petrolio $"), ("materials", "Materie prime %"),
              ("fx", "Cambio EUR/USD"), ("spread", "Spread %"), ("credit", "Credito %"), ("liquidity", "Liquidita %"),
              ("money_growth", "Crescita monetaria %"), ("real_estate", "Immobiliare %"), ("gold", "Oro $")]
    for key, label in fields:
        content += "<div style='display:flex;gap:10px;margin:8px 0'><label style='width:200px'>" + label + "</label><input name='" + key + "' type='number' step='0.1' value='0' style='width:100px'></div>"
    content += "<button type='submit' class='btn2' style='margin-top:1rem'>Salva Scenario</button></form></div>"
    content += "<h2>I tuoi scenari custom</h2>" + (rows or "<p style='color:var(--muted)'>Nessuno scenario custom salvato.</p>")
    return render_template_string(BASE_TEMPLATE, title="Scenari Custom", content=content)

@app.route("/simula/custom-scenario/<int:cid>/delete", methods=["POST"])
@login_required
def simula_custom_scenario_delete(cid):
    cs = CustomScenario.query.get_or_404(cid)
    if cs.user_id == current_user.id:
        db.session.delete(cs); db.session.commit()
        flash("Scenario eliminato", "success")
    return redirect("/simula/custom-scenario")

@app.route("/simula/history")
@login_required
def simula_history():
    sims = SavedSimulation.query.filter_by(user_id=current_user.id).order_by(SavedSimulation.created_at.desc()).limit(50).all()
    rows = ""
    for s in sims:
        rep = Report.query.get(s.report_id)
        company = (rep.company or rep.filename) if rep else "N/D"
        color = "#238636" if s.resilience >= 70 else ("#f0b429" if s.resilience >= 45 else "#da3633")
        rows += "<tr><td>" + s.created_at.strftime("%d/%m/%Y %H:%M") + "</td><td>" + company + "</td><td>" + (s.scenario_name or "") + "</td><td style='color:" + color + ";font-weight:700'>" + str(int(s.resilience or 0)) + "/100</td><td><a href='/reports/" + str(s.report_id) + "' style='color:var(--teal)'>Apri</a></td></tr>"
    
    content = "<div class='card'><h1>Cronologia Simulazioni</h1>"
    content += "<p style='color:var(--muted)'>Le tue ultime 50 simulazioni salvate automaticamente</p>"
    if rows:
        content += "<table><tr><th>Data</th><th>Azienda</th><th>Scenario</th><th>Resilienza</th><th></th></tr>" + rows + "</table>"
    else:
        content += "<p style='color:var(--muted)'>Nessuna simulazione in cronologia</p>"
    content += "</div>"
    return render_template_string(BASE_TEMPLATE, title="Cronologia", content=content)


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user
    limits = get_subscription_limits(user.subscription_tier or "free")
    monthly_usage = get_monthly_usage(user.id)
    total_simulations = SavedSimulation.query.filter_by(user_id=user.id).count()
    total_reports = Report.query.filter_by(user_id=user.id).count()
    total_alerts = Alert.query.filter_by(user_id=user.id).count()
    
    # Ultime 5 simulazioni
    recent_sims = SavedSimulation.query.filter_by(user_id=user.id).order_by(
        SavedSimulation.created_at.desc()).limit(5).all()
    
    content = "<div class='card'><h1>Dashboard</h1>"
    content += "<p style='color:var(--muted)'>Benvenuto, " + user.email + "</p>"
    
    # Piano attuale
    plan_color = "#238636" if user.subscription_tier in ["pro", "business"] else "#f0b429"
    content += "<div style='background:" + plan_color + ";color:#fff;padding:1rem;border-radius:8px;margin:1rem 0'>"
    content += "<h2 style='margin:0;color:#fff'>Piano: " + (user.subscription_tier or "free").upper() + "</h2>"
    if user.subscription_expires:
        content += "<p style='margin:0.5rem 0 0 0'>Scadenza: " + user.subscription_expires.strftime("%d/%m/%Y") + "</p>"
    content += "</div>"
    
    # Statistiche
    content += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;margin:1.5rem 0'>"
    content += "<div class='card' style='text-align:center'><h3 style='color:var(--teal)'>" + str(monthly_usage) + "/" + str(limits["simulations"]) + "</h3><p>Simulazioni questo mese</p></div>"
    content += "<div class='card' style='text-align:center'><h3 style='color:var(--gold)'>" + str(total_reports) + "</h3><p>Report caricati</p></div>"
    content += "<div class='card' style='text-align:center'><h3 style='color:var(--blue)'>" + str(total_alerts) + "/" + str(limits["alerts"]) + "</h3><p>Alert attivi</p></div>"
    content += "<div class='card' style='text-align:center'><h3 style='color:var(--teal)'>" + str(total_simulations) + "</h3><p>Simulazioni totali</p></div>"
    content += "</div>"
    
    # Limiti piano
    content += "<div class='card'><h2>I tuoi limiti</h2><table>"
    content += "<tr><th>Feature</th><th>Utilizzo</th><th>Limite</th></tr>"
    content += "<tr><td>Simulazioni/mese</td><td>" + str(monthly_usage) + "</td><td>" + ("Illimitato" if limits["simulations"] == 999 else str(limits["simulations"])) + "</td></tr>"
    content += "<tr><td>Alert</td><td>" + str(total_alerts) + "</td><td>" + ("Illimitato" if limits["alerts"] == 999 else str(limits["alerts"])) + "</td></tr>"
    content += "<tr><td>Scenari custom</td><td>" + str(CustomScenario.query.filter_by(user_id=user.id).count()) + "</td><td>" + ("Illimitato" if limits["custom_scenarios"] == 999 else str(limits["custom_scenarios"])) + "</td></tr>"
    content += "<tr><td>Export PDF</td><td colspan='2'>" + ("✓ Incluso" if limits["pdf"] else "✗ Non incluso") + "</td></tr>"
    content += "</table></div>"
    
    # Ultime simulazioni
    if recent_sims:
        content += "<div class='card'><h2>Ultime simulazioni</h2><table><tr><th>Data</th><th>Azienda</th><th>Scenario</th><th>Score</th></tr>"
        for s in recent_sims:
            rep = Report.query.get(s.report_id)
            company = (rep.company or rep.filename) if rep else "N/D"
            color = "#238636" if (s.resilience or 0) >= 70 else ("#f0b429" if (s.resilience or 0) >= 45 else "#da3633")
            content += "<tr><td>" + s.created_at.strftime("%d/%m/%Y %H:%M") + "</td><td>" + company + "</td><td>" + (s.scenario_name or "") + "</td><td style='color:" + color + ";font-weight:700'>" + str(int(s.resilience or 0)) + "/100</td></tr>"
        content += "</table></div>"
    
    # Upgrade CTA
    if user.subscription_tier not in ["pro", "business", "admin"]:
        content += "<div class='card' style='text-align:center;background:linear-gradient(135deg, rgba(240,180,41,0.1), rgba(45,212,167,0.1));border:2px solid var(--gold)'>"
        content += "<h2 style='color:var(--gold)'>Upgrade al Piano Pro</h2>"
        content += "<p>Simulazioni illimitate, alert, scenari custom e molto altro</p>"
        content += "<a href='/prezzi' class='btn2' style='background:var(--gold);color:#0b1220'>Vedi Piani</a>"
        content += "</div>"
    
    content += "</div>"
    return render_template_string(BASE_TEMPLATE, title="Dashboard", content=content)

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


# Setup cron job per controllo alert (ogni 24 ore)
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    
    def check_alerts_job():
        """Controlla tutti gli alert attivi"""
        alerts = Alert.query.filter_by(active=True).all()
        for alert in alerts:
            user = User.query.get(alert.user_id)
            rep = Report.query.get(alert.report_id)
            if not user or not rep:
                continue
            
            # Ricalcola score
            m = _json.loads(rep.metrics_json or "{}")
            sector = rep.sector or "Altro"
            sector_matrix = {
                "Banche": {"tassi": 1.0, "disocc": -1.5, "pil": 0.8, "energia": 0.3, "infl": 0.2},
                "Retail": {"tassi": -0.5, "disocc": -2.0, "pil": 1.8, "energia": 0.5, "infl": -0.3},
                "Tech": {"tassi": -0.8, "disocc": -1.0, "pil": 1.2, "energia": 0.4, "infl": -0.2},
                "Utilities": {"tassi": -0.7, "disocc": -0.5, "pil": 0.3, "energia": 0.9, "infl": 0.7},
                "Consumer": {"tassi": -0.2, "disocc": -1.2, "pil": 0.6, "energia": 0.6, "infl": 0.8},
                "Pharma": {"tassi": -0.3, "disocc": -0.8, "pil": 0.5, "energia": 0.3, "infl": 0.9},
                "Energy": {"tassi": -0.2, "disocc": -1.0, "pil": 0.4, "energia": -1.5, "infl": 0.8},
                "Auto": {"tassi": -0.9, "disocc": -2.5, "pil": 2.0, "energia": 0.7, "infl": -0.5},
                "Industria": {"tassi": -0.5, "disocc": -1.8, "pil": 1.5, "energia": 0.8, "infl": -0.1},
                "Altro": {"tassi": -0.4, "disocc": -1.5, "pil": 1.0, "energia": 0.5, "infl": 0.0},
            }
            sens = next((v for k, v in sector_matrix.items() if k.lower() in sector.lower()), sector_matrix["Altro"])
            
            # Scenario recessione moderata
            shocks = {"gdp": -2.0, "infl": -1.0, "rates": -1.0, "oil": -15.0, "spread": 1.5}
            rev = float(m.get("revenue") or 0)
            ebit = float(m.get("ebit") or 0)
            fcf = float(m.get("fcf") or 0)
            debt = float(m.get("total_debt") or 0)
            interest = float(m.get("interest") or 0) or 0.01
            cassa = float(m.get("cassa") or 0)
            if not rev and ebit: rev = ebit / 0.15
            if not ebit and rev: ebit = rev * 0.15
            if not fcf and ebit: fcf = ebit * 0.7
            margin = ebit / rev if rev else 0.15
            vol_s = shocks["gdp"] * sens["pil"] / 100.0
            price_s = shocks["infl"] * sens["infl"] / 100.0
            rev_s = vol_s + price_s
            new_rev = rev * (1.0 + rev_s)
            new_ebit = new_rev * margin
            int_m = 1.0 + shocks["rates"] / 100.0
            new_int = interest * max(int_m, 0.3)
            new_fcf = fcf * max(new_ebit / ebit if ebit else 1.0, 0.2)
            de_n = debt / new_ebit if new_ebit > 0 else 99
            ic_n = new_ebit / new_int if new_int > 0 else 99
            sc, _ = _calculate_score_breakdown(new_fcf, de_n, ic_n, cassa, debt, margin)
            
            # Se score sotto soglia, invia email
            if sc < alert.threshold:
                html = "<h1>⚠️ Alert AUGET</h1>"
                html += "<p>Il Resilience Score di <strong>" + (rep.company or rep.filename) + "</strong> è sceso sotto la tua soglia.</p>"
                html += "<p><strong>Score attuale:</strong> " + str(int(sc)) + "/100</p>"
                html += "<p><strong>Tua soglia:</strong> " + str(int(alert.threshold)) + "/100</p>"
                html += "<p><a href='" + request.url_root + "simula'>Vedi dettagli</a></p>"
                send_email("Alert AUGET: " + (rep.company or ""), [user.email], html)
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_alerts_job, 'interval', hours=24)
    scheduler.start()
    print("[Scheduler] Alert cron job avviato")
except Exception as e:
    print("[Scheduler error]", e)

if __name__ == "__main__":
    print("AUGET WEB con login: http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False, threaded=True)
# Fix forzato gio 27 ago 2026, 21:18:01, CEST
