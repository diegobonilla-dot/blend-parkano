import streamlit as st
import pandas as pd
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, value, LpStatus
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Integral Parkano", layout="wide")

def enviar_correo(asunto, cuerpo, destinatario):
    remitente = "mezclasparkano@gmail.com"
    password = "shre kfdy flin hscs" 
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo, 'plain'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
    except Exception as e:
        st.error(f"Error correo: {e}")

st.title("⚒️ Sistema de Mezclas y Balance Proyectado - Parkano")

# --- 🎯 BARRA LATERAL: OBJETIVOS Y PLANTA ---
st.sidebar.header("🎯 Objetivos del Blend")
t_min = st.sidebar.number_input("Tonelaje Mínimo (TMH)", 0.0, 5000.0, 980.0)
t_max = st.sidebar.number_input("Tonelaje Máximo (TMH)", 0.0, 5000.0, 1100.0)

st.sidebar.subheader("Rangos de Cabeza")
zn_min, zn_max = st.sidebar.slider("Rango Zn %", 0.0, 25.0, (11.0, 12.0))
pb_min, pb_max = st.sidebar.slider("Rango Pb %", 0.0, 5.0, (0.8, 1.0))
ag_min, ag_max = st.sidebar.slider("Rango Ag Oz/TM", 0.0, 5.0, (1.1, 1.5))

st.sidebar.header("⚙️ Parámetros de Planta")
h_perc = st.sidebar.slider("Humedad (%)", 0.0, 15.0, 10.0) / 100
rec_zn = st.sidebar.number_input("Recup. Zn (%)", 0.0, 100.0, 88.0) / 100
ley_conc_zn = st.sidebar.number_input("Ley Zn en Conc (%)", 0.0, 100.0, 50.0)

sheet_url = st.text_input("Link de Google Sheets:", "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0")

if st.button("🚀 GENERAR BLEND Y BALANCE"):
    try:
        # 1. Carga y Limpieza
        base_url = sheet_url.split('/edit')[0]
        gid = sheet_url.split('gid=')[1] if 'gid=' in sheet_url else '0'
        csv_url = f"{base_url}/export?format=csv&gid={gid}"
        df = pd.read_csv(csv_url)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # Buscador de columnas robusto
        c_lote = next((c for c in df.columns if "LOTE" in c), None)
        c_peso = next((c for c in df.columns if "PESO" in c), None)
        c_zn = next((c for c in df.columns if "ZN" in c), None)
        c_pb = next((c for c in df.columns if "PB" in c), None)
        c_ag = next((c for c in df.columns if "AG" in c), None)

        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df = df[df[c_peso] > 0.1].copy()

        # 2. Optimización del Blend
        prob = LpProblem("Blend_Parkano", LpMinimize)
        choices = LpVariable.dicts("L", df.index, lowBound=0)
        total_w = lpSum([choices[i] for i in df.index])
        
        prob += total_w # Función objetivo
        prob += total_w >= t_min
        prob += total_w <= t_max
        
        for i in df.index:
            prob += choices[i] <= df.loc[i, c_peso]
        
        # Restricciones de Leyes Ponderadas
        prob += lpSum([choices[i] * df.loc[i, c_zn] for i in df.index]) >= zn_min * total_w
        prob += lpSum([choices[i] * df.loc[i, c_zn] for i in df.index]) <= zn_max * total_w
        prob += lpSum([choices[i] * df.loc[i, c_pb] for i in df.index]) >= pb_min * total_w
        prob += lpSum([choices[i] * df.loc[i, c_pb] for i in df.index]) <= pb_max * total_w
        prob += lpSum([choices[i] * df.loc[i, c_ag] for i in df.index]) >= ag_min * total_w
        prob += lpSum([choices[i] * df.loc[i, c_ag] for i in df.index]) <= ag_max * total_w
        
        prob.solve()

        if LpStatus[prob.status] == 'Optimal':
            # --- PARTE 1: RESULTADOS DEL BLEND ---
            res = []
            for i in df.index:
                val = value(choices[i])
                if val and val > 0.1:
                    res.append({"Lote": df.loc[i, c_lote], "TMH": val, "Zn%": df.loc[i, c_zn], "Pb%": df.loc[i, c_pb], "Ag Oz/TM": df.loc[i, c_ag]})
            
            rdf = pd.DataFrame(res)
            st.subheader("📋 1. Reporte de Mezcla (Blend)")
            st.table(rdf.style.format("{:.2f}", subset=["TMH", "Zn%", "Pb%", "Ag Oz/TM"]))

            # --- PARTE 2: BALANCE METALÚRGICO PROYECTADO ---
            p_tmh = rdf['TMH'].sum()
            zn_cabeza = (rdf['TMH'] * rdf['Zn%']).sum() / p_tmh
            pb_cabeza = (rdf['TMH'] * rdf['Pb%']).sum() / p_tmh
            ag_cabeza = (rdf['TMH'] * rdf['Ag Oz/TM']).sum() / p_tmh
            
            tms_cabeza = p_tmh * (1 - h_perc)
            fino_zn = tms_cabeza * (zn_cabeza / 100) * rec_zn
            tms_conc_zn = fino_zn / (ley_conc_zn / 100)

            st.subheader("📊 2. Balance Metalúrgico Proyectado")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Mezcla", f"{p_tmh:.2f} TMH")
            col2.metric("Peso Seco", f"{tms_cabeza:.2f} TMS")
            col3.metric("Conc. Zinc", f"{tms_conc_zn:.2f} TMS")
            col4.metric("Ley Zn Cabeza", f"{zn_cabeza:.2f} %")

            # Correo con toda la información
            cuerpo = f"Reporte Parkano:\n\nBLEND: {p_tmh:.2f} TMH\nZn: {zn_cabeza:.2f}%\nPb: {pb_cabeza:.2f}%\nAg: {ag_cabeza:.2f}\nPROYECCIÓN: {tms_conc_zn:.2f} TMS Conc Zn"
            enviar_correo("Sistema Parkano: Blend + Balance", cuerpo, "diego.bonilla@parkano.com.bo")
            st.success("✅ Todo generado y enviado.")
        else:
            st.error("❌ No hay combinación de lotes que cumpla con esas leyes y tonelaje.")

    except Exception as e:
        st.error(f"Error crítico: {e}")
