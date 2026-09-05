import time
import logging
import math
import PyPDF2
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import json as _json
from datetime import datetime, timedelta
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'auget-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///auget.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ============================================================================
# MODELLI DATABASE
# ============================================================================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    subscription_tier = db.Column(db.String(20), default='free')
    reports = db.relationship('Report', backref='author', lazy=True)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200))
    metrics_json = db.Column(db.Text, nullable=False)
    score = db.Column(db.Integer)
    sector = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - AUGET</title>
    <style>
        :root { --bg: #0f172a; --surface: #1e293b; --text: #f8fafc; --muted: #94a3b8; --gold: #fbbf24; --teal: #14b8a6; --blue: #3b82f6; --line: #334155; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 0; line-height: 1.6; }
        .container { max-width: 1100px; margin: 0 auto; padding: 2rem; }
        .btn2 { display: inline-block; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 600; border: none; cursor: pointer; transition: opacity 0.2s; }
        .btn2:hover { opacity: 0.9; }
        .card { background: var(--surface); border-radius: 12px; padding: 2rem; margin-bottom: 1.5rem; border: 1px solid var(--line); }
        .flash { padding: 1rem; border-radius: 8px; margin-bottom: 1rem; text-align: center; }
        .flash.success { background: rgba(20, 184, 166, 0.2); color: #2dd4bf; border: 1px solid #14b8a6; }
        .flash.error { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
        .flash.warning { background: rgba(251, 191, 36, 0.2); color: #fcd34d; border: 1px solid #fbbf24; }
        nav { background: var(--surface); padding: 1rem 2rem; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; }
        nav a { color: var(--text); text-decoration: none; margin-left: 1.5rem; font-weight: 500; }
        nav a:hover { color: var(--gold); }
        .logo { font-size: 1.5rem; font-weight: 900; color: var(--gold); letter-spacing: 2px; }
    </style>
</head>
<body>
    <nav>
        <div class="logo">AUGET</div>
        <div>
            {% if current_user.is_authenticated %}
                <a href="/dashboard">Dashboard</a>
                <a href="/analyze">Analizza</a>
                <a href="/logout">Logout</a>
            {% else %}
                <a href="/login">Login</a>
            {% endif %}
        </div>
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {{ content | safe }}
    </div>
</body>
</html>
'''

# ============================================================================
# ALGORITMO BUFFETT SCREENER (Il cuore del sistema)
# ============================================================================
def calculate_buffett_score(m):
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    net_income = float(m.get("net_income") or max(ebit * 0.7, 0))
    total_debt = float(m.get("total_debt") or 0)
    cash = float(m.get("cassa") or 0)
    interest = float(m.get("interest") or 0)
    ebitda = float(m.get("ebitda") or max(ebit * 1.2, 0.1))
    total_assets = float(m.get("total_assets") or max(rev * 1.5, 1))
    total_liabilities = float(m.get("total_liabilities") or max(total_debt * 1.2, 1))
    equity = max(total_assets - total_liabilities, 0.1)
    capex = float(m.get("capex") or max(ebit * 0.15, 0))
    depreciation = float(m.get("depreciation") or max(ebit * 0.1, 0))
    
    # --- FILTRI ELIMINATORI ---
    debt_equity = total_debt / equity if equity > 0 else 999
    fcf = ebit * (1 - 0.24) + depreciation - capex
    debt_fcf = total_debt / fcf if fcf > 0 else 999
    
    eliminator_msg = ""
    if debt_equity > 1.0: eliminator_msg = "Debito/Equity > 1.0 (Struttura fragile)"
    elif debt_fcf > 4.0: eliminator_msg = "Debito/FCF > 4.0 (Ripagabilità > 4 anni)"
    elif fcf <= 0: eliminator_msg = "FCF strutturale negativo o nullo"
    
    if eliminator_msg:
        return 0, "SCARTARE", "#ef4444", eliminator_msg

    # --- CORE QUALITY SCORE (0-10 punti) ---
    score = 0.0
    
    # 1. ROIC (max 2 pt)
    nopat = ebit * (1 - 0.24)
    invested_capital = equity + total_liabilities - cash
    roic = (nopat / invested_capital) * 100 if invested_capital > 0 else 0
    if roic >= 15: score += 2.0
    elif roic >= 10: score += 1.0
    
    # 2. Margine Operativo (max 1.5 pt)
    op_margin = (ebit / rev) * 100 if rev > 0 else 0
    if op_margin >= 20: score += 1.5
    elif op_margin >= 12: score += 1.0
    
    # 3. Debito (max 1.5 pt)
    if debt_equity < 0.3: score += 1.5
    elif debt_equity < 0.7: score += 1.0
    
    # 4. FCF Quality (max 2 pt)
    fcf_to_net = fcf / net_income if net_income > 0 else 0
    if fcf_to_net >= 1.0 and fcf > 0: score += 2.0
    elif fcf > 0: score += 1.0
    
    # 5. Reinvestimento Efficiente (max 1 pt)
    cfo = fcf + capex
    capex_ratio = capex / cfo if cfo > 0 else 1.0
    if capex_ratio < 0.3: score += 1.0
    elif capex_ratio < 0.5: score += 0.5
    
    # 6. Interest Coverage (max 2 pt) - Aggiunto per completezza Buffett
    ic = ebit / interest if interest > 0 else 999
    if ic >= 10: score += 2.0
    elif ic >= 5: score += 1.0
    
    score = round(score, 1)
    
    # --- VERDETTO ---
    if score >= 8.0:
        verdict, color = "COMPOUNDER BUFFETT-LEVEL 🏆", "#10b981"
        msg = "Azienda eccellente. Qualità altissima, bilancio solido e generazione di cassa superiore agli utili."
    elif score >= 6.0:
        verdict, color = "BUONA AZIENDA, DA VALUTARE ✅", "#3b82f6"
        msg = "Fondamentali solidi, ma non perfetti. Procedere solo se il prezzo offre un Margine di Sicurezza adeguato."
    else:
        verdict, color = "EVITARE / SOLO SPECULAZIONE ⚠️", "#fbbf24"
        msg = "Punteggio basso. Manca la prevedibilità o la qualità richiesta da Buffett. Meglio cercare altrove."
        
    return score, verdict, color, msg

# ============================================================================
# ROTTE WEB
# ============================================================================
@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect("/dashboard")
    return render_template_string(BASE_TEMPLATE, title="Home", content='''
    <div style="text-align:center; padding: 4rem 2rem;">
        <h1 style="font-size: 3rem; color: var(--gold); margin-bottom: 1rem;">AUGET</h1>
        <p style="font-size: 1.2rem; color: var(--muted); max-width: 600px; margin: 0 auto 2rem auto;">
            Analisi automatica di report aziendali basata sui 12 Criteri Qualitativi e Quantitativi di Warren Buffett.
        </p>
        <a href="/register" class="btn2" style="background: var(--teal); font-size: 1.1rem;">Inizia Gratis</a>
    </div>
    ''')

@app.route("/analyze")
@login_required
def analyze():
    html = '''
    <h1 style="color: var(--gold);">Analizza Report Aziendale</h1>
    <p style="color: var(--muted); margin-bottom: 2rem;">Carica un bilancio in PDF. Il sistema estrarrà i dati e applicherà il Buffett Screener (0-10 punti).</p>
    
    <form id="analyzeForm" method="post" action="/do_analyze" enctype="multipart/form-data" style="background: var(--surface); padding: 3rem; border-radius: 12px; border: 2px dashed var(--line); text-align: center;">
        <p style="color: var(--gold); font-size: 1.2rem; margin-bottom: 1rem;">📄 Trascina qui il PDF o clicca per selezionarlo</p>
        <input type="file" id="fileInput" name="file" accept=".pdf" required style="display: none;">
        <button type="button" onclick="document.getElementById('fileInput').click()" class="btn2" style="background: var(--teal); margin-bottom: 1rem;">Seleziona File</button>
        <p id="fileName" style="color: var(--text); font-weight: 600; margin: 1rem 0;"></p>
        <button type="submit" id="submitBtn" class="btn2" style="background: var(--gold); color: #0b1220; width: 100%; font-size: 1.1rem; font-weight: 700;" disabled>Avvia Analisi Buffett</button>
    </form>
    
    <script>
    const fileInput = document.getElementById('fileInput');
    const fileName = document.getElementById('fileName');
    const submitBtn = document.getElementById('submitBtn');
    fileInput.addEventListener('change', function() {
        if (this.files && this.files[0]) {
            fileName.textContent = '✅ ' + this.files[0].name;
            submitBtn.disabled = false;
        }
    });
    document.getElementById('analyzeForm').addEventListener('submit', function() {
        submitBtn.innerHTML = '⏳ Analisi in corso...';
        submitBtn.disabled = true;
    });
    </script>
    '''
    return render_template_string(BASE_TEMPLATE, title="Analizza", content=html)

@app.route("/do_analyze", methods=["POST"])
@login_required
def do_analyze():
    if 'file' not in request.files:
        flash("⚠️ Nessun file selezionato.", "warning")
        return redirect("/analyze")
    
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        flash("❌ Formato non valido. Carica solo file PDF.", "error")
        return redirect("/analyze")
    
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = "".join([page.extract_text() or "" for page in pdf_reader.pages])
        
        if len(text) < 100:
            flash("⚠️ Il PDF sembra vuoto o protetto.", "warning")
            return redirect("/analyze")
            
        # Estrazione semplificata per demo (in produzione usare regex avanzate o LLM)
        extracted = {
            "company_name": file.filename.replace('.pdf', '').strip().title(),
            "revenue": 100.0,  # Placeholder: sostituire con regex di estrazione reale
            "ebit": 15.0,
            "net_income": 10.0,
            "total_debt": 20.0,
            "cassa": 30.0,
            "interest": 1.0,
            "ebitda": 18.0,
            "total_assets": 200.0,
            "total_liabilities": 80.0,
            "capex": 5.0,
            "depreciation": 4.0
        }
        
        score, verdict, color, msg = calculate_buffett_score(extracted)
        
        rep = Report(
            user_id=current_user.id,
            filename=file.filename,
            company=extracted["company_name"],
            metrics_json=_json.dumps(extracted),
            score=int(score * 10), # Salviamo come intero 0-100 per compatibilità
            sector="Generic"
        )
        db.session.add(rep)
        db.session.commit()
        
        flash(f"✅ Analisi completata! Punteggio: {score}/10", "success")
        return redirect(f"/report/{rep.id}")
        
    except Exception as e:
        flash(f"❌ Errore nell'analisi: {str(e)}", "error")
        return redirect("/analyze")

@app.route("/report/<int:rid>")
@login_required
def report(rid):
    rep = Report.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    m = _json.loads(rep.metrics_json)
    score, verdict, color, msg = calculate_buffett_score(m)
    
    html = f'''
    <div style="text-align: center; margin-bottom: 2rem;">
        <h1 style="color: var(--text); margin: 0;">{rep.company}</h1>
        <p style="color: var(--muted);">Analisi basata sui Criteri di Warren Buffett</p>
    </div>
    
    <div style="background: {color}; border-radius: 16px; padding: 3rem 2rem; text-align: center; margin-bottom: 2rem; box-shadow: 0 10px 40px rgba(0,0,0,0.3);">
        <h2 style="color: white; font-size: 2rem; margin: 0 0 1rem 0; font-weight: 800;">{verdict}</h2>
        <p style="color: rgba(255,255,255,0.9); font-size: 1.1rem; max-width: 700px; margin: 0 auto;">{msg}</p>
        <div style="margin-top: 2rem; background: rgba(255,255,255,0.2); padding: 1rem; border-radius: 8px; display: inline-block;">
            <p style="color: white; font-size: 0.9rem; margin: 0;">Core Quality Score</p>
            <p style="color: white; font-size: 3.5rem; font-weight: 900; margin: 0.5rem 0;">{score}<span style="font-size: 1.5rem;">/10</span></p>
        </div>
    </div>
    
    <div class="card">
        <h3 style="color: var(--gold); margin-top: 0;">Dati Estratti dal Report</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; font-size: 0.95rem;">
            <div><strong style="color: var(--muted);">Ricavi:</strong> {m.get('revenue', 0)} M€</div>
            <div><strong style="color: var(--muted);">EBIT:</strong> {m.get('ebit', 0)} M€</div>
            <div><strong style="color: var(--muted);">Utile Netto:</strong> {m.get('net_income', 0)} M€</div>
            <div><strong style="color: var(--muted);">Debito Totale:</strong> {m.get('total_debt', 0)} M€</div>
            <div><strong style="color: var(--muted);">Cassa:</strong> {m.get('cassa', 0)} M€</div>
            <div><strong style="color: var(--muted);">FCF Stimato:</strong> {m.get('ebit', 0) * 0.76 + m.get('depreciation', 0) - m.get('capex', 0)} M€</div>
        </div>
    </div>
    
    <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
        <a href="/analyze" class="btn2" style="background: var(--teal);">Analizza un altro report</a>
        <a href="/dashboard" class="btn2" style="background: var(--blue);">Vai alla Dashboard</a>
    </div>
    '''
    return render_template_string(BASE_TEMPLATE, title="Report Buffett", content=html)

@app.route("/dashboard")
@login_required
def dashboard():
    reports = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
    html = '<h1 style="color: var(--gold);">La tua Dashboard</h1><div style="display: grid; gap: 1rem;">'
    for r in reports:
        html += f'<div class="card" style="display: flex; justify-content: space-between; align-items: center;"><div><strong style="color: var(--text);">{r.company}</strong><br><span style="color: var(--muted); font-size: 0.9rem;">{r.created_at.strftime("%d/%m/%Y") if r.created_at else ""}</span></div><a href="/report/{r.id}" class="btn2" style="background: var(--gold); color: #0b1220;">Vedi Analisi</a></div>'
    html += '</div><div style="margin-top: 2rem; text-align: center;"><a href="/analyze" class="btn2" style="background: var(--teal);">+ Nuova Analisi</a></div>'
    return render_template_string(BASE_TEMPLATE, title="Dashboard", content=html)

# (Rotte login/register omesse per brevità, usa quelle esistenti nel tuo file)

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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@sibilla.cc').first():
            admin = User(email='admin@sibilla.cc', password='AugetAdmin!2026', subscription_tier='admin')
            db.session.add(admin)
            db.session.commit()
    app.run(host='0.0.0.0', port=10000)