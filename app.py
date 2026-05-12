import streamlit as st
import pandas as pd
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, value, LpStatus

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Parkano v6", layout="wide")


# ─────────────────────────────────────────────
#  TÍTULO
# ─────────────────────────────────────────────
st.title("⚒️ Sistema de Optimización y Balance Metalúrgico — Parkano")

# ─────────────────────────────────────────────
#  BARRA LATERAL — PARÁMETROS EDITABLES
# ─────────────────────────────────────────────
st.sidebar.header("🎯 Parámetros del Blend")

st.sidebar.subheader("Tonelaje (TMH)")
t_min = st.sidebar.number_input("Tonelaje Mínimo (TMH)", value=980.0, step=10.0)
t_max = st.sidebar.number_input("Tonelaje Máximo (TMH)", value=1100.0, step=10.0)

st.sidebar.subheader("Leyes de Cabeza Objetivo")
zn_min = st.sidebar.number_input("Zn Mín (%)",  value=11.0, step=0.1)
zn_max = st.sidebar.number_input("Zn Máx (%)",  value=12.0, step=0.1)
pb_min = st.sidebar.number_input("Pb Mín (%)",  value=0.8,  step=0.05)
pb_max = st.sidebar.number_input("Pb Máx (%)",  value=1.0,  step=0.05)
ag_min = st.sidebar.number_input("Ag Mín (DM)", value=1.1,  step=0.05)
ag_max = st.sidebar.number_input("Ag Máx (DM)", value=1.5,  step=0.05)

st.sidebar.header("⚙️ Parámetros de Planta")
h_perc  = st.sidebar.number_input("Humedad (%)",  value=5.0,  step=0.5) / 100.0
rec_zn  = st.sidebar.number_input("Rec. Zn (%)",  value=95.0, step=1.0) / 100.0
rec_pb  = st.sidebar.number_input("Rec. Pb (%)",  value=85.0, step=1.0) / 100.0
rec_ag  = st.sidebar.number_input("Rec. Ag (%)",  value=90.0, step=1.0) / 100.0

st.sidebar.header("🔒 Parámetros de Concentrados")
ley_conc_zn   = st.sidebar.number_input("Ley Conc. Zn (%)",      value=50.0, step=1.0) / 100.0
ley_conc_pb   = st.sidebar.number_input("Ley Conc. Pb (%)",      value=60.0, step=1.0) / 100.0
ag_min_conc_zn = st.sidebar.number_input("Ag mín en Conc. Zn (DM)", value=2.5, step=0.1)

# ─────────────────────────────────────────────
#  FUENTE DE DATOS
# ─────────────────────────────────────────────
sheet_url = st.text_input(
    "🔗 Link de Google Sheets (stock de mineral):",
    "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0"
)

