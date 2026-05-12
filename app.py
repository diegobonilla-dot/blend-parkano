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

sheet_url = st.text_input("Link de Google Sheets:", "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0")

if st.button("🚀 GENERAR BLEND"):
    try:
        # 1. Carga de datos
        csv_url = sheet_url.split('/edit')[0] + '/export?format=csv'
        df = pd.read_csv(csv_url)
        
        # Limpieza inicial: pasar todo a mayúsculas y quitar espacios locos
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # --- BUSCADOR INTELIGENTE DE COLUMNAS ---
        # Buscamos la columna que CONTENGA la palabra clave
        def buscar_columna(lista_nombres, palabra_clave):
            for col in lista_nombres:
                if palabra_clave in col:
                    return col
            return None

        c_lote = buscar_columna(df.columns, "LOTE")
        c_peso = buscar_columna(df.columns, "PESO")
        c_zn = buscar_columna(df.columns, "ZN")
        c_pb = buscar_columna(df.columns, "PB")
        c_ag = buscar_columna(df.columns, "AG")

        # Validación
        if not c_peso or not c_zn:
            st.error(f"No pude identificar las columnas. Detecté: {list(df.columns)}")
            st.stop()

        # 2. Limpieza de datos (Convertir a números)
        for col in [c_peso, c_zn, c_pb, c_ag]:
            if col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Filtramos filas que no sean lotes (como los totales)
        df = df[df[c_peso] > 0].copy()

        # 3. Optimización
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
                        "Ley PB": df.loc[i, c_pb]
                    })
            
            rdf = pd.DataFrame(res)
            st.subheader("📋 Resultados del Blend")
            st.dataframe(rdf)
            
            # 4. Cálculos de Balance
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
            
            # 5. Envío de Correo
            msg = f"Reporte Parkano:\nTotal: {p_tot:.2f} TMH\nZn: {zn_prom:.2f}%\nPb: {pb_prom:.2f}%"
            enviar_correo("Reporte Blend", msg, "diego.bonilla@parkano.com.bo")
            st.success("✅ ¡Proceso completo! Correo enviado.")

        else:
            st.error("No se pudo calcular una mezcla.")

    except Exception as e:
        st.error(f"Error detectado: {e}")
