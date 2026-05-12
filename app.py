import streamlit as st
import pandas as pd
import pulp
import matplotlib.pyplot as plt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import io
import re

# Configuración de la página
st.set_page_config(page_title="Optimizador Parkano", page_icon="🏭")

st.title("🏭 Generador de Blend - Parkano")
st.markdown("Herramienta de optimización para el armado de mezclas de mineral.")

# --- PARÁMETROS METALÚRGICOS (En la barra lateral) ---
st.sidebar.header("⚙️ Parámetros Planta")
h_perc = st.sidebar.slider("Humedad (%)", 0.0, 10.0, 5.0) / 100
rec_zn = st.sidebar.number_input("Recup. ZN (%)", value=95.0) / 100
rec_pb = st.sidebar.number_input("Recup. PB (%)", value=85.0) / 100
rec_ag = st.sidebar.number_input("Recup. AG (%)", value=90.0) / 100

ley_conc_zn = 50.0  # Ley fija según pedido
ley_conc_pb = 60.0  # Ley fija según pedido
ag_min_zn = 2.5     # Onzas fijas en Conc Zn


# Entradas del usuario
url_sheet = st.text_input("🔗 Link de Google Sheets (Asegúrate que esté como 'Anyone with the link')")
enviar_correo = st.checkbox("📧 Enviar reporte a Diego.bonilla@parkano.com.bo", value=True)

