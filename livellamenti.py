import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="LIVELLAMENTI PER ZONA", page_icon="⚖️", layout="wide")

st.title("⚖️ LIVELLAMENTI PER ZONA")

# --- DESCRIZIONE ---
st.markdown("""
### Descrizione del Programma
Questo strumento ottimizza i livelli di stock tra punti vendita della stessa area/reparto/apc.
Il sistema identifica chi ha merce in eccesso e chi è in rottura di stock, suggerendo il trasferimento ideale.
""")

# --- SIDEBAR: PARAMETRI INTERATTIVI ---
st.sidebar.header("⚙️ Parametri di Controllo")

# 1. Limite minimo economico
limite_minimo = st.sidebar.slider(
    "Limite minimo trasferimento (€)", 
    min_value=0, max_value=2000, value=300, step=25
)

# 2. Soglie Avanzamento
st.sidebar.subheader("Soglie di Avanzamento")
soglia_cedenti = st.sidebar.slider(
    "Soglia Max Cedenti (chi ha troppo)", 
    min_value=0.0, max_value=1.5, value=0.85, step=0.05,
    help="I negozi sotto questa soglia sono considerati potenziali cedenti."
)

soglia_riceventi = st.sidebar.slider(
    "Soglia Min Riceventi (chi ha poco)", 
    min_value=0.0, max_value=1.5, value=0.95, step=0.05,
    help="I negozi sopra questa soglia sono considerati potenziali riceventi."
)

# 3. Numero Max Negozi
st.sidebar.subheader("Limiti Operativi")
max_cedenti = st.sidebar.number_input(
    "Num. Max Negozi Cedenti", 
    min_value=1, max_value=20, value=5
)

max_riceventi = st.sidebar.number_input(
    "Num. Max Negozi Riceventi", 
    min_value=1, max_value=20, value=5
)

# --- SPIEGAZIONE DEI PARAMETRI ---
with st.expander("ℹ️ Come questi parametri influenzano il risultato"):
    st.write(f"""
    * **Limite minimo ({limite_minimo}€):** Evita micro-trasferimenti non convenienti a livello logistico.
    * **Soglia Cedenti ({soglia_cedenti}):** Più è bassa, più il codice seleziona solo chi ha stock molto elevato rispetto al venduto.
    * **Soglia Riceventi ({soglia_riceventi}):** Più è alta, più il codice si concentra solo su chi è in forte carenza.
    * **Max Cedenti/Riceventi:** Limita la complessità dell'operazione per ogni singolo reparto (consigliato: 5).
    """)
