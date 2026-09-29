"""
EcoFlow Audit - software dashboard for Smart-MatRec
Closed-Loop Solvent Recovery & Automated Mass-Balance Audit System
ALCHEMI 2026 | Problem Statement 2: Reduction of Industrial Waste

Run:
    pip install streamlit plotly pandas numpy
    streamlit run app.py
"""

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------
# Constants (Isopropanol, IPA, is the reference solvent)
# --------------------------------------------------------------------------
SOLVENT = "Isopropanol (IPA)"
DENSITY_KG_PER_L = 0.786                      # kg/L at ~20 C
CO2_PER_KG_IPA = 3 * 44.01 / 60.10            # C3H8O + 4.5 O2 -> 3 CO2 + 4 H2O  (~2.197 kg CO2/kg)
CAPEX_INR = 350_000                           # Smart-MatRec capital cost
LEAK_LOSS_L_PER_DAY = 25.0                    # extra loss when a flange leak is active (demo value)

GREEN, RED, GREY, BLUE = "#2e7d32", "#c62828", "#78909c", "#1565c0"

st.set_page_config(page_title="EcoFlow Audit | Smart-MatRec", page_icon="♻️", layout="wide")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def inr(x: float, decimals: int = 0) -> str:
    """Format a number in Indian digit grouping, e.g. 1234567 -> ₹12,34,567."""
    neg = x < 0
    s = f"{abs(x):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + "₹" + whole + ("." + frac if frac else "")


def mass_balance(feed, product, recovery_pct, leak_l=0.0):
    """
    Feed (I) = Product (P) + Recovered (R) + Unaccounted loss (U)
    Waste stream W = I - P   (solvent leaving the reactor as vent vapour / spent stream)
    R = W * recovery% (less any active leak)      U = W - R
    """
    waste = max(feed - product, 0.0)
    recovered = max(waste * recovery_pct / 100.0 - leak_l, 0.0)
    unaccounted = waste - recovered
    material_eff = (product + recovered) / feed * 100.0 if feed else 0.0
    recovery_eff = recovered / waste * 100.0 if waste else 0.0
    return dict(waste=waste, recovered=recovered, unaccounted=unaccounted,
                material_eff=material_eff, recovery_eff=recovery_eff)


# --------------------------------------------------------------------------
# Sidebar inputs
# --------------------------------------------------------------------------
st.sidebar.title("♻️ EcoFlow Audit")
st.sidebar.caption("Smart-MatRec | Solvent: " + SOLVENT)

st.sidebar.header("1. Mass-balance inputs")
feed = st.sidebar.number_input("Total Raw Solvent Input (L/day)", min_value=50.0, max_value=20000.0,
                               value=1000.0, step=50.0)
product = st.sidebar.number_input("Batch Process Requirement (L/day)", min_value=0.0, max_value=float(feed),
                                  value=min(700.0, float(feed)), step=25.0,
                                  help="Solvent that actually goes into product / is consumed by the batch.")
recovery_pct = st.sidebar.slider("Condenser Recovery Rate (%)", 0, 99, 85,
                                 help="Share of the waste-stream solvent condensed and recovered.")

st.sidebar.header("2. Financial inputs")
solvent_cost = st.sidebar.slider("Solvent Cost (₹/L)", 40, 250, 85, 5)
op_days = st.sidebar.slider("Operating Days / Year", 150, 365, 300, 5)

with st.sidebar.expander("Advanced assumptions"):
    conv_recovery_pct = st.slider("Conventional plant recovery (%)", 0, 60, 0,
                                  help="Recovery already achieved WITHOUT Smart-MatRec (0 = all waste solvent vented/disposed).")
    reuse_yield = st.slider("Reuse yield of recovered solvent (%)", 70, 100, 90,
                            help="Fraction of recovered solvent that meets spec and returns to the process.")
    opex_day = st.number_input("Recovery OpEx (₹/day)", min_value=0.0, value=2500.0, step=100.0,
                               help="Power, chilled water, vacuum pump, maintenance, operator share.")
    vent_fraction = st.slider("Share of unrecovered solvent lost to air (%)", 10, 100, 50,
                              help="Rest goes to liquid waste / incineration.")

# Leak state comes from the toggle in the alerts tab (widget state persists across reruns)
leak_active = st.session_state.get("leak_toggle", False)

