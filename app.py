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

# --- BARRA LATERAL ---
st.sidebar.header("⚙️ Parámetros de Planta")
h_perc = st.sidebar.slider("Humedad (%)", 0.0, 15.0, 10.0) / 100
rec_zn = st.sidebar.number_input("Rec. Zinc (%)", 0.0, 100.0, 85.0) / 100
rec_pb = st.sidebar.number_input("Rec. Plomo (%)", 0.0, 100.0, 80.0) / 100
rec_ag = st.sidebar.number_input("Rec. Plata (%)", 0.0, 100.0, 75.0) / 100
ley_conc_zn = st.sidebar.number_input("Ley Zn en Conc. (%)", 0.0, 100.0, 50.0)
ley_conc_pb = st.sidebar.number_input("Ley Pb en Conc. (%)", 0.0, 100.0, 60.0)
ag_min_zn = st.sidebar.number_input("Ag en Conc. Zn (DM)", 0.0, 100.0, 2.5)

st.title("⚒️ Sistema de Optimización de Mezclas - Parkano")
sheet_url = st.text_input("Pega el link de Google Sheets:")

if st.button("🚀 GENERAR BLEND"):
    if not sheet_url:
        st.warning("Pega el link primero.")
    else:
        try:
            # Convertir link a CSV correctamente
            base_url = sheet_url.split('/edit')[0]
            url = f"{base_url}/export?format=csv"
            df = pd.read_csv(url)
            
            # Limpiar nombres de columnas (quitar espacios y poner en mayúsculas)
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            # Buscador ultra-flexible de columnas
            def encontrar(lista_keywords):
                for key in lista_keywords:
                    for col in df.columns:
                        if key in col:
                            return col
                return None

            c_lote = encontrar(['LOTE', 'ID', 'NOMBRE'])
            c_peso = encontrar(['PESO', 'TMH', 'TON', 'MASA'])
            c_zn = encontrar(['ZN', 'ZINC'])
            c_pb = encontrar(['PB', 'PLOMO', 'LEAD'])
            c_ag = encontrar(['AG', 'PLATA', 'SILVER'])

            if not all([c_lote, c_peso, c_zn, c_pb, c_ag]):
                st.error(f"⚠️ Error de lectura. Columnas detectadas: {list(df.columns)}")
                st.info("Asegúrate de que tu Excel tenga encabezados como: Lote, Peso, Zn, Pb, Ag.")
                st.stop()

            # Optimización simple
            prob = LpProblem("Mezcla", LpMinimize)
            choices = LpVariable.dicts("L", df.index, lowBound=0)
            prob += lpSum([choices[i] for i in df.index])
            for i in df.index:
                prob += choices[i] <= df.loc[i, c_peso]
            
            prob.solve()
            
            if value(prob.status) == 1:
                res = []
                for i in df.index:
                    if value(choices[i]) > 0:
                        res.append({
                            "Lote": df.loc[i, c_lote],
                            "Peso_TMH": value(choices[i]),
                            "Zn%": df.loc[i, c_zn],
                            "Pb%": df.loc[i, c_pb],
                            "Ag_DM": df.loc[i, c_ag]
                        })
                
                rdf = pd.DataFrame(res)
                st.subheader("📋 Resultados del Blend")
                st.dataframe(rdf)
                
                # Balance
                p_tot = rdf['Peso_TMH'].sum()
                zn_p = (rdf['Peso_TMH'] * rdf['Zn%']).sum() / p_tot
                pb_p = (rdf['Peso_TMH'] * rdf['Pb%']).sum() / p_tot
                ag_p = (rdf['Peso_TMH'] * rdf['Ag_DM']).sum() / p_tot
                
                tms = p_tot * (1 - h_perc)
                w_zn = (tms * (zn_p/100) * rec_zn) / (ley_conc_zn/100)
                w_pb = (tms * (pb_p/100) * rec_pb) / (ley_conc_pb/100)

                st.subheader("📊 Balance Metalúrgico Proyectado")
                st.write(f"**Total Blend:** {p_tot:.2f} TMH | **Seco:** {tms:.2f} TMS")
                
                c1, c2 = st.columns(2)
                c1.metric("Conc. Zinc (TMS)", f"{w_zn:.2f}")
                c2.metric("Conc. Plomo (TMS)", f"{w_pb:.2f}")

                # Correo simplificado para evitar errores de envío
                msg = f"Blend Parkano:\nTotal: {p_tot:.2f} TMH\nZn: {zn_p:.2f}%\nPb: {pb_p:.2f}%"
                enviar_correo("Nuevo Blend Generado", msg, "diego.bonilla@parkano.com.bo")
                st.success("✅ ¡Mezcla procesada y correo enviado!")
            else:
                st.error("No se pudo optimizar con los datos actuales.")

        except Exception as e:
            st.error(f"Error inesperado: {e}")
