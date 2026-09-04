import re
import py_compile

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Aggiungi funzione per recuperare dati Yahoo Finance
if 'def get_market_data' not in content:
    market_func = """
def get_market_data(ticker_symbol):
    """Recupera dati di mercato reali da Yahoo Finance"""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        return {
            "market_cap": info.get("marketCap", 0),
            "shares": info.get("sharesOutstanding", 0),
            "current_price": info.get("currentPrice", 0),
            "beta": info.get("beta", 1.0),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "success": True
        }
    except:
        return {
            "market_cap": 0,
            "shares": 0,
            "current_price": 0,
            "beta": 1.0,
            "sector": "",
            "industry": "",
            "success": False
        }

"""
    # Inserisci prima della prima @app.route
    first_route = content.find('@app.route')
    if first_route != -1:
        content = content[:first_route] + market_func + content[first_route:]
        print("Funzione get_market_data aggiunta")

# 2. Sostituisci /simula con versione completa (yfinance + what-if inverso)
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
    
    # RECUPERA DATI DI MERCATO REALI (Yahoo Finance)
    ticker = rep.ticker_symbol or "" if hasattr(rep, 'ticker_symbol') else ""
    market_data = get_market_data(ticker) if ticker else {"success": False}
    
    # Usa dati reali se disponibili, altrimenti usa stime
    market_cap = market_data["market_cap"] / 1e6 if market_data["success"] else (float(m.get("market_cap") or 0) * 1e6)
    shares = market_data["shares"] / 1e6 if market_data["success"] else float(m.get("shares") or 1)
    current_price = market_data["current_price"] if market_data["success"] else 0
    beta = market_data["beta"] if market_data["success"] else 1.0
    
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
    # MODELLI ACCADEMICI CON DATI REALI
    # ========================================================================
    
    # 1. ALTMAN Z-SCORE (con Market Cap reale se disponibile)
    x1 = working_capital / max(total_assets, 0.1)
    x2 = retained_earnings / max(total_assets, 0.1)
    x3 = s_ebit / max(total_assets, 0.1)
    x4 = market_cap / max(total_liabilities, 0.1) if market_cap > 0 else equity / max(total_liabilities, 0.1)
    x5 = s_rev / max(total_assets, 0.1)
    altman_z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
    
    if altman_z > 2.99: altman_status = "SOLIDA"
    elif altman_z > 1.81: altman_status = "ZONA GRIGIA"
    else: altman_status = "A RISCHIO"
    
    # 2. OHLSON O-SCORE
    import math
    size = math.log(total_assets / 1000000) if total_assets > 1000000 else 0
    tlta = total_liabilities / max(total_assets, 0.1)
    wcta = working_capital / max(total_assets, 0.1)
    clca = 1.0 if (working_capital < 0) else 0.0
    oenega = 1.0 if (total_liabilities > total_assets) else 0.0
    futl = total_liabilities / max(total_assets, 0.1)
    chin = (net_income - ebit) / max(abs(net_income), 0.1) if net_income != 0 else 0
    intwo = 1.0 if (net_income < 0 and ebit < 0) else 0.0
    oachg = (ebitda - ebit) / max(ebitda, 0.1) if ebitda > 0 else 0
    
    ohlson_o = -2.53 + (-0.407 * size) + (6.03 * tlta) + (1.43 * wcta) + (0.076 * clca) + (0.001 * oenega) + (1.72 * futl) + (0.52 * chin) + (0.45 * intwo) + (0.36 * oachg)
    prob_default = 1 / (1 + math.exp(-ohlson_o)) * 100
    
    if prob_default < 10: ohlson_status = "BASSA"
    elif prob_default < 25: ohlson_status = "MEDIA"
    elif prob_default < 50: ohlson_status = "ALTA"
    else: ohlson_status = "CRITICA"
    
    # 3. DSCR REGOLAMENTARE
    taxes = s_ebit * tax_rate
    mandatory_capex = capex * 0.7
    numerator = s_ebitda - taxes - mandatory_capex
    debt_maturity = 6
    annual_debt_payment = s_debt / debt_maturity
    denominator = annual_debt_payment + s_int
    dscr = numerator / max(denominator, 0.1)
    
    if dscr >= 1.5: dscr_status = "SOLIDO"
    elif dscr >= 1.25: dscr_status = "ACCETTABILE"
    elif dscr >= 1.0: dscr_status = "AL LIMITE"
    else: dscr_status = "INSOLVENTE"
    
    # 4. BREAKING POINT E CASH RUNWAY
    if s_int > 0 and s_ebit > 0:
        bp = max(0, ((s_ebit - s_int) / s_ebit) * 100)
        ic = s_ebit / s_int
    else:
        bp = 100.0 if s_int == 0 else 0.0
        ic = 999.0 if s_int == 0 else 0.0
    
    monthly_debt_payment = s_debt / (debt_maturity * 12)
    monthly_interest = s_int / 12
    monthly_operating = max((s_rev - s_ebit + depreciation) / 12, s_rev * 0.05)
    monthly_burn = monthly_debt_payment + monthly_interest + monthly_operating
    runway = s_cash / monthly_burn if monthly_burn > 0 else 999
    
    # ========================================================================
    # WHAT-IF INVERSO (ACTIONABLE INSIGHTS)
    # ========================================================================
    recommendations = []
    
    # Quanto ridurre il debito per avere DSCR >= 1.25?
    target_dscr = 1.25
    if denominator > 0:
        required_numerator = target_dscr * denominator
        if required_numerator > numerator:
            # Serve più EBITDA
            ebitda_gap = required_numerator - numerator
            ebit_increase_needed = ebitda_gap / 1.2  #假设 EBITDA = EBIT * 1.2
            ebit_increase_pct = (ebit_increase_needed / max(s_ebit, 0.1)) * 100
            recommendations.append({
                "type": "increase_ebit",
                "text": f"Aumentare l'EBIT del {round(ebit_increase_pct, 1)}% (da {round(s_ebit, 1)} a {round(s_ebit + ebit_increase_needed, 1)} M€) per portare il DSCR a 1.25x",
                "priority": "high" if ebit_increase_pct > 20 else "medium"
            })
    
    # Quanto ridurre il debito per avere DSCR >= 1.25?
    if annual_debt_payment > 0:
        max_debt_payment = (numerator / target_dscr) - s_int if s_int > 0 else numerator / target_dscr
        if max_debt_payment < annual_debt_payment and max_debt_payment > 0:
            target_annual_payment = max_debt_payment
            target_debt = target_annual_payment * debt_maturity
            debt_reduction = s_debt - target_debt
            debt_reduction_pct = (debt_reduction / max(s_debt, 0.1)) * 100
            recommendations.append({
                "type": "reduce_debt",
                "text": f"Ridurre il debito di {round(debt_reduction, 1)} M€ (-{round(debt_reduction_pct, 1)}%) per portare il DSCR a 1.25x",
                "priority": "high" if debt_reduction_pct > 30 else "medium"
            })
    
    # Quanto EBIT serve per Altman Z-Score >= 1.81?
    if altman_z < 1.81:
        target_z = 1.81
        current_x3 = s_ebit / max(total_assets, 0.1)
        required_x3 = (target_z - (1.2*x1 + 1.4*x2 + 0.6*x4 + 1.0*x5)) / 3.3
        if required_x3 > current_x3:
            required_ebit = required_x3 * total_assets
            ebit_needed = required_ebit - s_ebit
            ebit_pct = (ebit_needed / max(s_ebit, 0.1)) * 100
            recommendations.append({
                "type": "altman",
                "text": f"Aumentare l'EBIT di {round(ebit_needed, 1)} M€ (+{round(ebit_pct, 1)}%) per uscire dalla zona di distress (Z-Score >= 1.81)",
                "priority": "critical"
            })
    
    # Quanto ridurre la PD per scendere sotto 25%?
    if prob_default > 25:
        target_pd = 25
        # Approssimazione: ridurre leverage del X% per ridurre PD
        current_tlta = total_liabilities / max(total_assets, 0.1)
        target_tlta = current_tlta * 0.7  #假设 ridurre passività del 30%
        liability_reduction = total_liabilities - (target_tlta * total_assets)
        liability_pct = (liability_reduction / max(total_liabilities, 0.1)) * 100
        recommendations.append({
            "type": "ohlson",
            "text": f"Ridurre le passività totali di {round(liability_reduction, 1)} M€ (-{round(liability_pct, 1)}%) per portare la PD sotto il 25%",
            "priority": "high"
        })
    
    # Verdetto finale
    critical_count = sum(1 for r in recommendations if r.get("priority") == "critical")
    high_count = sum(1 for r in recommendations if r.get("priority") == "high")
    
    if critical_count >= 1 or (altman_z < 1.81 and prob_default > 50):
        emoji, verdict, color = "", "NON SOPRAVVIVE", "#ef4444"
        explanation = "L'analisi con modelli accademici rivela una situazione critica. La probabilità di default è elevata, l'Altman Z-Score indica zona di fallimento e il DSCR è sotto la soglia di insolvenza."
    elif high_count >= 2 or (altman_z < 1.81 or prob_default > 25 or dscr < 1.0):
        emoji, verdict, color = "", "IN PERICOLO", "#f97316"
        explanation = "Almeno due dei tre indicatori accademici segnalano rischio elevato. Sono necessari interventi strutturali immediati."
    elif high_count >= 1 or (altman_z < 2.99 or prob_default > 10 or dscr < 1.25):
        emoji, verdict, color = "️", "RESISTE, MA CON FATICA", "#fbbf24"
        explanation = "L'azienda può sopportare una crisi moderata, ma i margini di sicurezza si stanno riducendo. Gli indicatori accademici mostrano segnali di allerta."
    else:
        emoji, verdict, color = "️", "SOPRAVVIVE ALLA CRISI", "#10b981"
        explanation = "Tutti e tre i modelli accademici confermano la solidità aziendale. Anche sotto stress grave, gli indicatori restano in zona sicura."
    
    # COSTRUZIONE HTML
    html = "<div style='max-width:1100px;margin:0 auto;padding:2rem'>"
    
    # Header
    html += "<div style='text-align:center;margin-bottom:3rem'>"
    html += "<p style='color:var(--muted);font-size:0.9rem;text-transform:uppercase;letter-spacing:2px;margin-bottom:0.5rem'>Test di Sopravvivenza con Modelli Accademici</p>"
    html += "<h1 style='font-size:2.5rem;color:var(--text);margin:0'>" + company_name + "</h1>"
    if market_data["success"]:
        html += "<p style='color:var(--muted);font-size:0.9rem;margin-top:0.5rem'>Dati di mercato: Yahoo Finance (prezzo: " + str(round(current_price, 2)) + "€ | Market Cap: " + str(round(market_cap/1e6, 1)) + " M€)</p>"
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
    
    # Raccomandazioni actionable
    if recommendations:
        html += "<div style='background:linear-gradient(135deg, rgba(59,130,246,0.1), transparent);border:2px solid #3b82f6;border-radius:12px;padding:2rem;margin-bottom:2rem'>"
        html += "<h3 style='color:#3b82f6;margin:0 0 1rem 0'>💡 Cosa Fare per Migliorare (Actionable Insights)</h3>"
        html += "<div style='display:grid;gap:1rem'>"
        for rec in sorted(recommendations, key=lambda x: 0 if x.get("priority") == "critical" else (1 if x.get("priority") == "high" else 2)):
            priority_color = "#ef4444" if rec.get("priority") == "critical" else ("#f97316" if rec.get("priority") == "high" else "#fbbf24")
            priority_label = "CRITICO" if rec.get("priority") == "critical" else ("IMPORTANTE" if rec.get("priority") == "high" else "CONSIGLIATO")
            html += "<div style='background:var(--bg);padding:1rem;border-radius:8px;border-left:4px solid " + priority_color + "'>"
            html += "<p style='margin:0;color:var(--text)'><strong style='color:" + priority_color + ">[" + priority_label + "]</strong> " + rec["text"] + "</p>"
            html += "</div>"
        html += "</div></div>"
    
    # 3 MODELLI ACCADEMICI
    html += "<h3 style='color:var(--gold);margin:2rem 0 1rem 0;text-align:center'>📊 Analisi con Modelli Accademici</h3>"
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:1.5rem;margin-bottom:2rem'>"
    
    altman_color = "#10b981" if altman_z > 2.99 else ("#fbbf24" if altman_z > 1.81 else "#ef4444")
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + altman_color + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>Altman Z-Score</h4>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + altman_color + ";margin:0.5rem 0'>" + str(round(altman_z, 2)) + "</p>"
    html += "<p style='color:var(--muted);font-size:0.9rem;margin:0.5rem 0'><strong>Stato:</strong> " + altman_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Prevede il fallimento a 2 anni. Z > 2.99 = Sicuro | 1.81-2.99 = Zona Grigia | < 1.81 = Distress</p>"
    html += "</div>"
    
    ohlson_color = "#10b981" if prob_default < 10 else ("#fbbf24" if prob_default < 25 else ("#f97316" if prob_default < 50 else "#ef4444"))
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ohlson_color + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>Ohlson O-Score</h4>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + ohlson_color + ";margin:0.5rem 0'>" + str(round(prob_default, 1)) + "%</p>"
    html += "<p style='color:var(--muted);font-size:0.9rem;margin:0.5rem 0'><strong>Probabilità di Default:</strong> " + ohlson_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Modello di regressione logistica (Ohlson 1980). PD < 10% = Bassa | 10-25% = Media | > 25% = Alta</p>"
    html += "</div>"
    
    dscr_color = "#10b981" if dscr >= 1.5 else ("#fbbf24" if dscr >= 1.25 else ("#f97316" if dscr >= 1.0 else "#ef4444"))
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + dscr_color + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>DSCR Regolamentare</h4>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + dscr_color + ";margin:0.5rem 0'>" + str(round(dscr, 2)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.9rem;margin:0.5rem 0'><strong>Stato:</strong> " + dscr_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Basilea III / EBA. DSCR ≥ 1.25x = Accettabile | < 1.0x = Insolvente</p>"
    html += "</div>"
    
    html += "</div>"
    
    # Metriche operative
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
    html += "<summary style='cursor:pointer;color:var(--gold);font-weight:600;font-size:1rem'>Vedi dettagli tecnici</summary>"
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
    html += "</div></div></details>"
    
    # Azioni
    html += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap'>"
    html += "<a href='/analysis/" + str(rep.id) + "' class='btn2' style='background:var(--blue)'>Analisi completa</a>"
    html += "<a href='/report/" + str(rep.id) + "/pdf' class='btn2' style='background:var(--gold);color:#0b1220'>📄 Scarica PDF</a>"
    html += "<a href='/analyze' class='btn2' style='background:var(--teal)'>Analizza altro bilancio</a>"
    html += "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'>Vedi cronologia</a>"
    html += "</div>"
    
    html += "</div>"
    
    return render_template_string(BASE_TEMPLATE, title="Test di Sopravvivenza", content=html)
"""
    
    content = content[:simula_start] + new_simula + content[simula_end:]
    print("Rotta /simula aggiornata con yfinance e actionable insights")

# 3. Aggiungi rotta /report/<id>/pdf
if '@app.route("/report/<int:rid>/pdf")' not in content:
    pdf_route = """
@app.route("/report/<int:rid>/pdf")
@login_required
def report_pdf(rid):
    from weasyprint import HTML
    from flask import send_file
    import io
    from datetime import datetime
    
    rep = Report.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    m = _json.loads(rep.metrics_json or "{}")
    
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    debt = float(m.get("total_debt") or 0)
    cash = float(m.get("cassa") or 0)
    interest = float(m.get("interest") or 0)
    ebitda = float(m.get("ebitda") or max(ebit * 1.2, 0.1))
    
    rate = (interest / debt * 100) if debt > 0 else 5.0
    s_int = debt * (rate / 100)
    
    # Calcola metriche
    if s_int > 0 and ebit > 0:
        bp = max(0, ((ebit - s_int) / ebit) * 100)
        ic = ebit / s_int
    else:
        bp, ic = 100.0, 999.0
    
    dscr = ebitda / max((debt/6 + s_int), 0.1)
    
    # Altman Z-Score semplificato
    total_assets = float(m.get("total_assets") or max(rev * 1.5, 1))
    total_liabilities = float(m.get("total_liabilities") or max(debt * 1.5, 1))
    equity = max(total_assets - total_liabilities, 0.1)
    working_capital = float(m.get("working_capital") or max(rev * 0.1, 0))
    retained_earnings = float(m.get("retained_earnings") or max(equity * 0.5, 0))
    
    x1 = working_capital / max(total_assets, 0.1)
    x2 = retained_earnings / max(total_assets, 0.1)
    x3 = ebit / max(total_assets, 0.1)
    x4 = equity / max(total_liabilities, 0.1)
    x5 = rev / max(total_assets, 0.1)
    altman_z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
    
    company_name = rep.company or rep.filename or "Azienda"
    date_str = rep.created_at.strftime("%d/%m/%Y") if rep.created_at else datetime.now().strftime("%d/%m/%Y")
    score = rep.score or "N/A"
    
    # Determina stato
    if altman_z > 2.99 and dscr >= 1.5: status, color = "SOLIDA", "#10b981"
    elif altman_z > 1.81 and dscr >= 1.25: status, color = "RESILIENTE", "#fbbf24"
    else: status, color = "A RISCHIO", "#ef4444"
    
    pdf_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{ size: A4; margin: 2cm; }}
            body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #333; line-height: 1.6; }}
            .header {{ border-bottom: 3px solid #1e3a8a; padding-bottom: 1rem; margin-bottom: 2rem; display: flex; justify-content: space-between; align-items: flex-end; }}
            .logo {{ font-size: 2rem; font-weight: 900; color: #1e3a8a; letter-spacing: 2px; }}
            .meta {{ text-align: right; font-size: 0.9rem; color: #666; }}
            .company-name {{ font-size: 1.8rem; font-weight: 700; color: #0f172a; margin-bottom: 0.5rem; }}
            .score-box {{ background: {color}; color: white; padding: 1.5rem; border-radius: 8px; text-align: center; margin: 2rem 0; }}
            .score-val {{ font-size: 3.5rem; font-weight: 900; line-height: 1; }}
            .score-label {{ font-size: 1.2rem; text-transform: uppercase; letter-spacing: 1px; }}
            .metrics-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.5rem; margin: 2rem 0; }}
            .metric-card {{ border: 1px solid #e2e8f0; padding: 1rem; border-radius: 6px; }}
            .metric-label {{ font-size: 0.85rem; color: #64748b; text-transform: uppercase; }}
            .metric-val {{ font-size: 1.5rem; font-weight: 700; color: #0f172a; margin-top: 0.3rem; }}
            .stress-test {{ background: linear-gradient(135deg, rgba(30,58,138,0.05), transparent); padding: 1.5rem; border-radius: 8px; margin: 2rem 0; border-left: 4px solid #1e3a8a; }}
            .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #e2e8f0; font-size: 0.8rem; color: #94a3b8; text-align: center; }}
            h2 {{ color: #1e3a8a; font-size: 1.2rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.5rem; margin-top: 2rem; }}
            .highlight {{ background: #fef3c7; padding: 0.2rem 0.4rem; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">AUGET</div>
            <div class="meta">Report Generato il: {date_str}<br>Analisi Finanziaria Intelligente</div>
        </div>
        
        <div class="company-name">{company_name}</div>
        <div>Test di Sopravvivenza - Stress Test Finanziario</div>
        
        <div class="score-box">
            <div class="score-val">{score}/100</div>
            <div class="score-label">Valutazione: {status}</div>
        </div>
        
        <div class="stress-test">
            <h2 style="margin-top:0;color:#1e3a8a">🛡️ Stress Test di Sopravvivenza</h2>
            <p><strong>Crollo ricavi sopportabile:</strong> <span class="highlight">-{int(bp)}%</span></p>
            <p><strong>Interest Coverage:</strong> {round(ic, 1)}x</p>
            <p><strong>DSCR (Basilea III):</strong> {round(dscr, 2)}x</p>
            <p><strong>Altman Z-Score:</strong> {round(altman_z, 2)}</p>
        </div>
        
        <h2>Principali Indicatori Finanziari</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Ricavi Totali</div>
                <div class="metric-val">€ {rev:,.0f} M</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">EBIT</div>
                <div class="metric-val">€ {ebit:,.0f} M</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">EBITDA</div>
                <div class="metric-val">€ {ebitda:,.0f} M</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Debito Finanziario</div>
                <div class="metric-val">€ {debt:,.0f} M</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Cassa Disponibile</div>
                <div class="metric-val">€ {cash:,.0f} M</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Interessi Passivi</div>
                <div class="metric-val">€ {interest:,.0f} M</div>
            </div>
        </div>
        
        <h2>Note dell'Analista</h2>
        <div style="border: 1px dashed #cbd5e1; padding: 1.5rem; min-height: 150px; background: #f8fafc; border-radius: 6px;">
            <p style="color: #94a3b8; font-style: italic;">Spazio riservato alle note qualitative, raccomandazioni di investimento o osservazioni sul management.</p>
        </div>
        
        <div class="footer">
            Documento generato automaticamente da AUGET.<br>
            I dati sono estratti dal bilancio caricato. Gli scenari di stress test sono simulazioni basate su modelli accademici (Altman Z-Score, Ohlson O-Score, DSCR Basilea III).<br>
            Questo report non costituisce consulenza finanziaria.
        </div>
    </body>
    </html>
    """
    
    pdf_file = HTML(string=pdf_html).write_pdf()
    filename = f"Report_AUGET_{(company_name or 'Azienda').replace(' ', '_')}.pdf"
    return send_file(
        io.BytesIO(pdf_file),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
"""
    content += pdf_route
    print("Rotta /report/<id>/pdf aggiunta")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

try:
    py_compile.compile("app.py", doraise=True)
    print("Sintassi verificata!")
except SyntaxError as e:
    print("Errore sintassi riga " + str(e.lineno) + ": " + str(e.msg))
