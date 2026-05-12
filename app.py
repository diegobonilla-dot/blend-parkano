import streamlit as st
import pandas as pd
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, value, LpStatus
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Parkano v5", layout="wide")

def enviar_correo(asunto, cuerpo_html, destinatario):
    remitente = "mezclasparkano@gmail.com"
    # IMPORTANTE: Esta contraseña debe ser una "App Password" de Google
    password = "shre kfdy flin hscs" 
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo_html, 'html'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error al enviar correo: {e}")
        return False

st.title("⚒️ Sistema de Optimización y Balance Metalúrgico - Parkano")

# --- PARÁMETROS EN BARRA LATERAL ---
st.sidebar.header("🎯 Objetivos del Blend")
t_min = st.sidebar.number_input("Tonelaje Mínimo (TMH)", value=100.0)
t_max = st.sidebar.number_input("Tonelaje Máximo (TMH)", value=500.0)

st.sidebar.subheader("Leyes de Cabeza")
zn_obj = st.sidebar.slider("Zn %", 0.0, 30.0, (10.0, 15.0))
pb_obj = st.sidebar.slider("Pb %", 0.0, 10.0, (1.0, 3.0))
ag_obj = st.sidebar.slider("Ag DM", 0.0, 5.0, (0.5, 2.0))

st.sidebar.header("⚙️ Parámetros Planta")
h_perc = st.sidebar.number_input("Humedad (%)", value=5.0) / 100
rec_zn = st.sidebar.number_input("Rec. Zn (%)", value=95.0) / 100
rec_pb = st.sidebar.number_input("Rec. Pb (%)", value=85.0) / 100
rec_ag = st.sidebar.number_input("Rec. Ag (%)", value=90.0) / 100

sheet_url = st.text_input("Pega el link de Google Sheets aquí:", "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0")

if st.button("🚀 GENERAR BLEND Y BALANCE"):
    try:
        # 1. LECTURA DE DATOS
        csv_url = sheet_url.replace('/edit#gid=', '/export?format=csv&gid=')
        if '/edit' in sheet_url and 'gid=' not in sheet_url:
            csv_url = sheet_url.replace('/edit', '/export?format=csv')
            
        df = pd.read_csv(csv_url)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # Mapeo flexible de columnas (Para que no falle si cambia el nombre)
        c_lote = next((c for c in df.columns if "LOTE" in c), None)
        c_peso = next((c for c in df.columns if "PESO" in c), None)
        c_zn = next((c for c in df.columns if "ZN" in c), None)
        c_pb = next((c for c in df.columns if "PB" in c), None)
        c_ag = next((c for c in df.columns if "AG" in c), None)

        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df_clean = df[df[c_peso] > 0].copy()

        # 2. OPTIMIZADOR
        prob = LpProblem("Optimizador_Parkano", LpMinimize)
        idx = df_clean.index
        vars = LpVariable.dicts("Lote", idx, lowBound=0)
        
        # Objetivo: Minimizar (solo para encontrar solución factible)
        prob += lpSum([vars[i] for i in idx])
        
        # Restricciones de Peso
        total_w = lpSum([vars[i] for i in idx])
        prob += total_w >= t_min
        prob += total_w <= t_max
        for i in idx:
            prob += vars[i] <= df_clean.loc[i, c_peso]

        # Restricciones de Leyes
        prob += lpSum([vars[i] * df_clean.loc[i, c_zn] for i in idx]) >= zn_obj[0] * total_w
        prob += lpSum([vars[i] * df_clean.loc[i, c_zn] for i in idx]) <= zn_obj[1] * total_w
        prob += lpSum([vars[i] * df_clean.loc[i, c_pb] for i in idx]) >= pb_obj[0] * total_w
        prob += lpSum([vars[i] * df_clean.loc[i, c_pb] for i in idx]) <= pb_obj[1] * total_w
        prob += lpSum([vars[i] * df_clean.loc[i, c_ag] for i in idx]) >= ag_obj[0] * total_w
        prob += lpSum([vars[i] * df_clean.loc[i, c_ag] for i in idx]) <= ag_obj[1] * total_w

        prob.solve()

        if LpStatus[prob.status] == 'Optimal':
            # 3. RESULTADOS DEL BLEND
            res_data = []
            for i in idx:
                tmh = value(vars[i])
                if tmh > 0.1:
                    res_data.append({
                        "Lote": df_clean.loc[i, c_lote],
                        "TMH": tmh,
                        "Zn %": df_clean.loc[i, c_zn],
                        "Pb %": df_clean.loc[i, c_pb],
                        "Ag DM": df_clean.loc[i, c_ag]
                    })
            
            rdf = pd.DataFrame(res_data)
            st.subheader("📋 Resultados del Blend Seleccionado")
            st.dataframe(rdf.style.format("{:.2f}", subset=["TMH", "Zn %", "Pb %", "Ag DM"]))

            # 4. BALANCE METALÚRGICO
            tmh_total = rdf['TMH'].sum()
            zn_cabeza = (rdf['TMH'] * rdf['Zn %']).sum() / tmh_total
            pb_cabeza = (rdf['TMH'] * rdf['Pb %']).sum() / tmh_total
            ag_cabeza = (rdf['TMH'] * rdf['Ag DM']).sum() / tmh_total
            
            tms_total = tmh_total * (1 - h_perc)
            
            # Concentrados
            tms_conc_zn = (tms_total * (zn_cabeza/100) * rec_zn) / 0.50 # 50% Ley Zn
            tms_conc_pb = (tms_total * (pb_cabeza/100) * rec_pb) / 0.60 # 60% Ley Pb
            
            # Distribución de Plata
            ag_fina_total = tms_total * ag_cabeza * rec_ag
            ag_en_conc_zn = tms_conc_zn * 2.5 # Aseguramos 2.5 DM
            ag_en_conc_pb = (ag_fina_total - ag_en_conc_zn) / tms_conc_pb
            
            st.subheader("📊 Balance Proyectado")
            col1, col2 = st.columns(2)
            col1.metric("Total TMH", f"{tmh_total:.2f}")
            col1.metric("Total TMS (-5%)", f"{tms_total:.2f}")
            col2.metric("Conc. Zn (TMS)", f"{tms_conc_zn:.2f}")
            col2.metric("Conc. Pb (TMS)", f"{tms_conc_pb:.2f}")

            # 5. ENVIAR REPORTE
            cuerpo = f"""
            <html>
            <body>
                <h2>Reporte de Mezcla - Parkano</h2>
                <p><b>TMH Total:</b> {tmh_total:.2f}</p>
                <p><b>Leyes Cabeza:</b> Zn: {zn_cabeza:.2f}%, Pb: {pb_cabeza:.2f}%, Ag: {ag_cabeza:.2f} DM</p>
                <hr>
                <h3>Proyección de Concentrados:</h3>
                <ul>
                    <li><b>Zinc:</b> {tms_conc_zn:.2f} TMS (@ 50% Zn y 2.5 DM Ag)</li>
                    <li><b>Plomo:</b> {tms_conc_pb:.2f} TMS (@ 60% Pb y {ag_en_conc_pb:.2f} DM Ag)</li>
                </ul>
            </body>
            </html>
            """
            if enviar_correo("Nuevo Balance Proyectado", cuerpo, "diego.bonilla@parkano.com.bo"):
                st.success("✅ Reporte enviado a diego.bonilla@parkano.com.bo")
                
        else:
            st.warning("⚠️ No se encontró una mezcla que cumpla con esas leyes. Intenta ampliar los rangos.")

    except Exception as e:
        st.error(f"Hubo un problema con los datos del Excel: {e}")
