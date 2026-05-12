import streamlit as st
import pandas as pd
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, value, LpStatus
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Sistema Parkano V4 - Balance Real", layout="wide")

def enviar_correo(asunto, cuerpo, destinatario):
    remitente = "mezclasparkano@gmail.com"
    password = "shre kfdy flin hscs" 
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo, 'html')) # Enviamos como HTML para mejor formato
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
    except Exception as e:
        st.error(f"Error correo: {e}")

st.title("⚒️ Sistema de Optimización: Blend & Balance Metalúrgico Proyectado")

# --- 🎯 PARÁMETROS EDITABLES (REQUERIMIENTOS JEFE) ---
st.sidebar.header("🎯 Parámetros del Blend")
t_min = st.sidebar.number_input("Tonelaje Mínimo (TMH)", value=980.0)
t_max = st.sidebar.number_input("Tonelaje Máximo (TMH)", value=1100.0)

st.sidebar.subheader("Leyes de Cabeza Objetivos")
zn_obj = st.sidebar.slider("Rango Zn %", 0.0, 20.0, (11.0, 12.0))
pb_obj = st.sidebar.slider("Rango Pb %", 0.0, 5.0, (0.8, 1.0))
ag_obj = st.sidebar.slider("Rango Ag DM", 0.0, 5.0, (1.1, 1.5))

st.sidebar.header("⚙️ Parámetros Metalúrgicos")
h_perc = st.sidebar.number_input("Humedad (%)", value=5.0) / 100
rec_zn = st.sidebar.number_input("Recuperación Zn (%)", value=95.0) / 100
rec_pb = st.sidebar.number_input("Recuperación Pb (%)", value=85.0) / 100
rec_ag = st.sidebar.number_input("Recuperación Ag (%)", value=90.0) / 100

st.sidebar.subheader("Calidad de Concentrados")
ley_c_zn = st.sidebar.number_input("Ley Zn en Conc. Zn (%)", value=50.0)
ag_en_zn = st.sidebar.number_input("Ag Mínima en Conc. Zn (DM)", value=2.5)
ley_c_pb = st.sidebar.number_input("Ley Pb en Conc. Pb (%)", value=60.0)

sheet_url = st.text_input("Link de Google Sheets:", "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0")