# ─────────────────────────────────────────────
#  BOTÓN PRINCIPAL
# ─────────────────────────────────────────────
if st.button("🚀 GENERAR BLEND Y BALANCE METALÚRGICO"):
    try:
        # ── 1. LECTURA DE DATOS ──────────────────────────────────────────
        # Extraer el ID del Sheets del URL
        import re
        sheet_id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
        
        if not sheet_id_match:
            st.error("❌ El link del Google Sheets no es válido. Asegúrate de usar un link que contenga '/d/'")
            st.stop()
        
        sheet_id = sheet_id_match.group(1)
        
        # Extraer el GID (ID de la hoja específica) si existe
        gid_match = re.search(r'[#&]gid=(\d+)', sheet_url)
        gid = gid_match.group(1) if gid_match else '0'
        
        # Construir la URL de exportación correctamente
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        
        try:
            df = pd.read_csv(csv_url)
        except Exception as e:
            st.error(f"❌ Error al leer el CSV: {e}")
            st.error("Intenta esto: Asegúrate de que el link sea compartible (public o con permisos de lectura)")
            st.stop()
        df.columns = [str(c).upper().strip() for c in df.columns]

        # Mapeo flexible de columnas
        c_lote = next((c for c in df.columns if "LOTE" in c or "ID" in c), None)
        c_peso = next((c for c in df.columns if "PESO" in c or "TMH" in c or "TON" in c), None)
        c_zn   = next((c for c in df.columns if c.startswith("ZN") or c == "LEY ZN" or c == "LEY_ZN"), None)
        c_pb   = next((c for c in df.columns if c.startswith("PB") or c == "LEY PB" or c == "LEY_PB"), None)
        c_ag   = next((c for c in df.columns if c.startswith("AG") or c == "LEY AG" or c == "LEY_AG"), None)

        missing = [n for n, c in [("LOTE", c_lote), ("PESO", c_peso), ("ZN", c_zn), ("PB", c_pb), ("AG", c_ag)] if c is None]
        if missing:
            st.error(f"No se encontraron las columnas: {missing}. Columnas detectadas: {list(df.columns)}")
            st.stop()

        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df_clean = df[df[c_peso] > 0].copy().reset_index(drop=True)

        with st.expander("📂 Ver stock de mineral cargado"):
            st.dataframe(df_clean[[c_lote, c_peso, c_zn, c_pb, c_ag]].rename(columns={
                c_lote: "Lote", c_peso: "TMH", c_zn: "Zn %", c_pb: "Pb %", c_ag: "Ag DM"
            }), use_container_width=True)

        # ── 2. OPTIMIZADOR (PuLP) ────────────────────────────────────────
        prob = LpProblem("Blend_Parkano", LpMinimize)
        idx  = df_clean.index.tolist()
        vars_lote = LpVariable.dicts("x", idx, lowBound=0)

        total_w = lpSum([vars_lote[i] for i in idx])

        # Objetivo: maximizar Zn total (minimizar negativo) para aprovechar el mineral
        prob += -lpSum([vars_lote[i] * df_clean.loc[i, c_zn] for i in idx])

        # Restricciones de tonelaje
        prob += total_w >= t_min
        prob += total_w <= t_max

        # Restricciones de disponibilidad por lote
        for i in idx:
            prob += vars_lote[i] <= df_clean.loc[i, c_peso]

        # Restricciones de leyes (usando variables auxiliares para el promedio ponderado)
        # Zn
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_zn] for i in idx]) >= zn_min * total_w
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_zn] for i in idx]) <= zn_max * total_w
        # Pb
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_pb] for i in idx]) >= pb_min * total_w
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_pb] for i in idx]) <= pb_max * total_w
        # Ag
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_ag] for i in idx]) >= ag_min * total_w
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_ag] for i in idx]) <= ag_max * total_w

        prob.solve()
        status = LpStatus[prob.status]

        if status != 'Optimal':
            st.warning(
                f"⚠️ No se encontró una mezcla factible con los rangos actuales (Estado: {status}). "
                "Prueba ampliando los rangos de ley o de tonelaje."
            )
            st.stop()

        # ── 3. ARMADO DE RESULTADOS DEL BLEND ───────────────────────────
        res_data = []
        for i in idx:
            tmh_i = value(vars_lote[i])
            if tmh_i is not None and tmh_i > 0.01:
                res_data.append({
                    "Lote":   df_clean.loc[i, c_lote],
                    "TMH":    round(tmh_i, 2),
                    "Zn %":   df_clean.loc[i, c_zn],
                    "Pb %":   df_clean.loc[i, c_pb],
                    "Ag DM":  df_clean.loc[i, c_ag],
                })

        rdf = pd.DataFrame(res_data)

        # Leyes de cabeza ponderadas
        tmh_total  = rdf['TMH'].sum()
        zn_cabeza  = (rdf['TMH'] * rdf['Zn %']).sum()  / tmh_total
        pb_cabeza  = (rdf['TMH'] * rdf['Pb %']).sum()  / tmh_total
        ag_cabeza  = (rdf['TMH'] * rdf['Ag DM']).sum() / tmh_total

        # Mostrar tabla blend
        st.subheader("📋 Lotes Seleccionados para el Blend")
        rdf_display = rdf.copy()
        rdf_display["% del Blend"] = (rdf_display["TMH"] / tmh_total * 100).round(1)
        st.dataframe(
            rdf_display.style.format({
                "TMH": "{:.2f}", "Zn %": "{:.2f}", "Pb %": "{:.2f}",
                "Ag DM": "{:.3f}", "% del Blend": "{:.1f}%"
            }),
            use_container_width=True
        )

        # Resumen de leyes de cabeza
        st.subheader("⚖️ Leyes de Cabeza del Blend")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("TMH Total", f"{tmh_total:.2f}")
        c2.metric("Zn Cabeza", f"{zn_cabeza:.2f} %")
        c3.metric("Pb Cabeza", f"{pb_cabeza:.2f} %")
        c4.metric("Ag Cabeza", f"{ag_cabeza:.3f} DM")

        # ── 4. BALANCE METALÚRGICO ───────────────────────────────────────
        st.subheader("📊 Balance Metalúrgico Proyectado")

        # Toneladas Secas
        tms_total = tmh_total * (1 - h_perc)

        # Metales finos recuperados (unidades: TM de metal)
        zn_fino_recuperado = tms_total * (zn_cabeza / 100) * rec_zn
        pb_fino_recuperado = tms_total * (pb_cabeza / 100) * rec_pb
        ag_fino_recuperado = tms_total * ag_cabeza * rec_ag   # DM·TMS → DM·TMS (kilos finos se calculan aparte)

        # ── Concentrado de ZINC ──────────────────────────────────────────
        # Peso del concentrado: metal fino / ley del concentrado
        tms_conc_zn = zn_fino_recuperado / ley_conc_zn

        # Plata en conc. Zn: se garantiza mínimo ag_min_conc_zn DM
        # (los DM en el concentrado son oz/TM concentrado seco)
        ag_en_conc_zn_dm = ag_min_conc_zn          # garantizado por especificación
        ag_fino_en_conc_zn = tms_conc_zn * ag_en_conc_zn_dm   # DM·TMS conc.

        # ── Concentrado de PLOMO ─────────────────────────────────────────
        tms_conc_pb = pb_fino_recuperado / ley_conc_pb

        # Plata restante va al concentrado de Pb
        ag_fino_en_conc_pb = ag_fino_recuperado - ag_fino_en_conc_zn
        if tms_conc_pb > 0:
            ag_en_conc_pb_dm = ag_fino_en_conc_pb / tms_conc_pb
        else:
            ag_en_conc_pb_dm = 0.0

        # Verificación: si la plata recuperada total < la que necesita el conc. Zn,
        # el conc. Zn igual tendrá 2.5 DM (viene del mineral); se avisa al usuario.
        if ag_fino_en_conc_pb < 0:
            st.warning(
                "⚠️ La plata recuperada total es insuficiente para cubrir los 2.5 DM "
                "garantizados en el concentrado de Zn. Revisa el blend o los parámetros."
            )
            ag_en_conc_pb_dm = 0.0

        # Ley Zn en conc. Pb (dilución esperada)
        zn_en_conc_pb = (tms_total * (zn_cabeza / 100) * (1 - rec_zn)) / tms_conc_pb if tms_conc_pb > 0 else 0

        # ── TABLA DE BALANCE ─────────────────────────────────────────────
        balance = pd.DataFrame({
            "Producto":          ["Cabeza (TMS)", "Concentrado Zn", "Concentrado Pb"],
            "TMS":               [round(tms_total, 2),    round(tms_conc_zn, 2),    round(tms_conc_pb, 2)],
            "Ley Zn (%)":        [round(zn_cabeza, 2),    round(ley_conc_zn * 100, 1), round(zn_en_conc_pb * 100, 2)],
            "Ley Pb (%)":        [round(pb_cabeza, 2),    "—",                      round(ley_conc_pb * 100, 1)],
            "Ag (DM)":           [round(ag_cabeza, 3),    round(ag_en_conc_zn_dm, 2), round(ag_en_conc_pb_dm, 2)],
            "Rec. Aplicada":     ["Base",                 f"{rec_zn*100:.0f}% Zn",  f"{rec_pb*100:.0f}% Pb / {rec_ag*100:.0f}% Ag"],
        })
        st.dataframe(balance, use_container_width=True, hide_index=True)

        # Métricas rápidas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("TMH Blend",       f"{tmh_total:.2f}")
        m2.metric("TMS (-Humedad)",  f"{tms_total:.2f}")
        m3.metric("Conc. Zn (TMS)", f"{tms_conc_zn:.2f}")
        m4.metric("Conc. Pb (TMS)", f"{tms_conc_pb:.2f}")

        st.info(
            f"✅ Conc. Zn asegurado a **{ag_en_conc_zn_dm:.2f} DM** de Ag  |  "
            f"Conc. Pb con **{ag_en_conc_pb_dm:.2f} DM** de Ag (plata restante)"
        )

    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.exception(e)
