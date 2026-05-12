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
ley_conc_zn = st.sidebar.number_input("Ley Zn en Conc. (%)", 0.0, 100.0, 50.0)
ley_conc_pb = st.sidebar.number_input("Ley Pb en Conc. (%)", 0.0, 100.0, 60.0)

sheet_url = st.text_input("Pega el link de Google Sheets:", "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0")

if st.button("🚀 GENERAR BLEND"):
    try:
        # 1. Carga de datos
        csv_url = sheet_url.split('/edit')[0] + '/export?format=csv'
        df = pd.read_csv(csv_url)
        
        # Limpieza de nombres de columnas (Quitar espacios extra)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapeo EXACTO según tu imagen de Google Sheets
        c_lote = "ID LOTE"
        c_peso = "Peso"
        c_zn = "Ley ZN"
        c_pb = "Ley PB"
        c_ag = "Ley AG"

        # 2. Validación de columnas
        if c_peso not in df.columns:
            st.error(f"Error: No se encontró la columna '{c_peso}'. Columnas detectadas: {list(df.columns)}")
            st.stop()

        # 3. Limpieza de datos (Convertir a números y quitar filas vacías)
        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df = df[df[c_peso] > 0].copy()

        # 4. Optimización (Mínimo peso para usar lo disponible)
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
                        "Peso": val,
                        "Ley ZN": df.loc[i, c_zn],
                        "Ley PB": df.loc[i, c_pb],
                        "Ley AG": df.loc[i, c_ag]
                    })
            
            rdf = pd.DataFrame(res)
            st.subheader("📋 Resultados del Blend")
            st.dataframe(rdf)
            
            # 5. Cálculos de Balance Final
            p_tot = rdf['Peso'].sum()
            zn_prom = (rdf['Peso'] * rdf['Ley ZN']).sum() / p_tot
            pb_prom = (rdf['Peso'] * rdf['Ley PB']).sum() / p_tot
            
            tms = p_tot * (1 - h_perc)
            conc_zn = (tms * (zn_prom/100) * rec_zn) / (ley_conc_zn/100)
            conc_pb = (tms * (pb_prom/100) * rec_pb) / (ley_conc_pb/100)

            st.subheader("📊 Balance Proyectado")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total TMH", f"{p_tot:.2f}")
            col2.metric("Conc. Zn (TMS)", f"{conc_zn:.2f}")
            col3.metric("Conc. Pb (TMS)", f"{conc_pb:.2f}")
            
            st.info(f"Leyes Promedio Mezcla: Zn {zn_prom:.2f}% | Pb {pb_prom:.2f}%")

            # 6. Envío de Correo (Simplificado para evitar IndentationError)
            mensaje = f"Reporte Mezcla Parkano:\n\nTotal: {p_tot:.2f} TMH\nLeyes: Zn {zn_prom:.2f}%, Pb {pb_prom:.2f}%\nConc. Zn: {conc_zn:.2f} TMS\nConc. Pb: {conc_pb:.2f} TMS"
            enviar_correo("Nuevo Reporte Generado", mensaje, "diego.bonilla@parkano.com.bo")
            st.success("✅ Reporte enviado correctamente.")

        else:
            st.error("No se pudo calcular una mezcla óptima.")

    except Exception as e:
        st.error(f"Error crítico: {e}")
