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
            url = sheet_url.replace('/edit?usp=sharing', '/export?format=csv').split('/edit')[0] + '/export?format=csv'
            df = pd.read_csv(url)
            
            # --- LIMPIEZA AUTOMÁTICA DE COLUMNAS ---
            # Esto quita espacios y pone todo en mayúsculas para no fallar
            df.columns = df.columns.str.strip().str.upper()
            
            # Buscamos las columnas por sus nombres en tu imagen
            col_lote = "ID LOTE"
            col_peso = "PESO"
            col_zn = "LEY ZN"
            col_pb = "LEY PB"
            col_ag = "LEY AG"

            # 2. Definir Optimización
            prob = LpProblem("Optimizar_Mezcla", LpMinimize)
            choices = LpVariable.dicts("Lote", df.index, lowBound=0, cat='Continuous')
            prob += lpSum([choices[i] for i in df.index])
            
            for i in df.index:
                prob += choices[i] <= df.loc[i, col_peso]
                
            prob.solve()
            
            if value(prob.status) == 1:
                res_list = []
                for i in df.index:
                    if value(choices[i]) > 0:
                        res_list.append({
                            "Lote": df.loc[i, col_lote],
                            "Peso_TMH": value(choices[i]),
                            "Zn%": df.loc[i, col_zn],
                            "Pb%": df.loc[i, col_pb],
                            "Ag_DM": df.loc[i, col_ag]
                        })
                
                res_df = pd.DataFrame(res_list)
                st.subheader("📋 Resumen del Blend")
                st.dataframe(res_df)
                
                # Balance proyectado
                p_final = res_df['Peso_TMH'].sum()
                zn_final = (res_df['Peso_TMH'] * res_df['Zn%']).sum() / p_final
                pb_final = (res_df['Peso_TMH'] * res_df['Pb%']).sum() / p_final
                ag_final = (res_df['Peso_TMH'] * res_df['Ag_DM']).sum() / p_final
                
                tms = p_final * (1 - h_perc)
                w_conc_zn = (tms * (zn_final/100) * rec_zn) / (ley_conc_zn/100)
                w_conc_pb = (tms * (pb_final/100) * rec_pb) / (ley_conc_pb/100)

                st.subheader("📊 Balance Proyectado")
                st.write(f"**Total Blend:** {p_final:.2f} TMH | **Zn:** {zn_final:.2f}% | **Pb:** {pb_final:.2f}%")
                
                st.success("✅ ¡Mezcla procesada con éxito!")
            else:
                st.error("No se encontró solución.")

        except Exception as e:
            st.error(f"Error: {e}. Verifica que el link sea público (Cualquiera con el enlace puede leer).")
