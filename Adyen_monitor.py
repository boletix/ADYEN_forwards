#!/usr/bin/env python3
"""
Adyen Investment Monitor — Leading Indicators Dashboard
========================================================
Tracks pre-earnings indicators for Adyen (ADYEN.AS) ahead of Q1 2026 Business Update (May 5, 2026).
Run daily via cron: 0 18 * * * python3 /path/to/adyen_monitor.py

Data sources (all free):
  - yfinance: stock prices, FX, volumes
  - Derived: valuation multiples, relative performance, signal scoring

Outputs:
  - data/snapshot_YYYY-MM-DD.json  (daily archive)
  - data/latest.json               (current state)
  - index.html                     (self-contained dashboard)
"""

import json
import os
import datetime
import sys

try:
    import yfinance as yf
except ImportError:
    print("ERROR: pip install yfinance --break-system-packages")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TODAY = datetime.date.today().isoformat()
LOOKBACK_DAYS = 90
START_DATE = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()

# Adyen financials (from H2 2025 report — update after each earnings)
ADYEN_SHARES_OUT = 31.54e6       # shares outstanding
ADYEN_FCF_TTM = 1.10e9           # trailing 12m FCF (EUR) — approx from reports
ADYEN_EBITDA_TTM = 1.25e9        # trailing 12m EBITDA (EUR)
ADYEN_NET_REVENUE_TTM = 2.36e9   # trailing 12m net revenue (EUR)
ADYEN_NET_CASH = 7.0e9           # net cash position (EUR) — approx

# Tickers to track
TICKERS = {
    # Core
    "ADYEN.AS":  {"name": "Adyen",          "category": "core"},
    # APAC drag proxies
    "PDD":       {"name": "PDD (Temu)",     "category": "apac_drag"},
    # E-commerce health
    "SHOP":      {"name": "Shopify",        "category": "ecom_health"},
    # Card networks (cross-border proxy)
    "V":         {"name": "Visa",           "category": "card_networks"},
    "MA":        {"name": "Mastercard",     "category": "card_networks"},
    # Competitors
    "PYPL":      {"name": "PayPal",         "category": "competitors"},
    "SQ":        {"name": "Block (Square)", "category": "competitors"},
    "GPN":       {"name": "Global Payments","category": "competitors"},
    "WLN.PA":    {"name": "Worldline",      "category": "competitors"},
    # FX
    "EURUSD=X":  {"name": "EUR/USD",        "category": "fx"},
}

# Adyen-specific thresholds for signal scoring
SIGNALS = {
    "adyen_price_vs_target": {"bull": 1426, "bear": 824, "desc": "Precio vs target analistas (€1,426)"},
    "pdd_30d_return":        {"bull": 0.0, "bear": -0.15, "desc": "PDD 30d return (proxy Temu health)"},
    "eurusd":                {"bull": 1.12, "bear": 1.06, "desc": "EUR/USD (>1.12 = FX headwind)"},
    "visa_30d_return":       {"bull": 0.02, "bear": -0.03, "desc": "Visa 30d return (cross-border proxy)"},
    "shop_30d_return":       {"bull": 0.05, "bear": -0.05, "desc": "Shopify 30d (e-com health)"},
    "adyen_ev_fcf":          {"bull": 20, "bear": 30, "desc": "EV/FCF (lower = cheaper)"},
}

