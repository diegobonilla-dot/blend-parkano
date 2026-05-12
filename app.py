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
    password = "shre kfdy flin hscs"  # Contraseña de aplicación
    
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

# --- BARRA LATERAL (PARÁMETROS) ---
st.sidebar.header("⚙️ Parámetros de Planta")
h_perc = st.sidebar.slider("Humedad (%)", 0.0, 15.0, 10.0) / 100

st.sidebar.subheader("Recuperaciones (%)")
rec_zn = st.sidebar.number_input("Rec. Zinc", 0.0, 100.0, 85.0) / 100
rec_pb = st.sidebar.number_input("Rec. Plomo", 0.0, 100.0, 80.0) / 100
rec_ag = st.sidebar.number_input("Rec. Plata", 0.0, 100.0, 75.0) / 100

st.sidebar.subheader("Leyes de Concentrado")
ley_conc_zn = st.sidebar.number_input("Ley Zn en Conc. Zn (%)", 0.0, 100.0, 50.0)
ley_conc_pb = st.sidebar.number_input("Ley Pb en Conc. Pb (%)", 0.0, 100.0, 60.0)
ag_min_zn = st.sidebar.number_input("Plata en Conc. Zn (DM)", 0.0, 100.0, 2.5)

# --- ENTRADA DE DATOS ---
st.title("⚒️ Sistema de Optimización de Mezclas - Parkano")
sheet_url = st.text_input("Pega el link de Google Sheets (Lotes):")

if st.button("🚀 GENERAR BLEND"):
    try:
        # 1. Leer Datos
        url = sheet_url.replace('/edit?usp=sharing', '/export?format=csv')
        df = pd.read_csv(url)
        
        # 2. Definir Problema
        prob = LpProblem("Optimizar_Mezcla", LpMinimize)
        choices = LpVariable.dicts("Lote", df.index, lowBound=0, cat='Continuous')
        
        # Objetivo: Minimizar peso (o ajustar según necesidad)
        prob += lpSum([choices[i] for i in df.index])
        
        # Restricciones de Ejemplo (Ajustar según necesidad de Mario)
        for i in df.index:
            prob += choices[i] <= df.loc[i, 'Peso']
            
        prob.solve()
        
        if value(prob.status) == 1:
            # 3. Resultados del Blend
            res_list = []
            for i in df.index:
                if value(choices[i]) > 0:
                    res_list.append({
                        "Lote": df.loc[i, 'Lote'],
                        "Peso_TMH": value(choices[i]),
                        "Zn%": df.loc[i, 'Zn%'],
                        "Pb%": df.loc[i, 'Pb%'],
                        "Ag_DM": df.loc[i, 'Ag_DM']
                    })
            
            res_df = pd.DataFrame(res_list)
            st.subheader("📋 Resumen del Blend Generado")
            st.dataframe(res_df)
            
            # 4. MATEMÁTICA DEL BALANCE
            p_final = res_df['Peso_TMH'].sum()
            zn_final = (res_df['Peso_TMH'] * res_df['Zn%']).sum() / p_final
            pb_final = (res_df['Peso_TMH'] * res_df['Pb%']).sum() / p_final
            ag_final = (res_df['Peso_TMH'] * res_df['Ag_DM']).sum() / p_final
            
            tms = p_final * (1 - h_perc)
            fino_zn_rec = tms * (zn_final / 100) * rec_zn
            fino_pb_rec = tms * (pb_final / 100) * rec_pb
            fino_ag_rec = (tms * ag_final) * rec_ag
            
            w_conc_zn = fino_zn_rec / (ley_conc_zn / 100)
            w_conc_pb = fino_pb_rec / (ley_conc_pb / 100)
            
            ag_total_en_zn = w_conc_zn * ag_min_zn
            ag_total_en_pb = max(0, fino_ag_rec - ag_total_en_zn)
            ley_ag_en_pb = ag_total_en_pb / w_conc_pb if w_conc_pb > 0 else 0

            balance_dict = {
                "Producto": ["Cabeza (Seca)", "Conc. Zinc", "Conc. Plomo"],
                "TMS": [tms, w_conc_zn, w_conc_pb],
                "Ley Zn %": [zn_final, ley_conc_zn, 0.0],
                "Ley Pb %": [pb_final, 0.0, ley_conc_pb],
                "Ley Ag DM": [ag_final, ag_min_zn, ley_ag_en_pb]
            }
            df_balance = pd.DataFrame(balance_dict)
            
            st.subheader("📊 Balance Metalúrgico Proyectado")
            st.table(df_balance.style.format("{:.2f}"))

            # 5. ENVÍO DE CORREO
            cuerpo = f"""
            Hola Diego,
            
            Se adjunta el reporte del blend generado y el balance proyectado de planta:
            
            1. RESUMEN DEL BLEND (Húmedo):
            - Peso Total: {p_final:.2f} TMH
            - Leyes: Zn {zn_final:.2f}% | Pb {pb_final:.2f}% | Ag {ag_final:.2f} DM
            
            2. BALANCE PROYECTADO (Seco):
            - Humedad aplicada: {h_perc*100}%
            - Conc. Zinc: {w_conc_zn:.2f} TMS @ {ley_conc_zn}% Zn | {ag_min_zn} DM Ag
            - Conc. Plomo: {w_conc_pb:.2f} TMS @ {ley_conc_pb}% Pb | {ley_ag_en_pb:.2f} DM Ag
            
            Saludos,
            Sistema de Mezclas Parkano.
            """
            
            enviar_correo("Reporte de Blend y Balance", cuerpo, "diego.bonilla@parkano.com.bo")
            st.success("✅ ¡Balance generado y correo enviado con éxito!")

        else:
            st.error("No se pudo encontrar una solución óptima.")

    except Exception as e:
        st.error(f"Error al procesar el archivo: {e}")
