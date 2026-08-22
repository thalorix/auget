CODE = r'''import os, sys
from datetime import datetime, timedelta
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json as _json

# Stub tkinter per deploy headless
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
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-me")
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
                 json={"from": "Buffett Analyzer <noreply@sibilla.cc>",
                       "to": [to], "subject": subject, "html": body}, timeout=10)
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

PLAN_LIMITS = {"basic": 10, "trial": 3, "pro": None, "enterprise": None, "demo": None}

def _used_this_month(uid):
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return Report.query.filter(Report.user_id == uid, Report.created_at >= start).count()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    subscription_tier = db.Column(db.String(20), default="none")
    subscription_expires = db.Column(db.DateTime)
    stripe_customer_id = db.Column(db.String(120))
    stripe_subscription_id = db.Column(db.String(120))
    
    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)
    
    @property
    def subscription_active(self):
        if self.subscription_tier == "demo":
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WatchItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    ticker = db.Column(db.String(20))
    name = db.Column(db.String(120))
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if not current_user.subscription_active:
            flash("Abbonamento scaduto o non attivo. Rinnova per continuare.", "error")
            return redirect(url_for("pricing"))
        return f(*args, **kwargs)
    return decorated

BASE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{{ title }}</title>
<style>
body{background:#0d1117;color:#e6e6e6;font-family:'Segoe UI',system-ui,sans-serif;margin:0;min-height:100vh}
.nav{background:#161b22;padding:1rem 2rem;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap}
.nav a{color:#f0b429;text-decoration:none;margin-left:1rem}
.container{max-width:900px;margin:2rem auto;padding:0 2rem}
.card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:2rem;margin:1rem 0}
h1{color:#f0b429}h2{color:#f0b429}
input,select,textarea{width:100%;padding:10px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6e6e6;margin:8px 0;box-sizing:border-box}
button{background:#f0b429;color:#0d1117;border:0;padding:12px 28px;border-radius:8px;font-weight:700;cursor:pointer;font-size:15px;width:100%}
button:hover{background:#ffc94d}
.alert{padding:12px;border-radius:6px;margin:1rem 0}
.error{background:#da3633;color:white}
.success{background:#238636;color:white}
.tier{border:2px solid #30363d;border-radius:12px;padding:1.5rem;margin:1rem 0;text-align:center}
.tier.active{border-color:#f0b429}
.tier h3{color:#f0b429;font-size:1.5rem;margin:0}
.price{font-size:2rem;color:#f0b429;margin:1rem 0}
table{width:100%;border-collapse:collapse;background:#161b22;margin:1rem 0}
td,th{border:1px solid #30363d;padding:8px;text-align:left}
</style></head>
<body>
<div class="nav">
  <div><strong style="color:#f0b429">Buffett Analyzer</strong></div>
  <div>
    <a href="/">Home</a><a href="/contatti">Contatti</a><a href="/collabora">Collabora</a>
    {% if current_user.is_authenticated %}
      <a href="/analyze">Analizza</a><a href="/reports">Report</a><a href="/watchlist">Watchlist</a><a href="/compare">Confronta</a><a href="/assistenza">Assistenza</a><a href="/feedback">Feedback</a><a href="/pricing">Piani</a>
      <span style="color:#9aa4b2">{{ current_user.email }}</span>
      <a href="/logout">Esci</a>
    {% else %}
      <a href="/login">Accedi</a><a href="/register">Registrati</a>
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
    content = """
    <div class="card" style="text-align:center">
      <h1 style="font-size:2.4rem">Analisi fondamentale automatica,<br>in stile Warren Buffett</h1>
      <p>Carica un bilancio (PDF, DOCX, TXT) e ottieni in pochi secondi una dashboard completa: punteggio 0-100, criteri quantitativi e qualitativi, valutazione DCF e metriche bancarie.</p>
      <p><a href="/register"><button style="width:auto;margin:0 6px">Inizia gratis</button></a>
      <a href="/login"><button style="width:auto;margin:0 6px;background:#30363d;color:#e6e6e6">Accedi</button></a></p>
    </div>
    <div class="card"><h2>Cosa fa</h2>
    <ul style="line-height:1.9">
      <li><strong>Punteggio Buffett 0-100</strong> con rubrica ponderata su 4 aree</li>
      <li><strong>40 criteri quantitativi</strong> per aziende industriali e tech</li>
      <li><strong>20 criteri bancari</strong> (ROE/RoTE, ROA, CET1, NPL, Cost/Income)</li>
      <li><strong>Gestione buyback</strong>: ROE/ROIC normalizzati per le Big Tech</li>
      <li><strong>Valutazione DCF multi-scenario</strong> con margine di sicurezza</li>
      <li><strong>Prezzo di borsa</strong> automatico (yfinance) o manuale</li>
    </ul></div>
    <div class="card"><h2>Come funziona</h2>
    <ol style="line-height:1.9">
      <li>Ti registri e scegli un piano (7 giorni di prova gratuita)</li>
      <li>Carichi il bilancio annuale o la relazione finanziaria</li>
      <li>Ricevi la dashboard completa e il report HTML esportabile</li>
    </ol></div>
    <div class="card"><h2>Chi sono</h2>
    <p>Sono Matteo Zanoni, sviluppatore e appassionato di value investing. Ho creato Buffett Analyzer per rendere l'analisi fondamentale professionale accessibile a tutti.</p>
    <p>Vuoi collaborare o hai una proposta? <a href="/collabora" style="color:#f0b429">Parliamone</a> · <a href="/contatti" style="color:#f0b429">Contatti</a></p></div>
    """
    return render_template_string(BASE_TEMPLATE, title="Buffett Analyzer", content=content)

@app.route("/contatti")
def contatti():
    content = """<div class="card"><h1>Contatti</h1>
    <p><strong>Email:</strong> info@sibilla.cc</p>
    <p><strong>Telegram:</strong> @sibilla_finance</p>
    <p><strong>LinkedIn:</strong> linkedin.com/in/matteo-zanoni</p>
    <p>Risposta entro 24-48 ore.</p></div>"""
    return render_template_string(BASE_TEMPLATE, title="Contatti", content=content)

@app.route("/collabora", methods=["GET", "POST"])
def collabora():
    if request.method == "POST":
        c = CollabRequest(name=request.form.get("name"), email=request.form.get("email"),
                          kind=request.form.get("kind"), message=request.form.get("message"))
        db.session.add(c); db.session.commit()
        flash("Proposta inviata! Ti risponderemo presto.", "success")
        return redirect("/collabora")
    content = """<div class="card"><h1>Collabora con noi</h1>
    <p>Partnership, consulenza, sviluppo o ricerca: racconta la tua proposta.</p>
    <form method="post">
      <input name="name" placeholder="Nome e cognome" required>
      <input type="email" name="email" placeholder="Email" required>
      <input name="kind" placeholder="Tipo di collaborazione">
      <textarea name="message" rows="5" placeholder="La tua proposta" required></textarea>
      <button type="submit" style="margin-top:1rem">Invia proposta</button>
    </form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Collabora", content=content)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if User.query.filter_by(email=email).first():
            flash("Email gia registrata", "error")
            return redirect(url_for("register"))
        user = User(email=email, subscription_tier="trial",
                    subscription_expires=datetime.utcnow() + timedelta(days=7))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        send_email(email, "Benvenuto in Buffett Analyzer",
                   "<p>Il tuo account e pronto: 7 giorni di prova gratuita.</p>")
        flash("Registrazione completata! Hai 7 giorni di prova gratuita.", "success")
        return redirect(url_for("pricing"))
    content = """<div class="card">
    <h1>Registrati</h1>
    <form method="post">
      <input type="email" name="email" placeholder="Email" required>
      <input type="password" name="password" placeholder="Password" required>
      <button type="submit">Crea account</button>
    </form>
    <p style="text-align:center;margin-top:1rem">Hai gia un account? <a href="/login" style="color:#f0b429">Accedi</a></p>
    </div>"""
    return render_template_string(BASE_TEMPLATE, title="Registrazione", content=content)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            if not user.subscription_active:
                return redirect(url_for("pricing"))
            return redirect(url_for("analyze_page"))
        flash("Credenziali non valide", "error")
    content = """<div class="card">
    <h1>Accedi</h1>
    <form method="post">
      <input type="email" name="email" placeholder="Email" required>
      <input type="password" name="password" placeholder="Password" required>
      <button type="submit">Accedi</button>
    </form>
    </div>"""
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
    <div class="tier {% if current_user.subscription_tier == 'basic' %}active{% endif %}">
      <h3>Basic</h3>
      <div class="price">9 euro/mese</div>
      <p>10 analisi al mese</p>
      <form method="post" action="/checkout/basic">
        <button type="submit">Scegli Basic</button>
      </form>
    </div>
    <div class="tier {% if current_user.subscription_tier == 'pro' %}active{% endif %}">
      <h3>Professional</h3>
      <div class="price">29 euro/mese</div>
      <p>Analisi illimitate + supporto prioritario</p>
      <form method="post" action="/checkout/pro">
        <button type="submit">Scegli Pro</button>
      </form>
    </div>
    <div class="tier {% if current_user.subscription_tier == 'enterprise' %}active{% endif %}">
      <h3>Enterprise</h3>
      <div class="price">99 euro/mese</div>
      <p>Tutto incluso + API access</p>
      <form method="post" action="/checkout/enterprise">
        <button type="submit">Scegli Enterprise</button>
      </form>
    </div>"""
    return render_template_string(BASE_TEMPLATE, title="Piani", content=content)

@app.route("/checkout/<tier>", methods=["POST"])
@login_required
def checkout(tier):
    prices = {"basic": 9, "pro": 29, "enterprise": 99}
    if tier not in prices:
        flash("Piano non valido", "error")
        return redirect(url_for("pricing"))
    if stripe and STRIPE_PRICES.get(tier):
        sess = stripe.checkout.Session.create(
            mode="subscription",
            client_reference_id=str(current_user.id),
            customer_email=current_user.email,
            line_items=[{"price": STRIPE_PRICES[tier], "quantity": 1}],
            subscription_data={"metadata": {"uid": str(current_user.id), "tier": tier}},
            metadata={"uid": str(current_user.id), "tier": tier},
            success_url=request.host_url + "analyze?pay=ok",
            cancel_url=request.host_url + "pricing")
        return redirect(sess.url)
    current_user.subscription_tier = tier
    current_user.subscription_expires = datetime.utcnow() + timedelta(days=30)
    db.session.commit()
    flash(f"Pagamento completato! Piano {tier} attivato per 30 giorni.", "success")
    send_email(current_user.email, "Ricevuta abbonamento",
               f"<p>Piano {tier} attivo fino al {current_user.subscription_expires:%d/%m/%Y}.</p>")
    return redirect(url_for("analyze_page"))

@app.route("/analyze")
@login_required
@subscription_required
def analyze_page():
    lim = PLAN_LIMITS.get(current_user.subscription_tier)
    used = _used_this_month(current_user.id)
    counter = f"<p style='color:#9aa4b2'>Analisi questo mese: {used}" + (f" / {lim}" if lim else " (illimitate)") + "</p>"
    content = """<div class="card">
    <h1>Analizza Bilancio</h1>
    <p>Carica un bilancio aziendale (PDF, DOCX, TXT, HTML).</p>""" + counter + """
    <form method="post" enctype="multipart/form-data" action="/do_analyze">
      <input type="file" name="report" accept=".pdf,.docx,.txt,.html,.htm" required>
      <button type="submit" style="margin-top:1rem">Analizza</button>
    </form>
    </div>"""
    return render_template_string(BASE_TEMPLATE, title="Analizza", content=content)

@app.route("/do_analyze", methods=["POST"])
@login_required
@subscription_required
def do_analyze():
    f = request.files.get("report")
    if not f or not f.filename:
        flash("Nessun file caricato", "error")
        return redirect(url_for("analyze_page"))
    lim = PLAN_LIMITS.get(current_user.subscription_tier)
    if lim is not None and _used_this_month(current_user.id) >= lim:
        flash(f"Limite piano raggiunto ({lim}/mese). Passa a Pro per analisi illimitate.", "error")
        return redirect(url_for("pricing"))
    path = os.path.join(app.config["UPLOAD_FOLDER"], f.filename)
    f.save(path)
    try:
        res = engine.analyze_document(path)
        html_path = engine.export_html(res)
        html = open(html_path, encoding="utf-8").read()
        sel = {"score": res.get("scores", {}).get("total")}
        for m in res.get("quant", []):
            if m.code in ("Q08", "Q09", "Q16", "Q32", "Q34", "B1", "B2", "B4", "B5"):
                sel[m.code] = m.value
        rep = Report(user_id=current_user.id, filename=f.filename,
                     company=res.get("company", ""),
                     score=sel["score"], html=html,
                     metrics_json=_json.dumps(sel))
        db.session.add(rep); db.session.commit()
        return redirect(f"/reports/{rep.id}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"Errore analisi: {str(e)}", "error")
        return redirect(url_for("analyze_page"))

@app.route("/reports")
@login_required
def reports():
    rs = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    rows = "".join(f"<div class='card'><h2>{r.company or r.filename}</h2><p>Score: {r.score} - {r.created_at.strftime('%d/%m/%Y %H:%M')}</p><a href='/reports/{r.id}' style='color:#f0b429'>Apri report</a></div>" for r in rs)
    content = "<h1>I tuoi report</h1>" + (rows or "<p>Nessun report salvato.</p>")
    return render_template_string(BASE_TEMPLATE, title="Report", content=content)

@app.route("/reports/<int:rid>")
@login_required
def report_view(rid):
    r = Report.query.get_or_404(rid)
    if r.user_id != current_user.id and current_user.subscription_tier != "demo":
        return ("non autorizzato", 403)
    return (r.html, 200, {"Content-Type": "text/html; charset=utf-8"})

@app.route("/watchlist", methods=["GET", "POST"])
@login_required
def watchlist():
    if request.method == "POST":
        w = WatchItem(user_id=current_user.id, ticker=request.form.get("ticker", "").upper(),
                      name=request.form.get("name"), note=request.form.get("note"))
        db.session.add(w); db.session.commit()
        flash("Aggiunto alla watchlist!", "success")
        return redirect("/watchlist")
    items = WatchItem.query.filter_by(user_id=current_user.id).order_by(WatchItem.created_at.desc()).all()
    rows = "".join(f"<div class='card'><h2>{w.ticker} - {w.name}</h2><p>{w.note or ''}</p><form method='post' action='/watchlist/{w.id}/delete'><button style='width:auto;background:#da3633;color:white'>Rimuovi</button></form></div>" for w in items)
    content = """<div class="card"><h1>Watchlist</h1>
    <p>Le aziende che segui.</p>
    <form method="post">
      <input name="ticker" placeholder="Ticker (es. MSFT)" required>
      <input name="name" placeholder="Nome azienda" required>
      <input name="note" placeholder="Nota (es. comprare sotto $400)">
      <button type="submit" style="margin-top:1rem">Aggiungi</button>
    </form></div>
    <h2>Le tue aziende</h2>""" + (rows or "<p>Watchlist vuota.</p>")
    return render_template_string(BASE_TEMPLATE, title="Watchlist", content=content)

@app.route("/watchlist/<int:wid>/delete", methods=["POST"])
@login_required
def watchlist_delete(wid):
    w = WatchItem.query.get_or_404(wid)
    if w.user_id == current_user.id:
        db.session.delete(w); db.session.commit()
    return redirect("/watchlist")

def _fmtv(x):
    try:
        return f"{float(x):.1f}" if x is not None else "N/D"
    except Exception:
        return "N/D"

def _get_metric(r, k):
    if k == "score":
        return r.score
    try:
        return (_json.loads(r.metrics_json or "{}")).get(k)
    except Exception:
        return None

@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    rs = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).limit(20).all()
    if request.method == "POST":
        ids = request.form.getlist("ids")[:3]
        reps = [r for r in rs if str(r.id) in ids]
        if len(reps) < 2:
            flash("Seleziona almeno 2 report", "error")
            return redirect("/compare")
        labels = [("score", "Score Buffett"), ("Q08", "Valore intrinseco/az"), ("Q09", "Margine sicurezza %"),
                  ("Q16", "Earnings Yield %"), ("Q32", "P/E"), ("Q34", "P/BV"),
                  ("B1", "ROE %"), ("B2", "ROA %"), ("B4", "CET1 %"), ("B5", "Cost/Income %")]
        rows = ""
        for k, lab in labels:
            cells = "".join(f"<td>{_fmtv(_get_metric(r, k))}</td>" for r in reps)
            rows += f"<tr><td style='color:#f0b429'>{lab}</td>{cells}</tr>"
        head = "".join(f"<th>{r.company or r.filename}</th>" for r in reps)
        content = f"<h1>Confronto aziende</h1><table><tr><td></td>{head}</tr>{rows}</table>"
        return render_template_string(BASE_TEMPLATE, title="Confronto", content=content)
    boxes = "".join(f"<label style='display:block;margin:6px 0'><input type='checkbox' name='ids' value='{r.id}'> {r.company or r.filename} ({r.created_at:%d/%m/%Y})</label>" for r in rs)
    content = f"<div class='card'><h1>Confronta aziende</h1><p>Seleziona 2-3 report salvati per il confronto fianco a fianco.</p><form method='post'>{boxes}<button type='submit' style='margin-top:1rem'>Confronta</button></form></div>"
    return render_template_string(BASE_TEMPLATE, title="Confronta", content=content)

@app.route("/assistenza", methods=["GET", "POST"])
@login_required
def assistenza():
    if request.method == "POST":
        t = Ticket(user_id=current_user.id, subject=request.form.get("subject"), message=request.form.get("message"))
        db.session.add(t); db.session.commit()
        flash("Ticket aperto! Ti risponderemo via email.", "success")
        return redirect("/assistenza")
    tickets = Ticket.query.filter_by(user_id=current_user.id).order_by(Ticket.created_at.desc()).all()
    rows = "".join(f"<div class='card'><h2>{t.subject}</h2><p>{t.message}</p><p style='color:#9aa4b2'>Stato: {t.status} - {t.created_at.strftime('%d/%m/%Y')}</p></div>" for t in tickets)
    content = """<div class="card"><h1>Assistenza</h1>
    <p>Apri un ticket: ti risponderemo via email.</p>
    <form method="post">
      <input name="subject" placeholder="Oggetto" required>
      <textarea name="message" rows="5" placeholder="Descrivi il problema" required></textarea>
      <button type="submit" style="margin-top:1rem">Apri ticket</button>
    </form></div>
    <h2>I tuoi ticket</h2>""" + (rows or "<p>Nessun ticket.</p>")
    return render_template_string(BASE_TEMPLATE, title="Assistenza", content=content)

@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        fb = Feedback(user_id=current_user.id, rating=int(request.form.get("rating", 5)), message=request.form.get("message"))
        db.session.add(fb); db.session.commit()
        flash("Grazie per il tuo feedback!", "success")
        return redirect("/feedback")
    content = """<div class="card"><h1>Feedback</h1>
    <p>Il tuo parere ci aiuta a migliorare.</p>
    <form method="post">
      <select name="rating">
        <option value="5">5 - Eccellente</option><option value="4">4 - Ottimo</option>
        <option value="3">3 - Buono</option><option value="2">2 - Discreto</option><option value="1">1 - Da migliorare</option>
      </select>
      <textarea name="message" rows="5" placeholder="Cosa ne pensi? Cosa miglioreresti?" required></textarea>
      <button type="submit" style="margin-top:1rem">Invia feedback</button>
    </form></div>"""
    return render_template_string(BASE_TEMPLATE, title="Feedback", content=content)

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    if not stripe:
        return ("stripe non configurato", 400)
    sig = request.headers.get("Stripe-Signature")
    try:
        ev = stripe.Webhook.construct_event(request.data, sig, os.environ.get("STRIPE_WEBHOOK_SECRET"))
    except Exception:
        return ("firma non valida", 400)
    t = ev["type"]; obj = ev["data"]["object"]
    if t == "checkout.session.completed":
        uid = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("uid")
        u = db.session.get(User, int(uid)) if uid else None
        if u:
            u.subscription_tier = (obj.get("metadata") or {}).get("tier", "pro")
            u.stripe_customer_id = obj.get("customer")
            try:
                sub = stripe.Subscription.retrieve(obj["subscription"])
                u.stripe_subscription_id = sub["id"]
                u.subscription_expires = datetime.utcfromtimestamp(sub["current_period_end"])
            except Exception:
                u.subscription_expires = datetime.utcnow() + timedelta(days=30)
            db.session.commit()
            send_email(u.email, "Abbonamento attivato", f"<p>Benvenuto! Piano {u.subscription_tier} attivo.</p>")
    elif t == "customer.subscription.deleted":
        uid = (obj.get("metadata") or {}).get("uid")
        u = db.session.get(User, int(uid)) if uid else None
        if u:
            u.subscription_tier = "none"; db.session.commit()
            send_email(u.email, "Abbonamento terminato", "<p>Il tuo abbonamento e terminato. Rinnova quando vuoi.</p>")
    elif t == "invoice.payment_failed":
        u = User.query.filter_by(email=obj.get("customer_email")).first()
        if u:
            send_email(u.email, "Pagamento non riuscito", "<p>Aggiorna il metodo di pagamento dal portale.</p>")
    return ("ok", 200)

@app.route("/account/portal")
@login_required
def portal():
    if not stripe or not current_user.stripe_customer_id:
        flash("Nessun abbonamento Stripe attivo", "error")
        return redirect(url_for("pricing"))
    sess = stripe.billing_portal.Session.create(customer=current_user.stripe_customer_id, return_url=request.host_url)
    return redirect(sess.url)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(email="demo@demo.com").first():
        demo = User(email="demo@demo.com", subscription_tier="demo",
                    subscription_expires=datetime.utcnow() + timedelta(days=3650))
        demo.set_password("demo123")
        db.session.add(demo)
        db.session.commit()
        print("Account demo creato: demo@demo.com / demo123")

if __name__ == "__main__":
    print("Buffett Analyzer WEB con login: http://127.0.0.1:5001")
    print("Account demo: demo@demo.com / demo123")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False, threaded=True)
'''
with open("app.py", "w", encoding="utf-8") as f:
    f.write(CODE)
print("OK: app.py ricostruito, byte:", len(CODE))