# ─────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────
def fetch_prices(ticker: str, start: str, end: str) -> dict:
    """Fetch OHLCV data from yfinance, return as serializable dict."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return {"error": f"No data for {ticker}"}
        
        # Handle MultiIndex columns from yfinance
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)
        
        last = df.iloc[-1]
        first = df.iloc[0]
        high = float(df["High"].max())
        low = float(df["Low"].min())
        
        # 30-day return
        if len(df) >= 22:
            price_30d_ago = float(df.iloc[-22]["Close"])
            ret_30d = (float(last["Close"]) - price_30d_ago) / price_30d_ago
        else:
            ret_30d = None
        
        # 7-day return
        if len(df) >= 5:
            price_7d_ago = float(df.iloc[-5]["Close"])
            ret_7d = (float(last["Close"]) - price_7d_ago) / price_7d_ago
        else:
            ret_7d = None
        
        total_return = (float(last["Close"]) - float(first["Close"])) / float(first["Close"])
        
        # Price history for sparkline (last 60 data points)
        hist = df["Close"].tail(60)
        history = [{"date": d.strftime("%Y-%m-%d"), "price": round(float(p), 2)} for d, p in hist.items()]
        
        return {
            "price": round(float(last["Close"]), 2),
            "date": df.index[-1].strftime("%Y-%m-%d"),
            "high_period": round(high, 2),
            "low_period": round(low, 2),
            "return_period": round(total_return * 100, 2),
            "return_30d": round(ret_30d * 100, 2) if ret_30d else None,
            "return_7d": round(ret_7d * 100, 2) if ret_7d else None,
            "avg_volume": int(df["Volume"].tail(20).mean()) if "Volume" in df.columns else None,
            "history": history,
        }
    except Exception as e:
        return {"error": str(e)}


def compute_adyen_valuation(price: float) -> dict:
    """Compute Adyen valuation multiples from current price."""
    market_cap = price * ADYEN_SHARES_OUT
    ev = market_cap - ADYEN_NET_CASH
    
    return {
        "market_cap_eur_b": round(market_cap / 1e9, 2),
        "ev_eur_b": round(ev / 1e9, 2),
        "ev_fcf": round(ev / ADYEN_FCF_TTM, 1),
        "ev_ebitda": round(ev / ADYEN_EBITDA_TTM, 1),
        "ev_revenue": round(ev / ADYEN_NET_REVENUE_TTM, 1),
        "fcf_yield_pct": round((ADYEN_FCF_TTM / market_cap) * 100, 2),
        "price_to_analyst_target": round((1426 / price - 1) * 100, 1),
    }


def score_signals(data: dict) -> list:
    """Score each leading indicator as bull/neutral/bear."""
    results = []
    
    adyen = data.get("ADYEN.AS", {})
    pdd = data.get("PDD", {})
    eurusd = data.get("EURUSD=X", {})
    visa = data.get("V", {})
    shop = data.get("SHOP", {})
    valuation = data.get("_valuation", {})
    
    def classify(value, bull_threshold, bear_threshold, invert=False):
        if value is None:
            return "no_data"
        if not invert:
            if value >= bull_threshold: return "bull"
            if value <= bear_threshold: return "bear"
        else:  # lower is better (e.g., EV/FCF)
            if value <= bull_threshold: return "bull"
            if value >= bear_threshold: return "bear"
        return "neutral"
    
    # 1. Adyen price vs analyst target
    adyen_price = adyen.get("price")
    if adyen_price:
        results.append({
            "name": "Adyen precio vs target €1,426",
            "value": f"€{adyen_price}",
            "detail": f"Upside: {round((1426/adyen_price - 1)*100, 1)}%",
            "signal": "bull" if adyen_price < 1000 else ("bear" if adyen_price > 1400 else "neutral"),
            "category": "valuation",
        })
    
    # 2. PDD 30d return (Temu health → APAC drag)
    pdd_ret = pdd.get("return_30d")
    if pdd_ret is not None:
        results.append({
            "name": "PDD (Temu) — 30d return",
            "value": f"{pdd_ret:+.1f}%",
            "detail": "Proxy salud retailers APAC → drag Adyen",
            "signal": classify(pdd_ret / 100, 0.0, -0.15),
            "category": "apac_drag",
        })
    
    # 3. EUR/USD
    fx = eurusd.get("price")
    if fx:
        results.append({
            "name": "EUR/USD",
            "value": f"{fx:.4f}",
            "detail": ">1.12 = FX headwind para Adyen (reporta en EUR)",
            "signal": "bear" if fx > 1.12 else ("bull" if fx < 1.06 else "neutral"),
            "category": "fx",
        })
    
    # 4. Visa 30d (cross-border volumes)
    visa_ret = visa.get("return_30d")
    if visa_ret is not None:
        results.append({
            "name": "Visa — 30d return",
            "value": f"{visa_ret:+.1f}%",
            "detail": "Proxy volúmenes cross-border internacionales",
            "signal": classify(visa_ret / 100, 0.02, -0.03),
            "category": "ecom_health",
        })
    
    # 5. Mastercard 30d
    ma = data.get("MA", {})
    ma_ret = ma.get("return_30d")
    if ma_ret is not None:
        results.append({
            "name": "Mastercard — 30d return",
            "value": f"{ma_ret:+.1f}%",
            "detail": "Proxy volúmenes cross-border",
            "signal": classify(ma_ret / 100, 0.02, -0.03),
            "category": "ecom_health",
        })
    
    # 6. Shopify 30d (e-com health & Stripe proxy)
    shop_ret = shop.get("return_30d")
    if shop_ret is not None:
        results.append({
            "name": "Shopify — 30d return",
            "value": f"{shop_ret:+.1f}%",
            "detail": "Salud e-commerce + proxy volumen Stripe",
            "signal": classify(shop_ret / 100, 0.05, -0.05),
            "category": "ecom_health",
        })
    
    # 7. EV/FCF
    ev_fcf = valuation.get("ev_fcf")
    if ev_fcf:
        results.append({
            "name": "Adyen EV/FCF",
            "value": f"{ev_fcf}x",
            "detail": f"FCF yield: {valuation.get('fcf_yield_pct', '?')}%",
            "signal": classify(ev_fcf, 20, 30, invert=True),
            "category": "valuation",
        })
    
    # 8. Worldline relative (legacy competitor health)
    wln = data.get("WLN.PA", {})
    wln_ret = wln.get("return_30d")
    if wln_ret is not None:
        results.append({
            "name": "Worldline — 30d return",
            "value": f"{wln_ret:+.1f}%",
            "detail": "Legacy competitor — si cae, ¿flujo hacia Adyen?",
            "signal": "bull" if wln_ret < -5 else ("bear" if wln_ret > 10 else "neutral"),
            "category": "competitors",
        })
    
    # 9. PayPal relative
    pypl = data.get("PYPL", {})
    pypl_ret = pypl.get("return_30d")
    if pypl_ret is not None:
        results.append({
            "name": "PayPal — 30d return",
            "value": f"{pypl_ret:+.1f}%",
            "detail": "Competitor directo (Braintree enterprise)",
            "signal": "neutral",
            "category": "competitors",
        })

    # 10. Adyen own momentum
    adyen_ret_7d = adyen.get("return_7d")
    if adyen_ret_7d is not None:
        results.append({
            "name": "Adyen — momentum 7d",
            "value": f"{adyen_ret_7d:+.1f}%",
            "detail": "¿El mercado anticipa algo antes del Q1 update?",
            "signal": classify(adyen_ret_7d / 100, 0.03, -0.03),
            "category": "core",
        })
    
    return results


# ─────────────────────────────────────────────────────────────────────
# DASHBOARD GENERATION
# ─────────────────────────────────────────────────────────────────────
def generate_dashboard(snapshot: dict):
    """Generate self-contained HTML dashboard from snapshot data."""
    
    signals = snapshot["signals"]
    tickers_data = snapshot["tickers"]
    valuation = snapshot["valuation"]
    
    # Count signals
    n_bull = sum(1 for s in signals if s["signal"] == "bull")
    n_bear = sum(1 for s in signals if s["signal"] == "bear")
    n_neutral = sum(1 for s in signals if s["signal"] == "neutral")
    
    # Overall sentiment
    score = n_bull - n_bear
    if score >= 3: sentiment = "BULLISH"
    elif score <= -3: sentiment = "BEARISH"
    else: sentiment = "NEUTRAL"
    
    sentiment_color = {"BULLISH": "#1D9E75", "BEARISH": "#E24B4A", "NEUTRAL": "#BA7517"}[sentiment]
    
    # Build signal rows HTML
    signal_rows = ""
    for s in signals:
        sig_class = {"bull": "sig-bull", "bear": "sig-bear", "neutral": "sig-neutral", "no_data": "sig-none"}[s["signal"]]
        sig_icon = {"bull": "&#9650;", "bear": "&#9660;", "neutral": "&#9679;", "no_data": "?"}[s["signal"]]
        signal_rows += f"""
        <tr>
          <td><span class="sig-dot {sig_class}">{sig_icon}</span></td>
          <td class="sig-name">{s['name']}</td>
          <td class="sig-value">{s['value']}</td>
          <td class="sig-detail">{s['detail']}</td>
        </tr>"""
    
    # Build sparkline data for Adyen
    adyen_hist = tickers_data.get("ADYEN.AS", {}).get("history", [])
    adyen_sparkline_data = json.dumps([h["price"] for h in adyen_hist])
    adyen_sparkline_dates = json.dumps([h["date"] for h in adyen_hist])
    
    # Build competitor comparison rows
    comp_rows = ""
    for ticker_id in ["ADYEN.AS", "PDD", "SHOP", "V", "MA", "PYPL", "WLN.PA", "GPN"]:
        td = tickers_data.get(ticker_id, {})
        meta = TICKERS.get(ticker_id, {})
        if "error" in td:
            continue
        ret30 = td.get("return_30d")
        ret_class = "pos" if ret30 and ret30 > 0 else "neg"
        comp_rows += f"""
        <tr>
          <td class="comp-name">{meta.get('name', ticker_id)}</td>
          <td>{td.get('price', '?')}</td>
          <td class="{ret_class}">{f'{ret30:+.1f}%' if ret30 is not None else '—'}</td>
          <td class="{('pos' if td.get('return_period',0) > 0 else 'neg')}">{td.get('return_period', '?')}%</td>
        </tr>"""
    
    # Key dates
    days_to_q1 = (datetime.date(2026, 5, 5) - datetime.date.today()).days
    days_to_q1_text = f"{days_to_q1} días" if days_to_q1 > 0 else "HOY" if days_to_q1 == 0 else "PASADO"
    
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Adyen Monitor — Leading Indicators</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #0a0a0f;
  --surface: #12121a;
  --surface-2: #1a1a26;
  --border: rgba(255,255,255,0.06);
  --text: #e8e6e1;
  --text-2: #8a8880;
  --text-3: #5a5850;
  --green: #1D9E75;
  --red: #E24B4A;
  --amber: #BA7517;
  --blue: #3266ad;
  --purple: #7F77DD;
  --font: 'DM Sans', -apple-system, sans-serif;
  --mono: 'JetBrains Mono', monospace;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}}
.header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--border);
}}
.header h1 {{
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}}
.header h1 span {{ color: var(--blue); }}
.header-meta {{
  text-align: right;
  font-size: 0.8rem;
  color: var(--text-2);
  font-family: var(--mono);
}}
.countdown {{
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  font-weight: 500;
  color: var(--amber);
  margin-top: 4px;
}}

/* Metric cards */
.metrics {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 2rem;
}}
.metric {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
}}
.metric-label {{ font-size: 0.75rem; color: var(--text-2); text-transform: uppercase; letter-spacing: 0.05em; }}
.metric-value {{ font-size: 1.5rem; font-weight: 700; font-family: var(--mono); margin-top: 4px; }}
.metric-sub {{ font-size: 0.75rem; color: var(--text-3); margin-top: 2px; font-family: var(--mono); }}

/* Sentiment badge */
.sentiment {{
  display: inline-block;
  padding: 6px 16px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.05em;
  background: {sentiment_color}22;
  color: {sentiment_color};
  border: 1px solid {sentiment_color}44;
}}

/* Signal table */
.section-title {{
  font-size: 1rem;
  font-weight: 700;
  margin: 2rem 0 1rem;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.section-title::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}}
th {{
  text-align: left;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-3);
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}}
td {{
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}}
.sig-dot {{
  display: inline-block;
  width: 24px;
  text-align: center;
  font-size: 0.7rem;
}}
.sig-bull {{ color: var(--green); }}
.sig-bear {{ color: var(--red); }}
.sig-neutral {{ color: var(--amber); font-size: 0.5rem; }}
.sig-none {{ color: var(--text-3); }}
.sig-name {{ font-weight: 500; }}
.sig-value {{ font-family: var(--mono); font-weight: 500; }}
.sig-detail {{ color: var(--text-2); font-size: 0.8rem; }}
.pos {{ color: var(--green); font-family: var(--mono); }}
.neg {{ color: var(--red); font-family: var(--mono); }}
.comp-name {{ font-weight: 500; }}

/* Sparkline */
.chart-container {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 2rem;
  height: 220px;
  position: relative;
}}

/* Footer */
.footer {{
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
  font-size: 0.75rem;
  color: var(--text-3);
  display: flex;
  justify-content: space-between;
}}
.footer a {{ color: var(--blue); text-decoration: none; }}

/* Key dates */
.key-dates {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 2rem;
}}
.key-date {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}}
.key-date-label {{ font-size: 0.8rem; color: var(--text-2); }}
.key-date-value {{ font-family: var(--mono); font-size: 0.85rem; font-weight: 500; }}

@media (max-width: 600px) {{
  body {{ padding: 1rem; }}
  .metrics {{ grid-template-columns: 1fr 1fr; }}
  .header {{ flex-direction: column; gap: 1rem; }}
  .header-meta {{ text-align: left; }}
}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1><span>ADYEN</span> Investment Monitor</h1>
    <p style="color: var(--text-2); font-size: 0.85rem; margin-top: 4px;">Leading indicators · Pre-Q1 2026 Business Update</p>
  </div>
  <div class="header-meta">
    <div>Última actualización: {snapshot['timestamp']}</div>
    <div class="countdown">Q1 Update: {days_to_q1_text}</div>
  </div>
</div>

<!-- Key metrics -->
<div class="metrics">
  <div class="metric">
    <div class="metric-label">Precio Adyen</div>
    <div class="metric-value">€{tickers_data.get('ADYEN.AS', {}).get('price', '?')}</div>
    <div class="metric-sub">Target analistas: €1,426</div>
  </div>
  <div class="metric">
    <div class="metric-label">EV/FCF</div>
    <div class="metric-value">{valuation.get('ev_fcf', '?')}x</div>
    <div class="metric-sub">FCF yield: {valuation.get('fcf_yield_pct', '?')}%</div>
  </div>
  <div class="metric">
    <div class="metric-label">Upside a target</div>
    <div class="metric-value" style="color: var(--green);">+{valuation.get('price_to_analyst_target', '?')}%</div>
    <div class="metric-sub">€{valuation.get('market_cap_eur_b', '?')}B mkt cap</div>
  </div>
  <div class="metric">
    <div class="metric-label">Sentimiento indicadores</div>
    <div class="metric-value"><span class="sentiment">{sentiment}</span></div>
    <div class="metric-sub">{n_bull}&#9650; {n_neutral}&#9679; {n_bear}&#9660;</div>
  </div>
  <div class="metric">
    <div class="metric-label">EUR/USD</div>
    <div class="metric-value">{tickers_data.get('EURUSD=X', {}).get('price', '?')}</div>
    <div class="metric-sub">FX impact en reported revenue</div>
  </div>
  <div class="metric">
    <div class="metric-label">PDD (Temu) 30d</div>
    <div class="metric-value" style="color: {'var(--green)' if (pdd_ret := tickers_data.get('PDD', {}).get('return_30d')) and pdd_ret > 0 else 'var(--red)'};">{f'{pdd_ret:+.1f}%' if pdd_ret is not None else '—'}</div>
    <div class="metric-sub">Proxy drag APAC</div>
  </div>
</div>

<!-- Adyen price chart -->
<div class="section-title">Adyen — evolución de precio (últimos 60 sesiones)</div>
<div class="chart-container">
  <canvas id="sparkline"></canvas>
</div>

<!-- Key upcoming dates -->
<div class="section-title">Fechas clave</div>
<div class="key-dates">
  <div class="key-date">
    <span class="key-date-label">PDD Earnings</span>
    <span class="key-date-value">~May 2026</span>
  </div>
  <div class="key-date">
    <span class="key-date-label">Adyen Q1 Update</span>
    <span class="key-date-value" style="color: var(--amber);">May 5, 2026</span>
  </div>
  <div class="key-date">
    <span class="key-date-label">Shopify Q1 Earnings</span>
    <span class="key-date-value">~May 2026</span>
  </div>
  <div class="key-date">
    <span class="key-date-label">Adyen H1 2026 Earnings</span>
    <span class="key-date-value">Aug 13, 2026</span>
  </div>
</div>

<!-- Signals table -->
<div class="section-title">Indicadores adelantados — scoring</div>
<table>
  <thead>
    <tr>
      <th style="width:40px;">Señal</th>
      <th>Indicador</th>
      <th>Valor</th>
      <th>Contexto</th>
    </tr>
  </thead>
  <tbody>
    {signal_rows}
  </tbody>
</table>

<!-- Comparables -->
<div class="section-title">Comparables — rendimiento relativo</div>
<table>
  <thead>
    <tr>
      <th>Empresa</th>
      <th>Precio</th>
      <th>30d</th>
      <th>{LOOKBACK_DAYS}d</th>
    </tr>
  </thead>
  <tbody>
    {comp_rows}
  </tbody>
</table>

<!-- Checklist -->
<div class="section-title">Checklist pre-Q1 Update (5 mayo)</div>
<div style="background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; font-size: 0.85rem; line-height: 2;">
  <div>&#9744; ¿PDD reporta GMV EE.UU. estable o en recuperación?</div>
  <div>&#9744; ¿Aranceles US-China se relajan o se endurecen? (de minimis status)</div>
  <div>&#9744; ¿Visa/MA reportan cross-border volumes creciendo?</div>
  <div>&#9744; ¿Shopify GMV confirma e-com sano? (si sí, problema de Adyen = share loss)</div>
  <div>&#9744; ¿EUR/USD se mantiene &lt;1.10 o sube? (FX headwind)</div>
  <div>&#9744; ¿Adyen Q1 net revenue growth &gt;20% cc? → tesis "bache temporal" intacta</div>
  <div>&#9744; ¿Volumen POS in-store crece &gt;25%? → moat omnicanal confirmado</div>
  <div>&#9744; ¿Noticias de merchants grandes migrando a Checkout.com?</div>
</div>

<div class="footer">
  <div>Datos: Yahoo Finance (yfinance) · No es consejo de inversión</div>
  <div>Generado: {snapshot['timestamp']} · <a href="data/latest.json">JSON</a></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const prices = {adyen_sparkline_data};
const dates = {adyen_sparkline_dates};
const ctx = document.getElementById('sparkline').getContext('2d');

const gradient = ctx.createLinearGradient(0, 0, 0, 200);
gradient.addColorStop(0, 'rgba(50, 102, 173, 0.3)');
gradient.addColorStop(1, 'rgba(50, 102, 173, 0.0)');

new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: dates,
    datasets: [{{
      data: prices,
      borderColor: '#3266ad',
      backgroundColor: gradient,
      fill: true,
      tension: 0.3,
      pointRadius: 0,
      pointHitRadius: 10,
      borderWidth: 2,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: '#1a1a26',
        titleColor: '#8a8880',
        bodyColor: '#e8e6e1',
        bodyFont: {{ family: "'JetBrains Mono'" }},
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        callbacks: {{
          label: (ctx) => '€' + ctx.raw.toFixed(2)
        }}
      }}
    }},
    scales: {{
      x: {{
        display: true,
        ticks: {{ color: '#5a5850', maxTicksLimit: 8, font: {{ size: 10, family: "'JetBrains Mono'" }} }},
        grid: {{ color: 'rgba(255,255,255,0.03)' }}
      }},
      y: {{
        display: true,
        ticks: {{ color: '#5a5850', callback: v => '€' + v, font: {{ size: 10, family: "'JetBrains Mono'" }} }},
        grid: {{ color: 'rgba(255,255,255,0.03)' }}
      }}
    }}
  }}
}});
</script>

</body>
</html>"""
    
    return html


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[{TODAY}] Adyen Monitor — fetching data...")
    
    # Fetch all tickers
    all_data = {}
    for ticker, meta in TICKERS.items():
        print(f"  Fetching {meta['name']} ({ticker})...")
        all_data[ticker] = fetch_prices(ticker, START_DATE, TODAY)
    
    # Compute valuation
    adyen_price = all_data.get("ADYEN.AS", {}).get("price")
    valuation = compute_adyen_valuation(adyen_price) if adyen_price else {}
    all_data["_valuation"] = valuation
    
    # Score signals
    signals = score_signals(all_data)
    
    # Build snapshot
    snapshot = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "date": TODAY,
        "tickers": {k: v for k, v in all_data.items() if not k.startswith("_")},
        "valuation": valuation,
        "signals": signals,
    }
    
    # Save JSON
    json_path = os.path.join(DATA_DIR, f"snapshot_{TODAY}.json")
    latest_path = os.path.join(DATA_DIR, "latest.json")
    
    with open(json_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    with open(latest_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    
    print(f"  Saved: {json_path}")
    
    # Generate dashboard
    dashboard_html = generate_dashboard(snapshot)
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(html_path, "w") as f:
        f.write(dashboard_html)
    
    print(f"  Dashboard: {html_path}")
    print(f"  Signals: {sum(1 for s in signals if s['signal']=='bull')} bull / "
          f"{sum(1 for s in signals if s['signal']=='neutral')} neutral / "
          f"{sum(1 for s in signals if s['signal']=='bear')} bear")
    print("Done!")


if __name__ == "__main__":
    main()
