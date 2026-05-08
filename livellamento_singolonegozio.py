import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="LIVELLAMENTO DA HUB", page_icon="🏢", layout="wide")

st.title("🏢 LIVELLAMENTO DA NEGOZIO HUB")

# --- DESCRIZIONE ---
st.markdown("""
### Descrizione del Programma
Questo strumento è progettato per svuotare uno specifico **Negozio HUB** (cedente fisso) distribuendo il suo stock in eccesso verso i negozi della stessa area/reparto che hanno le performance migliori (riceventi).
""")

# --- SEZIONE REQUISITI FILE (TEMPLATE) ---
colonne_necessarie = ['Area Manager', 'Dept code', 'apc', 'Avanzamento', 'valore', 'ST Adj', 'Store code']

with st.expander("🚨 REQUISITI DEL FILE EXCEL (LEGGIMI)"):
    st.write("⚠️ **Attenzione:** Il file deve contenere esattamente queste colonne:")
    
    # Esempio visivo
    template_data = {
        "Area Manager": ["Luca Bianchi"], "Dept code": [101], "apc": ["Z1"],
        "Store code": [1562], "Avanzamento": [0.80], "valore": [-1200.00], "ST Adj": [1]
    }
    st.table(pd.DataFrame(template_data))
    
    # Bottone per scaricare il template
    template_buffer = BytesIO()
    with pd.ExcelWriter(template_buffer, engine='openpyxl') as writer:
        pd.DataFrame(columns=colonne_necessarie).to_excel(writer, index=False)
    
    st.download_button(
        label="📥 Scarica Template Excel",
        data=template_buffer.getvalue(),
        file_name="template_hub.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.divider()

# --- SIDEBAR: PARAMETRI INTERATTIVI ---
st.sidebar.header("⚙️ Parametri Hub & Controllo")

# 1. Selezione Negozio Hub
codice_hub = st.sidebar.number_input(
    "Codice Negozio HUB (Cedente)", 
    min_value=1, max_value=9999, value=1562,
    help="Questo negozio sarà l'unico a cedere merce."
)

# 2. Parametri Economici
limite_minimo = st.sidebar.slider(
    "Limite minimo trasferimento (€)", 
    min_value=0, max_value=2000, value=300, step=25
)

# 3. Soglie Avanzamento
st.sidebar.subheader("Soglie di Avanzamento")
soglia_max_hub = st.sidebar.slider(
    "Soglia Max Avanzamento HUB", 
    min_value=0.0, max_value=1.5, value=0.95, step=0.05,
    help="L'Hub cede merce solo se il suo avanzamento è sotto questo valore."
)

soglia_min_riceventi = st.sidebar.slider(
    "Soglia Min Riceventi", 
    min_value=0.0, max_value=1.5, value=0.95, step=0.05,
    help="I negozi ricevono merce solo se sono sopra questa soglia."
)

# 4. Limite Riceventi
max_riceventi = st.sidebar.number_input(
    "Num. Max Negozi Riceventi per gruppo", 
    min_value=1, max_value=50, value=10
)

# --- SPIEGAZIONE DEI PARAMETRI ---
with st.expander("ℹ️ Come questi valori influenzano il risultato"):
    st.write(f"""
    * 🚨 **Negozio Hub ({codice_hub}):** Il sistema cercherà questo codice in ogni Area/Reparto. Se lo trova e ha valore negativo, inizierà a distribuire.
    * 💰 **Limite minimo ({limite_minimo}€):** Non verranno suggeriti spostamenti sotto questa cifra.
    * 📈 **Soglia Riceventi ({soglia_min_riceventi}):** Più è alta, più il sistema sarà 'aggressivo' nel mandare merce solo a chi sta vendendo tantissimo.
    """)

# --- CARICAMENTO FILE E LOGICA ---
uploaded_file = st.file_uploader("Carica il file Excel per il livellamento Hub", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file, header=0)
    
    if not all(col in df.columns for col in colonne_necessarie):
        st.error(f"🚨 **ERRORE:** Colonne mancanti! Il file deve avere: {colonne_necessarie}")
    else:
        log_trasferimenti = []
        
        # Gruppi
        gruppi = list(df.groupby(['Area Manager', 'Dept code', 'apc']))
        totale_gruppi = len(gruppi)
        
        testo_progresso = st.empty()
        barra_progresso = st.progress(0)

        for i, ((area, dept, apc), group) in enumerate(gruppi):
            # Update UI
            testo_progresso.markdown(f"⏳ Analisi HUB nel reparto: `{dept}` | Area: **{area}**")
            barra_progresso.progress((i + 1) / totale_gruppi)

            # 1. Selezione Cedente (Solo l'HUB impostato)
            filtro_cedente = (
                (group['Store code'] == codice_hub) &
                (group['valore'] < 0) &
                (group['Avanzamento'] < soglia_max_hub) &
                (group['ST Adj'] != 0)
            )
            cedenti = group[filtro_cedente].copy()

            # 2. Selezione Riceventi
            filtro_riceventi = (
                (group['Store code'] != codice_hub) &
                (group['Avanzamento'] > soglia_min_riceventi) &
                (group['valore'] > 0) &
                (group['Avanzamento'] > 0) &
                (group['ST Adj'] != 0)
            )

            riceventi = (group[filtro_riceventi]
                         .sort_values(by='Avanzamento', ascending=False)
                         .head(max_riceventi).copy())

            if cedenti.empty or riceventi.empty:
                continue

            cedenti['disponibile_da_cedere'] = cedenti['valore'].abs()
            riceventi['capacita_ricezione'] = riceventi['valore']

            # 3. Algoritmo di Distribuzione
            for idx_c, cedente in cedenti.iterrows():
                quantita_da_dare = cedente['disponibile_da_cedere']
                
                for idx_r, ricevente in riceventi.iterrows():
                    capacita_attuale = riceventi.at[idx_r, 'capacita_ricezione']
                    
                    if capacita_attuale < limite_minimo: 
                        continue

                    quantita_trasferita = min(quantita_da_dare, capacita_attuale)

                    if quantita_trasferita >= limite_minimo:
                        log_trasferimenti.append({
                            'Area Manager': area, 'Dept code': dept, 'apc': apc,
                            'Store HUB (Cedente)': cedente['Store code'],
                            'Avanzamento HUB': round(cedente['Avanzamento'], 2),
                            'Store Ricevente': ricevente['Store code'],
                            'Avanzamento Ricevente': round(ricevente['Avanzamento'], 2),
                            'Valore Trasferito (€)': round(quantita_trasferita, 2)
                        })

                        quantita_da_dare -= quantita_trasferita
                        riceventi.at[idx_r, 'capacita_ricezione'] -= quantita_trasferita

                        if quantita_da_dare < limite_minimo: 
                            break

        testo_progresso.empty()
        barra_progresso.empty()

        # --- OUTPUT RISULTATI ---
        if log_trasferimenti:
            df_output = pd.DataFrame(log_trasferimenti)
            
            st.success(f"✅ Distribuzione dall'HUB {codice_hub} completata!")
            
            # KPI
            c1, c2 = st.columns(2)
            c1.metric("Num. Negozi Aiutati", len(df_output['Store Ricevente'].unique()))
            c2.metric("Valore Totale Distribuito", f"{df_output['Valore Trasferito (€)'].sum():,.2f} €")

            # Tabella Riepilogo Aree
            st.subheader("📊 Riepilogo Svuotamento HUB per Area")
            riepilogo = df_output.groupby('Area Manager')['Valore Trasferito (€)'].agg(['sum', 'count']).rename(columns={'sum': 'Valore Totale (€)', 'count': 'Num. Negozi'})
            st.table(riepilogo)

            # Dettaglio
            st.subheader("📑 Dettaglio Trasferimenti HUB")
            st.dataframe(df_output, use_container_width=True)

            # Download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_output.to_excel(writer, index=False, sheet_name='Piano_HUB')
            
            st.download_button("📥 Scarica Risultati Hub", output.getvalue(), f"piano_HUB_{codice_hub}.xlsx")
        else:
            st.warning(f"⚠️ Nessun match trovato: il negozio {codice_hub} non può cedere merce o non ci sono riceventi che superano la soglia del {soglia_min_riceventi*100}%.")
