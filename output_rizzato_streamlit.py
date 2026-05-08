import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# Configurazione pagina (opzionale, per cambiare l'icona nel tab del browser)
st.set_page_config(page_title="Controllo Smistamenti", page_icon="📦")

st.title("📦 Verifica Corrispondenza Ente/Assegnazione")

# --- SEZIONE DESCRIZIONE ---
st.markdown("""
### Cosa fa questo strumento?
Questo programma automatizza il controllo dei pallet verificando la coerenza tra l'ente emittente e l'assegnazione finale.

**Istruzioni:**
1. Carica il file Excel estratto dal sistema (es. `file.xlsx`).
2. Il sistema controllerà ogni **ID_PRELIEVO**.
3. Se per un singolo ID esiste anche solo un errore di smistamento (*mismatch*), l'intero ID verrà segnalato.
4. Se l'ID è corretto in tutte le sue righe, apparirà una **'x'** nella colonna **CHECK**.

---
""")

# --- LOGICA DI CARICAMENTO ---
uploaded_file = st.file_uploader("Trascina qui il file Excel o clicca per selezionarlo", type=["xlsx"])

if uploaded_file is not None:
    with st.spinner('Elaborazione dati in corso...'):
        # Lettura del file
        df = pd.read_excel(uploaded_file, dtype={'ID_PRELIEVO': str})

        # Logica di calcolo (la tua originale)
        df['mismatch'] = df['ENTE_EMIT'] != df['ASSEGNZIONE']
        has_error_in_group = df.groupby('ID_PRELIEVO')['mismatch'].transform('any')
        df['CHECK'] = np.where(~has_error_in_group, 'x', '')
        
        df_finale = df.drop(columns=['mismatch'])

        # Mostra i risultati
        st.success("Analisi completata!")
        
        col1, col2 = st.columns(2)
        col1.metric("Righe analizzate", len(df_finale))
        col2.metric("ID Univoci", df_finale['ID_PRELIEVO'].nunique())

        st.dataframe(df_finale.head(10)) # Mostra una tabella interattiva con le prime 10 righe

        # Preparazione download
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_finale.to_excel(writer, index=False, sheet_name='Checked')
        
        st.download_button(
            label="⬇️ Scarica il file elaborato",
            data=output.getvalue(),
            file_name='Database_Pallet_Checked.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