# --- SEZIONE REQUISITI FILE ---
with st.expander("📂 Requisiti del file Excel (Template)"):
    st.write("Il file caricato deve contenere esattamente queste colonne con questi nomi:")
    
    # Creiamo un esempio del formato richiesto
    template_data = {
        "Area Manager": ["Nome Cognome", "Nome Cognome"],
        "Dept code": [123, 456],
        "apc": ["A1", "B2"],
        "Store code": ["S001", "S002"],
        "Avanzamento": [0.75, 1.10],
        "valore": [-500.00, 800.00],
        "ST Adj": [1, 1]
    }
    template_df = pd.DataFrame(template_data)
    
    # Mostriamo la tabella statica
    st.table(template_df)
    
    st.info("💡 **Nota Bene:** La colonna 'Avanzamento' deve essere in formato numerico (es. 0.85 per 85%) e la colonna 'valore' deve avere segno negativo per i potenziali cedenti.")
    # Genera un file Excel vuoto con solo le intestazioni
    template_buffer = BytesIO()
    with pd.ExcelWriter(template_buffer, engine='openpyxl') as writer:
        pd.DataFrame(columns=colonne_necessarie).to_excel(writer, index=False)
    
    st.download_button(
        label="📥 Scarica Excel d'esempio (Template)",
        data=template_buffer.getvalue(),
        file_name="template_livellamento.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
# --- CARICAMENTO FILE ---
uploaded_file = st.file_uploader("Carica il file Excel", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file, header=0)
    
    colonne_necessarie = ['Area Manager', 'Dept code', 'apc', 'Avanzamento', 'valore', 'ST Adj', 'Store code']
    
    if not all(col in df.columns for col in colonne_necessarie):
        st.error(f"Errore: Il file caricato non contiene tutte le colonne necessarie: {colonne_necessarie}")
    else:
        log_trasferimenti = []
        
        # Prepariamo i gruppi e i widget di progresso
        gruppi = list(df.groupby(['Area Manager', 'Dept code', 'apc']))
        totale_gruppi = len(gruppi)
        
        testo_progresso = st.empty()
        barra_progresso = st.progress(0)

        # --- CICLO DI ELABORAZIONE ---
        for i, ((area, dept, apc), group) in enumerate(gruppi):
            # Aggiornamento UI
            testo_progresso.markdown(f"🔄 Elaborazione Area: **{area}** | Reparto: `{dept}`")
            barra_progresso.progress((i + 1) / totale_gruppi)

            # 1. Selezione Cedenti
            cedenti = (group[(group['Avanzamento'] < soglia_cedenti) & 
                             (group['valore'] < 0) & 
                             (group['Avanzamento'] > 0) & 
                             (group['ST Adj'] != 0)]
                       .sort_values(by='Avanzamento', ascending=True)
                       .head(max_cedenti).copy())

            if not cedenti.empty:
                cedenti['disponibile_da_cedere'] = cedenti['valore'].abs()

            # 2. Selezione Riceventi
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

            # 3. Algoritmo di Bilanciamento (Incrocio Cedenti -> Riceventi)
            for idx_c, cedente in cedenti.iterrows():
                quantita_da_dare = cedente['disponibile_da_cedere']
                if quantita_da_dare < limite_minimo: 
                    continue

                for idx_r, ricevente in riceventi.iterrows():
                    capacita_attuale = riceventi.at[idx_r, 'capacita_ricezione']
                    if capacita_attuale < limite_minimo: 
                        continue

                    quantita_trasferita = min(quantita_da_dare, capacita_attuale)

                    if quantita_trasferita >= limite_minimo:
                        log_trasferimenti.append({
                            'Area Manager': area, 
                            'Dept code': dept, 
                            'apc': apc,
                            'Store Cedente': cedente['Store code'],
                            'Avanzamento Cedente': round(cedente['Avanzamento'], 2),
                            'Store Ricevente': ricevente['Store code'],
                            'Avanzamento Ricevente': round(ricevente['Avanzamento'], 2),
                            'Valore Trasferito (€)': round(quantita_trasferita, 2)
                        })
                        
                        quantita_da_dare -= quantita_trasferita
                        riceventi.at[idx_r, 'capacita_ricezione'] -= quantita_trasferita
                        
                        if quantita_da_dare < limite_minimo: 
                            break

        # Pulizia indicatori progresso
        testo_progresso.empty()
        barra_progresso.empty()

        # --- OUTPUT RISULTATI ---
        if log_trasferimenti:
            df_output = pd.DataFrame(log_trasferimenti)
            
            st.success(f"✅ Analisi conclusa con successo! Trovati {len(df_output)} trasferimenti ottimali.")
           # --- NUOVA SEZIONE: KPI TOTALI ---
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Totale Trasferimenti", f"{len(df_output)}")
            with col_b:
                valore_totale = df_output['Valore Trasferito (€)'].sum()
                st.metric("Valore Totale Spostato", f"{valore_totale:,.2f} €")

            st.divider()

            # --- NUOVA SEZIONE: TABELLA RIASSUNTIVA PER AREA MANAGER ---
            st.subheader("📊 Riepilogo per Area Manager")
            
            # Creiamo una pivot table che somma il valore trasferito per ogni Area
            riepilogo_area = (
                df_output.groupby('Area Manager')['Valore Trasferito (€)']
                .agg(['sum', 'count'])
                .rename(columns={'sum': 'Totale Valore (€)', 'count': 'Num. Operazioni'})
                .sort_values(by='Totale Valore (€)', ascending=False)
            )
            
            # Visualizziamo la tabella di riepilogo
            st.table(riepilogo_area) 

            st.divider()

            # --- DETTAGLIO COMPLETO ---
            st.subheader("📑 Dettaglio Completo Piano Trasferimenti")
            st.dataframe(df_output, use_container_width=True) 

            # Generazione Excel per Download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_output.to_excel(writer, index=False, sheet_name='Piano_Livellamento')
            
            st.download_button(
                label="📥 Scarica Risultati in Excel", 
                data=output.getvalue(), 
                file_name="piano_livellamento_zona.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("⚠️ Nessun trasferimento trovato. Prova ad abbassare il 'Limite minimo' o a rendere meno stringenti le soglie di avanzamento.")
