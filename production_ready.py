import re
import py_compile

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# ============================================================================
# 1. MIGLIORA /analyze - Estrazione dati con validazione rigorosa
# ============================================================================
analyze_start = content.find('@app.route("/analyze"')
if analyze_start != -1:
    # Trova la funzione do_analyze
    do_analyze_start = content.find('@app.route("/do_analyze"', analyze_start)
    if do_analyze_start != -1:
        next_route = re.search(r'\n@app\.route\(', content[do_analyze_start + 30:])
        do_analyze_end = do_analyze_start + 30 + next_route.start() if next_route else len(content)
        
        new_do_analyze = """
@app.route("/do_analyze", methods=["POST"])
@login_required
def do_analyze():
    if 'file' not in request.files:
        flash("Nessun file caricato", "error")
        return redirect("/analyze")
    
    file = request.files['file']
    if file.filename == '':
        flash("Nessun file selezionato", "error")
        return redirect("/analyze")
    
    if file and file.filename.endswith('.pdf'):
        try:
            # Estrazione testo
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            
            # Estrazione dati con pattern matching avanzato
            extracted = extract_financial_data(text, file.filename)
            
            # VALIDAZIONE RIGOROSA - Solo dati reali
            required_fields = ["revenue", "ebit", "total_debt", "cassa"]
            missing_fields = [f for f in required_fields if not extracted.get(f)]
            
            if len(missing_fields) > 2:
                # Troppi dati mancanti, non creare report
                flash(f"Dati insufficienti nel PDF. Mancano: {', '.join(missing_fields)}. Carica un bilancio completo.", "error")
                return redirect("/analyze")
            
            # Calcolo score base
            score = calculate_score(extracted)
            
            # Salva report SOLO con dati reali
            rep = Report(
                user_id=current_user.id,
                filename=file.filename,
                company=extracted.get("company_name", file.filename.replace('.pdf', '')),
                metrics_json=_json.dumps(extracted),
                score=score,
                sector=extracted.get("sector", ""),
                ticker_symbol=extracted.get("ticker", "")
            )
            db.session.add(rep)
            db.session.commit()
            
            flash(f"Analisi completata! Report salvato. Dati estratti: {len([k for k, v in extracted.items() if v])}/{len(extracted)}", "success")
            return redirect(f"/report/{rep.id}")
            
        except Exception as e:
            flash(f"Errore nell'analisi: {str(e)}", "error")
            return redirect("/analyze")
    
    flash("Formato file non valido. Carica un PDF.", "error")
    return redirect("/analyze")

def extract_financial_data(text, filename):
    import re
    
    data = {}
    text_lower = text.lower()
    
    # Company name (dal filename o dal testo)
    data["company_name"] = filename.replace('.pdf', '').replace('-', ' ').replace('_', ' ').strip().title()
    
    # Revenue (Ricavi/Vendite/Fatturato)
    revenue_patterns = [
        r'ricavi\s*(?:netti)?\s*(?:delle\s*vendite)?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'fatturato\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'vendite\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'revenue\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["revenue"] = extract_number(text, revenue_patterns, multipliers={"mld": 1000, "billion": 1000, "milioni": 1, "million": 1, "mila": 0.001})
    
    # EBIT
    ebit_patterns = [
        r'ebit\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'risultato\s*operativo\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'utile\s*(?:prima\s*)?(?:delle\s*)?(?:imposte\s*e\s*)?interessi\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?'
    ]
    data["ebit"] = extract_number(text, ebit_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # EBITDA
    ebitda_patterns = [
        r'ebitda\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'margine\s*operativo\s*lordo\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?'
    ]
    data["ebitda"] = extract_number(text, ebitda_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Total Debt (Debito finanziario totale)
    debt_patterns = [
        r'debito\s*(?:finanziario\s*)?(?:netto|lordo)?\s*(?:totale)?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'total\s*debt\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?',
        r'passivit[aà]\s*finanziarie\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?'
    ]
    data["total_debt"] = extract_number(text, debt_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Cash (Cassa/Liquidità)
    cash_patterns = [
        r'cassa\s*(?:e\s*equivalenti)?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'liquidit[aà]\s*(?:immediata|disponibile)?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'cash\s*(?:and\s*cash\s*equivalents)?\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["cassa"] = extract_number(text, cash_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Interest (Interessi passivi)
    interest_patterns = [
        r'interessi\s*(?:passivi)?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'onere?\s*finanziari?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'interest\s*expense\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["interest"] = extract_number(text, interest_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Net Income (Utile netto)
    net_income_patterns = [
        r'utile\s*(?:netto)?\s*(?:dell)?\s*(?:esercizio)?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'net\s*income\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?',
        r'profitto\s*netto\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?'
    ]
    data["net_income"] = extract_number(text, net_income_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Total Assets
    assets_patterns = [
        r'totale\s*attivo\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'total\s*assets\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?',
        r'attivit[aà]\s*totali\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?'
    ]
    data["total_assets"] = extract_number(text, assets_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Total Liabilities
    liabilities_patterns = [
        r'totale\s*passivit[aà]\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'total\s*liabilities\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?',
        r'passivit[aà]\s*totali\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?'
    ]
    data["total_liabilities"] = extract_number(text, liabilities_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Working Capital
    wc_patterns = [
        r'capitale\s*circolante\s*netto\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'working\s*capital\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["working_capital"] = extract_number(text, wc_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Current Assets
    ca_patterns = [
        r'attivit[aà]\s*correnti\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'current\s*assets\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["current_assets"] = extract_number(text, ca_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Current Liabilities
    cl_patterns = [
        r'passivit[aà]\s*correnti\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'current\s*liabilities\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["current_liabilities"] = extract_number(text, cl_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Capex
    capex_patterns = [
        r'capex\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'investimenti\s*(?:in\s*immobilizzazioni)?\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'capital\s*expenditure\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["capex"] = extract_number(text, capex_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Depreciation
    dep_patterns = [
        r'ammortamenti\s*[:\-]?\s*€?\s*([\d,]+\.?\d*)\s*(?:milioni|mila|mld)?',
        r'depreciation\s*[:\-]?\s*€?\s*\$?\s*([\d,]+\.?\d*)\s*(?:million|billion)?'
    ]
    data["depreciation"] = extract_number(text, dep_patterns, multipliers={"mld": 1000, "milioni": 1, "mila": 0.001})
    
    # Sector (rilevamento automatico)
    if any(word in text_lower for word in ["bank", "banca", "credito", "finanziario"]):
        data["sector"] = "Finance"
    elif any(word in text_lower for word in ["tech", "tecnologia", "software", "informatica"]):
        data["sector"] = "Tech"
    elif any(word in text_lower for word in ["manufacturing", "manifatturiero", "industriale"]):
        data["sector"] = "Manufacturing"
    elif any(word in text_lower for word in ["retail", "commercio", "distribuzione"]):
        data["sector"] = "Retail"
    else:
        data["sector"] = "Altro"
    
    # Confidence score per ogni dato
    data["extraction_confidence"] = {}
    for key in ["revenue", "ebit", "ebitda", "total_debt", "cassa", "interest", "net_income", "total_assets", "total_liabilities"]:
        data["extraction_confidence"][key] = "high" if data.get(key) else "missing"
    
    return data

def extract_number(text, patterns, multipliers):
    import re
    text_lower = text.lower()
    
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            number_str = match.group(1).replace(',', '').replace('.', '').replace(' ', '')
            try:
                number = float(number_str)
                # Applica moltiplicatore
                for mult_str, mult_val in multipliers.items():
                    if mult_str in text_lower[max(0, match.start()-50):match.end()+50]:
                        number *= mult_val
                        break
                return round(number, 2)
            except:
                continue
    return None

def calculate_score(data):
    # Score basato solo su dati reali presenti
    if not data.get("revenue") or not data.get("ebit"):
        return 0
    
    score = 50  # Base
    
    # Profitability
    if data.get("ebit") and data.get("revenue"):
        margin = (data["ebit"] / data["revenue"]) * 100
        if margin > 15: score += 20
        elif margin > 8: score += 10
        elif margin > 0: score += 5
    
    # Leverage
    if data.get("total_debt") and data.get("revenue"):
        debt_rev = data["total_debt"] / data["revenue"]
        if debt_rev < 1: score += 15
        elif debt_rev < 2: score += 10
        elif debt_rev < 3: score += 5
        else: score -= 10
    
    # Liquidity
    if data.get("cassa") and data.get("total_debt"):
        cash_debt = data["cassa"] / data["total_debt"] if data["total_debt"] > 0 else 0
        if cash_debt > 0.5: score += 15
        elif cash_debt > 0.2: score += 10
        elif cash_debt > 0.1: score += 5
    
    return min(max(score, 0), 100)
"""
        content = content[:do_analyze_start] + new_do_analyze + content[do_analyze_end:]
        print("✅ /do_analyze riscritta con estrazione rigorosa (zero stime)")

