# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import io
import json
import base64
import fitz  
import re
from openai import OpenAI

# Configuración de interfaz
st.set_page_config(page_title="Auditoría de Ferralla", layout="wide", page_icon="🏗️")
st.title("🏗️ Validador de Planillas de Ferralla vs Contrato")
st.subheader("Extracción 100% Automatizada por IA mediante Visión de Croquis")

# Tabla de pesos contractuales pactados
PESOS_CONTRATO = {
    8: 0.40, 10: 0.62, 12: 0.89, 16: 1.58, 20: 2.47, 25: 3.85, 32: 6.31
}

with st.sidebar:
    st.header("📋 Parámetros de Control")
    st.dataframe(pd.DataFrame(list(PESOS_CONTRATO.items()), columns=["Diámetro (Ø)", "Kg/ml"]), use_container_width=True, hide_index=True)
    st.markdown("---")
    st.subheader("🔑 Credenciales del Extractor")
    api_key = st.text_input("Introduce tu Clave de GitHub (ghp_...)", type="password")

archivo_planilla = st.file_uploader("Subir PDF de la Planilla de Ferralla original", type=["pdf"])
umbral = st.slider("Tolerancia de desvíos (± Kg)", 0.0, 5.0, 0.5, 0.1)

if archivo_planilla is not None:
    st.success(f"Archivo recibido para lectura automática: {archivo_planilla.name}")
    
    if not api_key:
        st.warning("⚠️ Introduce tu clave ghp_ en la barra lateral para activar el motor de visión artificial de GPT-4o.")
    else:
        with st.spinner("🔄 El motor está transformando el PDF y extrayendo los croquis visuales línea por línea..."):
            try:
                # 1. Conversión nativa de PDF a imagen
                pdf_bytes = archivo_planilla.read()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                pagina = doc.load_page(0)  
                pix = pagina.get_pixmap(dpi=150) 
                img_data = pix.tobytes("jpeg")
                img_base64 = base64.b64encode(img_data).decode("utf-8")
                
                # 2. Conectar al modelo GPT-4o usando la pasarela de GitHub Models
                client = OpenAI(
                    base_url="https://azure.com",
                    api_key=api_key
                )
                
                instrucciones_prompt = """
                Analiza esta planilla de ferralla. Recorre cada fila e identifica:
                - bloque: La zona o sección (ej: REF.INF.X (A14-PNT.1)).
                - barra: El código o despiece (ej: 2016 20).
                - diam: El diámetro numérico en mm (ej: 16).
                - cant: La cantidad de barras (ej: 2).
                - seg_cm: Lista con los números en centímetros leídos exclusivamente del dibujo/croquis visual de la izquierda (ej: [20, 760]).
                - tall_kg: Kilos totales impresos que el taller le asigna a este bloque (ej: 242.82).

                Genera tu respuesta estrictamente como una lista en formato JSON directa dentro de corchetes, utilizando exclusivamente comillas dobles. No añadas la palabra 'json' ni bloques markdown.
                """
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "user", "content": [
                            {"type": "text", "text": instrucciones_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                        ]}
                    ]
                )
                
                if hasattr(response, 'choices') and response.choices:
                    resultado_texto = response.choices.message.content.strip()
                elif hasattr(response, 'content'):
                    resultado_texto = response.content.strip()
                else:
                    resultado_texto = str(response).strip()
                
                # Reparador de formato y limpieza por expresiones regulares
                resultado_texto = resultado_texto.replace("\n", " ").replace("\r", " ")
                resultado_texto = re.sub(r"```json\s*", "", resultado_texto)
                resultado_texto = re.sub(r"```\s*", "", resultado_texto)
                resultado_texto = resultado_texto.replace("'", '"')
                
                match = re.search(r"\[\s*\{.*\}\s*\]", resultado_texto)
                if not match:
                    st.error("La IA ha devuelto una respuesta con formato inválido. Por favor, vuelve a pulsar Intro en el cajetín de la clave para reintentar la lectura.")
                    st.stop()
                    
                datos_extraidos = json.loads(match.group(0))
                
                # 3. Procesamiento matemático automatizado
                filas_auditoria = []
                for item in datos_extraidos:
                    segmentos = item.get("seg_cm", [])
                    segmentos_limpios = [float(x) for x in segmentos if str(x).replace('.','',1).isdigit() or isinstance(x, (int, float))]
                    
                    desarrollo_ml = sum(segmentos_limpios) / 100.0
                    total_ml = desarrollo_ml * int(item.get("cant", 1))
                    peso_u = PESOS_CONTRATO.get(int(item.get("diam", 8)), 0.0)
                    kg_contrato = round(total_ml * peso_u, 2)
                    
                    filas_auditoria.append({
                        "Bloque/Zona": item.get("bloque", "General"),
                        "Despiece": item.get("barra", "-"),
                        "Ø": item.get("diam", 0),
                        "Cant.": item.get("cant", 0),
                        "Desarrollo Croquis (m)": desarrollo_ml,
                        "Total Metros (ml)": total_ml,
                        "Kg/ml Contrato": peso_u,
                        "Kgs Reales Contrato": kg_contrato,
                        "Subtotal Taller Bloque": item.get("tall_kg", 0.0)
                    })
                
                df_resultado = pd.DataFrame(filas_auditoria)
                
                # 4. Despliegue de Resultados en Pantalla
                st.markdown("### 📊 1. Auditoría Automatizada por Línea de Croquis")
                st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                
                st.markdown("### 🚨 2. Consolidación y Alertas de Desvíos de Acero")
                resumen = df_resultado.groupby("Bloque/Zona").agg({
                    "Kgs Reales Contrato": "sum",
                    "Subtotal Taller Bloque": "first"
                }).reset_index()
                resumen["Desvío (Kg)"] = round(resumen["Subtotal Taller Bloque"] - resumen["Kgs Reales Contrato"], 2)
                
                def pintar_alertas(val):
                    return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;' if abs(val) > umbral else 'background-color: #e6ffe6; color: #006600;'
                
                st.dataframe(resumen.style.map(pintar_alertas, subset=["Desvío (Kg)"]), use_container_width=True, hide_index=True)
                
                # 5. Descarga de resultados a Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as w:
                    df_resultado.to_excel(w, sheet_name="Detalle_Barras", index=False)
                    resumen.to_excel(w, sheet_name="Resumen_Desvios", index=False)
                    
                st.download_button(
                    label="📥 Descargar Auditoría Completa en Excel",
                    data=buffer.getvalue(),
                    file_name="auditoria_automatica_ferralla.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
            except Exception as e:
                st.error(f"Error durante el procesamiento del documento: {e}")
