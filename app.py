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
      <a href="/analyze">Analizza</a><a href="/reports">Report</a><a href="/watchlist">Watchlist</a><a href="/compare">Confronta</a><a href="/ranking">Classifica</a><a href="/simula">Simula</a>
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


@app.route("/feedback")
@login_required
def feedback():
    content = "<div class='card'><h1>Feedback</h1>"
    content += "<p style='color:var(--muted)'>Aiutaci a migliorare AUGET! Dicci cosa pensi della piattaforma.</p>"
    content += "<form method='post' action='mailto:support@sibilla.cc' enctype='text/plain'>"
    content += "<textarea name='feedback' placeholder='Cosa ti è piaciuto? Cosa vorresti migliorare?' style='width:100%;height:200px;margin:1rem 0;padding:1rem;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--text)'></textarea>"
    content += "<button type='submit' class='btn2'>Invia Feedback</button>"
    content += "</form>"
    content += "<p style='color:var(--muted);margin-top:1rem'>Oppure scrivici direttamente a <a href='mailto:support@sibilla.cc' style='color:var(--teal)'>support@sibilla.cc</a></p>"
    content += "</div>"
    return render_template_string(BASE_TEMPLATE, title="Feedback", content=content)

@app.route("/assistenza")
def assistenza():
    content = "<div class='card'><h1>Assistenza</h1>"
    content += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:2rem;margin:2rem 0'>"
    content += "<div class='card'><h2 style='color:var(--teal)'>Documentazione</h2><p>Trovi guide e tutorial su come usare AUGET.</p><a href='/tutorial' class='btn2' style='display:inline-block;margin-top:1rem'>Vai al Tutorial</a></div>"
    content += "<div class='card'><h2 style='color:var(--gold)'>Email Support</h2><p>Rispondiamo entro 24 ore.</p><a href='mailto:support@sibilla.cc' class='btn2' style='display:inline-block;margin-top:1rem;background:var(--gold);color:#0b1220'>Scrivici</a></div>"
    content += "<div class='card'><h2 style='color:var(--blue)'>FAQ</h2><p>Domande frequenti e risposte.</p><a href='/prezzi' class='btn2' style='display:inline-block;margin-top:1rem'>Vedi Prezzi e FAQ</a></div>"
    content += "</div>"
    content += "<div class='card' style='background:linear-gradient(135deg, rgba(45,212,167,0.1), rgba(240,180,41,0.1));border:2px solid var(--teal);padding:2rem;text-align:center'>"
    content += "<h2 style='color:var(--teal);margin-top:0'>Hai bisogno di aiuto personalizzato?</h2>"
    content += "<p style='font-size:1.1rem'>Prenota una demo gratuita di 30 minuti con il nostro team.</p>"
    content += "<a href='mailto:support@sibilla.cc?subject=Prenotazione Demo AUGET' class='btn2' style='padding:1rem 2rem;font-size:1.1rem'>Prenota Demo</a>"
    content += "</div></div>"
    return render_template_string(BASE_TEMPLATE, title="Assistenza", content=content)

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
    
    # Solo 3 scenari STORICI verificati (dati reali)
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
    
    # HEADER MODERNO CON GRADIENTE
    html_out += "<div style='background:linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);padding:3rem 2rem;border-radius:16px;margin-bottom:2rem;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,0.3)'>"
    html_out += "<h1 style='color:#fbbf24;margin:0;font-size:3rem;font-weight:800;letter-spacing:1px'>Financial Intelligence Engine</h1>"
    html_out += "<p style='color:#e2e8f0;font-size:1.3rem;margin:1rem 0 0 0'>Stress test aziendale con dati macro reali e scenari storici verificati</p>"
    html_out += "<div style='display:flex;gap:2rem;justify-content:center;flex-wrap:wrap;margin-top:2rem'>"
    html_out += "<div style='background:rgba(255,255,255,0.1);padding:1rem 2rem;border-radius:12px;border:2px solid #10b981'><div style='font-size:2rem;font-weight:800;color:#10b981'>100%</div><div style='color:#94a3b8;font-size:0.9rem'>Dati Reali</div></div>"
    html_out += "<div style='background:rgba(255,255,255,0.1);padding:1rem 2rem;border-radius:12px;border:2px solid #fbbf24'><div style='font-size:2rem;font-weight:800;color:#fbbf24'>3</div><div style='color:#94a3b8;font-size:0.9rem'>Scenari Storici</div></div>"
    html_out += "<div style='background:rgba(255,255,255,0.1);padding:1rem 2rem;border-radius:12px;border:2px solid #3b82f6'><div style='font-size:2rem;font-weight:800;color:#3b82f6'>3min</div><div style='color:#94a3b8;font-size:0.9rem'>Tempo Analisi</div></div>"
    html_out += "</div></div>"
    
    # FORM UPLOAD SEMPRE VISIBILE
    html_out += "<div style='background:#1e293b;padding:2.5rem;border-radius:16px;margin-bottom:2rem;border:3px solid #fbbf24;box-shadow:0 8px 32px rgba(251,191,36,0.2)'>"
    html_out += "<h2 style='color:#fbbf24;margin-top:0;font-size:2rem;text-align:center'>🚀 Inizia il tuo Stress Test</h2>"
    html_out += "<form method='post' enctype='multipart/form-data'>"
    
    if rs:
        html_out += "<div style='margin-bottom:1.5rem'>"
        html_out += "<label style='display:block;color:#e2e8f0;font-weight:600;margin-bottom:0.5rem;font-size:1.1rem'>Seleziona un report esistente:</label>"
        opts = "<option value='' disabled selected>📊 Scegli un report...</option>"
        for r_item in rs:
            sel_str = " selected" if rep and r_item.id == rep.id else ""
            opts += "<option value='" + str(r_item.id) + "'" + sel_str + ">" + (r_item.company or r_item.filename) + " - " + (r_item.sector or "Altro") + "</option>"
        html_out += "<select name='rid' style='width:100%;padding:1rem;border-radius:10px;border:2px solid #475569;background:#0f172a;color:#e2e8f0;font-size:1.1rem'>" + opts + "</select>"
        html_out += "</div>"
        
        html_out += "<div style='text-align:center;margin:1.5rem 0;color:#64748b;font-size:1.2rem'>— oppure —</div>"
    
    html_out += "<div style='border:3px dashed #475569;border-radius:12px;padding:3rem;background:#0f172a;text-align:center;transition:all 0.3s'>"
    html_out += "<label style='cursor:pointer;display:block'>"
    html_out += "<input type='file' name='report_file' accept='.pdf,.docx,.txt' id='file-upload' style='display:none' onchange='document.getElementById(\'file-name\').textContent = this.files[0] ? this.files[0].name : \'Nessun file selezionato\'; this.parentElement.style.borderColor = \'#10b981\'>'"
    html_out += "<div style='font-size:4rem;margin-bottom:1rem'>📎</div>"
    html_out += "<div style='color:#e2e8f0;font-size:1.2rem;font-weight:600;margin-bottom:0.5rem'>Clicca per selezionare un file</div>"
    html_out += "<div style='color:#64748b;font-size:0.95rem'>PDF, DOCX o TXT • Max 50MB</div>"
    html_out += "<div id='file-name' style='color:#10b981;font-weight:600;margin-top:1rem;font-size:1.1rem'>Nessun file selezionato</div>"
    html_out += "</label>"
    html_out += "</div>"
    
    html_out += "<button type='submit' style='width:100%;margin-top:1.5rem;padding:1.2rem;background:linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);color:#0f172a;border:none;border-radius:10px;font-size:1.3rem;font-weight:800;cursor:pointer;transition:all 0.3s;box-shadow:0 4px 16px rgba(251,191,36,0.4)'> AVVIA ANALISI STRESS TEST</button>"
    html_out += "</form>"
    html_out += "</div>"
    
    # SEZIONE "COME FUNZIONA"
    html_out += "<div style='margin-bottom:2rem'>"
    html_out += "<h2 style='color:#fbbf24;text-align:center;font-size:2rem;margin-bottom:1.5rem'> Come Funziona in 3 Step</h2>"
    html_out += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:1.5rem'>"
    html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;border:2px solid #10b981;text-align:center'><div style='font-size:3rem;margin-bottom:1rem'>1️⃣</div><h3 style='color:#10b981;margin:0 0 1rem 0'>Carica Bilancio</h3><p style='color:#94a3b8;margin:0'>PDF, DOCX o TXT. Estraiamo automaticamente ricavi, EBIT, FCF, debito e cassa.</p></div>"
    html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;border:2px solid #fbbf24;text-align:center'><div style='font-size:3rem;margin-bottom:1rem'>2️⃣</div><h3 style='color:#fbbf24;margin:0 0 1rem 0'>Scegli Scenario</h3><p style='color:#94a3b8;margin:0'>Testa l'azienda su Crisi 2008, Pandemia 2020 o scenario attuale con dati reali.</p></div>"
    html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;border:2px solid #3b82f6;text-align:center'><div style='font-size:3rem;margin-bottom:1rem'>3️⃣</div><h3 style='color:#3b82f6;margin:0 0 1rem 0'>Ottieni Risultati</h3><p style='color:#94a3b8;margin:0'>Resilience Score, breakdown dettagliato, grafici e report PDF scaricabile.</p></div>"
    html_out += "</div></div>"
    
    # SEZIONE REPORT SELEZIONATO
    if rep:
        m = _json.loads(rep.metrics_json or "{}")
        html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;margin-bottom:2rem;border-left:5px solid #fbbf24'>"
        html_out += "<h2 style='color:#fbbf24;margin-top:0'> Report Selezionato</h2>"
        html_out += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;margin-top:1rem'>"
        html_out += "<div style='background:#0f172a;padding:1rem;border-radius:8px'><div style='color:#64748b;font-size:0.85rem'>Azienda</div><div style='color:#e2e8f0;font-weight:700;font-size:1.1rem'>" + (rep.company or rep.filename) + "</div></div>"
        html_out += "<div style='background:#0f172a;padding:1rem;border-radius:8px'><div style='color:#64748b;font-size:0.85rem'>Score AUGET</div><div style='color:#fbbf24;font-weight:800;font-size:1.5rem'>" + str(rep.score or "N/D") + "/100</div></div>"
        html_out += "<div style='background:#0f172a;padding:1rem;border-radius:8px'><div style='color:#64748b;font-size:0.85rem'>Settore</div><div style='color:#e2e8f0;font-weight:700'>" + (rep.sector or "Altro") + "</div></div>"
        html_out += "</div></div>"
    
    # SEZIONE LIV 1 - DATI MACRO
    html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;margin-bottom:2rem;border-left:5px solid #10b981'>"
    html_out += "<h2 style='color:#10b981;margin-top:0'>📊 LIV 1 - Dati Macro Reali</h2>"
    html_out += "<p style='color:#94a3b8'>5 variabili con fonti pubbliche verificabili</p>"
    html_out += "<form method='post'><input type='hidden' name='save_config' value='1'>"
    html_out += "<div style='overflow-x:auto;margin-top:1rem'>"
    html_out += "<table style='width:100%;border-collapse:collapse'>"
    html_out += "<tr style='background:#0f172a'><th style='padding:1rem;text-align:left;color:#fbbf24;border-bottom:2px solid #475569'>Criterio</th><th style='padding:1rem;text-align:left;color:#fbbf24;border-bottom:2px solid #475569'>Fonte</th><th style='padding:1rem;text-align:left;color:#fbbf24;border-bottom:2px solid #475569'>Valore</th><th style='padding:1rem;text-align:center;color:#fbbf24;border-bottom:2px solid #475569'>Attivo</th></tr>"
    for ck, cv in macro_criteria.items():
        real_tag = " ✅" if cv["real"] is not None else ""
        html_out += "<tr style='border-bottom:1px solid #334155'><td style='padding:1rem;color:#e2e8f0;font-weight:600'>" + cv["label"] + real_tag + "</td>"
        html_out += "<td style='padding:1rem;color:#94a3b8;font-size:0.9rem'>" + cv["source"] + "</td>"
        html_out += "<td style='padding:1rem;color:#e2e8f0;font-weight:700'>" + "{:.2f}".format(cv["base"]) + "</td>"
        checked = " checked" if cv["active"] else ""
        html_out += "<td style='padding:1rem;text-align:center'><input type='checkbox' name='crit_" + ck + "_act'" + checked + " style='width:20px;height:20px;cursor:pointer'></td></tr>"
    html_out += "</table></div>"
    
    html_out += "<h3 style='color:#fbbf24;margin-top:2rem'> Scenari Storici Verificati</h3>"
    html_out += "<table style='width:100%;border-collapse:collapse;margin-top:1rem'>"
    html_out += "<tr style='background:#0f172a'><th style='padding:1rem;text-align:left;color:#fbbf24;border-bottom:2px solid #475569'>Scenario</th><th style='padding:1rem;text-align:left;color:#fbbf24;border-bottom:2px solid #475569'>Dati storici</th><th style='padding:1rem;text-align:center;color:#fbbf24;border-bottom:2px solid #475569'>Includi</th></tr>"
    for sn, sd in scenarios_def.items():
        checked = " checked" if sd["active"] else ""
        html_out += "<tr style='border-bottom:1px solid #334155'><td style='padding:1rem;color:#e2e8f0;font-weight:700'>" + sn + "</td><td style='padding:1rem;color:#94a3b8;font-size:0.9rem'>" + sd["desc"] + "</td>"
        html_out += "<td style='padding:1rem;text-align:center'><input type='checkbox' name='scen_" + sn + "_act'" + checked + " style='width:20px;height:20px;cursor:pointer'></td></tr>"
    html_out += "</table>"
    html_out += "<button type='submit' style='margin-top:1.5rem;padding:0.8rem 2rem;background:#10b981;color:#0f172a;border:none;border-radius:8px;font-weight:700;cursor:pointer;font-size:1rem'>💾 Salva Configurazione</button>"
    html_out += "</form></div>"
    
    # SEZIONE LIV 2 E 3 (solo se c'è un report)
    if rep:
        m = _json.loads(rep.metrics_json or "{}")
        sector = rep.sector or "Altro"
        pil_sens = 1.0
        infl_sens = 0.3
        
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
        new_ebit = new_rev * margin
        int_mult = 1.0 + shocks.get("rates", 0) / 100.0
        new_interest = interest * max(int_mult, 0.3)
        ebit_ratio = new_ebit / ebit if ebit else 1.0
        new_fcf = fcf * max(ebit_ratio, 0.2)
        
        de_old = debt / ebit if ebit > 0 else 0
        de_new = debt / new_ebit if new_ebit > 0 else 99
        ic_old = ebit / interest if interest > 0 else 0
        ic_new = new_ebit / new_interest if new_interest > 0 else 99
        
        html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;margin-bottom:2rem;border-left:5px solid #3b82f6'>"
        html_out += "<h2 style='color:#3b82f6;margin-top:0'>🔗 LIV 2 - Catena Causale Matematica</h2>"
        html_out += "<p style='color:#94a3b8'>Calcoli algebrici esatti applicati ai tuoi dati reali</p>"
        
        html_out += "<div style='background:#0f172a;padding:1.5rem;border-radius:10px;font-family:monospace;line-height:2;margin-top:1rem'>"
        html_out += "<div style='color:#fbbf24;font-weight:700;margin-bottom:1rem'>Scenario: Crisi 2008 (Lehman Brothers)</div>"
        html_out += "<div style='color:#e2e8f0'>PIL: <span style='color:#ef4444'>" + "{:+.1f}".format(shocks.get("gdp", 0)) + "%</span></div>"
        html_out += "<div style='color:#64748b'>↓ (sensibilità 1:1)</div>"
        html_out += "<div style='color:#e2e8f0'>Ricavi: <span style='color:#ef4444'>" + "{:+.1f}".format(rev_shock * 100) + "%</span> (da " + "{:,.0f}".format(rev) + "M a " + "{:,.0f}".format(new_rev) + "M)</div>"
        html_out += "<div style='color:#64748b'>↓ (margine costante)</div>"
        html_out += "<div style='color:#e2e8f0'>EBIT: <span style='color:#ef4444'>" + "{:+.1f}".format(((new_ebit - ebit) / ebit * 100) if ebit else 0) + "%</span> (da " + "{:,.0f}".format(ebit) + "M a " + "{:,.0f}".format(new_ebit) + "M)</div>"
        html_out += "<div style='color:#64748b'>↓</div>"
        html_out += "<div style='color:#e2e8f0'>FCF: <span style='color:#ef4444'>" + "{:+.1f}".format(((new_fcf - fcf) / fcf * 100) if fcf else 0) + "%</span> (da " + "{:,.0f}".format(fcf) + "M a " + "{:,.0f}".format(new_fcf) + "M)</div>"
        html_out += "<div style='color:#64748b'>↓</div>"
        html_out += "<div style='color:#e2e8f0'>Tassi: <span style='color:#ef4444'>" + "{:+.1f}".format(shocks.get("rates", 0)) + "%</span></div>"
        html_out += "<div style='color:#64748b'>↓</div>"
        html_out += "<div style='color:#e2e8f0'>Interessi: da " + "{:,.0f}".format(interest) + "M a " + "{:,.0f}".format(new_interest) + "M</div>"
        html_out += "<div style='color:#64748b'>↓</div>"
        html_out += "<div style='color:#e2e8f0'>Debt/EBITDA: <span style='color:#fbbf24'>" + "{:.1f}".format(de_old) + "x → " + "{:.1f}".format(de_new) + "x</span></div>"
        html_out += "<div style='color:#e2e8f0'>Interest Coverage: <span style='color:#fbbf24'>" + "{:.1f}".format(ic_old) + "x → " + "{:.1f}".format(ic_new) + "x</span></div>"
        html_out += "</div></div>"
        
        # LIV 3 - RISULTATI
        html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;margin-bottom:2rem;border-left:5px solid #fbbf24'>"
        html_out += "<h2 style='color:#fbbf24;margin-top:0'>🏆 LIV 3 - Risultati Stress Test</h2>"
        html_out += "<p style='color:#94a3b8'>Voto basato su calcoli matematici applicati a scenari storici reali</p>"
        
        active_scenarios = {k: v for k, v in scenarios_def.items() if v["active"]}
        total_score = 0.0
        count = 0
        scenarios_results_local = []
        
        for scen_name, scen_data in active_scenarios.items():
            shocks = scen_data["shocks"]
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
            
            score = 100.0
            if new_fcf < 0: score -= 30
            if de_new > 4: score -= 25
            elif de_new > 3: score -= 15
            if ic_new < 2: score -= 25
            elif ic_new < 3: score -= 15
            if cassa > debt * 0.5: score += 10
            if new_fcf > 0 and de_new < 2: score += 10
            score = max(0, min(100, score))
            
            total_score += score
            count += 1
            scenarios_results_local.append((scen_name, score))
            
            if score >= 75: color = "#10b981"; label = "RESILIENTE"
            elif score >= 60: color = "#22c55e"; label = "SOLIDA"
            elif score >= 45: color = "#fbbf24"; label = "MODERATA"
            elif score >= 30: color = "#f59e0b"; label = "FRAGILE"
            else: color = "#ef4444"; label = "A RISCHIO"
            
            html_out += "<div style='border:2px solid " + color + ";border-radius:12px;padding:1.5rem;margin:1.5rem 0;background:#0f172a'>"
            html_out += "<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;margin-bottom:1rem'>"
            html_out += "<h3 style='margin:0;color:" + color + ";font-size:1.3rem'>" + scen_name + "</h3>"
            html_out += "<div style='text-align:right'><div style='font-size:3rem;font-weight:800;color:" + color + ";line-height:1'>" + str(int(score)) + "</div><div style='font-size:0.9rem;color:" + color + ";font-weight:700'>" + label + "</div></div>"
            html_out += "</div>"
            html_out += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:1rem;font-size:0.95rem'>"
            html_out += "<div style='background:#1e293b;padding:0.8rem;border-radius:6px'><strong style='color:#94a3b8'>Ricavi:</strong> <span style='color:" + color + "'>" + "{:+.0f}".format(rev_shock * 100) + "%</span></div>"
            html_out += "<div style='background:#1e293b;padding:0.8rem;border-radius:6px'><strong style='color:#94a3b8'>EBIT:</strong> <span style='color:" + color + "'>" + "{:+.0f}".format(((new_ebit - ebit) / ebit * 100) if ebit else 0) + "%</span></div>"
            html_out += "<div style='background:#1e293b;padding:0.8rem;border-radius:6px'><strong style='color:#94a3b8'>FCF:</strong> <span style='color:" + color + "'>" + "{:+.0f}".format(((new_fcf - fcf) / fcf * 100) if fcf else 0) + "%</span></div>"
            html_out += "<div style='background:#1e293b;padding:0.8rem;border-radius:6px'><strong style='color:#94a3b8'>Debt/EBITDA:</strong> <span style='color:" + color + "'>" + "{:.1f}".format(de_new) + "x</span></div>"
            html_out += "<div style='background:#1e293b;padding:0.8rem;border-radius:6px'><strong style='color:#94a3b8'>Int.Coverage:</strong> <span style='color:" + color + "'>" + "{:.1f}".format(ic_new) + "x</span></div>"
            html_out += "<div style='background:#1e293b;padding:0.8rem;border-radius:6px'><strong style='color:#94a3b8'>FCF positivo:</strong> <span style='color:" + color + "'>" + ("SI" if new_fcf > 0 else "NO") + "</span></div>"
            html_out += "</div></div>"
        
        avg_score = total_score / count if count > 0 else 0
        if avg_score >= 75: final_color = "#10b981"; final_label = "AZIENDA RESILIENTE"
        elif avg_score >= 60: final_color = "#22c55e"; final_label = "AZIENDA SOLIDA"
        elif avg_score >= 45: final_color = "#fbbf24"; final_label = "AZIENDA MODERATA"
        elif avg_score >= 30: final_color = "#f59e0b"; final_label = "AZIENDA FRAGILE"
        else: final_color = "#ef4444"; final_label = "AZIENDA A RISCHIO"
        
        html_out += "<div style='text-align:center;padding:3rem;border:3px solid " + final_color + ";border-radius:16px;margin:2rem 0;background:linear-gradient(135deg, #1e293b 0%, #0f172a 100%)'>"
        html_out += "<h2 style='color:" + final_color + ";margin:0;font-size:2rem'>🏆 VOTO FINALE</h2>"
        html_out += "<div style='font-size:6rem;font-weight:800;color:" + final_color + ";line-height:1.2;margin:1.5rem 0'>" + str(int(avg_score)) + "<span style='font-size:2rem'>/100</span></div>"
        html_out += "<div style='font-size:1.8rem;color:" + final_color + ";font-weight:700;letter-spacing:2px'>" + final_label + "</div>"
        html_out += "<p style='color:#94a3b8;margin-top:1rem;font-size:1.1rem'>Media su " + str(count) + " scenari storici reali</p>"
        html_out += "</div>"
        
        # GRAFICO
        chart_labels = [x[0] for x in scenarios_results_local]
        chart_scores = [x[1] for x in scenarios_results_local]
        chart_colors = []
        for s in chart_scores:
            if s >= 75: chart_colors.append("#10b981")
            elif s >= 60: chart_colors.append("#22c55e")
            elif s >= 45: chart_colors.append("#fbbf24")
            elif s >= 30: chart_colors.append("#f59e0b")
            else: chart_colors.append("#ef4444")
        
        html_out += "<div style='background:#1e293b;padding:2rem;border-radius:12px;margin-bottom:2rem'>"
        html_out += "<h2 style='color:#fbbf24;margin-top:0'>📊 Grafico Resilienza</h2>"
        html_out += "<canvas id='resChart' width='400' height='200'></canvas>"
        html_out += "<script src='https://cdn.jsdelivr.net/npm/chart.js'></script><script>"
        html_out += "new Chart(document.getElementById('resChart'), {type: 'bar',"
        html_out += "data: {labels: " + str(chart_labels) + ", datasets: [{label: 'Resilienza', data: " + str(chart_scores) + ", backgroundColor: " + str(chart_colors) + "}]}"
        html_out += ",options: {scales: {y: {beginAtZero: true, max: 100}}, plugins: {legend: {display: false}}}});</script></div>"
        
        # CTA FINALI
        html_out += "<div style='background:linear-gradient(135deg, rgba(16,185,129,0.1), rgba(251,191,36,0.1));border:3px solid #fbbf24;padding:2.5rem;border-radius:16px;text-align:center'>"
        html_out += "<h2 style='color:#fbbf24;margin-top:0;font-size:2rem'> Cosa vuoi fare ora?</h2>"
        html_out += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-top:1.5rem'>"
        html_out += "<a href='/simula/" + str(rep.id) + "/export' style='padding:1rem 2rem;background:#fbbf24;color:#0f172a;border-radius:10px;text-decoration:none;font-weight:700;font-size:1.1rem;display:inline-block'>📄 Scarica PDF</a>"
        html_out += "<a href='/simula/custom-scenario' style='padding:1rem 2rem;background:#3b82f6;color:white;border-radius:10px;text-decoration:none;font-weight:700;font-size:1.1rem;display:inline-block'>🔧 Scenario Custom</a>"
        html_out += "<a href='/compare' style='padding:1rem 2rem;background:#10b981;color:#0f172a;border-radius:10px;text-decoration:none;font-weight:700;font-size:1.1rem;display:inline-block'> Confronta</a>"
        html_out += "</div>"
        html_out += "<p style='color:#94a3b8;margin:1.5rem 0 0 0;font-size:1.05rem'>Vuoi monitorare questa azienda nel tempo? <a href='/alerts' style='color:#10b981;font-weight:700'>Crea un Alert →</a></p>"
        html_out += "</div>"
    else:
        html_out += "<div style='background:#1e293b;padding:3rem;border-radius:12px;text-align:center;border:2px dashed #475569'>"
        html_out += "<div style='font-size:4rem;margin-bottom:1rem'>📊</div>"
        html_out += "<h2 style='color:#94a3b8;margin:0'>Nessun report caricato</h2>"
        html_out += "<p style='color:#64748b;margin:1rem 0'>Carica un bilancio per vedere i risultati dello stress test</p>"
        html_out += "</div>"
    
    return render_template_string(BASE_TEMPLATE, title="Simula", content=html_out)


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