if st.button("🚀 GENERAR BLEND Y BALANCE PROYECTADO"):
    try:
        # 1. CARGA DE DATOS
        base_url = sheet_url.split('/edit')[0]
        gid = sheet_url.split('gid=')[1] if 'gid=' in sheet_url else '0'
        csv_url = f"{base_url}/export?format=csv&gid={gid}"
        df = pd.read_csv(csv_url)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        c_lote = next((c for c in df.columns if "LOTE" in c), None)
        c_peso = next((c for c in df.columns if "PESO" in c), None)
        c_zn = next((c for c in df.columns if "ZN" in c), None)
        c_pb = next((c for c in df.columns if "PB" in c), None)
        c_ag = next((c for c in df.columns if "AG" in c), None)

        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df = df[df[c_peso] > 0.1].copy()

        # 2. GENERADOR DE BLEND
        prob = LpProblem("Blend_Parkano", LpMinimize)
        choices = LpVariable.dicts("L", df.index, lowBound=0)
        tw = lpSum([choices[i] for i in df.index])
        
        prob += tw
        prob += tw >= t_min
        prob += tw <= t_max
        for i in df.index:
            prob += choices[i] <= df.loc[i, c_peso]
        
        # Restricciones de Ley de Cabeza
        prob += lpSum([choices[i] * df.loc[i, c_zn] for i in df.index]) >= zn_obj[0] * tw
        prob += lpSum([choices[i] * df.loc[i, c_zn] for i in df.index]) <= zn_obj[1] * tw
        prob += lpSum([choices[i] * df.loc[i, c_pb] for i in df.index]) >= pb_obj[0] * tw
        prob += lpSum([choices[i] * df.loc[i, c_pb] for i in df.index]) <= pb_obj[1] * tw
        prob += lpSum([choices[i] * df.loc[i, c_ag] for i in df.index]) >= ag_obj[0] * tw
        prob += lpSum([choices[i] * df.loc[i, c_ag] for i in df.index]) <= ag_obj[1] * tw
        
        prob.solve()

        if LpStatus[prob.status] == 'Optimal':
            # --- DATOS DEL BLEND ---
            res = []
            for i in df.index:
                v = value(choices[i])
                if v and v > 0.1:
                    res.append({"Lote": df.loc[i, c_lote], "TMH": v, "Zn%": df.loc[i, c_zn], "Pb%": df.loc[i, c_pb], "Ag DM": df.loc[i, c_ag]})
            rdf = pd.DataFrame(res)
            
            st.subheader("📋 1. Reporte de Mezcla (Blend Seleccionado)")
            st.table(rdf.style.format("{:.2f}", subset=["TMH", "Zn%", "Pb%", "Ag DM"]))

            # --- CALCULOS DE BALANCE METALÚRGICO ---
            tmh_total = rdf['TMH'].sum()
            zn_cab = (rdf['TMH'] * rdf['Zn%']).sum() / tmh_total
            pb_cab = (rdf['TMH'] * rdf['Pb%']).sum() / tmh_total
            ag_cab = (rdf['TMH'] * rdf['Ag DM']).sum() / tmh_total
            
            tms_total = tmh_total * (1 - h_perc) # DESCUENTO DE HUMEDAD
            
            # Recuperación de Finos
            fino_zn = tms_total * (zn_cab/100) * rec_zn
            fino_pb = tms_total * (pb_cab/100) * rec_pb
            fino_ag_total = tms_total * ag_cab * rec_ag # Finos de Plata en DM totales
            
            # Pesos de Concentrados
            tms_conc_zn = fino_zn / (ley_c_zn/100)
            tms_conc_pb = fino_pb / (ley_c_pb/100)
            
            # DISTRIBUCIÓN DE PLATA (REQUERIMIENTO ESPECIAL)
            # 1. Asegurar 2.5 DM en el conc de Zn
            ag_fino_en_zn = tms_conc_zn * ag_en_zn
            # 2. El resto va al conc de Pb
            ag_fino_en_pb = fino_ag_total - ag_fino_en_zn
            ley_ag_en_pb = ag_fino_en_pb / tms_conc_pb

            # --- VISUALIZACIÓN ---
            st.subheader("📊 2. Balance Metalúrgico Proyectado")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.info("**ALIMENTACIÓN (CABEZA)**")
                st.write(f"TMH: {tmh_total:.2f}")
                st.write(f"TMS (Humedad {h_perc*100}%): {tms_total:.2f}")
                st.write(f"Leyes: Zn {zn_cab:.2f}% | Pb {pb_cab:.2f}% | Ag {ag_cab:.2f} DM")
            with c2:
                st.success("**CONCENTRADO ZINC**")
                st.write(f"Peso: {tms_conc_zn:.2f} TMS")
                st.write(f"Ley Zn: {ley_c_zn}%")
                st.write(f"Ley Ag (Asegurada): {ag_en_zn} DM")
            with c3:
                st.warning("**CONCENTRADO PLOMO**")
                st.write(f"Peso: {tms_conc_pb:.2f} TMS")
                st.write(f"Ley Pb: {ley_c_pb}%")
                st.write(f"Ley Ag (Remanente): {ley_ag_en_pb:.2f} DM")

            # --- ENVÍO DE CORREO HTML ---
            html_msg = f"""
            <h3>Reporte Operativo Parkano</h3>
            <p><b>Blend:</b> {tmh_total:.2f} TMH ({tms_total:.2f} TMS)</p>
            <p><b>Cabeza:</b> Zn {zn_cab:.2f}%, Pb {pb_cab:.2f}%, Ag {ag_cab:.2f} DM</p>
            <hr>
            <h4>Producción Proyectada:</h4>
            <ul>
                <li><b>Conc. Zn:</b> {tms_conc_zn:.2f} TMS @ {ley_c_zn}% Zn y {ag_en_zn} DM Ag</li>
                <li><b>Conc. Pb:</b> {tms_conc_pb:.2f} TMS @ {ley_c_pb}% Pb y {ley_ag_en_pb:.2f} DM Ag</li>
            </ul>
            """
            enviar_correo("Balance Proyectado Parkano", html_msg, "diego.bonilla@parkano.com.bo")
            st.success("✅ Balance enviado a correo.")
        else:
            st.error("❌ Los parámetros actuales son imposibles con el stock disponible.")
    except Exception as e:
        st.error(f"Error: {e}")
