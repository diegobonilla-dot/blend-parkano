import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

st.set_page_config(page_title="Control Tower — Minera Parkano", page_icon="⛏️", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:linear-gradient(135deg,#0B0F1A,#131B2E)}
[data-testid="stHeader"]{background:transparent}
section[data-testid="stSidebar"]{background:#0B0F1A}
.block-container{padding-top:1rem}
div[data-testid="metric-container"]{background:linear-gradient(135deg,#131B2E,#1A2438);padding:.9rem 1.1rem;border-radius:10px;border-left:3px solid #C8A951}
div[data-testid="metric-container"] label{color:#6B7C99!important;font-size:.68rem!important;font-weight:700;text-transform:uppercase;letter-spacing:.07em}
div[data-testid="metric-container"] [data-testid="stMetricValue"]{color:#E8E0CC!important;font-size:1.35rem!important;font-weight:800}
div[data-testid="metric-container"] [data-testid="stMetricDelta"]{font-size:.72rem!important}
h1,h2,h3{color:#C8A951!important;font-weight:700}
.stTabs [data-baseweb="tab-list"]{background:#131B2E;padding:.4rem;border-radius:8px;gap:.3rem}
.stTabs [data-baseweb="tab"]{background:#1A2438;border-radius:6px;color:#6B7C99;padding:.6rem 1.4rem;font-weight:600;border:none}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#C8A951,#9A7D2E)!important;color:#0B0F1A!important}
hr{border-color:rgba(200,169,81,.2)}
</style>
""", unsafe_allow_html=True)

SID = "1jh_7rzOG1pisxwIIiT1CCfY3F0fdXmNA9vaaZFJUfns"
URL_OPS  = f"https://docs.google.com/spreadsheets/d/{SID}/export?format=csv&gid=158096369"
URL_TESO = f"https://docs.google.com/spreadsheets/d/{SID}/export?format=csv&gid=0"

# ─── Conversión número boliviano: "5.971,56" → 5971.56 / "Bs8.134.479,10" → 8134479.10
def bo(v):
    if pd.isna(v): return np.nan
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip()
    for r in ['Bs','%','\xa0',' ']: s = s.replace(r,'')
    if s in ('','-','#DIV/0!','#VALUE!','#REF!','#N/A','nan',''): return np.nan
    s = s.replace('.','').replace(',','.')
    try: return float(s)
    except: return np.nan

@st.cache_data(ttl=300)
def cargar_ops():
    df = pd.read_csv(URL_OPS, dtype=str)
    df.columns = df.columns.str.strip()
    # Usar posicion para garantizar robustez
    cn = {df.columns[0]:'Fecha',
          df.columns[1]:'Ingreso_TMH',
          df.columns[2]:'Inventario_TMH',
          df.columns[3]:'Ley_Zn',
          df.columns[4]:'Ley_Ag',
          df.columns[5]:'Ley_Pb',
          df.columns[6]:'Inv_CC_Zn',
          df.columns[7]:'Inv_CC_Pb',
          df.columns[8]:'TMH_Proc'}
    df = df.rename(columns=cn)
    df = df[list(cn.values())].copy()
    df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
    for c in df.columns[1:]:
        df[c] = df[c].apply(bo)
    df = df.dropna(subset=['Fecha']).sort_values('Fecha').reset_index(drop=True)
    return df

@st.cache_data(ttl=300)
def cargar_teso():
    try:
        df = pd.read_csv(URL_TESO, dtype=str)
        df.columns = df.columns.str.strip()
        cn = {df.columns[0]:'Fecha',
              df.columns[1]:'Bancos',
              df.columns[2]:'Caja',
              df.columns[3]:'CxC_Vig',
              df.columns[4]:'CxC_Ven',
              df.columns[5]:'CxP_Gen',
              df.columns[6]:'CxP_Min'}
        df = df.rename(columns=cn)
        df = df[[c for c in cn.values() if c in df.columns]].copy()
        df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
        for c in df.columns[1:]:
            df[c] = df[c].apply(bo)
        df = df.dropna(subset=['Fecha'])
        # Eliminar filas donde todos los numericos son NaN
        num_cols = [c for c in df.columns if c != 'Fecha']
        df = df.dropna(subset=num_cols, how='all')
        df = df.sort_values('Fecha').reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()

# ─── Cargar datos ───
df_ops = cargar_ops()
df_teso = cargar_teso()

if df_ops.empty:
    st.error("⚠️ No se pudieron cargar datos de Operaciones")
    st.stop()

# ─── Fecha de referencia (ayer o última disponible) ───
ayer = (datetime.now() - timedelta(days=1)).date()

def fecha_ref_para(df):
    fechas = df['Fecha'].dt.date.values
    return ayer if ayer in fechas else pd.Series(fechas).dropna().max()

fref_ops  = fecha_ref_para(df_ops)
fref_teso = fecha_ref_para(df_teso) if not df_teso.empty else None

def snap(df, fref):
    """Fila de referencia para KPIs"""
    r = df[df['Fecha'].dt.date == fref]
    return r.iloc[-1] if len(r) > 0 else df.iloc[-1]

def f2(v, dec=2, pre='', suf=''):
    return f"{pre}{v:,.{dec}f}{suf}" if pd.notna(v) and v == v else "—"

def cplot():
    return dict(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#6B7C99', size=11), margin=dict(l=10,r=10,t=10,b=50),
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, font_size=11),
        xaxis=dict(showgrid=False, nticks=10, tickangle=-30, tickfont_size=10),
        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.06)', tickfont_size=10)
    )

# ─── HEADER ───
c1,c2,c3,c4 = st.columns([3,1,1,1])
with c1: st.markdown("# ⛏️ MINERA PARKANO — Control Tower")
with c2: st.metric("Registros Ops.", len(df_ops))
with c3: st.metric("Registros Tes.", len(df_teso) if not df_teso.empty else 0)
with c4: st.metric("Datos al", fref_ops.strftime("%d/%m/%Y"))
st.markdown("---")

# ─── FILTROS ───
c1,c2,c3,c4 = st.columns([1.5,1.5,1,0.8])
with c1: f_desde = st.date_input("Desde", value=df_ops['Fecha'].min().date())
with c2: f_hasta = st.date_input("Hasta", value=fref_ops)
with c3:
    mmap = {"Todos":0,"Enero":1,"Febrero":2,"Marzo":3,"Abril":4,"Mayo":5,"Junio":6}
    mes = st.selectbox("Mes", list(mmap.keys()))
with c4:
    st.markdown("&nbsp;", unsafe_allow_html=True)
    if st.button("🔄 Actualizar"):
        st.cache_data.clear()
        st.rerun()

# Filtrar operaciones
df_f = df_ops[(df_ops['Fecha']>=pd.to_datetime(f_desde)) & (df_ops['Fecha']<=pd.to_datetime(f_hasta))].copy()
if mes != "Todos": df_f = df_f[df_f['Fecha'].dt.month == mmap[mes]]
df_f = df_f.reset_index(drop=True)

if len(df_f) == 0:
    st.warning("Sin datos para el rango seleccionado"); st.stop()

s = snap(df_f, fref_ops)   # snapshot de operaciones

# ─── TABS ───
t1,t2,t3,t4 = st.tabs(["📊 Operaciones","💰 Tesorería","🔮 Análisis Predictivo","📋 Datos"])

# ═══════════════════════ TAB 1: OPERACIONES ═══════════════════════
with t1:
    st.markdown(f"### KPIs al {fref_ops.strftime('%d/%m/%Y')}")
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: st.metric("🗻 Inv. Broza", f2(s['Inventario_TMH'],2,' ','  TMH'))
    with c2: st.metric("⛏️ Ley Zn", f2(s['Ley_Zn'],2,'','%'), delta=f"Prom: {df_f['Ley_Zn'].mean():.2f}%")
    with c3: st.metric("🥈 Ley Ag", f2(s['Ley_Ag'],2,'','%'), delta=f"Prom: {df_f['Ley_Ag'].mean():.2f}%")
    with c4: st.metric("🔵 Ley Pb", f2(s['Ley_Pb'],2,'','%'), delta=f"Prom: {df_f['Ley_Pb'].mean():.2f}%")
    with c5: st.metric("📥 Ingreso día", f2(s['Ingreso_TMH'],2,'',' TMH'))
    with c6: st.metric("⚙️ Procesado día", f2(s['TMH_Proc'],2,'',' TMH'))

    inv_val = s['Inventario_TMH'] if pd.notna(s['Inventario_TMH']) else 0
    if inv_val < 500:
        st.error(f"⚠️ **ALERTA INVENTARIO CRÍTICO** — {inv_val:,.2f} TMH (umbral mínimo: 500 TMH)")
    elif inv_val < 1000:
        st.warning(f"⚡ **Inventario bajo** — {inv_val:,.2f} TMH (cerca del umbral crítico)")

    st.markdown("---")

    # Gráfico 1: Inventario (área, ancho completo)
    st.markdown("#### Evolución del Inventario de Broza (TMH)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['Inventario_TMH'],
                             mode='lines', name='Inventario',
                             line=dict(color='#C8A951', width=2.5),
                             fill='tozeroy', fillcolor='rgba(200,169,81,0.1)'))
    fig.add_hline(y=500, line=dict(color='#FF4D6D', width=1.5, dash='dash'),
                  annotation_text="Umbral crítico 500 TMH",
                  annotation_font=dict(color='#FF4D6D', size=10))
    fig.update_layout(**cplot(), height=280)
    st.plotly_chart(fig, use_container_width=True)

    # Gráficos 2+3: Leyes y barras (mitad cada uno)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Leyes Zn / Ag / Pb (%)")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['Ley_Zn'], name='Zn%', mode='lines', line=dict(color='#4A9B8E', width=2)))
        fig.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['Ley_Ag'], name='Ag%', mode='lines', line=dict(color='#C8A951', width=2)))
        fig.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['Ley_Pb'], name='Pb%', mode='lines', line=dict(color='#8B6FA6', width=2)))
        fig.update_layout(**cplot(), height=260)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("#### Inventario CC Zn & Pb (TMH)")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['Inv_CC_Zn'], name='CC Zn', mode='lines', line=dict(color='#4A9B8E', width=2)))
        fig.add_trace(go.Scatter(x=df_f['Fecha'], y=df_f['Inv_CC_Pb'], name='CC Pb', mode='lines', line=dict(color='#8B6FA6', width=2)))
        fig.update_layout(**cplot(), height=260)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("#### Ingreso Broza Diario (TMH)")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_f['Fecha'], y=df_f['Ingreso_TMH'], name='Ingreso', marker_color='#4A9B8E', marker_line_width=0))
        fig.update_layout(**cplot(), height=240)
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        st.markdown("#### TMH Procesadas por Día")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_f['Fecha'], y=df_f['TMH_Proc'], name='TMH Proc.', marker_color='#8B6FA6', marker_line_width=0))
        fig.update_layout(**cplot(), height=240)
        st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════ TAB 2: TESORERÍA ═══════════════════════
with t2:
    if df_teso.empty:
        st.info("⚠️ Sin datos de Tesorería disponibles")
    else:
        st.markdown(f"### KPIs Tesorería al {fref_teso.strftime('%d/%m/%Y')}")
        ts = snap(df_teso, fref_teso)

        bancos = ts['Bancos'] if 'Bancos' in ts.index and pd.notna(ts['Bancos']) else 0
        caja   = ts['Caja']   if 'Caja'   in ts.index and pd.notna(ts['Caja'])   else 0
        cxc    = ts['CxC_Vig']if 'CxC_Vig' in ts.index and pd.notna(ts['CxC_Vig']) else 0
        cxp    = ts['CxP_Min']if 'CxP_Min' in ts.index and pd.notna(ts['CxP_Min']) else 0
        liq    = bancos + caja
        ct     = cxc - cxp

        c1,c2,c3,c4,c5,c6 = st.columns(6)
        with c1: st.metric("🏦 Bancos",       f"Bs {bancos:,.0f}")
        with c2: st.metric("💵 Caja",          f"Bs {caja:,.0f}")
        with c3: st.metric("💰 Liquidez Total",f"Bs {liq:,.0f}")
        with c4: st.metric("📈 CxC Vigente",   f"Bs {cxc:,.0f}")
        with c5: st.metric("📉 CxP Mineral",   f"Bs {cxp:,.0f}")
        with c6:
            color = "normal" if ct >= 0 else "inverse"
            st.metric("⚖️ Capital Trabajo", f"Bs {ct:,.0f}", delta="Positivo ✓" if ct>=0 else "Déficit ⚠️", delta_color=color)

        st.markdown("---")

        st.markdown("#### Evolución Efectivo: Bancos & Caja")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_teso['Fecha'], y=df_teso['Bancos'], name='Bancos', mode='lines', line=dict(color='#3DDC84', width=2.5), fill='tozeroy', fillcolor='rgba(61,220,132,0.08)'))
        fig.add_trace(go.Scatter(x=df_teso['Fecha'], y=df_teso['Caja'], name='Caja', mode='lines', line=dict(color='#C8A951', width=2)))
        fig.update_layout(**cplot(), height=280)
        st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### CxC Vigente vs CxP Mineral")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_teso['Fecha'], y=df_teso['CxC_Vig'], name='CxC Vigente', line=dict(color='#3DDC84', width=2)))
            fig.add_trace(go.Scatter(x=df_teso['Fecha'], y=df_teso['CxP_Min'], name='CxP Mineral', line=dict(color='#FF4D6D', width=2)))
            fig.update_layout(**cplot(), height=260)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("#### Capital de Trabajo (CxC - CxP)")
            ct_serie = df_teso['CxC_Vig'].fillna(0) - df_teso['CxP_Min'].fillna(0)
            col_ct = ['#3DDC84' if v >= 0 else '#FF4D6D' for v in ct_serie]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_teso['Fecha'], y=ct_serie, name='Cap. Trabajo', marker_color=col_ct, marker_line_width=0))
            fig.add_hline(y=0, line=dict(color='#6B7C99', width=1, dash='dot'))
            fig.update_layout(**cplot(), height=260)
            st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════ TAB 3: ANÁLISIS PREDICTIVO ═══════════════════════
with t3:
    st.markdown("### 🔮 Análisis Predictivo")
    inv_c = df_f['Inventario_TMH'].dropna()

    if len(inv_c) < 3:
        st.warning("Se necesitan al menos 3 registros para el análisis")
    else:
        X = np.arange(len(inv_c)).astype(float)
        y = inv_c.values.astype(float)
        n = len(X)
        sl = (n*(X*y).sum()-X.sum()*y.sum())/(n*(X**2).sum()-X.sum()**2)
        ic = (y.sum()-sl*X.sum())/n
        yp = sl*X+ic
        sst = ((y-y.mean())**2).sum()
        r2  = 1-((y-yp)**2).sum()/sst if sst>0 else 0

        adj = 'Excelente' if r2>.7 else 'Bueno' if r2>.5 else 'Moderado' if r2>.3 else 'Débil'
        tend = '↗ CRECIENTE' if sl>0 else '↘ DECRECIENTE'
        color_t = 'green' if sl>0 else 'red'

        c1,c2 = st.columns(2)
        with c1:
            st.markdown("#### Regresión Lineal — Inventario Broza")
            st.metric("Ecuación", f"y = {sl:.3f}x + {ic:.1f}")
            st.metric("R² — bondad de ajuste", f"{r2*100:.1f}% ({adj})")
            st.metric("Pendiente", f"{sl:+.2f} TMH/día")
            st.metric("Proyección +30 días", f"{sl*30:+,.0f} TMH")
            st.markdown(f"**Tendencia del período:** :{color_t}[{tend}]")
        with c2:
            st.markdown("#### Estadísticas del Período")
            st.metric("Media Inventario", f"{y.mean():,.2f} TMH")
            st.metric("Máximo Inventario", f"{y.max():,.2f} TMH")
            st.metric("Mínimo Inventario", f"{y.min():,.2f} TMH")
            st.metric("Desv. Estándar",    f"{y.std():,.2f} TMH")
            st.metric("Registros analizados", f"{n} días")

        st.markdown("#### Real vs Línea de Tendencia")
        fechas = df_f.loc[inv_c.index,'Fecha']
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=fechas, y=y, mode='lines', name='Real',
                                 line=dict(color='#C8A951', width=2.5),
                                 fill='tozeroy', fillcolor='rgba(200,169,81,0.08)'))
        fig.add_trace(go.Scatter(x=fechas, y=yp, mode='lines', name='Tendencia',
                                 line=dict(color='#FF4D6D', width=2.5, dash='dash')))
        fig.update_layout(**cplot(), height=360)
        st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════ TAB 4: DATOS ═══════════════════════
with t4:
    st.markdown("### 📋 Histórico Operaciones")
    show = df_f.copy()
    show['Fecha'] = show['Fecha'].dt.strftime('%d/%m/%Y')
    st.dataframe(show, use_container_width=True, height=460)
    csv = df_f.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Descargar CSV filtrado", data=csv,
                       file_name=f'parkano_ops_{datetime.now().strftime("%Y%m%d")}.csv',
                       mime='text/csv')

st.markdown("---")
upd = df_ops['Fecha'].max().strftime('%d/%m/%Y')
st.caption(f"⛏️ Minera Parkano — Control Tower SSOT | Última actualización datos: {upd} | {len(df_ops)} reg. ops · {len(df_teso)} reg. tes. | Auto-refresh: 5 min")
