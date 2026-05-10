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
            # Zinc: entre 11.60 y 11.80
            prob += zn_total >= 11.60 * peso_total
            prob += zn_total <= 12.00 * peso_total
            # Plomo: entre 0.90 y 1.05
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
                        
                        cuerpo = f"Hola Diego,\n\nSe adjunta el reporte del blend generado automáticamente.\n\nPeso: {p_final:.2f} TM\nZn: {zn_final:.2f}%\nPb: {pb_final:.2f}%"
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