# --------------------------------------------------------------------------
# Core calculations
# --------------------------------------------------------------------------
new = mass_balance(feed, product, recovery_pct, LEAK_LOSS_L_PER_DAY if leak_active else 0.0)
conv = mass_balance(feed, product, conv_recovery_pct)

reused_new = new["recovered"] * reuse_yield / 100
reused_conv = conv["recovered"] * reuse_yield / 100

gross_saving_day = (reused_new - reused_conv) * solvent_cost
net_saving_day = gross_saving_day - opex_day
net_saving_year = net_saving_day * op_days
payback_months = CAPEX_INR / (net_saving_year / 12) if net_saving_year > 0 else float("inf")

extra_recovered_l = max(new["recovered"] - conv["recovered"], 0.0)
voc_prevented_kg_day = extra_recovered_l * DENSITY_KG_PER_L * vent_fraction / 100
co2e_t_year = voc_prevented_kg_day * CO2_PER_KG_IPA * op_days / 1000

annual_cost_conv = (feed - reused_conv) * solvent_cost * op_days
annual_cost_new = (feed - reused_new) * solvent_cost * op_days + opex_day * op_days

# --------------------------------------------------------------------------
# Header + tabs
# --------------------------------------------------------------------------
st.title("EcoFlow Audit: Live Solvent Mass-Balance Dashboard")
st.caption("Smart-MatRec | Closed-Loop Solvent Recovery & Automated Mass-Balance Audit System")

tab_mb, tab_alert, tab_roi, tab_cmp, tab_exp = st.tabs(
    ["⚖️ Mass Balance", "🚨 Anomaly & Leak Alerts", "💰 ROI & Environment", "📊 Conventional vs Smart-MatRec",
     "📄 Audit Report"])

# ---- 1. Mass balance -------------------------------------------------------
with tab_mb:
    st.subheader("Dynamic Mass Balance Tracker")
    st.latex(r"\text{Input} = \text{Product} + \text{Recovered} + \text{Unaccounted Loss}")
    st.latex(rf"{feed:,.0f} \;=\; {product:,.0f} \;+\; {new['recovered']:,.1f} \;+\; {new['unaccounted']:,.1f}"
             r"\quad \text{(L/day)}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Waste-stream solvent", f"{new['waste']:,.0f} L/day")
    c2.metric("Recovered solvent", f"{new['recovered']:,.1f} L/day")
    c3.metric("Unaccounted Material Loss", f"{new['unaccounted']:,.1f} L/day",
              delta=f"{new['unaccounted'] - conv['unaccounted']:,.1f} vs conventional", delta_color="inverse")
    c4.metric("Overall Material Efficiency", f"{new['material_eff']:.1f} %",
              delta=f"{new['material_eff'] - conv['material_eff']:+.1f} pts vs conventional")

    st.markdown(
        f"**Recovery Efficiency** = Recovered / Waste x 100 = {new['recovered']:,.1f} / {new['waste']:,.0f} x 100 "
        f"= **{new['recovery_eff']:.1f} %**   |   "
        f"**Material Efficiency** = (Product + Recovered) / Input x 100 = **{new['material_eff']:.1f} %**"
    )
    if leak_active:
        st.warning(f"Leak simulation is ON: {LEAK_LOSS_L_PER_DAY:.0f} L/day is being deducted from recovered solvent.")

    fig = go.Figure()
    for name, val, col in [("Product (used)", product, BLUE), ("Recovered", new["recovered"], GREEN),
                           ("Unaccounted loss", new["unaccounted"], RED)]:
        fig.add_bar(y=["Solvent fate"], x=[val], name=name, orientation="h", marker_color=col,
                    text=[f"{val:,.0f} L"], textposition="inside")
    fig.update_layout(barmode="stack", height=220, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=-0.4), xaxis_title="L/day")
    st.plotly_chart(fig, use_container_width=True)

