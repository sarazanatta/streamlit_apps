import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# Configurazione Pagina
st.set_page_config(page_title="Bilanciamento Avanzato Stock", page_icon="⚖️")

st.title("⚖️ Bilanciamento Avanzato Stock")

# --- DESCRIZIONE ---
st.markdown("""
### Descrizione del Programma
Questo strumento ottimizza i livelli di stock tra punti vendita dello stesso reparto/area.
Utilizza i parametri nella barra a sinistra per regolare la sensibilità dell'algoritmo.
""")

# --- SIDEBAR: PARAMETRI INTERATTIVI ---
st.sidebar.header("Parametri di Controllo")

# 1. Limite minimo economico
limite_minimo = st.sidebar.slider(
    "Limite minimo trasferimento (€)", 
    min_value=0, max_value=1000, value=300, step=50
)

# 2. Soglie Avanzamento
soglia_cedenti = st.sidebar.slider(
    "Soglia Max Avanzamento Cedenti (chi ha troppo)", 
    min_value=0.0, max_value=1.0, value=0.85, step=0.05
)

soglia_riceventi = st.sidebar.slider(
    "Soglia Min Avanzamento Riceventi (chi ha poco)", 
    min_value=0.0, max_value=1.0, value=0.95, step=0.05
)

# 3. Numero Max Negozi
max_cedenti = st.sidebar.number_input(
    "Num. Max Negozi Cedenti per gruppo", 
    min_value=1, max_value=20, value=5
)

max_riceventi = st.sidebar.number_input(
    "Num. Max Negozi Riceventi per gruppo", 
    min_value=1, max_value=20, value=5
)

# --- SPIEGAZIONE DEI PARAMETRI ---
with st.expander("ℹ️ Come questi valori influenzano il risultato"):
    st.write(f"""
    * **Limite minimo ({limite_minimo}€):** Impedisce trasferimenti troppo piccoli (es. spostare 10€ di merce non conviene per i costi di logistica).
    * **Soglia Cedenti ({soglia_cedenti}):** Più è bassa, più il programma è "selettivo": considererà cedenti solo i negozi con pochissime vendite rispetto allo stock.
    * **Soglia Riceventi ({soglia_riceventi}):** Più è alta, più il programma cercherà di aiutare solo chi è in vera emergenza stock.
    * **Max Cedenti/Riceventi:** Limita il numero di negozi coinvolti per ogni Area/Dept. Utile per non frammentare troppo le spedizioni.
    """)

# --- LOGICA APPLICATIVA ---
uploaded_file = st.file_uploader("Carica il file Excel", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file, header=0)
    
    colonne_necessarie = ['Area Manager', 'Dept code', 'apc', 'Avanzamento', 'valore', 'ST Adj', 'Store code']
    if not all(col in df.columns for col in colonne_necessarie):
        st.error("Errore: Colonne mancanti nel file!")
    else:
        log_trasferimenti = []
        per_area_dept_apc = df.groupby(['Area Manager', 'Dept code', 'apc'])

        for (area, dept, apc), group in per_area_dept_apc:
            # Selezione Cedenti (Usa soglia_cedenti e max_cedenti)
            cedenti = (group[(group['Avanzamento'] < soglia_cedenti) & 
                             (group['valore'] < 0) & 
                             (group['Avanzamento'] > 0) & 
                             (group['ST Adj'] != 0)]
                       .sort_values(by='Avanzamento', ascending=True)
                       .head(max_cedenti).copy())

            if not cedenti.empty:
                cedenti['disponibile_da_cedere'] = cedenti['valore'].abs()

            # Selezione Riceventi (Usa soglia_riceventi e max_riceventi)
            riceventi = (group[(group['Avanzamento'] > soglia_riceventi) & 
                               (group['valore'] > 0) & 
                               (group['Avanzamento'] > 0) & 
                               (group['ST Adj'] != 0)]
                         .sort_values(by='Avanzamento', ascending=False)
                         .head(max_riceventi).copy())

            if not riceventi.empty:
                riceventi['capacita_ricezione'] = riceventi['valore']

            if cedenti.empty or riceventi.empty:
                continue

            # Algoritmo di Bilanciamento
            for idx_c, cedente in cedenti.iterrows():
                quantita_da_dare = cedente['disponibile_da_cedere']
                if quantita_da_dare < limite_minimo: continue

                for idx_r, ricevente in riceventi.iterrows():
                    capacita_attuale = riceventi.at[idx_r, 'capacita_ricezione']
                    if capacita_attuale < limite_minimo: continue

                    quantita_trasferita = min(quantita_da_dare, capacita_attuale)

                    if quantita_trasferita >= limite_minimo:
                        log_trasferimenti.append({
                            'Area Manager': area, 'Dept code': dept, 'apc': apc,
                            'Store Cedente': cedente['Store code'],
                            'Avanzamento Cedente': cedente['Avanzamento'],
                            'Store Ricevente': ricevente['Store code'],
                            'Avanzamento Ricevente': ricevente['Avanzamento'],
                            'Valore Trasferito (€)': round(quantita_trasferita, 2)
                        })
                        quantita_da_dare -= quantita_trasferita
                        riceventi.at[idx_r, 'capacita_ricezione'] -= quantita_trasferita
                        if quantita_da_dare < limite_minimo: break

        if log_trasferimenti:
            df_output = pd.DataFrame(log_trasferimenti)
            st.success(f"Analisi conclusa: {len(df_output)} trasferimenti ottimizzati.")
            st.dataframe(df_output)

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_output.to_excel(writer, index=False)
            
            st.download_button("📥 Scarica Risultati", output.getvalue(), "piano_trasferimenti.xlsx")
        else:
            st.warning("Nessun trasferimento trovato con questi parametri.")