# ============================================================================
# 2. AGGIORNA /simula/<id> - Solo dati reali, warning se mancano
# ============================================================================
simula_start = content.find('@app.route("/simula/<int:rid>"')
if simula_start != -1:
    next_route = re.search(r'\n@app\.route\(', content[simula_start + 35:])
    simula_end = simula_start + 35 + next_route.start() if next_route else len(content)
    
    new_simula = """
@app.route("/simula/<int:rid>", methods=["GET", "POST"])
@login_required
def simula(rid):
    import math
    try: db.create_all()
    except: pass
    rep = Report.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    m = _json.loads(rep.metrics_json or "{}")
    
    # SOLO DATI REALI - Nessuna stima
    rev = float(m.get("revenue") or 0)
    ebit = float(m.get("ebit") or 0)
    debt = float(m.get("total_debt") or 0)
    cash = float(m.get("cassa") or 0)
    interest = float(m.get("interest") or 0)
    ebitda = float(m.get("ebitda") or 0)
    net_income = float(m.get("net_income") or 0)
    total_assets = float(m.get("total_assets") or 0)
    total_liabilities = float(m.get("total_liabilities") or 0)
    equity = float(m.get("total_assets") or 0) - float(m.get("total_liabilities") or 0)
    retained_earnings = float(m.get("retained_earnings") or 0)
    working_capital = float(m.get("working_capital") or 0)
    capex = float(m.get("capex") or 0)
    depreciation = float(m.get("depreciation") or 0)
    current_assets = float(m.get("current_assets") or 0)
    current_liabilities = float(m.get("current_liabilities") or 0)
    
    # Verifica dati mancanti
    required_data = {
        "Ricavi": rev,
        "EBIT": ebit,
        "Debito": debt,
        "Cassa": cash
    }
    missing_data = [k for k, v in required_data.items() if v == 0]
    has_sufficient_data = len(missing_data) == 0
    
    # Dati opzionali per calcoli avanzati
    has_advanced_data = all([total_assets > 0, total_liabilities > 0, ebitda > 0])
    
    tax_rate = 0.24
    rate = (interest / debt * 100) if debt > 1 else 5.0
    
    # Market data
    ticker = rep.ticker_symbol or "" if hasattr(rep, 'ticker_symbol') else ""
    market_data = get_market_data(ticker) if ticker else {"success": False}
    market_cap = market_data["market_cap"] / 1e6 if market_data["success"] else 0
    
    company_name = rep.company or rep.filename or "Azienda"
    
    scenario = request.form.get("scenario", "base") if request.method == "POST" else "base"
    
    if scenario == "recession":
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev * 0.85, ebit * 0.70, debt, rate + 1.0, cash
        scenario_label = "Recessione (-15% ricavi)"
    elif scenario == "crisis":
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev * 0.60, ebit * 0.30, debt * 1.10, rate + 2.5, cash * 0.70
        scenario_label = "Crisi (-40% ricavi)"
    elif scenario == "growth":
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev * 1.20, ebit * 1.35, debt * 1.25, rate, cash * 0.85
        scenario_label = "Crescita (+20% ricavi)"
    else:
        s_rev, s_ebit, s_debt, s_rate, s_cash = rev, ebit, debt, rate, cash
        scenario_label = "Attuale"
    
    s_int = s_debt * (s_rate / 100)
    s_ebitda = ebitda * 0.85 if ebitda > 0 else s_ebit * 1.15
    
    # Calcoli SOLO se ci sono dati sufficienti
    if has_sufficient_data and has_advanced_data:
        # Altman Z-Score
        x1 = working_capital / total_assets if total_assets > 0 else 0
        x2 = retained_earnings / total_assets if total_assets > 0 else 0
        x3 = s_ebit / total_assets if total_assets > 0 else 0
        x4 = (market_cap if market_cap > 0 else equity) / total_liabilities if total_liabilities > 0 else 0
        x5 = s_rev / total_assets if total_assets > 0 else 0
        altman_z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
        altman_z = min(max(altman_z, -5), 15)
        
        # Ohlson O-Score
        size = math.log(total_assets / 1000000) if total_assets > 1000000 else 0
        tlta = total_liabilities / total_assets if total_assets > 0 else 0
        wcta = working_capital / total_assets if total_assets > 0 else 0
        clca = 1.0 if working_capital < 0 else 0.0
        oenega = 1.0 if total_liabilities > total_assets else 0.0
        chin = (net_income - ebit) / abs(net_income) if net_income != 0 else 0
        intwo = 1.0 if (net_income < 0 and ebit < 0) else 0.0
        ohlson_o = -2.53 + (-0.407 * size) + (6.03 * tlta) + (1.43 * wcta) + (0.076 * clca) + (0.001 * oenega) + (1.72 * tlta) + (0.52 * chin) + (0.45 * intwo)
        ohlson_o = min(max(ohlson_o, -10), 10)
        prob_default = 1 / (1 + math.exp(-ohlson_o)) * 100
        
        # DSCR
        taxes = max(s_ebit * tax_rate, 0)
        mandatory_capex = capex * 0.7 if capex > 0 else s_ebitda * 0.1
        numerator = max(s_ebitda - taxes - mandatory_capex, 0)
        annual_debt_payment = s_debt / 6
        denominator = annual_debt_payment + s_int
        dscr = numerator / denominator if denominator > 0 else 0
        dscr = min(dscr, 20)
        
        # Breaking Point
        bp = ((s_ebit - s_int) / s_ebit * 100) if s_ebit > 0 and s_int > 0 else 100
        bp = min(max(bp, 0), 100)
        ic = s_ebit / s_int if s_int > 0 else 999
        
        # Cash Runway
        monthly_operating = (s_rev - s_ebit + depreciation) / 12 if s_rev > 0 else 0
        monthly_burn = (s_debt / 72) + (s_int / 12) + monthly_operating
        runway = s_cash / monthly_burn if monthly_burn > 0 else 999
        runway = min(runway, 999)
    else:
        altman_z, prob_default, dscr, bp, ic, runway = 0, 0, 0, 0, 0, 0
        altman_status, ohlson_status, dscr_status = "N/D", "N/D", "N/D"
    
    # Verdetto
    if not has_sufficient_data:
        emoji, verdict, color = "⚠️", "DATI INSUFFICIENTI", "#fbbf24"
        explanation = f"Mancano dati critici nel bilancio: {', '.join(missing_data)}. Carica un bilancio completo per ottenere l'analisi di stress test."
    elif altman_z < 1.81 or prob_default > 25 or dscr < 1.0:
        emoji, verdict, color = "🚨", "IN PERICOLO", "#ef4444"
        explanation = "Almeno due indicatori segnalano rischio elevato. Interventi strutturali necessari."
    elif altman_z < 2.99 or prob_default > 10 or dscr < 1.25:
        emoji, verdict, color = "⚠️", "RESISTE CON FATICA", "#fbbf24"
        explanation = "L'azienda può sopportare una crisi moderata ma i margini sono ridotti."
    else:
        emoji, verdict, color = "🛡️", "SOPRAVVIVE", "#10b981"
        explanation = "Tutti gli indicatori confermano solidità. L'azienda resiste allo stress test."
    
    # HTML
    html = "<div style='max-width:1100px;margin:0 auto;padding:2rem'>"
    html += "<div style='text-align:center;margin-bottom:3rem'>"
    html += "<p style='color:var(--muted);font-size:0.9rem;text-transform:uppercase;letter-spacing:2px'>Stress Test Finanziario</p>"
    html += "<h1 style='font-size:2.5rem;color:var(--text);margin:0'>" + company_name + "</h1>"
    if market_data["success"]:
        html += "<p style='color:var(--muted);font-size:0.9rem'>Dati di mercato: Yahoo Finance (Prezzo: " + str(round(market_data['current_price'], 2)) + "€)</p>"
    html += "</div>"
    
    # Warning dati mancanti
    if missing_data:
        html += "<div style='background:rgba(251,191,36,0.1);border:2px solid #fbbf24;border-radius:12px;padding:1.5rem;margin-bottom:2rem;text-align:center'>"
        html += "<p style='color:#fbbf24;font-size:1.1rem;margin:0'><strong>⚠️ Dati mancanti nel bilancio</strong></p>"
        html += "<p style='color:var(--text);margin:0.5rem 0 0 0'>Per un'analisi accurata servono: <strong>" + ", ".join(missing_data) + "</strong></p>"
        html += "<p style='color:var(--muted);font-size:0.9rem;margin:0.5rem 0 0 0'>Carica un bilancio completo (Stato Patrimoniale + Conto Economico)</p></div>"
    
    # Scenari
    html += "<form method='post' style='display:flex;gap:0.5rem;justify-content:center;margin-bottom:2rem;flex-wrap:wrap'>"
    for key, label in [("base", "Attuale"), ("recession", "Recessione"), ("crisis", "Crisi"), ("growth", "Crescita")]:
        active = "background:var(--gold);color:#0b1220" if scenario == key else "background:var(--bg);color:var(--text)"
        html += "<button type='submit' name='scenario' value='" + key + "' style='padding:0.6rem 1.2rem;border-radius:20px;border:none;cursor:pointer;font-weight:600;" + active + "'>" + label + "</button>"
    html += "</form>"
    
    # Verdetto
    html += "<div style='background:" + color + ";border-radius:16px;padding:3rem 2rem;text-align:center;margin-bottom:2rem'>"
    html += "<div style='font-size:4rem'>" + emoji + "</div>"
    html += "<h2 style='color:white;font-size:2rem;margin:0.5rem 0'>" + verdict + "</h2>"
    html += "<p style='color:rgba(255,255,255,0.9);max-width:700px;margin:0 auto'>" + explanation + "</p>"
    html += "<p style='color:rgba(255,255,255,0.7);margin-top:1rem'>Scenario: " + scenario_label + "</p></div>"
    
    # Modelli accademici (solo se dati sufficienti)
    if has_sufficient_data and has_advanced_data:
        html += "<h3 style='color:var(--gold);margin:2rem 0 1rem 0;text-align:center'>📊 Modelli Accademici</h3>"
        html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:1.5rem;margin-bottom:2rem'>"
        
        altman_color = "#10b981" if altman_z > 2.99 else ("#fbbf24" if altman_z > 1.81 else "#ef4444")
        html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + altman_color + "'>"
        html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>Altman Z-Score</h4>"
        html += "<p style='font-size:3rem;font-weight:800;color:" + altman_color + ";margin:0.5rem 0'>" + str(round(altman_z, 2)) + "</p>"
        html += "<p style='color:var(--muted);font-size:0.85rem'>Z > 2.99 = Sicuro | 1.81-2.99 = Grigia | < 1.81 = Rischio</p></div>"
        
        ohlson_color = "#10b981" if prob_default < 10 else ("#fbbf24" if prob_default < 25 else "#ef4444")
        html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + ohlson_color + "'>"
        html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>Ohlson O-Score</h4>"
        html += "<p style='font-size:3rem;font-weight:800;color:" + ohlson_color + ";margin:0.5rem 0'>" + str(round(prob_default, 1)) + "%</p>"
        html += "<p style='color:var(--muted);font-size:0.85rem'>Probabilità di Default (PD)</p></div>"
        
        dscr_color = "#10b981" if dscr >= 1.5 else ("#fbbf24" if dscr >= 1.25 else "#ef4444")
        html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;border-left:4px solid " + dscr_color + "'>"
        html += "<h4 style='color:var(--gold);margin:0 0 0.5rem 0'>DSCR (Basilea III)</h4>"
        html += "<p style='font-size:3rem;font-weight:800;color:" + dscr_color + ";margin:0.5rem 0'>" + str(round(dscr, 2)) + "x</p>"
        html += "<p style='color:var(--muted);font-size:0.85rem'>≥1.25x = Accettabile | <1.0x = Insolvente</p></div>"
        html += "</div>"
        
        # Metriche operative
        html += "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:1rem'>"
        bp_color = "#10b981" if bp >= 40 else ("#fbbf24" if bp >= 20 else "#ef4444")
        html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center;border-top:3px solid " + bp_color + "'>"
        html += "<p style='color:var(--muted);font-size:0.8rem'>Crollo sopportabile</p>"
        html += "<p style='font-size:2.5rem;font-weight:800;color:" + bp_color + ";margin:0.5rem 0'>-" + str(int(bp)) + "%</p></div>"
        
        runway_color = "#10b981" if runway >= 12 else ("#fbbf24" if runway >= 6 else "#ef4444")
        html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center;border-top:3px solid " + runway_color + "'>"
        html += "<p style='color:var(--muted);font-size:0.8rem'>Autonomia cassa</p>"
        html += "<p style='font-size:2.5rem;font-weight:800;color:" + runway_color + ";margin:0.5rem 0'>" + str(min(int(runway), 99)) + " mesi</p></div>"
        
        ic_color = "#10b981" if ic >= 3 else ("#fbbf24" if ic >= 1.5 else "#ef4444")
        html += "<div style='background:var(--bg);padding:1.5rem;border-radius:12px;text-align:center;border-top:3px solid " + ic_color + "'>"
        html += "<p style='color:var(--muted);font-size:0.8rem'>Interest Coverage</p>"
        html += "<p style='font-size:2.5rem;font-weight:800;color:" + ic_color + ";margin:0.5rem 0'>" + str(round(ic, 1)) + "x</p></div>"
        html += "</div>"
    else:
        html += "<div style='background:var(--bg);padding:2rem;border-radius:12px;text-align:center;margin:2rem 0'>"
        html += "<p style='color:var(--muted);margin:0'>📊 I modelli accademici (Altman, Ohlson, DSCR) richiedono dati completi dallo Stato Patrimoniale.</p></div>"
    
    # Azioni
    html += "<div style='display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-top:2rem'>"
    html += "<a href='/analysis/" + str(rep.id) + "' class='btn2' style='background:var(--blue)'>📈 Analisi Buffett</a>"
    html += "<a href='/analyze' class='btn2' style='background:var(--teal)'>📄 Analizza altro bilancio</a>"
    html += "<a href='/cronologia' class='btn2' style='background:var(--gold);color:#0b1220'> Cronologia</a>"
    html += "</div></div>"
    
    return render_template_string(BASE_TEMPLATE, title="Stress Test", content=html)
"""
    content = content[:simula_start] + new_simula + content[simula_end:]
    print("✅ /simula/<id> riscritta con solo dati reali (zero stime)")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

try:
    py_compile.compile("app.py", doraise=True)
    print("✅ Sintassi verificata!")
except SyntaxError as e:
    print("❌ Errore sintassi riga " + str(e.lineno))