# ---- 2. Alerts -------------------------------------------------------------
with tab_alert:
    st.subheader("Real-Time Anomaly & Leak Alert Panel")
    st.caption("Simulated sensor stream. In deployment these tags come from the PLC / IoT gateway (Modbus/OPC-UA).")
    st.toggle("🔧 Simulate Solvent Leak", key="leak_toggle",
              help="Injects a flange leak: vent pressure drops, VOC ppm at the flange rises, recovery falls.")

    if "hist" not in st.session_state:
        st.session_state.hist = []

    def live_panel(leak: bool, recovered_l_day: float):
        rng = np.random.default_rng()
        pressure = rng.normal(1.1, 0.12) if leak else rng.normal(2.0, 0.06)      # kPa(g)
        flange_ppm = rng.normal(420, 55) if leak else rng.normal(6, 1.5)          # VOC ppm at flange
        cond_temp = rng.normal(11.5, 0.5) if leak else rng.normal(8.0, 0.25)      # deg C
        flow = max(rng.normal(recovered_l_day / 24, 0.4), 0)                      # L/h recovered

        st.session_state.hist.append(pressure)
        st.session_state.hist = st.session_state.hist[-40:]

        flange_leak = flange_ppm > 50
        low_pressure = pressure < 1.5
        hot_condenser = cond_temp > 10

        if flange_leak or low_pressure or hot_condenser:
            st.error("🚨 ALERT: Loss of containment suspected. Flange VOC above 50 ppm limit. "
                     "Inspect vent header flange F-102 and isolate the reactor vent line.")
        else:
            st.success("✅ All sensors within normal limits. Closed loop healthy.")

        a, b, c, d, e = st.columns(5)
        a.metric("Reactor vent vapour pressure", f"{pressure:.2f} kPa(g)", "LOW" if low_pressure else "Normal",
                 delta_color="inverse" if low_pressure else "off")
        b.metric("Flange VOC concentration", f"{flange_ppm:.0f} ppm", "HIGH" if flange_leak else "Normal",
                 delta_color="inverse" if flange_leak else "off")
        c.metric("Condenser outlet temp", f"{cond_temp:.1f} °C", "HIGH" if hot_condenser else "Normal",
                 delta_color="inverse" if hot_condenser else "off")
        d.metric("Recovered-solvent flow", f"{flow:.1f} L/h")
        e.metric("Flange leak status", "🔴 LEAK" if flange_leak else "🟢 OK")

        line = go.Figure(go.Scatter(y=st.session_state.hist, mode="lines+markers",
                                    line=dict(color=RED if leak else GREEN)))
        line.add_hline(y=1.5, line_dash="dash", line_color=GREY, annotation_text="Low-pressure alarm")
        line.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Vent pressure (kPa g)",
                           xaxis_title="Last readings")
        st.plotly_chart(line, use_container_width=True)

    if hasattr(st, "fragment"):
        st.fragment(run_every=2)(live_panel)(leak_active, new["recovered"])   # auto-refresh every 2 s
    else:
        live_panel(leak_active, new["recovered"])
        st.button("Refresh sensors")

# ---- 3. ROI & environment ---------------------------------------------------
with tab_roi:
    st.subheader("Financial ROI & Environmental Impact")
    st.caption("Change Solvent Cost and Operating Days in the sidebar. Savings are measured against the conventional "
               f"baseline ({conv_recovery_pct}% recovery) after {reuse_yield}% reuse yield and OpEx of {inr(opex_day)}/day.")
    r1, r2, r3 = st.columns(3)
    r1.metric("Daily Savings", inr(net_saving_day))
    r2.metric("Annual Savings", inr(net_saving_year))
    r3.metric("Payback Period (CapEx ₹3,50,000)",
              f"{payback_months:.2f} months" if np.isfinite(payback_months) else "No payback")
    e1, e2, e3 = st.columns(3)
    e1.metric("VOC prevented", f"{voc_prevented_kg_day:,.1f} kg/day")
    e2.metric("Annual VOC emissions prevented", f"{co2e_t_year:,.1f} t CO2e/year")
    e3.metric("Fresh solvent avoided", f"{(reused_new - reused_conv) * op_days / 1000:,.1f} kL/year")
    with st.expander("Calculation basis"):
        st.markdown(
            f"- Daily savings = (Reused solvent, Smart-MatRec − Reused solvent, conventional) x ₹/L − OpEx = "
            f"({reused_new:,.1f} − {reused_conv:,.1f}) x {solvent_cost} − {opex_day:,.0f} = **{inr(net_saving_day)}**\n"
            f"- Payback (months) = CapEx / (Annual savings / 12) = {CAPEX_INR:,} / ({net_saving_year:,.0f} / 12)\n"
            f"- CO2e = extra solvent recovered x {DENSITY_KG_PER_L} kg/L x air-loss share x {CO2_PER_KG_IPA:.3f} kg CO2/kg IPA "
            f"(stoichiometric oxidation, C3H8O + 4.5 O2 → 3 CO2 + 4 H2O) x days / 1000\n"
            f"- Excludes installation downtime, statutory fees and carbon credits (conservative)."
        )

