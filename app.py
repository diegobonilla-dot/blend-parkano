import streamlit as st
import pandas as pd
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, value
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema de Mezclas Parkano", layout="wide")

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
        st.error(f"Error al enviar correo: {e}")

st.title("⚒️ Sistema de Optimización de Mezclas - Parkano")

# --- BARRA LATERAL ---
st.sidebar.header("⚙️ Parámetros de Planta")
h_perc = st.sidebar.slider("Humedad (%)", 0.0, 15.0, 10.0) / 100
rec_zn = st.sidebar.number_input("Rec. Zinc (%)", 0.0, 100.0, 85.0) / 100
rec_pb = st.sidebar.number_input("Rec. Plomo (%)", 0.0, 100.0, 80.0) / 100
rec_ag = st.sidebar.number_input("Rec. Plata (%)", 0.0, 100.0, 75.0) / 100
ley_conc_zn = st.sidebar.number_input("Ley Zn en Conc. (%)", 0.0, 100.0, 50.0)
ley_conc_pb = st.sidebar.number_input("Ley Pb en Conc. (%)", 0.0, 100.0, 60.0)

sheet_url = st.text_input("Pega el link de Google Sheets:", "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0")

if st.button("🚀 GENERAR BLEND"):
    try:
        # 1. Lectura del archivo
        csv_url = sheet_url.split('/edit')[0] + '/export?format=csv'
        df = pd.read_csv(csv_url)
        
        # 2. Limpieza de columnas para que coincidan con tu imagen
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Mapeo exacto según tu imagen image_9cdba0.png
        c_lote = "ID LOTE"
        c_peso = "PESO"
        c_zn = "LEY ZN"
        c_pb = "LEY PB"
        c_ag = "LEY AG"

        # Verificar si las columnas existen tras la limpieza
        if c_peso not in df.columns:
            st.error(f"No encuentro la columna 'Peso'. Columnas leídas: {list(df.columns)}")
            st.stop()

        # 3. Limpieza de datos (quitar vacíos y totales)
        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df = df[(df[c_peso] > 0) & (df[c_lote].notna())].copy()

        # 4. Optimización
        prob = LpProblem("Mezcla", LpMinimize)
        choices = LpVariable.dicts("L", df.index, lowBound=0)
        prob += lpSum([choices[i] for i in df.index])
        for i in df.index:
            prob += choices[i] <= df.loc[i, c_peso]
        
        prob.solve()
        
        if value(prob.status) == 1:
            res = []
            for i in df.index:
                val = value(choices[i])
                if val and val > 0.1:
                    res.append({
                        "Lote": df.loc[i, c_lote],
                        "Peso_TMH": val,
                        "Zn%": df.loc[i, c_zn],
                        "Pb%": df.loc[i, c_pb],
                        "Ag_DM": df.loc[i, c_ag]
                    })
            
            rdf = pd.DataFrame(res)
            st.subheader("📋 Resumen del Blend")
            st.dataframe(rdf)
            
            # 5. Cálculos de Balance
            p_tot = rdf['Peso_TMH'].sum()
            zn_p = (rdf['Peso_TMH'] * rdf['Zn%']).sum() / p_tot
            pb_p = (rdf['Peso_TMH'] * rdf['Pb%']).sum() / p_tot
            
            tms = p_tot * (1 - h_perc)
            w_zn = (tms * (zn_p/100) * rec_zn) / (ley_conc_zn/100)
            w_pb = (tms * (pb_p/100) * rec_pb) / (ley_conc_pb/100)

            st.subheader("📊 Balance Metalúrgico")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total TMH", f"{p_tot:.2f}")
            c2.metric("Conc. Zn (TMS)", f"{w_zn:.2f}")
            c3.metric("Conc. Pb (TMS)", f"{w_pb:.2f}")

            # 6. Enviar Correo
            asunto_mail = "Reporte de Mezcla Generado"
            cuerpo_mail = f"Total Blend: {p_tot:.2f} TMH\nZn promedio: {zn_p:.2f}%\nPb promedio: {pb_p:.2f}%"
            enviar_correo(asunto_mail, cuerpo_mail, "diego.bonilla@parkano.com.bo")
            st.success("✅ Blend generado y enviado por correo.")

        else:
            st.error("No se encontró una solución válida.")

    except Exception as e:
        st.error(f"Error al procesar: {e}")
