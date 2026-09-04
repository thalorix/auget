import re
import py_compile

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Verifica se la rotta esiste già
if '@app.route("/analysis/<int:rid>")' not in content:
    
    new_analysis = """
@app.route("/analysis/<int:rid>")
@login_required
def analysis(rid):
    rep = Report.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    m = _json.loads(rep.metrics_json or "{}")
    
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    debt = float(m.get("total_debt") or 0)
    cash = float(m.get("cassa") or 0)
    interest = float(m.get("interest") or 0)
    ebitda = float(m.get("ebitda") or max(ebit * 1.2, 0.1))
    net_income = float(m.get("net_income") or max(ebit * 0.7, 0))
    total_assets = float(m.get("total_assets") or max(rev * 1.5, 1))
    total_liabilities = float(m.get("total_liabilities") or max(debt * 1.5, 1))
    equity = max(total_assets - total_liabilities, 0.1)
    retained_earnings = float(m.get("retained_earnings") or max(equity * 0.5, 0))
    working_capital = float(m.get("working_capital") or max(rev * 0.1, 0))
    market_cap = float(m.get("market_cap") or 0)
    shares = float(m.get("shares") or 1)
    capex = float(m.get("capex") or max(ebit * 0.15, 0))
    nwc_change = float(m.get("nwc_change") or 0)
    depreciation = float(m.get("depreciation") or max(ebit * 0.1, 0))
    tax_rate = float(m.get("tax_rate") or 0.24)
    
    # 1. ALTMAN Z-SCORE
    x1 = working_capital / max(total_assets, 0.1)
    x2 = retained_earnings / max(total_assets, 0.1)
    x3 = ebit / max(total_assets, 0.1)
    x4 = market_cap / max(total_liabilities, 0.1) if market_cap > 0 else equity / max(total_liabilities, 0.1)
    x5 = rev / max(total_assets, 0.1)
    altman_z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
    
    if altman_z > 2.99: altman_status, altman_color = "SOLIDA", "#10b981"
    elif altman_z > 1.81: altman_status, altman_color = "ZONA GRIGIA", "#fbbf24"
    else: altman_status, altman_color = "A RISCHIO", "#ef4444"
    
    # 2. BENEISH M-SCORE (semplificato)
    dsri = 1.0
    gmi = 1.0
    aqi = 1.0
    sgi = 1.0
    depi = 1.0
    sgai = 1.0
    lvgi = 1.0
    tata = (net_income - (ebit * (1 - tax_rate))) / max(rev, 0.1)
    beneish_m = -4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi + 0.892*sgi + 0.115*depi - 0.172*sgai + 4.679*tata - 0.327*lvgi
    
    if beneish_m > -1.78: beneish_status, beneish_color = "POSSIBILE MANIPOLAZIONE", "#ef4444"
    else: beneish_status, beneish_color = "BILANCIO AFFIDABILE", "#10b981"
    
    # 3. FREE CASH FLOW REALE
    nopat = ebit * (1 - tax_rate)
    fcf_real = nopat + depreciation - capex - nwc_change
    fcf_yield = fcf_real / max(market_cap if market_cap > 0 else rev, 0.1) * 100
    
    # 4. DCF SEMPLIFICATO
    growth_rate = 0.03
    discount_rate = 0.10
    terminal_value = fcf_real * (1 + growth_rate) / max(discount_rate - growth_rate, 0.01)
    intrinsic_value = terminal_value / max(shares, 1)
    current_price = market_cap / max(shares, 1) if market_cap > 0 and shares > 0 else 0
    
    if current_price > 0:
        upside = ((intrinsic_value - current_price) / current_price) * 100
        if upside > 20: valuation_status, valuation_color = "SOTTOVALUTATA", "#10b981"
        elif upside > -20: valuation_status, valuation_color = "PREZZO GIUSTO", "#fbbf24"
        else: valuation_status, valuation_color = "SOPRAVVALUTATA", "#ef4444"
    else:
        upside = 0
        valuation_status, valuation_color = "DATI INSUFFICIENTI", "#6b7280"
    
    # 5. MULTIPLI
    pe_ratio = current_price / max(net_income / max(shares, 1), 0.01) if current_price > 0 and net_income > 0 else 0
    ev = (market_cap + debt - cash) if market_cap > 0 else 0
    ev_ebitda = ev / max(ebitda, 0.1) if ev > 0 else 0
    
    # 6. TREND (cerca altri report della stessa azienda)
    company_name = rep.company or rep.filename
    similar_reports = Report.query.filter(
        Report.user_id == current_user.id,
        Report.company == rep.company
    ).order_by(Report.created_at.asc()).all() if rep.company else []
    
    trend_data = []
    for r in similar_reports:
        rm = _json.loads(r.metrics_json or "{}")
        trend_data.append({
            "date": r.created_at.strftime("%d/%m/%Y") if r.created_at else "N/D",
            "revenue": rm.get("revenue", 0),
            "ebit": rm.get("ebit", 0),
            "score": r.score
        })
    
    # 7. RED FLAGS
    red_flags = []
    if interest > 0 and ebit < interest:
        red_flags.append(("EBIT < Interessi", "L'azienda non genera abbastanza utile per coprire gli interessi", "high"))
    if debt / max(ebitda, 0.1) > 4.0:
        red_flags.append(("Debito/EBITDA > 4x", "Sovraindebitamento critico", "high"))
    if cash < 0:
        red_flags.append(("Cassa negativa", "Liquidità in crisi", "high"))
    if altman_z < 1.81:
        red_flags.append(("Altman Z-Score basso", "Alto rischio di fallimento", "high"))
    if beneish_m > -1.78:
        red_flags.append(("Beneish M-Score alto", "Possibile manipolazione del bilancio", "medium"))
    if fcf_real < 0:
        red_flags.append(("FCF negativo", "L'azienda brucia cassa invece di generarla", "medium"))
    
    # COSTRUZIONE HTML
    html = "<div style='max-width:1000px;margin:0 auto;padding:2rem'>"
    
    # Header
    html += "<div style='text-align:center;margin-bottom:3rem'>"
    html += "<p style='color:var(--muted);font-size:0.9rem;text-transform:uppercase;letter-spacing:2px;margin-bottom:0.5rem'>Analisi Completa</p>"
    html += "<h1 style='font-size:2.5rem;color:var(--text);margin:0'>" + company_name + "</h1>"
    html += "<p style='color:var(--muted);font-size:1.1rem;margin-top:0.5rem'>Valutazione professionale e Red Flags</p>"
    html += "</div>"
    
    # Red Flags
    if red_flags:
        html += "<div style='background:#fef2f2;border:2px solid #ef4444;border-radius:12px;padding:1.5rem;margin-bottom:2rem'>"
        html += "<h3 style='color:#ef4444;margin:0 0 1rem 0'>⚠️ Red Flags (" + str(len(red_flags)) + ")</h3>"
        for flag_title, flag_desc, flag_severity in red_flags:
            severity_color = "#ef4444" if flag_severity == "high" else "#f97316"
            html += "<div style='margin-bottom:0.8rem;padding-bottom:0.8rem;border-bottom:1px solid #fecaca'>"
            html += "<strong style='color:" + severity_color + "'>" + flag_title + "</strong><br>"
            html += "<span style='color:#6b7280;font-size:0.9rem'>" + flag_desc + "</span>"
            html += "</div>"
        html += "</div>"
    
    # Grid principale
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:1.5rem;margin-bottom:2rem'>"
    
    # Altman Z-Score
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-top:4px solid " + altman_color + "'>"
    html += "<h3 style='color:var(--gold);margin:0 0 1rem 0'>Altman Z-Score</h3>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + altman_color + ";margin:0'>" + str(round(altman_z, 2)) + "</p>"
    html += "<p style='color:var(--muted);margin:0.5rem 0 0 0'>" + altman_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem;margin-top:0.5rem'>Z > 2.99 = Solida | 1.81-2.99 = Grigia | < 1.81 = Rischio</p>"
    html += "</div>"
    
    # Beneish M-Score
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-top:4px solid " + beneish_color + "'>"
    html += "<h3 style='color:var(--gold);margin:0 0 1rem 0'>Beneish M-Score</h3>"
    html += "<p style='font-size:3rem;font-weight:800;color:" + beneish_color + ";margin:0'>" + str(round(beneish_m, 2)) + "</p>"
    html += "<p style='color:var(--muted);margin:0.5rem 0 0 0'>" + beneish_status + "</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem;margin-top:0.5rem'>M < -1.78 = Affidabile | M > -1.78 = Manipolazione</p>"
    html += "</div>"
    
    # Valutazione DCF
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-top:4px solid " + valuation_color + "'>"
    html += "<h3 style='color:var(--gold);margin:0 0 1rem 0'>Valutazione DCF</h3>"
    if current_price > 0:
        html += "<p style='font-size:2rem;font-weight:800;color:" + valuation_color + ";margin:0'>" + valuation_status + "</p>"
        html += "<p style='color:var(--muted);margin:0.5rem 0 0 0'>Upside: " + str(round(upside, 1)) + "%</p>"
        html += "<p style='color:var(--muted);font-size:0.85rem;margin-top:0.5rem'>Prezzo attuale: " + str(round(current_price, 2)) + " | Valore intrinseco: " + str(round(intrinsic_value, 2)) + "</p>"
    else:
        html += "<p style='font-size:1.5rem;font-weight:700;color:" + valuation_color + ";margin:0'>" + valuation_status + "</p>"
        html += "<p style='color:var(--muted);font-size:0.85rem;margin-top:0.5rem'>Servono dati di mercato (prezzo, azioni)</p>"
    html += "</div>"
    
    html += "</div>"
    
    # FCF e Multipli
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(250px, 1fr));gap:1rem;margin-bottom:2rem'>"
    
    fcf_color = "#10b981" if fcf_real > 0 else "#ef4444"
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center'>"
    html += "<h4 style='color:var(--muted);margin:0 0 0.5rem 0'>Free Cash Flow</h4>"
    html += "<p style='font-size:2rem;font-weight:800;color:" + fcf_color + ";margin:0'>" + str(round(fcf_real, 1)) + " M€</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Yield: " + str(round(fcf_yield, 1)) + "%</p>"
    html += "</div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center'>"
    html += "<h4 style='color:var(--muted);margin:0 0 0.5rem 0'>P/E Ratio</h4>"
    html += "<p style='font-size:2rem;font-weight:800;color:var(--gold);margin:0'>" + str(round(pe_ratio, 1)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Prezzo / Utile per azione</p>"
    html += "</div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center'>"
    html += "<h4 style='color:var(--muted);margin:0 0 0.5rem 0'>EV/EBITDA</h4>"
    html += "<p style='font-size:2rem;font-weight:800;color:var(--gold);margin:0'>" + str(round(ev_ebitda, 1)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Enterprise Value / EBITDA</p>"
    html += "</div>"
    
    html += "</div>"
    
    # Trend
    if trend_data:
        html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;margin-bottom:2rem'>"
        html += "<h3 style='color:var(--gold);margin:0 0 1rem 0'>Andamento Storico (" + str(len(trend_data)) + " bilanci)</h3>"
        html += "<div style='overflow-x:auto'><table style='width:100%;border-collapse:collapse'>"
        html += "<tr style='border-bottom:2px solid var(--line)'><th style='padding:0.8rem;text-align:left'>Data</th><th style='padding:0.8rem;text-align:right'>Ricavi</th><th style='padding:0.8rem;text-align:right'>EBIT</th><th style='padding:0.8rem;text-align:right'>Score</th></tr>"
        for t in trend_data:
            html += "<tr style='border-bottom:1px solid var(--line)'>"
            html += "<td style='padding:0.8rem'>" + t["date"] + "</td>"
            html += "<td style='padding:0.8rem;text-align:right'>" + str(round(t["revenue"], 1)) + " M€</td>"
            html += "<td style='padding:0.8rem;text-align:right'>" + str(round(t["ebit"], 1)) + " M€</td>"
            html += "<td style='padding:0.8rem;text-align:right;font-weight:700'>" + str(t["score"]) + "</td>"
            html += "</tr>"
        html += "</table></div></div>"
    
    # Azioni
    html += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap'>"
    html += "<a href='/simula' class='btn2' style='background:var(--teal)'>Test di Sopravvivenza</a>"
    html += "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'>Cronologia</a>"
    html += "</div>"
    
    html += "</div>"
    
    return render_template_string(BASE_TEMPLATE, title="Analisi Completa", content=html)
"""
    
    content += new_analysis
    print("Rotta /analysis aggiunta con successo")
    
    # Aggiungi link "Analisi completa" nella rotta /simula
    simula_link = "<a href='/analysis/" + str(rep.id) + "' class='btn2' style='background:var(--blue)'>Analisi completa</a>"
    if "Analisi completa" not in content:
        content = content.replace(
            "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'>Vedi cronologia</a>",
            "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'>Vedi cronologia</a><a href='/analysis/" + str(rep.id) + "' class='btn2' style='background:var(--blue)'>Analisi completa</a>"
        )
        print("Link 'Analisi completa' aggiunto in /simula")
    
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(content)
    
    try:
        py_compile.compile("app.py", doraise=True)
        print("Sintassi verificata!")
    except SyntaxError as e:
        print("Errore sintassi riga " + str(e.lineno) + ": " + str(e.msg))
else:
    print("Rotta /analysis gia esistente")
