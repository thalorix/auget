import os, sys
from datetime import datetime, timedelta
from flask import Flask, request, redirect, url_for, render_template_string, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
try:
    import tkinter as _tkcheck
except Exception:
    import types as _types, sys as _sys2
    class _Stub:
        def __init__(self, *a, **k): pass
        def __getattr__(self, k): return _Stub()
        def __call__(self, *a, **k): return _Stub()
    class _StubBase:
        def __init__(self, *a, **k): pass
        def __getattr__(self, k): return _StubBase()
        def __call__(self, *a, **k): return _StubBase()
    
    # Modulo tkinter con classi vere (per ereditarietà)
    tk = _types.ModuleType("tkinter")
    for cls_name in ("Frame", "Tk", "Toplevel", "Canvas", "Scrollbar", "Label",
                     "Button", "Entry", "Text", "Listbox", "Checkbutton",
                     "Radiobutton", "Menu", "Message", "Scale", "Spinbox"):
        setattr(tk, cls_name, type(cls_name, (_StubBase,), {}))
    tk.__getattr__ = lambda k: _Stub()
    _sys2.modules["tkinter"] = tk
    
    # Modulo tkinter.ttk
    ttk = _types.ModuleType("tkinter.ttk")
    for cls_name in ("Frame", "Treeview", "Notebook", "Button", "Label", "Entry"):
        setattr(ttk, cls_name, type(cls_name, (_StubBase,), {}))
    ttk.__getattr__ = lambda k: _Stub()
    _sys2.modules["tkinter.ttk"] = ttk
    
    # Altri submodule
    for nm in ("tkinter.filedialog", "tkinter.messagebox", "tkinter.scrolledtext"):
        m = _types.ModuleType(nm)
        m.__getattr__ = lambda k: _Stub()
        _sys2.modules[nm] = m
import test1 as engine

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-key-change-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["UPLOAD_FOLDER"] = os.path.join(BASE, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    subscription_tier = db.Column(db.String(20), default="none")
    subscription_expires = db.Column(db.DateTime)
    
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
.nav{background:#161b22;padding:1rem 2rem;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center}
.nav a{color:#f0b429;text-decoration:none;margin-left:1rem}
.container{max-width:900px;margin:2rem auto;padding:0 2rem}
.card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:2rem;margin:1rem 0}
h1{color:#f0b429}h2{color:#f0b429}
input,select{width:100%;padding:10px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6e6e6;margin:8px 0;box-sizing:border-box}
button{background:#f0b429;color:#0d1117;border:0;padding:12px 28px;border-radius:8px;font-weight:700;cursor:pointer;font-size:15px;width:100%}
button:hover{background:#ffc94d}
.alert{padding:12px;border-radius:6px;margin:1rem 0}
.error{background:#da3633;color:white}
.success{background:#238636;color:white}
.tier{border:2px solid #30363d;border-radius:12px;padding:1.5rem;margin:1rem 0;text-align:center}
.tier.active{border-color:#f0b429}
.tier h3{color:#f0b429;font-size:1.5rem;margin:0}
.price{font-size:2rem;color:#f0b429;margin:1rem 0}
</style></head>
<body>
<div class="nav">
  <div><strong style="color:#f0b429">Buffett Analyzer</strong></div>
  <div>
    {% if current_user.is_authenticated %}
      <span>{{ current_user.email }} ({{ current_user.subscription_tier }})</span>
      <a href="/analyze">Analizza</a>
      <a href="/pricing">Piani</a>
      <a href="/logout">Esci</a>
    {% else %}
      <a href="/login">Accedi</a>
      <a href="/register">Registrati</a>
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

@app.route("/")
def index():
    content = """<div class="card">
    <h1>&#9878; Buffett Analyzer</h1>
    <p>Analizza bilanci aziendali con i criteri di Warren Buffett.</p>
    <p>Supporto completo per banche e aziende con buyback massicci.</p>
    {% if not current_user.is_authenticated %}
    <p><a href="/register" style="color:#f0b429">Registrati</a> per iniziare.</p>
    {% endif %}
    </div>"""
    return render_template_string(BASE_TEMPLATE, title="Home", content=content)

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
    current_user.subscription_tier = tier
    current_user.subscription_expires = datetime.utcnow() + timedelta(days=30)
    db.session.commit()
    flash(f"Pagamento completato! Piano {tier} attivato per 30 giorni.", "success")
    return redirect(url_for("analyze_page"))

@app.route("/analyze")
@login_required
@subscription_required
def analyze_page():
    content = """<div class="card">
    <h1>Analizza Bilancio</h1>
    <p>Carica un bilancio aziendale (PDF, DOCX, TXT, HTML).</p>
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
    path = os.path.join(app.config["UPLOAD_FOLDER"], f.filename)
    f.save(path)
    try:
        res = engine.analyze_document(path)
        html_path = engine.export_html(res)
        return send_file(os.path.abspath(html_path), mimetype="text/html")
    except Exception as e:
        flash(f"Errore: {str(e)}", "error")
        return redirect(url_for("analyze_page"))

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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
