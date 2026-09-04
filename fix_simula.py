import re
import py_compile

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Trova la rotta /simula esistente
simula_start = content.find('@app.route("/simula"')
if simula_start != -1:
    next_route = re.search(r'\n@app\.route\(', content[simula_start + 20:])
    simula_end = simula_start + 20 + next_route.start() if next_route else len(content)
    
    # Controlla se c'è /simula/export dopo
    export_start = content.find('@app.route("/simula/export")')
    if export_start != -1 and export_start > simula_start and export_start < simula_end:
        simula_end = export_start
    
    new_simula = """
@app.route("/simula", methods=["GET", "POST"])
@login_required
def simula():
    try: db.create_all()
    except: pass
    rep = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).first()
    if not rep:
        return render_template_string(BASE_TEMPLATE, title="Test di Sopravvivenza", content="<div class='card' style='text-align:center;padding:4rem'><h1 style='font-size:2.5rem;color:var(--gold);margin-bottom:1rem'>Test di Sopravvivenza</h1><p style='font-size:1.2rem;color:var(--muted);margin-bottom:2rem'>Carica prima un bilancio per scoprire se l'azienda sopravvive a una crisi.</p><a href='/analyze' class='btn2' style='background:var(--teal);padding:1rem 2rem'>Analizza un Bilancio</a></div>")
    
    m = _json.loads(rep.metrics_json or "{}")
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    debt = float(m.get("total_debt") or 0)
    cash = float(m.get("cassa") or 0)
    interest = float(m.get("interest") or 0)
    ebitda = float(m.get("ebitda") or max(ebit * 1.2, 0.1))
    depreciation = float(m.get("depreciation") or max(ebit * 0.1, 0))
    
    rate = (interest / debt * 100) if debt > 0 else 5.0
    
    # Nome azienda intelligente (fallback su filename se company è errato)
    company_name = rep.company or ""
    filename = rep.filename or ""
    if company_name and filename:
        # Se company e filename sono molto diversi, mostra entrambi
        filename_clean = filename.replace('.pdf', '').replace('-', ' ').replace('_', ' ').strip()
        if company_name.lower() not in filename_clean.lower() and filename_clean.lower() not in company_name.lower():
            display_name = company_name
            name_subtitle = "(file: " + filename + ")"
        else:
            display_name = company_name
            name_subtitle = ""
    else:
        display_name = company_name or filename
        name_subtitle = ""
    
    # Scenario applicato
    scenario = request.form.get("scenario", "base") if request.method == "POST" else "base"
    
    if scenario == "recession":
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev * 0.85, ebit * 0.70, debt, rate + 1.0, cash
        scenario_label = "Recessione moderata"
    elif scenario == "crisis":
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev * 0.60, ebit * 0.25, debt * 1.15, rate + 2.5, cash * 0.70
        scenario_label = "Crisi grave"
    elif scenario == "growth":
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev * 1.25, ebit * 1.45, debt * 1.30, rate, cash * 0.80
        scenario_label = "Crescita aggressiva"
    else:
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev, ebit, debt, rate, cash
        scenario_label = "Situazione attuale"
    
    s_int = s_debt * (s_rate / 100)
    
    # ALGORITMO MIGLIORATO
    
    # 1. Breaking Point (quanto può crollare l'EBIT prima del default)
    if s_int > 0 and s_ebit > 0:
        bp = max(0, ((s_ebit - s_int) / s_ebit) * 100)
        ic = s_ebit / s_int
    else:
        bp = 100.0 if s_int == 0 else 0.0
        ic = 999.0 if s_int == 0 else 0.0
    
    # 2. Debt/EBITDA (leverage)
    debt_ebitda = s_debt / max(ebitda, 0.1)
    
    # 3. Cash Runway con burn rate REALISTICO
    # Burn rate = uscite mensili totali (rata debito + interessi + costi operativi)
    monthly_debt_payment = s_debt / 60  # stima: rimborso in 5 anni
    monthly_interest = s_int / 12
    monthly_operating = max((s_rev - s_ebit + depreciation) / 12, s_rev * 0.05)  # costi operativi mensili
    monthly_burn = monthly_debt_payment + monthly_interest + monthly_operating
    
    runway = s_cash / monthly_burn if monthly_burn > 0 else 999
    
    # 4. SCORE PONDERATO DI SOPRAVVIVENZA (0-100)
    # Breaking Point: 35% del peso (max 35 punti se bp>=40%)
    bp_score = min(bp / 40.0, 1.0) * 35
    
    # Interest Coverage: 25% del peso (max 25 punti se ic>=3.0)
    ic_score = min(ic / 3.0, 1.0) * 25
    
    # Cash Runway: 20% del peso (max 20 punti se runway>=12 mesi)
    runway_score = min(runway / 12.0, 1.0) * 20
    
    # Debt/EBITDA: 20% del peso (max 20 punti se de<2.0, zero se de>4.0)
    de_score = max(0, (4.0 - debt_ebitda) / 2.0) * 20
    
    survival_score = bp_score + ic_score + runway_score + de_score
    
    # Verdetto basato su score ponderato
    if survival_score >= 75:
        emoji, verdict, color = "🛡️", "SOPRAVVIVE ALLA CRISI", "#10b981"
        explanation = "L'azienda è una fortezza finanziaria. Anche con un crollo grave dei ricavi, ha abbastanza margine operativo, cassa e struttura del debito per resistere a una recessione prolungata senza rischi di default."
    elif survival_score >= 50:
        emoji, verdict, color = "️", "RESISTE, MA CON FATICA", "#fbbf24"
        explanation = "L'azienda può sopportare una crisi moderata, ma non un crollo prolungato. I margini si riducono rapidamente e la cassa va monitorata attentamente. Un peggioramento del 20-30% dei ricavi la porterebbe in zona di pericolo."
    elif survival_score >= 25:
        emoji, verdict, color = "", "IN PERICOLO", "#f97316"
        explanation = "L'azienda ha poca riserva di sicurezza. Basta un piccolo calo dei ricavi o un aumento dei tassi per mettere a rischio la sopravvivenza. La struttura del debito è troppo pesante rispetto alla generazione di cassa."
    else:
        emoji, verdict, color = "💀", "NON SOPRAVVIVE", "#ef4444"
        explanation = "L'azienda è in zona di default tecnico. L'EBIT attuale non copre nemmeno gli interessi, la cassa è insufficiente e il debito è insostenibile. Senza un intervento immediato (ricapitalizzazione o ristrutturazione), il fallimento è probabile."
    
    # COSTRUZIONE HTML - Design migliorato
    html = "<div style='max-width:800px;margin:0 auto;padding:2rem'>"
    
    # Header
    html += "<div style='text-align:center;margin-bottom:3rem'>"
    html += "<p style='color:var(--muted);font-size:0.9rem;text-transform:uppercase;letter-spacing:2px;margin-bottom:0.5rem'>Test di Sopravvivenza</p>"
    html += "<h1 style='font-size:2.5rem;color:var(--text);margin:0'>" + display_name + "</h1>"
    if name_subtitle:
        html += "<p style='color:var(--muted);font-size:0.9rem;margin-top:0.5rem'>" + name_subtitle + "</p>"
    html += "<p style='color:var(--muted);font-size:1.1rem;margin-top:0.5rem'>Sopravvive a una crisi grave?</p>"
    html += "</div>"
    
    # Scenari rapidi (FLEX ROW, non colonna)
    html += "<form method='post' style='display:flex;gap:0.5rem;justify-content:center;margin-bottom:3rem;flex-wrap:wrap'>"
    for key, label in [("base", "Attuale"), ("recession", "Recessione"), ("crisis", "Crisi"), ("growth", "Crescita")]:
        active = "background:var(--gold);color:#0b1220" if scenario == key else "background:var(--bg);color:var(--text)"
        html += "<button type='submit' name='scenario' value='" + key + "' style='padding:0.6rem 1.2rem;border-radius:20px;border:none;cursor:pointer;font-size:0.9rem;font-weight:600;" + active + "'>" + label + "</button>"
    html += "</form>"
    
    # Box risposta principale
    html += "<div style='background:" + color + ";border-radius:16px;padding:3rem 2rem;text-align:center;margin-bottom:2rem;box-shadow:0 10px 40px rgba(0,0,0,0.3)'>"
    html += "<div style='font-size:4rem;margin-bottom:1rem'>" + emoji + "</div>"
    html += "<h2 style='color:white;font-size:2rem;margin:0 0 1rem 0;font-weight:800'>" + verdict + "</h2>"
    html += "<p style='color:rgba(255,255,255,0.9);font-size:1.1rem;line-height:1.6;max-width:600px;margin:0 auto'>" + explanation + "</p>"
    html += "<p style='color:rgba(255,255,255,0.7);font-size:0.9rem;margin-top:1.5rem'>Scenario: " + scenario_label + " | Score: " + str(round(survival_score, 0)) + "/100</p>"
    html += "</div>"
    
    # 4 Metriche chiave (non 3)
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:1rem;margin-bottom:2rem'>"
    
    bp_color = "#10b981" if bp >= 40 else ("#fbbf24" if bp >= 20 else "#ef4444")
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center;border-top:3px solid " + bp_color + "'>"
    html += "<p style='color:var(--muted);font-size:0.8rem;text-transform:uppercase;margin:0 0 0.5rem 0'>Crollo sopportabile</p>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + bp_color + ";margin:0'>-" + str(int(bp)) + "%</p>"
    html += "</div>"
    
    runway_val = str(min(int(runway), 99)) if runway < 999 else "99+"
    runway_color = "#10b981" if runway >= 12 else ("#fbbf24" if runway >= 6 else "#ef4444")
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center;border-top:3px solid " + runway_color + "'>"
    html += "<p style='color:var(--muted);font-size:0.8rem;text-transform:uppercase;margin:0 0 0.5rem 0'>Autonomia cassa</p>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + runway_color + ";margin:0'>" + runway_val + "<span style='font-size:1rem'> mesi</span></p>"
    html += "</div>"
    
    ic_color = "#10b981" if ic >= 3 else ("#fbbf24" if ic >= 1.5 else "#ef4444")
    ic_display = str(round(ic, 1)) + "x" if ic < 999 else "N/D"
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center;border-top:3px solid " + ic_color + "'>"
    html += "<p style='color:var(--muted);font-size:0.8rem;text-transform:uppercase;margin:0 0 0.5rem 0'>Copertura interessi</p>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ic_color + ";margin:0'>" + ic_display + "</p>"
    html += "</div>"
    
    de_color = "#10b981" if debt_ebitda < 2 else ("#fbbf24" if debt_ebitda < 3.5 else "#ef4444")
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center;border-top:3px solid " + de_color + "'>"
    html += "<p style='color:var(--muted);font-size:0.8rem;text-transform:uppercase;margin:0 0 0.5rem 0'>Debito/EBITDA</p>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + de_color + ";margin:0'>" + str(round(debt_ebitda, 1)) + "x</p>"
    html += "</div>"
    
    html += "</div>"
    
    # Dettagli tecnici (espandibili)
    html += "<details style='background:var(--bg);border-radius:12px;padding:1.5rem;margin-bottom:2rem'>"
    html += "<summary style='cursor:pointer;color:var(--gold);font-weight:600;font-size:1rem'>Vedi dettagli tecnici</summary>"
    html += "<div style='margin-top:1rem;padding-top:1rem;border-top:1px solid var(--line)'>"
    html += "<div style='display:grid;grid-template-columns:repeat(2, 1fr);gap:1rem;font-size:0.9rem'>"
    html += "<div><strong style='color:var(--muted)'>Ricavi:</strong> " + str(round(s_rev, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>EBIT:</strong> " + str(round(s_ebit, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Debito:</strong> " + str(round(s_debt, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Cassa:</strong> " + str(round(s_cash, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Tasso interesse:</strong> " + str(round(s_rate, 2)) + "%</div>"
    html += "<div><strong style='color:var(--muted)'>Interessi annui:</strong> " + str(round(s_int, 2)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>EBITDA:</strong> " + str(round(ebitda, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Burn rate mensile:</strong> " + str(round(monthly_burn, 2)) + " M€</div>"
    html += "</div></div></details>"
    
    # Azioni
    html += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap'>"
    html += "<a href='/analysis/" + str(rep.id) + "' class='btn2' style='background:var(--blue)'>Analisi completa</a>"
    html += "<a href='/analyze' class='btn2' style='background:var(--teal)'>Analizza altro bilancio</a>"
    html += "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'>Vedi cronologia</a>"
    html += "</div>"
    
    html += "</div>"
    
    return render_template_string(BASE_TEMPLATE, title="Test di Sopravvivenza", content=html)
"""
    
    content = content[:simula_start] + new_simula + content[simula_end:]
    print("Vecchia rotta /simula rimossa e sostituita con versione migliorata")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

try:
    py_compile.compile("app.py", doraise=True)
    print("Sintassi verificata!")
except SyntaxError as e:
    print("Errore sintassi riga " + str(e.lineno) + ": " + str(e.msg))
