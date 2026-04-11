#!/usr/bin/env python3
"""
Adyen Deep Dive Analysis — Static HTML Generator
=================================================
Generates analysis.html with embedded matplotlib charts (base64).
Runs alongside Adyen_monitor.py in GitHub Actions.

Sections:
  1) Business Analysis (bridges, cascade, margins)
  2) Monte Carlo DCF (3 scenarios, overlapping histograms)
  3) Unit Economics (cohorts, NRR, LTV/CAC)
  4) Market & Multiples (price history, EV/EBITDA, events)
  5) Base-Case DCF (conservative assumptions, sensitivity)
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import FuncFormatter
import io, base64, datetime, warnings, os
warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

# ── CONFIG ───────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)
TICKER = "ADYEN.AS"
SHARES = 31.54
NET_CASH_B = 7.0
PRICE_FB = 860.0
TODAY = datetime.date.today().isoformat()

C = {
    "bg":"#0b0b12","panel":"#111119","p2":"#1a1a26","grid":"#252535",
    "text":"#e8e6e1","dim":"#8a8880","faint":"#4a4a44",
    "blue":"#4488cc","green":"#22b07d","red":"#e8524a",
    "amber":"#d4952b","purple":"#8b7fd8","teal":"#3aafa9",
    "pink":"#d4537e","gray":"#6a6a66",
}

plt.style.use("dark_background")
plt.rcParams.update({
    "figure.facecolor":C["bg"],"axes.facecolor":C["panel"],
    "axes.edgecolor":C["grid"],"axes.labelcolor":C["text"],
    "xtick.color":C["dim"],"ytick.color":C["dim"],
    "text.color":C["text"],"axes.titleweight":"bold",
    "axes.titlesize":14,"font.size":10,
    "grid.color":C["grid"],"grid.alpha":.35,
    "legend.frameon":False,"figure.dpi":120,
})

# ── DATA ─────────────────────────────────────────────────────
H = pd.DataFrame([
    {"yr":2020,"tpv":304,"rev":684,"ebitda":434,"dna":27,"ebit":407,"ni":358,"cx":27,"fcf":350,"emp":2146,"merch":45000},
    {"yr":2021,"tpv":516,"rev":1011,"ebitda":640,"dna":40,"ebit":600,"ni":508,"cx":45,"fcf":490,"emp":2571,"merch":60000},
    {"yr":2022,"tpv":731,"rev":1295,"ebitda":608,"dna":52,"ebit":556,"ni":578,"cx":55,"fcf":550,"emp":3332,"merch":75000},
    {"yr":2023,"tpv":970,"rev":1627,"ebitda":744,"dna":65,"ebit":679,"ni":700,"cx":73,"fcf":660,"emp":4234,"merch":95000},
    {"yr":2024,"tpv":1293,"rev":1996,"ebitda":992,"dna":80,"ebit":912,"ni":925,"cx":100,"fcf":870,"emp":4345,"merch":115000},
    {"yr":2025,"tpv":1500,"rev":2363,"ebitda":1250,"dna":95,"ebit":1155,"ni":1063,"cx":118,"fcf":1100,"emp":4771,"merch":138000},
])

SA = pd.DataFrame([
    {"p":"H1'22","rev":609,"tpv":346,"ebitda":298},{"p":"H2'22","rev":686,"tpv":385,"ebitda":310},
    {"p":"H1'23","rev":739,"tpv":426,"ebitda":320},{"p":"H2'23","rev":888,"tpv":544,"ebitda":424},
    {"p":"H1'24","rev":914,"tpv":620,"ebitda":423},{"p":"H2'24","rev":1083,"tpv":673,"ebitda":569},
    {"p":"H1'25","rev":1094,"tpv":649,"ebitda":544},{"p":"H2'25","rev":1270,"tpv":745,"ebitda":702},
])

COHORTS = pd.DataFrame([
    {"yr":"2021","exist":720,"new":291,"total":1011},{"yr":"2022","exist":940,"new":355,"total":1295},
    {"yr":"2023","exist":1250,"new":377,"total":1627},{"yr":"2024","exist":1550,"new":446,"total":1996},
    {"yr":"2025","exist":1870,"new":493,"total":2363},
])

NRR = pd.DataFrame([{"yr":"2021","nrr":125},{"yr":"2022","nrr":118},{"yr":"2023","nrr":121},{"yr":"2024","nrr":124},{"yr":"2025","nrr":121}])

EVENTS = [
    ("2023-08-17",-39,"H1'23: rev slowdown + hiring surge"),
    ("2024-02-08",+20,"H2'23: margin rebound"),
    ("2025-08-14",-20,"H1'25: APAC tariffs, guidance cut"),
    ("2026-02-12",-20,"H2'25: Q4 miss, 2026 guidance below consensus"),
]

# ── DERIVED ──────────────────────────────────────────────────
H["opex"]=H["rev"]-H["ebitda"]; H["nopat"]=(H["ebit"]*.77).round(0)
H["tax"]=(H["ebit"]*.23).round(0); H["em%"]=(H["ebitda"]/H["rev"]*100).round(1)
H["fcf%"]=(H["fcf"]/H["rev"]*100).round(1); H["tr"]=(H["rev"]/H["tpv"]/10).round(2)
H["rev/m"]=(H["rev"]*1e6/H["merch"]/1e3).round(0); H["rev/e"]=(H["rev"]*1e6/H["emp"]/1e3).round(0)
H["eb/e"]=(H["ebitda"]*1e6/H["emp"]/1e3).round(0); H["fcf/sh"]=(H["fcf"]/SHARES).round(1)
H["ev_eb"]=[None,120,65,55,50,22]; H["roic%"]=(H["nopat"]/(H["rev"]*.30)*100).round(0)

G = H[["yr"]].iloc[1:].reset_index(drop=True)
for c in ["tpv","rev","ebitda","fcf"]:
    G[c]=(H[c].pct_change()*100).round(1).iloc[1:].values
G.columns=["yr","TPV","Revenue","EBITDA","FCF"]

SA["rg"]=[np.nan,np.nan]+[round((SA.iloc[i]["rev"]/SA.iloc[i-2]["rev"]-1)*100,1) for i in range(2,len(SA))]
SA["em"]=(SA["ebitda"]/SA["rev"]*100).round(1)

# ── HELPERS ──────────────────────────────────────────────────
def fm(v,_=None): return f"€{v/1e3:.1f}B" if abs(v)>=1000 else f"€{v:,.0f}M"
def fp(v,_=None): return f"{v:.0f}%"
def sty(ax,t=None,yl=None):
    if t: ax.set_title(t,loc="left",pad=10,fontsize=13)
    if yl: ax.set_ylabel(yl)
    ax.grid(True,axis="y",ls="--",lw=.5,alpha=.25)
    for s in ax.spines.values(): s.set_color(C["grid"])

def kpi(ax,lbl,val,sub="",col=C["text"]):
    ax.set_xticks([]); ax.set_yticks([]); ax.set_facecolor(C["p2"])
    for s in ax.spines.values(): s.set_visible(False)
    ax.text(.05,.72,lbl.upper(),fontsize=8,color=C["dim"],fontweight="bold",transform=ax.transAxes)
    ax.text(.05,.32,str(val),fontsize=17,color=col,fontweight="bold",transform=ax.transAxes)
    if sub: ax.text(.05,.08,sub,fontsize=8,color=C["faint"],transform=ax.transAxes)

def tn(mean,std,lo,hi,n=None):
    if n is None:
        while True:
            v=np.random.normal(mean,std)
            if lo<=v<=hi: return v
    v=np.random.normal(mean,std,size=n)
    m=(v<lo)|(v>hi)
    while m.any(): v[m]=np.random.normal(mean,std,size=m.sum()); m=(v<lo)|(v>hi)
    return v

def fig_to_b64(fig):
    buf=io.BytesIO(); fig.savefig(buf,format="png",bbox_inches="tight",facecolor=C["bg"]); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

def get_price():
    if not YF_OK: return PRICE_FB
    try:
        t=yf.Ticker(TICKER); p=t.fast_info.get("last_price") or t.fast_info.get("lastPrice")
        return float(p) if p else PRICE_FB
    except: return PRICE_FB

# ── MONTE CARLO ──────────────────────────────────────────────
SCENARIOS={
    "bear":{"lbl":"Bear","col":C["red"],"tpv_g":(.12,.04,.02,.22),"tr_d":-5e-6,"tr_v":1e-5,"em":(.48,.04,.35,.62),"mexp":.003,"cx":(.055,.008,.02,.08),"wacc":.10,"g":.025},
    "base":{"lbl":"Base","col":C["blue"],"tpv_g":(.18,.04,.08,.28),"tr_d":0,"tr_v":1e-5,"em":(.52,.03,.38,.62),"mexp":.005,"cx":(.05,.008,.02,.08),"wacc":.09,"g":.03},
    "bull":{"lbl":"Bull","col":C["green"],"tpv_g":(.24,.04,.14,.35),"tr_d":5e-6,"tr_v":1e-5,"em":(.54,.03,.40,.65),"mexp":.008,"cx":(.045,.008,.02,.08),"wacc":.085,"g":.035},
}

def mc_run(sc,N=8000,Y=5,tpv0=1500.,tr0=.00158):
    prices=np.empty(N); paths=[]
    for i in range(N):
        tpv=tpv0; tr=tr0; fcfs=[]; path=[]
        for y in range(1,Y+1):
            z1,z2=np.random.normal(0,1,2); rho=-.3; z2c=rho*z1+np.sqrt(1-rho**2)*z2
            g=np.clip(sc["tpv_g"][0]+sc["tpv_g"][1]*z1,sc["tpv_g"][2],sc["tpv_g"][3]); tpv*=(1+g)
            tr_eq=tr0+sc["tr_d"]*y*10; tr+=.5*(tr_eq-tr)+sc["tr_v"]*np.random.normal(); tr=np.clip(tr,.0012,.0022)
            nr=tpv*1e9*tr; em=np.clip(sc["em"][0]+y*sc["mexp"]+sc["em"][1]*z2c,sc["em"][2],sc["em"][3])
            ebitda=nr*em; dna=nr*tn(.04,.005,.02,.07); ebit=ebitda-dna
            nopat=ebit*(1-tn(.23,.02,.18,.30)); cx=nr*tn(sc["cx"][0],sc["cx"][1],sc["cx"][2],sc["cx"][3])
            fcf=nopat+dna-cx; fcfs.append(fcf)
            path.append({"yr":2025+y,"nr":nr/1e6,"eb":ebitda/1e6,"fcf":fcf/1e6,"tpv":tpv})
        w=sc["wacc"]; gt=sc["g"]; tv=fcfs[-1]*(1+gt)/(w-gt)
        dcf=sum(f/(1+w)**(j+1) for j,f in enumerate(fcfs))+tv/(1+w)**Y
        prices[i]=((dcf+NET_CASH_B*1e9)/1e6)/SHARES; paths.append(path)
    prices.sort(); pct=np.percentile(prices,[5,10,25,50,75,90,95])
    blo=int(np.floor(prices.min()/50)*50); bhi=int(np.ceil(prices.max()/50)*50)
    edges=np.arange(blo,bhi+50,50); hist,_=np.histogram(prices,bins=edges)
    avg=[]
    for y in range(Y):
        avg.append({"yr":paths[0][y]["yr"],"nr":np.mean([p[y]["nr"] for p in paths]),
                     "eb":np.mean([p[y]["eb"] for p in paths]),"fcf":np.mean([p[y]["fcf"] for p in paths]),
                     "tpv":np.mean([p[y]["tpv"] for p in paths])})
    return {"prices":prices,"N":N,"p5":pct[0],"p10":pct[1],"p25":pct[2],"p50":pct[3],"p75":pct[4],"p90":pct[5],"p95":pct[6],
            "mean":prices.mean(),"std":prices.std(),"edges":edges,"hist":hist,"avg":pd.DataFrame(avg)}

def tornado(N=4000):
    sc=SCENARIOS["base"]; recs=[]
    for _ in range(N):
        z1,z2=np.random.normal(0,1,2); rho=-.3; z2c=rho*z1+np.sqrt(1-rho**2)*z2
        g=np.clip(sc["tpv_g"][0]+sc["tpv_g"][1]*z1,sc["tpv_g"][2],sc["tpv_g"][3])
        em=np.clip(sc["em"][0]+sc["em"][1]*z2c,sc["em"][2],sc["em"][3])
        tax=tn(.23,.02,.18,.30); cx=tn(sc["cx"][0],sc["cx"][1],sc["cx"][2],sc["cx"][3])
        d_tr=tn(0,sc["tr_v"],-3e-5,3e-5); tpv=1500*(1+g); tr=np.clip(.00158+d_tr,.0012,.0022)
        nr=tpv*1e9*tr; ebitda=nr*em; dna=nr*.04; ebit=ebitda-dna; nopat=ebit*(1-tax); capex=nr*cx
        recs.append({"TPV_growth":g,"EBITDA_margin":em,"Tax_rate":tax,"CapEx_rate":cx,"Take_rate_chg":d_tr,"FCF":(nopat+dna-capex)/1e6})
    return pd.DataFrame(recs).corr()["FCF"].drop("FCF").sort_values(key=abs,ascending=False)

def run_base_dcf():
    wacc=.12; g_t=.035; tpv=1500; proj=[]
    for yr,g,tr,em,cx in [(2026,.19,.00155,.50,.05),(2027,.17,.00152,.51,.05),(2028,.15,.00150,.52,.05),(2029,.13,.00148,.52,.05),(2030,.12,.00147,.52,.05)]:
        tpv*=(1+g); nr=tpv*1e9*tr; ebitda=nr*em; dna=nr*.04; ebit=ebitda-dna; nopat=ebit*.77; capex=nr*cx; fcf=nopat+dna-capex
        proj.append({"yr":yr,"tpv":tpv,"tr":tr*100,"nr":nr/1e6,"eb":ebitda/1e6,"em%":em*100,"nop":nopat/1e6,"fcf":fcf/1e6,"g":g*100})
    df=pd.DataFrame(proj); fcfs=[r["fcf"]*1e6 for r in proj]
    tv=fcfs[-1]*(1+g_t)/(wacc-g_t); dcf=sum(f/(1+wacc)**(i+1) for i,f in enumerate(fcfs))+tv/(1+wacc)**5
    price=((dcf+NET_CASH_B*1e9)/1e6)/SHARES
    pv_f=sum(f/(1+wacc)**(i+1) for i,f in enumerate(fcfs)); pv_tv=tv/(1+wacc)**5; tv_w=pv_tv/(pv_f+pv_tv)*100
    sens={}
    for w in [.08,.09,.10,.11,.12,.13,.14]:
        for g in [.020,.025,.030,.035,.040]:
            if w<=g: sens[(w,g)]="—"; continue
            tv_s=fcfs[-1]*(1+g)/(w-g); d=sum(f/(1+w)**(i+1) for i,f in enumerate(fcfs))+tv_s/(1+w)**5
            sens[(w,g)]=f"€{((d+NET_CASH_B*1e9)/1e6)/SHARES:.0f}"
    return df,price,tv_w,sens

# ═══════════════════════════════════════════════════════════════
# CHART GENERATORS
# ═══════════════════════════════════════════════════════════════
def chart_business():
    fig=plt.figure(figsize=(20,13),facecolor=C["bg"])
    gs=GridSpec(3,12,figure=fig,height_ratios=[.65,2,2],hspace=.35,wspace=.3)
    L=H.iloc[-1]
    for i,(lb,vl,sb,co) in enumerate([("FCF 2025",fm(L["fcf"]),f"Margin {L['fcf%']:.0f}%",C["green"]),
        ("EBITDA%",f"{L['em%']:.0f}%","2025",C["purple"]),("Take rate",f"{L['tr']:.2f}%",f"TPV €{L['tpv']:.0f}B",C["amber"]),
        ("ROIC",f"{L['roic%']:.0f}%","NOPAT/IC proxy",C["green"])]):
        kpi(fig.add_subplot(gs[0,i*3:(i+1)*3]),lb,vl,sb,co)
    ax=fig.add_subplot(gs[1,:7]); x=np.arange(len(H)); w=.18
    for j,(c,cl,a,lb) in enumerate([("rev",C["blue"],.3,"Net Revenue"),("ebitda",C["purple"],.5,"EBITDA"),("nopat",C["amber"],.7,"NOPAT"),("fcf",C["green"],.95,"FCF")]):
        ax.bar(x+(j-1.5)*w,H[c],w,color=cl,alpha=a,label=lb)
    ax.set_xticks(x); ax.set_xticklabels(H["yr"].astype(str)); ax.yaxis.set_major_formatter(FuncFormatter(fm))
    sty(ax,"Bridge: Revenue → EBITDA → NOPAT → FCF","€M"); ax.legend(loc="upper left",ncol=2,fontsize=9)
    ax2=fig.add_subplot(gs[1,7:]); x2=np.arange(len(G))
    for j,(c,cl) in enumerate([("TPV",C["gray"]),("Revenue",C["blue"]),("EBITDA",C["purple"]),("FCF",C["green"])]):
        ax2.bar(x2+j*.18-.27,G[c],.18,color=cl,label=c)
    ax2.axhline(0,color=C["grid"],lw=1); ax2.set_xticks(x2); ax2.set_xticklabels(G["yr"].astype(str))
    ax2.yaxis.set_major_formatter(FuncFormatter(fp)); sty(ax2,"Crecimiento YoY","%"); ax2.legend(fontsize=8)
    ax3=fig.add_subplot(gs[2,:]); ax3.bar(SA["p"],SA["rev"],color=C["blue"],alpha=.22,label="Net Rev €M")
    ax3b=ax3.twinx(); ax3b.plot(SA["p"],SA["rg"],color=C["green"],marker="o",lw=2.2,label="Rev YoY %")
    ax3b.plot(SA["p"],SA["em"],color=C["amber"],marker="s",lw=2.2,label="EBITDA Margin %")
    sty(ax3,"Semi-annual: Revenue, Growth, Margin","€M"); ax3b.set_ylabel("%")
    for s in ax3b.spines.values(): s.set_color(C["grid"])
    h1,l1=ax3.get_legend_handles_labels(); h2,l2=ax3b.get_legend_handles_labels()
    ax3b.legend(h1+h2,l1+l2,loc="upper left",fontsize=9); plt.tight_layout()
    return fig_to_b64(fig)

def chart_mc(mc,cp):
    fig=plt.figure(figsize=(20,16),facecolor=C["bg"])
    gs=GridSpec(3,12,figure=fig,height_ratios=[.65,2.4,2.4],hspace=.38,wspace=.3)
    br=mc["base"]
    irr=((br["p50"]/cp)**.2-1)*100; pw=(br["prices"]>cp).mean()*100
    for i,(lb,vl,sb,co) in enumerate([("Precio",f"€{cp:.0f}","actual",C["text"]),
        ("P50 Base",f"€{br['p50']:.0f}",f"Upside {(br['p50']/cp-1)*100:+.0f}%",C["blue"]),
        ("P50 Bear",f"€{mc['bear']['p50']:.0f}","",C["red"]),("P50 Bull",f"€{mc['bull']['p50']:.0f}","",C["green"]),
        ("IRR Base",f"{irr:.1f}%","5Y",C["green"] if irr>0 else C["red"]),("P(win)",f"{pw:.0f}%","base",C["green"])]):
        kpi(fig.add_subplot(gs[0,i*2:(i+1)*2]),lb,vl,sb,co)
    ax_h=fig.add_subplot(gs[1,:]); 
    for k in ["bear","base","bull"]:
        r=mc[k]; sc=SCENARIOS[k]; centers=(r["edges"][:-1]+r["edges"][1:])/2
        ax_h.fill_between(centers,r["hist"],alpha=.22,color=sc["col"],step="mid")
        ax_h.step(centers,r["hist"],where="mid",color=sc["col"],lw=1.8,label=f"{sc['lbl']} (P50 €{r['p50']:.0f})")
    ax_h.axvline(cp,color=C["red"],ls="--",lw=2,alpha=.8)
    ax_h.text(cp+20,ax_h.get_ylim()[1]*.85,f"Actual €{cp:.0f}",color=C["red"],fontsize=10)
    sty(ax_h,"Distribución precio/acción — 3 escenarios superpuestos (bins €50)","Frecuencia"); ax_h.legend(fontsize=11)
    ax_c=fig.add_subplot(gs[2,:6])
    for k in ["bear","base","bull"]:
        r=mc[k]; sc=SCENARIOS[k]; sp=np.sort(r["prices"]); cdf=np.arange(1,len(sp)+1)/len(sp)*100
        ax_c.plot(sp,cdf,color=sc["col"],lw=2,label=sc["lbl"])
    ax_c.axvline(cp,color=C["red"],ls="--",lw=1.5); ax_c.axhline(50,color=C["faint"],ls=":",lw=1)
    sty(ax_c,"CDF por escenario","Prob. acumulada %"); ax_c.set_xlim(0,4000); ax_c.set_ylim(0,100); ax_c.legend(fontsize=10)
    ax_t=fig.add_subplot(gs[2,6:]); corr=tornado(4000)
    cols_t=[C["green"] if v>0 else C["red"] for v in corr.values]
    bars=ax_t.barh(range(len(corr)),corr.values,color=cols_t,alpha=.8)
    ax_t.set_yticks(range(len(corr))); ax_t.set_yticklabels(corr.index,fontsize=11); ax_t.axvline(0,color=C["grid"],lw=1)
    for b,v in zip(bars,corr.values): ax_t.text(v+(.01 if v>0 else -.06),b.get_y()+b.get_height()/2,f"{v:.2f}",va="center",fontsize=10,color=C["text"])
    sty(ax_t,"Sensibilidad: correlación con FCF","Pearson r"); plt.tight_layout()
    return fig_to_b64(fig)

def chart_units():
    fig=plt.figure(figsize=(20,16),facecolor=C["bg"])
    gs=GridSpec(3,12,figure=fig,height_ratios=[.65,2,2],hspace=.35,wspace=.3)
    L=H.iloc[-1]
    for i,(lb,vl,sb,co) in enumerate([("Rev/merchant",f"€{L['rev/m']:.0f}K","2025",C["blue"]),
        ("NRR","~121%","net rev retention",C["green"]),("Gross churn","~3-5%","estimated",C["amber"]),
        ("FCF/acción",f"€{L['fcf/sh']:.1f}","",C["purple"])]):
        kpi(fig.add_subplot(gs[0,i*3:(i+1)*3]),lb,vl,sb,co)
    ax_co=fig.add_subplot(gs[1,:6])
    ax_co.bar(COHORTS["yr"],COHORTS["exist"],color=C["blue"],label="Existentes"); ax_co.bar(COHORTS["yr"],COHORTS["new"],bottom=COHORTS["exist"],color=C["green"],label="Nuevas cohortes")
    for _,r in COHORTS.iterrows(): ax_co.text(r["yr"],r["total"]+30,f"{r['exist']/r['total']*100:.0f}/{r['new']/r['total']*100:.0f}",ha="center",fontsize=9,color=C["dim"])
    sty(ax_co,"Revenue: existentes vs nuevas cohortes (€M)","€M"); ax_co.legend(fontsize=9)
    ax_nr=fig.add_subplot(gs[1,6:]); bars_nr=ax_nr.bar(NRR["yr"],NRR["nrr"],color=[C["green"] if n>=120 else C["amber"] for n in NRR["nrr"]],alpha=.85)
    ax_nr.axhline(100,color=C["red"],ls="--",lw=1,alpha=.5); ax_nr.set_ylim(95,135)
    for b,n in zip(bars_nr,NRR["nrr"]): ax_nr.text(b.get_x()+b.get_width()/2,b.get_height()+.8,f"{n}%",ha="center",fontsize=11,color=C["text"])
    sty(ax_nr,"Net Revenue Retention Rate","NRR %")
    # LTV/CAC
    ltv_data=[]
    for _,r in H.iterrows():
        rpm=r["rev"]*1e6/r["merch"]; gm=r["ebitda"]/r["rev"]; ltv=sum(rpm*gm*1.05**y/1.09**y for y in range(25))
        nm=r["merch"]-(H[H["yr"]==r["yr"]-1]["merch"].values[0] if r["yr"]>2020 else 0)
        cac=(r["opex"]*.15*1e6/nm) if nm>0 else 0
        ltv_data.append({"yr":str(r["yr"]),"ltv":ltv/1e3,"cac":cac/1e3,"r":ltv/(cac*1e3)*1e3 if cac>0 else 0})
    ld=pd.DataFrame(ltv_data)
    ax_l=fig.add_subplot(gs[2,:6]); ax_l.bar(ld["yr"],ld["ltv"],color=C["green"],alpha=.6,label="LTV €K"); ax_l.bar(ld["yr"],ld["cac"],color=C["red"],alpha=.6,label="CAC €K")
    ax_l2=ax_l.twinx(); ax_l2.plot(ld["yr"],ld["r"],color=C["amber"],marker="D",lw=2.3,label="LTV/CAC")
    sty(ax_l,"LTV vs CAC por merchant (€K)","€K"); 
    for s in ax_l2.spines.values(): s.set_color(C["grid"])
    h1,l1=ax_l.get_legend_handles_labels(); h2,l2=ax_l2.get_legend_handles_labels(); ax_l2.legend(h1+h2,l1+l2,fontsize=9)
    ax_ef=fig.add_subplot(gs[2,6:]); x_ef=np.arange(len(H))
    ax_ef.bar(x_ef-.18,H["rev/e"],.35,color=C["blue"],alpha=.4,label="Rev/emp €K"); ax_ef.bar(x_ef+.18,H["eb/e"],.35,color=C["green"],label="EBITDA/emp €K")
    ax_ef.set_xticks(x_ef); ax_ef.set_xticklabels(H["yr"].astype(str)); sty(ax_ef,"Productividad por empleado","€K"); ax_ef.legend(fontsize=9)
    plt.tight_layout(); return fig_to_b64(fig)

def chart_market(cp):
    fig=plt.figure(figsize=(20,14),facecolor=C["bg"])
    gs=GridSpec(3,12,figure=fig,height_ratios=[2.5,2,1.8],hspace=.38,wspace=.3)
    ax_px=fig.add_subplot(gs[0,:])
    has_ph=False
    if YF_OK:
        try:
            ph=yf.Ticker(TICKER).history(period="5y",interval="1wk")
            if not ph.empty:
                has_ph=True; ax_px.plot(ph.index,ph["Close"],color=C["blue"],lw=1.8); ax_px.fill_between(ph.index,ph["Close"],color=C["blue"],alpha=.08)
                for dt_s,chg,txt in EVENTS:
                    try:
                        dt=pd.Timestamp(dt_s)
                        if dt>=ph.index[0]:
                            idx=ph.index.get_indexer([dt],method="nearest")[0]; p_at=ph["Close"].iloc[idx]
                            col_e=C["red"] if chg<0 else C["green"]
                            ax_px.annotate(txt,xy=(ph.index[idx],p_at),xytext=(0,55 if chg<0 else -55),textcoords="offset points",
                                fontsize=8,color=col_e,arrowprops=dict(arrowstyle="->",color=col_e,lw=1.2),ha="center",
                                bbox=dict(boxstyle="round,pad=0.3",facecolor=C["p2"],edgecolor=col_e,alpha=.9))
                    except: pass
        except: pass
    if not has_ph: ax_px.text(.5,.5,"Cotización no disponible",ha="center",va="center",fontsize=14,color=C["dim"],transform=ax_px.transAxes)
    sty(ax_px,"ADYEN.AS — Cotización 5 años + eventos","€/acción")
    ax_ev=fig.add_subplot(gs[1,:6]); ve=H[H["ev_eb"].notna()]
    ax_ev.bar(ve["yr"].astype(str),ve["ev_eb"],color=C["purple"],alpha=.7)
    for _,r in ve.iterrows(): ax_ev.text(str(int(r["yr"])),r["ev_eb"]+1,f"{r['ev_eb']:.0f}x",ha="center",fontsize=10,color=C["text"])
    sty(ax_ev,"EV/EBITDA histórico","Múltiplo")
    ax_rm=fig.add_subplot(gs[1,6:]); ax_rm.bar(H["yr"].astype(str),H["roic%"],color=C["green"],alpha=.5,label="ROIC %")
    ax_rm2=ax_rm.twinx(); ax_rm2.plot(H["yr"].astype(str),H["em%"],color=C["purple"],marker="o",lw=2.3,label="EBITDA %")
    ax_rm2.plot(H["yr"].astype(str),H["fcf%"],color=C["teal"],marker="s",lw=2.3,label="FCF %")
    sty(ax_rm,"ROIC + márgenes","ROIC %")
    for s in ax_rm2.spines.values(): s.set_color(C["grid"])
    h1,l1=ax_rm.get_legend_handles_labels(); h2,l2=ax_rm2.get_legend_handles_labels(); ax_rm2.legend(h1+h2,l1+l2,fontsize=9)
    # Narrative
    ax_n=fig.add_subplot(gs[2,:]); ax_n.set_facecolor(C["p2"])
    for s in ax_n.spines.values(): s.set_visible(False)
    ax_n.set_xticks([]); ax_n.set_yticks([])
    txt=("NARRATIVA vs FUNDAMENTALES\n\n"
         "2021: Pico €2,700 · EV/EBITDA 120x · Rev +48% · Euforia fintech\n"
         "2022: Caída a €1,200 · EV/EBITDA 65x · Rev +28% · Compression por tipos\n"
         "2023 H1: Flash -39% · Hiring surge + margen 43% · Primera decepción\n"
         "2023 H2: Rebote · Management corrige: frena hiring, margen 48%\n"
         "2024: Recupera €1,500+ · Rev +23% · EBITDA 50% · 'Está de vuelta'\n"
         "2025: -20% x2 (APAC tariffs + guidance miss) · Rev sigue +21% cc\n"
         f"Abr 2026: €{cp:.0f} · EV/EBITDA ~22x · ¿Bache o desaceleración estructural?")
    ax_n.text(.02,.92,txt,fontsize=10,color=C["text"],transform=ax_n.transAxes,va="top",family="monospace",linespacing=1.5)
    plt.tight_layout(); return fig_to_b64(fig)

def chart_dcf(cp):
    df,price,tv_w,sens=run_base_dcf()
    fig=plt.figure(figsize=(20,10),facecolor=C["bg"])
    gs=GridSpec(2,12,figure=fig,height_ratios=[.6,2.5],hspace=.35,wspace=.3)
    up=(price/cp-1)*100; irr=((price/cp)**.2-1)*100
    for i,(lb,vl,sb,co) in enumerate([("DCF price",f"€{price:.0f}",f"Upside {up:+.0f}%",C["green"] if price>cp else C["red"]),
        ("WACC","12.0%","conservador",C["text"]),("Terminal g","3.5%","",C["text"]),("TV weight",f"{tv_w:.0f}%","",C["amber"])]):
        kpi(fig.add_subplot(gs[0,i*3:(i+1)*3]),lb,vl,sb,co)
    ax=fig.add_subplot(gs[1,:8])
    yrs=list(H["yr"].values[-2:])+list(df["yr"].values); rev=list(H["rev"].values[-2:])+list(df["nr"].round(0))
    fcf_all=list(H["fcf"].values[-2:])+list(df["fcf"].round(0)); eb_all=list(H["ebitda"].values[-2:])+list(df["eb"].round(0))
    cols=[C["blue"]]*2+[C["teal"]]*5
    ax.bar([str(y) for y in yrs],rev,color=cols,alpha=.2,label="Net Revenue")
    ax.plot([str(y) for y in yrs],eb_all,color=C["purple"],marker="o",lw=2.2,label="EBITDA")
    ax.plot([str(y) for y in yrs],fcf_all,color=C["green"],marker="o",lw=2.6,label="FCF")
    ax.axvline(1.5,color=C["dim"],ls=":",lw=1); ax.yaxis.set_major_formatter(FuncFormatter(fm))
    sty(ax,"DCF: proyección (€M)","€M"); ax.legend(fontsize=9)
    ax_a=fig.add_subplot(gs[1,8:]); ax_a.set_xticks([]); ax_a.set_yticks([]); ax_a.set_facecolor(C["p2"])
    for s in ax_a.spines.values(): s.set_visible(False)
    t="SUPUESTOS\n\n"
    for _,r in df.iterrows(): t+=f"{int(r['yr'])}: TPV +{r['g']:.0f}% TR {r['tr']:.3f}%\n     EM {r['em%']:.0f}% FCF €{r['fcf']:.0f}M\n\n"
    t+=f"WACC 12% · g 3.5%\nTV weight {tv_w:.0f}%\n\nPRECIO: €{price:.0f}\nvs €{cp:.0f} ({up:+.0f}%)\nIRR 5Y: {irr:.1f}%"
    ax_a.text(.05,.95,t,fontsize=10,color=C["text"],transform=ax_a.transAxes,va="top",family="monospace",linespacing=1.4)
    plt.tight_layout(); return fig_to_b64(fig), price, up, irr, tv_w, sens, df

# ═══════════════════════════════════════════════════════════════
# HTML GENERATION
# ═══════════════════════════════════════════════════════════════
def generate_html():
    print("Adyen Analysis — generating charts...")
    cp = get_price()
    print(f"  Price: €{cp:.2f}")

    print("  [1/5] Business analysis...")
    b64_biz = chart_business()

    print("  [2/5] Monte Carlo (8,000 × 3 scenarios)...")
    np.random.seed(SEED)
    mc = {k: mc_run(v, 8000) for k,v in SCENARIOS.items()}
    b64_mc = chart_mc(mc, cp)

    # MC summary
    mc_rows = ""
    for k,v in SCENARIOS.items():
        r=mc[k]; up=(r["p50"]/cp-1)*100; irr=((r["p50"]/cp)**.2-1)*100; pw=(r["prices"]>cp).mean()*100
        mc_rows += f'<tr><td style="color:{v["col"]};font-weight:600">{v["lbl"]}</td>'
        mc_rows += f'<td>€{r["p10"]:.0f}</td><td>€{r["p25"]:.0f}</td><td style="font-weight:700">€{r["p50"]:.0f}</td>'
        mc_rows += f'<td>€{r["p75"]:.0f}</td><td>€{r["p90"]:.0f}</td><td>€{r["mean"]:.0f}</td>'
        mc_rows += f'<td>{up:+.0f}%</td><td>{irr:.1f}%</td><td>{pw:.0f}%</td></tr>'

    print("  [3/5] Unit economics...")
    b64_unit = chart_units()

    print("  [4/5] Market & multiples...")
    b64_mkt = chart_market(cp)

    print("  [5/5] Base-case DCF...")
    b64_dcf, dcf_price, dcf_up, dcf_irr, tv_w, sens, dcf_df = chart_dcf(cp)

    # Sensitivity table HTML
    wacc_r=[.08,.09,.10,.11,.12,.13,.14]; g_r=[.020,.025,.030,.035,.040]
    sens_html='<table class="tbl"><thead><tr><th>WACC \\ g</th>'
    for g in g_r: sens_html+=f'<th>{g*100:.1f}%</th>'
    sens_html+='</tr></thead><tbody>'
    for w in wacc_r:
        sens_html+=f'<tr><td style="font-weight:600">{w*100:.0f}%</td>'
        for g in g_r:
            v=sens.get((w,g),"—"); hl=' style="background:rgba(34,176,125,.15);font-weight:700"' if w==.12 and g==.035 else ""
            sens_html+=f'<td{hl}>{v}</td>'
        sens_html+='</tr>'
    sens_html+='</tbody></table>'

    # Cascade table
    cas_html='<table class="tbl"><thead><tr><th>Year</th><th>TPV €B</th><th>TR%</th><th>Rev</th><th>OpEx</th><th>EBITDA</th><th>EM%</th><th>D&A</th><th>Tax</th><th>NOPAT</th><th>CapEx</th><th>FCF</th><th>FCF%</th></tr></thead><tbody>'
    for _,r in H.iterrows():
        cas_html+=f'<tr><td>{int(r["yr"])}</td><td>€{r["tpv"]:.0f}B</td><td class="am">{r["tr"]:.2f}%</td>'
        cas_html+=f'<td class="bl">€{r["rev"]:.0f}</td><td class="rd">-€{r["opex"]:.0f}</td>'
        cas_html+=f'<td class="pu">€{r["ebitda"]:.0f}</td><td class="pu">{r["em%"]:.0f}%</td>'
        cas_html+=f'<td>-€{r["dna"]:.0f}</td><td>-€{r["tax"]:.0f}</td>'
        cas_html+=f'<td class="am">€{r["nopat"]:.0f}</td><td>-€{r["cx"]:.0f}</td>'
        cas_html+=f'<td class="gr" style="font-weight:600">€{r["fcf"]:.0f}</td><td class="gr">{r["fcf%"]:.0f}%</td></tr>'
    cas_html+='</tbody></table>'

    L=H.iloc[-1]; pw_b=(mc["base"]["prices"]>cp).mean()*100

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Adyen Deep Dive</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0b0b12;--s:#111119;--s2:#1a1a26;--bd:rgba(255,255,255,.06);--t:#e8e6e1;--t2:#8a8880;--t3:#4a4a44;
--gr:#22b07d;--rd:#e8524a;--bl:#4488cc;--am:#d4952b;--pu:#8b7fd8;--tl:#3aafa9}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--t);line-height:1.6;padding:1.5rem;max-width:1400px;margin:0 auto}}
h1{{font-size:1.5rem;font-weight:700;letter-spacing:-.02em}} h1 span{{color:var(--bl)}}
h2{{font-size:1.15rem;font-weight:700;margin:2rem 0 .8rem;padding-top:1.5rem;border-top:1px solid var(--bd)}}
.sub{{color:var(--t2);font-size:.85rem;margin-bottom:1rem}}
.nav{{display:flex;gap:6px;margin:1rem 0;flex-wrap:wrap}}
.nav a{{padding:6px 16px;border-radius:6px;background:var(--s);border:1px solid var(--bd);color:var(--t2);text-decoration:none;font-size:12px;font-weight:500}}
.nav a:hover,.nav a.active{{color:var(--t);background:var(--s2);border-color:var(--bl)}}
img{{width:100%;border-radius:8px;margin:.5rem 0 1.5rem}}
.tbl{{width:100%;border-collapse:collapse;font-size:12px;font-family:'JetBrains Mono',monospace;margin:.5rem 0 1.5rem}}
.tbl th{{padding:8px 6px;text-align:right;color:var(--t3);font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--bd)}}
.tbl td{{padding:6px;text-align:right;border-bottom:1px solid var(--bd);color:var(--t2)}}
.tbl td:first-child,.tbl th:first-child{{text-align:left;color:var(--t);font-weight:600}}
.bl{{color:var(--bl)}} .gr{{color:var(--gr)}} .rd{{color:var(--rd)}} .am{{color:var(--am)}} .pu{{color:var(--pu)}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:.8rem 0 1.2rem}}
.m{{background:var(--s2);border-radius:6px;padding:.75rem 1rem}}
.m-l{{font-size:10px;color:var(--t3);text-transform:uppercase;letter-spacing:.05em}}
.m-v{{font-size:1.3rem;font-weight:700;font-family:'JetBrains Mono',monospace;margin-top:2px}}
.m-s{{font-size:10px;color:var(--t3);font-family:'JetBrains Mono',monospace}}
.note{{background:var(--s);border:1px solid var(--bd);border-radius:8px;padding:1rem;font-size:13px;color:var(--t2);line-height:1.7;margin:1rem 0}}
.ft{{margin-top:2rem;padding-top:1rem;border-top:1px solid var(--bd);font-size:11px;color:var(--t3);display:flex;justify-content:space-between}}
.ft a{{color:var(--bl);text-decoration:none}}
</style>
</head>
<body>
<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:.5rem">
<h1><span>ADYEN</span> Deep Dive Analysis</h1>
<span style="font-size:11px;color:var(--t3);font-family:'JetBrains Mono',monospace">€{cp:.0f} · {TODAY}</span>
</div>
<p class="sub">2020-2025 histórico · Monte Carlo DCF 5Y · Unit Economics · Mercado & Múltiplos · DCF Conservador</p>

<div class="nav">
<a href="index.html">← Leading Indicators</a>
<a href="#s1">1. Negocio</a><a href="#s2">2. Monte Carlo</a><a href="#s3">3. Unit Economics</a><a href="#s4">4. Mercado</a><a href="#s5">5. DCF</a>
</div>

<h2 id="s1">1 · Análisis del negocio</h2>
<p class="sub">Bridges: TPV → Net Revenue → EBITDA → NOPAT → FCF · Crecimiento YoY · Semi-annual</p>
<img src="data:image/png;base64,{b64_biz}" alt="Business Analysis">
<h3>Cascade: TPV → FCF (€M)</h3>
{cas_html}

<h2 id="s2">2 · Monte Carlo DCF</h2>
<p class="sub">8,000 iteraciones × 3 escenarios · Variables correlacionadas · Take rate mean-reverting · Bins €50</p>
<table class="tbl">
<thead><tr><th>Scenario</th><th>P10</th><th>P25</th><th>P50</th><th>P75</th><th>P90</th><th>Mean</th><th>Upside</th><th>IRR 5Y</th><th>P(win)</th></tr></thead>
<tbody>{mc_rows}</tbody>
</table>
<img src="data:image/png;base64,{b64_mc}" alt="Monte Carlo">
<div class="note">
<strong>Mejoras del motor MC vs modelo simple:</strong><br>
• Variables correlacionadas (ρ=-0.3 entre TPV growth y EBITDA margin)<br>
• Take rate mean-reverting (Ornstein-Uhlenbeck) en vez de random walk<br>
• Bins de €50 para mayor granularidad en la distribución
</div>

<h2 id="s3">3 · Unit Economics</h2>
<p class="sub">Cohorts, NRR, LTV/CAC, eficiencia operativa</p>
<img src="data:image/png;base64,{b64_unit}" alt="Unit Economics">
<div class="note">
<strong>Lectura clave:</strong> ~79% del revenue viene de wallet expansion con merchants existentes. NRR ~121% implica churn neto negativo.
El gross churn real es ~3-5%, compensado con creces por upsell. El take rate baja (0.22%→0.16%) pero el revenue/merchant sube
porque los merchants procesan más volumen cada año.
</div>

<h2 id="s4">4 · Mercado & Múltiplos</h2>
<p class="sub">Cotización 5Y, EV/EBITDA, ROIC, narrativa vs fundamentales</p>
<img src="data:image/png;base64,{b64_mkt}" alt="Market">

<h2 id="s5">5 · DCF Base-Case Conservador</h2>
<p class="sub">Take rate estabilizado · Growth decelerando · Margin 48-52% · WACC 12% · g 3.5%</p>
<div class="metrics">
<div class="m"><div class="m-l">DCF price</div><div class="m-v" style="color:{'var(--gr)' if dcf_price>cp else 'var(--rd)'}">€{dcf_price:.0f}</div><div class="m-s">Upside {dcf_up:+.0f}%</div></div>
<div class="m"><div class="m-l">WACC</div><div class="m-v">12.0%</div><div class="m-s">Conservador</div></div>
<div class="m"><div class="m-l">Terminal g</div><div class="m-v">3.5%</div></div>
<div class="m"><div class="m-l">TV weight</div><div class="m-v">{tv_w:.0f}%</div></div>
<div class="m"><div class="m-l">IRR 5Y</div><div class="m-v">{dcf_irr:.1f}%</div></div>
</div>
<img src="data:image/png;base64,{b64_dcf}" alt="DCF">
<h3>Sensibilidad: WACC vs Terminal Growth</h3>
<p class="sub">Celda resaltada = supuestos base (WACC 12%, g 3.5%)</p>
{sens_html}

<h2>Resumen ejecutivo</h2>
<div class="metrics">
<div class="m"><div class="m-l">Precio actual</div><div class="m-v">€{cp:.0f}</div></div>
<div class="m"><div class="m-l">DCF conservador</div><div class="m-v" style="color:var(--gr)">€{dcf_price:.0f}</div><div class="m-s">{dcf_up:+.0f}%</div></div>
<div class="m"><div class="m-l">MC P50 B/B/B</div><div class="m-v">€{mc['bear']['p50']:.0f}/{mc['base']['p50']:.0f}/{mc['bull']['p50']:.0f}</div></div>
<div class="m"><div class="m-l">P(win) Base</div><div class="m-v" style="color:var(--gr)">{pw_b:.0f}%</div></div>
<div class="m"><div class="m-l">NRR 2025</div><div class="m-v">~121%</div></div>
<div class="m"><div class="m-l">EV/EBITDA</div><div class="m-v">~22x</div></div>
<div class="m"><div class="m-l">FCF yield</div><div class="m-v">{L['fcf']/SHARES/cp*100:.1f}%</div></div>
</div>
<div class="note">
<strong>Próximo catalizador:</strong> Q1 2026 Business Update — 5 mayo 2026<br>
Si net rev growth &gt;20% cc → tesis "bache temporal" intacta. Si &lt;19% → repricing continúa.
</div>

<div class="ft">
<div>Datos: Adyen shareholder letters · Yahoo Finance · No es consejo de inversión</div>
<div>Generado: {TODAY} · <a href="index.html">Leading Indicators →</a></div>
</div>
</body></html>"""

    return html

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    html = generate_html()
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis.html")
    with open(out_path, "w") as f:
        f.write(html)
    print(f"  Output: {out_path}")
    print("Done!")
