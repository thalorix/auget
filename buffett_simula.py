import re
import py_compile

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Trova /simula esistente
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
        return render_template_string(BASE_TEMPLATE, title="Buffett Analyzer", content="<div class='card' style='text-align:center;padding:4rem'><h1 style='font-size:2.5rem;color:var(--gold);margin-bottom:1rem'>Buffett Value Analyzer</h1><p style='font-size:1.2rem;color:var(--muted);margin-bottom:2rem'>Carica un bilancio per scoprire se è un ottimo investimento secondo i principi di Warren Buffett.</p><a href='/analyze' class='btn2' style='background:var(--teal);padding:1rem 2rem'>Analizza un Bilancio</a></div>")
    
    m = _json.loads(rep.metrics_json or "{}")
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    net_income = float(m.get("net_income") or max(ebit * 0.7, 0))
    total_assets = float(m.get("total_assets") or max(rev * 1.5, 1))
    total_liabilities = float(m.get("total_liabilities") or max(rev * 0.8, 1))
    equity = max(total_assets - total_liabilities, 0.1)
    working_capital = float(m.get("working_capital") or max(rev * 0.1, 0))
    current_assets = float(m.get("current_assets") or max(working_capital * 1.5, 1))
    current_liabilities = float(m.get("current_liabilities") or max(working_capital * 0.5, 1))
    interest = float(m.get("interest") or 0)
    ebitda = float(m.get("ebitda") or max(ebit * 1.2, 0.1))
    capex = float(m.get("capex") or max(ebit * 0.15, 0))
    depreciation = float(m.get("depreciation") or max(ebit * 0.1, 0))
    shares = float(m.get("shares") or 1)
    market_cap = float(m.get("market_cap") or 0)
    
    # Dati di mercato reali (Yahoo Finance)
    ticker = rep.ticker_symbol or "" if hasattr(rep, 'ticker_symbol') else ""
    market_data = get_market_data(ticker) if ticker else {"success": False}
    
    if market_data["success"]:
        market_cap = market_data["market_cap"] / 1e6 if market_data["market_cap"] > 0 else market_cap
        shares = market_data["shares"] / 1e6 if market_data["shares"] > 0 else shares
        current_price = market_data["current_price"]
    
    # ========================================================================
    # I 10 PILASTRI DI BUFFETT
    # ========================================================================
    
    # 1. ROE (Return on Equity)
    roe = (net_income / equity) * 100 if equity > 0 else 0
    roe_score = 20 if roe > 15 else (15 if roe > 10 else (10 if roe > 5 else 0))
    
    # 2. ROIC (Return on Invested Capital)
    invested_capital = equity + total_liabilities - current_liabilities
    roic = (ebit * (1 - 0.24) / invested_capital) * 100 if invested_capital > 0 else 0
    roic_score = 20 if roic > 12 else (15 if roic > 8 else (10 if roic > 5 else 0))
    
    # 3. Gross Margin (stima)
    gross_margin = (ebitda / rev) * 100 if rev > 0 else 0
    margin_score = 15 if gross_margin > 40 else (12 if gross_margin > 25 else (8 if gross_margin > 15 else 0))
    
    # 4. Debt/Equity
    debt_equity = total_liabilities / equity if equity > 0 else 999
    debt_score = 15 if debt_equity < 0.5 else (12 if debt_equity < 1.0 else (8 if debt_equity < 1.5 else 0))
    
    # 5. Current Ratio
    current_ratio = current_assets / current_liabilities if current_liabilities > 0 else 0
    liquidity_score = 10 if current_ratio > 1.5 else (7 if current_ratio > 1.2 else (4 if current_ratio > 1.0 else 0))
    
    # 6. Interest Coverage
    interest_coverage = ebit / interest if interest > 0 else 999
    interest_score = 10 if interest_coverage > 5 else (7 if interest_coverage > 3 else (4 if interest_coverage > 1.5 else 0))
    
    # 7. FCF Yield
    fcf = ebit * (1 - 0.24) + depreciation - capex
    fcf_yield = (fcf / market_cap) * 100 if market_cap > 0 else 0
    fcf_score = 10 if fcf_yield > 5 else (7 if fcf_yield > 3 else (4 if fcf_yield > 1 else 0))
    
    # 8. P/E Ratio
    eps = net_income / shares if shares > 0 else 0
    pe_ratio = current_price / eps if current_price > 0 and eps > 0 else 0
    pe_score = 10 if 0 < pe_ratio < 15 else (8 if 0 < pe_ratio < 25 else (5 if pe_ratio > 25 else 0))
    
    # 9. P/B Ratio
    book_value = equity / shares if shares > 0 else 0
    pb_ratio = current_price / book_value if current_price > 0 and book_value > 0 else 0
    pb_score = 5 if 0 < pb_ratio < 1.5 else (4 if 0 < pb_ratio < 3 else (2 if pb_ratio > 3 else 0))
    
    # 10. DCF Semplificato (Valore Intrinseco)
    growth_rate = 0.03
    discount_rate = 0.10
    terminal_value = fcf * (1 + growth_rate) / max(discount_rate - growth_rate, 0.01)
    intrinsic_value = terminal_value / shares if shares > 0 else 0
    upside = ((intrinsic_value - current_price) / current_price) * 100 if current_price > 0 else 0
    valuation_score = 10 if upside > 30 else (8 if upside > 10 else (5 if upside > -10 else 0))
    
    # BUFFETT SCORE TOTALE (0-100)
    buffett_score = roe_score + roic_score + margin_score + debt_score + liquidity_score + interest_score + fcf_score + pe_score + pb_score + valuation_score
    
    # VERDETTO
    if buffett_score >= 80:
        emoji, verdict, color = "🏆", "WONDERFUL COMPANY", "#10b981"
        explanation = "Azienda eccellente con moat forte, bilanci solidi e prezzo attraente. Warren Buffett la comprerebbe senza esitazione."
    elif buffett_score >= 60:
        emoji, verdict, color = "✅", "GOOD COMPANY", "#3b82f6"
        explanation = "Buona azienda con fondamentali solidi. Valuta il prezzo di ingresso: se in sconto rispetto al valore intrinseco, può essere un buon investimento."
    elif buffett_score >= 40:
        emoji, verdict, color = "⚠️", "FAIR COMPANY", "#fbbf24"
        explanation = "Azienda nella media. Né carne né pesce. Potrebbe avere qualche punto debole nei fondamentali o essere sopravvalutata dal mercato."
    else:
        emoji, verdict, color = "", "AVOID", "#ef4444"
        explanation = "Azienda con fondamentali deboli o troppo costosa. Buffett la eviterebbe. Cerca opportunità migliori."
    
    company_name = rep.company or rep.filename or "Azienda"
    
    # HTML
    html = "<div style='max-width:1100px;margin:0 auto;padding:2rem'>"
    
    # Header
    html += "<div style='text-align:center;margin-bottom:3rem'>"
    html += "<p style='color:var(--muted);font-size:0.9rem;text-transform:uppercase;letter-spacing:2px;margin-bottom:0.5rem'>Buffett Value Analyzer</p>"
    html += "<h1 style='font-size:2.5rem;color:var(--text);margin:0'>" + company_name + "</h1>"
    if market_data["success"]:
        html += "<p style='color:var(--muted);font-size:0.9rem;margin-top:0.5rem'>Dati di mercato: Yahoo Finance (Prezzo: " + str(round(current_price, 2)) + "€ | Market Cap: " + str(round(market_cap, 1)) + " M€)</p>"
    html += "<p style='color:var(--muted);font-size:1.1rem;margin-top:0.5rem'>Vale la pena investire secondo i principi di Warren Buffett?</p>"
    html += "</div>"
    
    # Box Verdetto
    html += "<div style='background:" + color + ";border-radius:16px;padding:3rem 2rem;text-align:center;margin-bottom:2rem;box-shadow:0 10px 40px rgba(0,0,0,0.3)'>"
    html += "<div style='font-size:4rem;margin-bottom:1rem'>" + emoji + "</div>"
    html += "<h2 style='color:white;font-size:2rem;margin:0 0 1rem 0;font-weight:800'>" + verdict + "</h2>"
    html += "<p style='color:rgba(255,255,255,0.9);font-size:1.1rem;line-height:1.6;max-width:700px;margin:0 auto'>" + explanation + "</p>"
    html += "<div style='margin-top:2rem;background:rgba(255,255,255,0.2);padding:1rem;border-radius:8px;display:inline-block'>"
    html += "<p style='color:white;font-size:0.9rem;margin:0'>Buffett Score</p>"
    html += "<p style='color:white;font-size:3rem;font-weight:900;margin:0.5rem 0'>" + str(buffett_score) + "<span style='font-size:1.5rem'>/100</span></p>"
    html += "</div></div>"
    
    # I 10 Pilastri
    html += "<h3 style='color:var(--gold);margin:2rem 0 1rem 0;text-align:center'>📊 I 10 Pilastri di Buffett</h3>"
    html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:1.5rem;margin-bottom:2rem'>"
    
    # Quality Metrics
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if roe > 15 else "#fbbf24" if roe > 10 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>1. ROE (Return on Equity)</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if roe > 15 else "#fbbf24" if roe > 10 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(roe, 1)) + "%</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: >15% = Eccellente | >10% = Buono</p></div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if roic > 12 else "#fbbf24" if roic > 8 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>2. ROIC (Return on Invested Capital)</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if roic > 12 else "#fbbf24" if roic > 8 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(roic, 1)) + "%</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: >12% = Moat Forte | >8% = Buono</p></div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if gross_margin > 40 else "#fbbf24" if gross_margin > 25 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>3. Margine Operativo</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if gross_margin > 40 else "#fbbf24" if gross_margin > 25 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(gross_margin, 1)) + "%</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: >40% = Pricing Power | >25% = Buono</p></div>"
    
    # Financial Strength
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if debt_equity < 0.5 else "#fbbf24" if debt_equity < 1.0 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>4. Debt/Equity</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if debt_equity < 0.5 else "#fbbf24" if debt_equity < 1.0 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(debt_equity, 2)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: <0.5 = Conservativo | <1.0 = Accettabile</p></div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if current_ratio > 1.5 else "#fbbf24" if current_ratio > 1.2 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>5. Current Ratio</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if current_ratio > 1.5 else "#fbbf24" if current_ratio > 1.2 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(current_ratio, 2)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: >1.5 = Liquido | >1.2 = Sano</p></div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if interest_coverage > 5 else "#fbbf24" if interest_coverage > 3 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>6. Interest Coverage</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if interest_coverage > 5 else "#fbbf24" if interest_coverage > 3 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(interest_coverage, 1)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: >5x = Tranquillo | >3x = Accettabile</p></div>"
    
    # Profitability & Valuation
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if fcf_yield > 5 else "#fbbf24" if fcf_yield > 3 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>7. FCF Yield</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if fcf_yield > 5 else "#fbbf24" if fcf_yield > 3 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(fcf_yield, 1)) + "%</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: >5% = Attraente | >3% = Buono</p></div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if 0 < pe_ratio < 15 else "#fbbf24" if 0 < pe_ratio < 25 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>8. P/E Ratio</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if 0 < pe_ratio < 15 else "#fbbf24" if 0 < pe_ratio < 25 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(pe_ratio, 1)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: <15x = Value | <25x = Accettabile</p></div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if 0 < pb_ratio < 1.5 else "#fbbf24" if 0 < pb_ratio < 3 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>9. P/B Ratio</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if 0 < pb_ratio < 1.5 else "#fbbf24" if 0 < pb_ratio < 3 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(pb_ratio, 2)) + "x</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: <1.5x = Sottovalutato | <3x = Accettabile</p></div>"
    
    html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ("#10b981" if upside > 30 else "#fbbf24" if upside > 10 else "#ef4444") + "'>"
    html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>10. Upside Potenziale (DCF)</h4>"
    html += "<p style='font-size:2.5rem;font-weight:800;color:" + ("#10b981" if upside > 30 else "#fbbf24" if upside > 10 else "#ef4444") + ";margin:0.5rem 0'>" + str(round(upside, 1)) + "%</p>"
    html += "<p style='color:var(--muted);font-size:0.85rem'>Target: >30% = Forte Sconto | >10% = Attraente</p></div>"
    
    html += "</div>"
    
    # Dettagli tecnici
    html += "<details style='background:var(--bg);border-radius:12px;padding:1.5rem;margin-bottom:2rem'>"
    html += "<summary style='cursor:pointer;color:var(--gold);font-weight:600;font-size:1rem'>Vedi dettagli finanziari</summary>"
    html += "<div style='margin-top:1rem;padding-top:1rem;border-top:1px solid var(--line)'>"
    html += "<div style='display:grid;grid-template-columns:repeat(2, 1fr);gap:1rem;font-size:0.9rem'>"
    html += "<div><strong style='color:var(--muted)'>Ricavi:</strong> " + str(round(rev, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>EBIT:</strong> " + str(round(ebit, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Utile Netto:</strong> " + str(round(net_income, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>FCF:</strong> " + str(round(fcf, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Patrimonio Netto:</strong> " + str(round(equity, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>Debito Totale:</strong> " + str(round(total_liabilities, 1)) + " M€</div>"
    html += "<div><strong style='color:var(--muted)'>EPS:</strong> " + str(round(eps, 2)) + " €</div>"
    html += "<div><strong style='color:var(--muted)'>Book Value:</strong> " + str(round(book_value, 2)) + " €</div>"
    html += "</div></div></details>"
    
    # Azioni
    html += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap'>"
    html += "<a href='/analysis/" + str(rep.id) + "' class='btn2' style='background:var(--blue)'>Analisi completa</a>"
    html += "<a href='/analyze' class='btn2' style='background:var(--teal)'>Analizza altro bilancio</a>"
    html += "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'>Vedi cronologia</a>"
    html += "</div></div>"
    
    return render_template_string(BASE_TEMPLATE, title="Buffett Analyzer", content=html)
"""
    
    content = content[:simula_start] + new_simula + content[simula_end:]
    print("✅ /simula riscritta con filosofia Buffett")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

try:
    py_compile.compile("app.py", doraise=True)
    print("✅ Sintassi verificata!")
except SyntaxError as e:
    print("❌ Errore sintassi riga " + str(e.lineno) + ": " + str(e.msg))