# ---- 4. Comparison charts -----------------------------------------------------
with tab_cmp:
    st.subheader("Conventional Process vs Smart-MatRec")
    k1, k2 = st.columns(2)

    loss_fig = go.Figure(go.Bar(x=["Conventional", "Smart-MatRec"],
                                y=[conv["unaccounted"], new["unaccounted"]],
                                marker_color=[RED, GREEN],
                                text=[f"{conv['unaccounted']:,.0f}", f"{new['unaccounted']:,.0f}"],
                                textposition="outside"))
    loss_fig.update_layout(title="Material loss (L/day)", height=380, yaxis_title="L/day")
    k1.plotly_chart(loss_fig, use_container_width=True)

    cost_fig = go.Figure(go.Bar(x=["Conventional", "Smart-MatRec"],
                                y=[annual_cost_conv, annual_cost_new],
                                marker_color=[RED, GREEN],
                                text=[inr(annual_cost_conv), inr(annual_cost_new)],
                                textposition="outside"))
    cost_fig.update_layout(title="Annual solvent + operating cost (₹)", height=380, yaxis_title="₹ / year")
    k2.plotly_chart(cost_fig, use_container_width=True)

    months = np.arange(0, 25)
    cum_conv = annual_cost_conv / 12 * months
    cum_new = CAPEX_INR + annual_cost_new / 12 * months
    cum_fig = go.Figure()
    cum_fig.add_scatter(x=months, y=cum_conv, name="Conventional", line=dict(color=RED))
    cum_fig.add_scatter(x=months, y=cum_new, name="Smart-MatRec (incl. CapEx)", line=dict(color=GREEN))
    cum_fig.update_layout(title="Cumulative cost: break-even where the lines cross", height=380,
                          xaxis_title="Months", yaxis_title="₹")
    st.plotly_chart(cum_fig, use_container_width=True)

# ---- 5. Report exporter -------------------------------------------------------
with tab_exp:
    st.subheader("Automated Compliance Report Exporter")
    st.caption("30-day daily mass-balance log. Today's row uses the live inputs above; earlier rows are simulated "
               "day-to-day variation for demonstration. In deployment, rows are written from the flowmeter historian.")
    log_days = st.slider("Days in log", 7, 90, 30)

    def build_log(n_days: int) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        rows = []
        today = dt.date.today()
        for i in range(n_days):
            day = today - dt.timedelta(days=n_days - 1 - i)
            is_today = i == n_days - 1
            scale = 1.0 if is_today else 1 + rng.normal(0, 0.02)
            f = feed * scale
            p = product * scale
            rr = recovery_pct if is_today else float(np.clip(recovery_pct + rng.normal(0, 1.5), 0, 99))
            leak_l = LEAK_LOSS_L_PER_DAY if (is_today and leak_active) else 0.0
            m = mass_balance(f, p, rr, leak_l)
            rows.append({
                "Date": day.isoformat(),
                "Solvent": SOLVENT,
                "Feed_L": round(f, 1),
                "Product_L": round(p, 1),
                "Waste_Stream_L": round(m["waste"], 1),
                "Recovered_L": round(m["recovered"], 1),
                "Unaccounted_Loss_L": round(m["unaccounted"], 1),
                "Unaccounted_Loss_kg": round(m["unaccounted"] * DENSITY_KG_PER_L, 1),
                "Balance_Check_L": round(f - p - m["recovered"] - m["unaccounted"], 3),
                "Recovery_Efficiency_pct": round(m["recovery_eff"], 1),
                "Material_Efficiency_pct": round(m["material_eff"], 1),
                "Leak_Alarm": "YES" if leak_l else "NO",
                "Value_Recovered_INR": round(m["recovered"] * reuse_yield / 100 * solvent_cost),
                "Value_Lost_INR": round(m["unaccounted"] * solvent_cost),
                "Data_Source": "LIVE_INPUT" if is_today else "SIMULATED",
            })
        return pd.DataFrame(rows)

    log_df = build_log(log_days)
    st.dataframe(log_df, use_container_width=True, height=300)
    st.download_button("⬇️ Download Mass-Balance Audit CSV",
                       data=log_df.to_csv(index=False).encode("utf-8"),
                       file_name=f"smart_matrec_mass_balance_{dt.date.today().isoformat()}.csv",
                       mime="text/csv")