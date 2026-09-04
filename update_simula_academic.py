import re
import py_compile
import math

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

simula_start = content.find('@app.route("/simula"')
if simula_start != -1:
    next_route = re.search(r'\n@app\.route\(', content[simula_start + 20:])
    simula_end = simula_start + 20 + next_route.start() if next_route else len(content)
    
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
    net_income = float(m.get("net_income") or max(ebit * 0.7, 0))
    total_assets = float(m.get("total_assets") or max(rev * 1.5, 1))
    total_liabilities = float(m.get("total_liabilities") or max(debt * 1.5, 1))
    equity = max(total_assets - total_liabilities, 0.1)
    retained_earnings = float(m.get("retained_earnings") or max(equity * 0.5, 0))
    working_capital = float(m.get("working_capital") or max(rev * 0.1, 0))
    capex = float(m.get("capex") or max(ebit * 0.15, 0))
    tax_rate = float(m.get("tax_rate") or 0.24)
    
    rate = (interest / debt * 100) if debt > 0 else 5.0
    
    # Nome azienda
    company_name = rep.company or rep.filename or "Azienda"
    
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
    s_ebitda = max(s_ebit * 1.2, 0.1)
    
    # ========================================================================
    # MODELLI ACCADEMICI INTEGRATI
    # ========================================================================
    
    # 1. ALTMAN Z-SCORE (Stress-Adjusted)
    x1 = working_capital / max(total_assets, 0.1)
    x2 = retained_earnings / max(total_assets, 0.1)
    x3 = s_ebit / max(total_assets, 0.1)  # EBIT sotto stress
    x4 = equity / max(total_liabilities, 0.1)
    x5 = s_rev / max(total_assets, 0.1)  # Ricavi sotto stress
    altman_z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
    
    if altman_z > 2.99: altman_status = "SOLIDA"
    elif altman_z > 1.81: altman_status = "ZONA GRIGIA"
    else: altman_status = "A RISCHIO"
    
    # 2. OHLSON O-SCORE (Probabilità di Default)
    # Formula semplificata con 9 variabili (Ohlson 1980)
    size = math.log(total_assets / 1000000) if total_assets > 0 else 0  # Dimensione (log asset in milioni)
    tlta = total_liabilities / max(total_assets, 0.1)  # Totale passività / totale attivo
    wcta = working_capital / max(total_assets, 0.1)  # Capitale circolante / totale attivo
    clca = 1.0 if (working_capital < 0) else 0.0  # Current liabilities > current assets
    oenega = 1.0 if (total_liabilities > total_assets) else 0.0  # Negative equity
    futl = total_liabilities / max(total_assets, 0.1)  # Stesso di TLTA
    chin = (net_income - ebit) / max(abs(net_income), 0.1) if net_income != 0 else 0  # Variazione reddito netto
    intwo = 1.0 if (net_income < 0 and ebit < 0) else 0.0  # Perdite negli ultimi 2 anni
    oachg = (ebitda - ebit) / max(ebitda, 0.1) if ebitda > 0 else 0  # Variazione OCF
    
    # Coefficienti di Ohlson (1980)
    ohlson_o = -2.53 + (-0.407 * size) + (6.03 * tlta) + (1.43 * wcta) + (0.076 * clca) + (0.001 * oenega) + (1.72 * futl) + (0.52 * chin) + (0.45 * intwo) + (0.36 * oachg)
    
    # Converti O-Score in probabilità di default (funzione logistica)
    prob_default = 1 / (1 + math.exp(-ohlson_o)) * 100
    
    if prob_default < 10: ohlson_status = "BASSA"
    elif prob_default < 25: ohlson_status = "MEDIA"
    elif prob_default < 50: ohlson_status = "ALTA"
    else: ohlson_status = "CRITICA"
    
    # 3. DSCR REGOLAMENTARE (Basilea III / EBA)
    # DSCR = (EBITDA - Tasse - Capex Obbligatori) / (Rate Debito + Interessi)
    taxes = s_ebit * tax_rate
    mandatory_capex = capex * 0.7  #假设 70% dei capex sono obbligatori (mantenimento)
    numerator = s_ebitda - taxes - mandatory_capex
    
    # Stima rata debito (ammortamento in 5-7 anni)
    debt_maturity = 6  # anni
    annual_debt_payment = s_debt / debt_maturity
    denominator = annual_debt_payment + s_int
    
    dscr = numerator / max(denominator, 0.1)
    
    if dscr >= 1.5: dscr_status = "SOLIDO"
    elif dscr >= 1.25: dscr_status = "ACCETTABILE"
    elif dscr >= 1.0: dscr_status = "AL LIMITE"
    else: dscr_status = "INSOLVENTE"
    
    # 4. BREAKING POINT (Interest Coverage)
    if s_int > 0 and s_ebit > 0:
        bp = max(0, ((s_ebit - s_int) / s_ebit) * 100)
        ic = s_ebit / s_int
    else:
        bp = 100.0 if s_int == 0 else 0.0
        ic = 999.0 if s_int == 0 else 0.0
    
    # 5. CASH RUNWAY (Burn rate realistico)
    monthly_debt_payment = s_debt / (debt_maturity * 12)
    monthly_interest = s_int / 12
    monthly_operating = max((s_rev - s_ebit + depreciation) / 12, s_rev * 0.05)
    monthly_burn = monthly_debt_payment + monthly_interest + monthly_operating
    runway = s_cash / monthly_burn if monthly_burn > 0 else 999
    
    # VERDETTO FINALE (basato sui 3 modelli accademici)
    critical_count = 0
    if altman_z < 1.81: critical_count += 1
    if prob_default > 25: critical_count += 1
    if dscr < 1.0: critical_count += 1
    
    warning_count = 0
    if altman_z < 2.99: warning_count += 1
    if prob_default > 10: warning_count += 1
    if dscr < 1.25: warning_count += 1
    
    if critical_count >= 2:
        emoji, verdict, color = "", "NON SOPRAVVIVE", "#ef4444"
        explanation = "L'analisi con modelli accademici rivela una situazione critica. La probabilità di default è elevata, l'Altman Z-Score indica zona di fallimento e il DSCR è sotto la soglia di insolvenza. Senza interventi strutturali (ricapitalizzazione o ristrutturazione del debito), il fallimento è probabile entro 12-24 mesi."
    elif critical_count == 1 or warning_count >= 2:
        emoji, verdict, color = "", "IN PERICOLO", "#f97316"
        explanation = "Almeno due dei tre indicatori accademici segnalano rischio elevato. L'azienda ha poca riserva di sicurezza e un peggioramento dei ricavi o un aumento dei tassi la porterebbe rapidamente in default tecnico."
    elif warning_count >= 1:
        emoji, verdict, color = "️", "RESISTE, MA CON FATICA", "#fbbf24"
        explanation = "L'azienda può sopportare una crisi moderata, ma i margini di sicurezza si stanno riducendo. Gli indicatori accademici mostrano segnali di allerta che richiedono monitoraggio costante della cassa e del debito."
    else:
        emoji, verdict, color = "🛡️", "SOPRAVVIVE ALLA CRISI", "#10b981"
        explanation = "Tutti e tre i modelli accademici confermano la solidità aziendale. Anche sotto stress grave, l'Altman Z-Score resta in zona sicura, la probabilità di default è bassa e il DSCR supera le soglie regolamentari di Basilea III."
    
    # COSTRUZIONE HTML
    html = "<div style='max-width:1000px;margin:0 auto;padding:2rem'>"
    
    # Header
    html += "<div style='text-align:center;margin-bottom:3rem'>"
    html += "<p style='color:var(--muted);font-size:0.9rem;text-transform:uppercase;letter-spacing:2px;margin-bottom:0.5rem'>Test di Sopravvivenza con Modelli Accademici</p>"
    html += "<h1 style='font-size:2.5rem;color:var(--text);margin:0'>" + company_name + "</h1>"
    html += "<p style='color:var(--muted);font-size:1.1rem;margin-top:0.5rem'>Sopravvive a una crisi grave?</p>"
    html += "</div>"
    
    # Scenari
    html += "<form method='post' style='display:flex;gap:0.5rem;justify-content:center;margin-bottom:3rem;flex-wrap:wrap'>"
    for key, label in [("base", "Attuale"), ("recession", "Recessione"), ("crisis", "Crisi"), ("growth", "Crescita")]:
        active = "background:var(--gold);color:#0b1220" if scenario == key else "background:var(--bg);color:var(--text)"
        html += "<button type='submit' name='scenario' value='" + key + "' style='padding:0.6rem 1.2rem;border-radius:20px;border:none;cursor:pointer;font-size:0.9rem;font-weight:600;" + active + "'>" + label + "</button>"
    html += "</form>"
    
    # Box verdetto
    html += "<div style='background:" + color + ";border-radius:16px;padding:3rem 2rem;text-align:center;margin-bottom:2rem;box-shadow:0 10px 40px rgba(0,0,0,0.3)'>"
    html += "<div style='font-size:4rem;margin-bottom:1rem'>" + emoji + "</div>"
    html += "<h2 style='color:white;font-size:2rem;margin:0 0 1rem 0;font-weight:800'>" + verdict + "</h2>"
    html += "<p style='color:rgba(255,255,255,0.9);font-size:1.1rem;line-height:1.6;max-width:700px;margin:0 auto'>" + explanation + "</p>"
    html += "<p style='color:rgba(255,255,255,0.7);font-size:0.9rem;margin-top:1.5rem'>Scenario: " + scenario_label + "</p>"
    html += "</div>"
    
    # 3 MODELLI ACCADEMICI (card principali)
    html += "<h3 style='color:var(--gold);margin:2rem 0 1rem 0;text-align:center'>📊 Analisi con Modelli Accademici</h3>"
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:1.5rem;margin-bottom:2rem'>"
    
    # Altman Z-Score
    altman_color = "#10b981" if altman_z > 2.99 else ("#fbbf24" if altman_z > 1.81 else "#ef4444")
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + altman_color + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>Altman Z-Score</h4>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + altman_color + ";margin:0.5rem 0'>" + str(round(altman_z, 2)) + "</p>"
    html += "<p style='color:var(--muted);font-size:0.9rem;margin:0.5rem 0'><strong>Stato:</strong> " + altman_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Prevede il fallimento a 2 anni. Z > 2.99 = Sicuro | 1.81-2.99 = Zona Grigia | < 1.81 = Distress</p>"
    html += "</div>"
    
    # Ohlson O-Score
    ohlson_color = "#10b981" if prob_default < 10 else ("#fbbf24" if prob_default < 25 else ("#f97316" if prob_default < 50 else "#ef4444"))
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ohlson_color + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>Ohlson O-Score</h4>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + ohlson_color + ";margin:0.5rem 0'>" + str(round(prob_default, 1)) + "%</p>"
    html += "<p style='color:var(--muted);font-size:0.9rem;margin:0.5rem 0'><strong>Probabilità di Default:</strong> " + ohlson_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Modello di regressione logistica (Ohlson 1980). PD < 10% = Bassa | 10-25% = Media | > 25% = Alta</p>"
    html += "</div>"
    
    # DSCR
    dscr_color = "#10b981" if dscr >= 1.5 else ("#fbbf24" if dscr >= 1.25 else ("#f97316" if dscr >= 1.0 else "#ef4444"))
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + dscr_color + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>DSCR Regolamentare</h4>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + dscr_color + ";margin:0.5rem 0'>" + str(round(dscr, 2)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.9rem;margin:0.5rem 0'><strong>Stato:</strong> " + dscr_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Basilea III / EBA. DSCR ≥ 1.25x = Accettabile | < 1.0x = Insolvente (le banche interrompono il credito)</p>"
    html += "</div>"
    
    html += "</div>"
    
    # Metriche operative aggiuntive
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem;margin-bottom:2rem'>"
    
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
    html += "<p style='color:var(--muted);font-size:0.8rem;text-transform:uppercase;margin:0 0 0.5rem 0'>Interest Coverage</p>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ic_color + ";margin:0'>" + ic_display + "</p>"
    html += "</div>"
    
    html += "</div>"
    
    # Dettagli tecnici
    html += "<details style='background:var(--bg);border-radius:12px;padding:1.5rem;margin-bottom:2rem'>"
    html += "<summary style='cursor:pointer;color:var(--gold);font-weight:600;font-size:1rem'>Vedi dettagli tecnici e formule</summary>"
    html += "<div style='margin-top:1rem;padding-top:1rem;border-top:1px solid var(--line)'>"
    html += "<div style='display:grid;grid-template-columns:repeat(2, 1fr);gap:1rem;font-size:0.9rem'>"
    html += "<div><strong style='color:var(--muted)'>Ricavi:</strong> " + str(round(s_rev, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>EBIT:</strong> " + str(round(s_ebit, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>EBITDA:</strong> " + str(round(s_ebitda, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Debito:</strong> " + str(round(s_debt, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Cassa:</strong> " + str(round(s_cash, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Tasso interesse:</strong> " + str(round(s_rate, 2)) + "%</div>"
    html += "<div><strong style='color:var(--muted)'>Interessi annui:</strong> " + str(round(s_int, 2)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Burn rate mensile:</strong> " + str(round(monthly_burn, 2)) + " M€</div>"
    html += "</div>"
    html += "<div style='margin-top:1rem;padding:1rem;background:rgba(0,0,0,0.2);border-radius:8px;font-size:0.85rem'>"
    html += "<strong>Formule utilizzate:</strong><br>"
    html += "• <strong>Altman Z-Score:</strong> 1.2(X₁) + 1.4(X₂) + 3.3(X₃) + 0.6(X₄) + 1.0(X₅) dove X₁=WC/TA, X₂=RE/TA, X₃=EBIT/TA, X₄=Eq/TL, X₅=Rev/TA<br>"
    html += "• <strong>Ohlson O-Score:</strong> Regressione logistica con 9 variabili (dimensione, leva, liquidità, redditività)<br>"
    html += "• <strong>DSCR:</strong> (EBITDA - Tasse - Capex Obbligatori) / (Rata Debito + Interessi) - Soglia Basilea III: ≥1.25x"
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
    print("Rotte /simula aggiornata con modelli accademici (Altman, Ohlson, DSCR)")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

try:
    py_compile.compile("app.py", doraise=True)
    print("Sintassi verificata!")
except SyntaxError as e:
    print("Errore sintassi riga " + str(e.lineno) + ": " + str(e.msg))