if st.button("🚀 GENERAR BLEND"):
    if not url_sheet:
        st.error("Por favor, ingresa un link de Google Sheets.")
    else:
        try:
            # 1. Lectura de datos desde Google Sheets
            match = re.search(r'/d/([a-zA-Z0-9-_]+)', url_sheet)
            if not match:
                st.error("URL de Google Sheets no válida.")
                st.stop()
            
            sheet_id = match.group(1)
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            df = pd.read_csv(csv_url)
            
            # Limpiar nombres de columnas (quitar espacios y poner en mayúsculas)
            df.columns = df.columns.str.strip().str.upper()

            # 2. Configuración de la Optimización Matemática
            prob = pulp.LpProblem("Mejor_Blend", pulp.LpMinimize)
            idx = df.index.tolist()
            # Variable binaria: 1 si se elige el lote, 0 si no.
            v = pulp.LpVariable.dicts("lote", idx, cat='Binary')

            # Definición de fórmulas
            peso_total = pulp.lpSum([v[i] * df.loc[i, 'PESO'] for i in idx])
            zn_total = pulp.lpSum([v[i] * df.loc[i, 'PESO'] * df.loc[i, 'LEY ZN'] for i in idx])
            pb_total = pulp.lpSum([v[i] * df.loc[i, 'PESO'] * df.loc[i, 'LEY PB'] for i in idx])

            # --- REGLAS Y PARÁMETROS DEL BLEND ---
            # Peso: +/- 1000 TM
            prob += peso_total >= 980
            prob += peso_total <= 1030
            # Zinc: entre 11.60 y 12.00
            prob += zn_total >= 11.60 * peso_total
            prob += zn_total <= 12.00 * peso_total
            # Plomo: entre 0.90 y 1.00
            prob += pb_total >= 0.90 * peso_total
            prob += pb_total <= 1.00 * peso_total
            # Plata: entre 1.00 y 1.50 DM
            ag_total = pulp.lpSum([v[i] * df.loc[i, 'PESO'] * df.loc[i, 'LEY AG'] for i in idx])
            prob += ag_total >= 1.1 * peso_total
            prob += ag_total <= 1.50 * peso_total
            
            # Resolver el problema
            prob.solve(pulp.PULP_CBC_CMD(msg=0))

            # 3. Mostrar Resultados
            if pulp.LpStatus[prob.status] == 'Optimal':
                final_idx = [i for i in idx if v[i].varValue == 1]
                res_df = df.loc[final_idx, ['ID LOTE', 'PESO', 'LEY ZN', 'LEY PB', 'LEY AG']].copy()
                
                # Calcular promedios finales
                p_final = res_df['PESO'].sum()
                zn_final = (res_df['PESO'] * res_df['LEY ZN']).sum() / p_final
                pb_final = (res_df['PESO'] * res_df['LEY PB']).sum() / p_final
                ag_final = (res_df['PESO'] * res_df['LEY AG']).sum() / p_final
                
                # Añadir fila de totales al final de la tabla
                res_df.loc['TOTAL'] = ['TOTAL / PROM', round(p_final, 2), round(zn_final, 2), round(pb_final, 2), round(ag_final, 2)]

                st.success("✅ ¡Se encontró el blend perfecto!")
                st.write(f"**Tonelaje:** {p_final:.2f} TM | **Zn:** {zn_final:.2f}% | **Pb:** {pb_final:.2f}% | **Ag:** {ag_final:.2f} DM")
                st.dataframe(res_df)
                # --- MATEMÁTICA DEL BALANCE ---
                tms = p_final * (1 - h_perc)  # Toneladas Secas
            
               # Contenidos finos recuperados
               fino_zn_rec = tms * (zn_final / 100) * rec_zn
               fino_pb_rec = tms * (pb_final / 100) * rec_pb
               fino_ag_rec = (tms * ag_final) * rec_ag
            
               # Pesos de los concentrados (TMS)
               w_conc_zn = fino_zn_rec / (ley_conc_zn / 100)
               w_conc_pb = fino_pb_rec / (ley_conc_pb / 100)
            
               # Reparto de Plata (Ag)
               ag_total_en_zn = w_conc_zn * ag_min_zn # 2.5 DM fijos
               ag_total_en_pb = max(0, fino_ag_rec - ag_total_en_zn) # El resto al Pb
               ley_ag_en_pb = ag_total_en_pb / w_conc_pb if w_conc_pb > 0 else 0

               # Crear Tabla de Balance para mostrar en pantalla
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

                # 4. Generar la imagen para que puedan copiar y pegar
                fig, ax = plt.subplots(figsize=(10, len(res_df)*0.4 + 1))
                ax.axis('off')
                ax.table(cellText=res_df.values, colLabels=res_df.columns, loc='center', cellLoc='center')
                plt.title(f"Reporte de Blend: {p_final:.1f} TM | Zn {zn_final:.2f}% | Pb {pb_final:.2f}%", pad=20)
                
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
                img_bytes = buf.getvalue()
                st.image(img_bytes, caption="Imagen del reporte (puedes guardarla o copiarla)")

                # 5. Envío de Correo Electrónico
                if enviar_correo:
                    try:
                        email_user = st.secrets["EMAIL_USER"]
                        email_pass = st.secrets["EMAIL_PASS"]
                        
                        msg = MIMEMultipart()
                        msg['From'] = email_user
                        msg['To'] = "Diego.bonilla@parkano.com.bo"
                        msg['Subject'] = f"REPORTE BLEND: {p_final:.1f} TM - Zn {zn_final:.2f}%"
                        
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
                        msg.attach(MIMEText(cuerpo, 'plain'))
                        
                        adjunto = MIMEImage(img_bytes)
                        adjunto.add_header('Content-Disposition', 'attachment', filename="reporte_blend.png")
                        msg.attach(adjunto)

                        with smtplib.SMTP('smtp.gmail.com', 587) as server:
                            server.starttls()
                            server.login(email_user, email_pass)
                            server.send_message(msg)
                        
                        st.info("📧 Correo enviado a Diego.bonilla@parkano.com.bo")
                    except Exception as e:
                        st.warning(f"El blend se creó pero el correo no salió. Revisa los Secrets. Error: {e}")
            else:
                st.error("🚨 NO SE PUEDE ARMAR EL BLEND con los lotes y parámetros actuales.")
                
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
