#smistamento per taglia minimizzando il numero di negozi coinvolti come cedenti
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# Configurazione Pagina
st.set_page_config(page_title="Ottimizzatore Globale Smistamento", page_icon="🎯", layout="wide")

st.title("🎯 Ottimizzatore Globale (Minimo numero di Enti)")
st.markdown("L'algoritmo seleziona prioritariamente i negozi che possono evadere il maggior numero di articoli/taglie diversi contemporaneamente.")
# --- SEZIONE TEMPLATE SEMPRE VISIBILE ---
st.subheader("📖 Struttura dei File Richiesti")
st.write("Per il corretto funzionamento, i tuoi file Excel devono seguire questa struttura:")

col_t1, col_t2 = st.columns(2)

with col_t1:
    st.markdown("### 1. File RICHIESTA")
    st.markdown("**Colonne necessarie:** `COD ARTICOLO`, `XS`, `S`, `M`, `L`, `XL`, `XXL`")
    
    esempio_req = pd.DataFrame({
        'COD ARTICOLO': ['ART_01', 'ART_02'],
        'XS': [1, 0], 'S': [2, 1], 'M': [0, 2],
        'L': [5, 0], 'XL': [0, 1], 'XXL': [1, 0]
    })
    st.dataframe(esempio_req, hide_index=True, use_container_width=True)
    st.info("💡 Questo file elenca la richiesta da soddisfare")

with col_t2:
    st.markdown("### 2. File DB STOCK")
    st.markdown("**Colonne necessarie:** `COD ARTICOLO`, `NEGOZIO`, `XS`, `S`, `M`, `L`, `XL`, `XXL`")
    
    esempio_db = pd.DataFrame({
        'COD ARTICOLO': ['ART_01', 'ART_01', 'ART_02'],
        'NEGOZIO': ['MILANO', 'ROMA', 'MILANO'],
        'XS': [10, 5, 2], 'S': [8, 12, 0], 'M': [15, 3, 10],
        'L': [20, 0, 5], 'XL': [5, 5, 8], 'XXL': [2, 1, 0]
    })
    st.dataframe(esempio_db, hide_index=True, use_container_width=True)
    st.info("💡 Questo file è il db dello stock per negozio/articolo")

st.markdown("---")
def optimize_global_picking(df_req, df_db):
    size_cols = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
    
    # Pulizia e normalizzazione
    df_req = df_req.copy()
    df_db = df_db.copy()
    for col in size_cols:
        df_req[col] = pd.to_numeric(df_req[col], errors='coerce').fillna(0).astype(int)
        df_db[col] = pd.to_numeric(df_db[col], errors='coerce').fillna(0).astype(int)

    # Creiamo un dizionario della richiesta residua: {(Articolo, Taglia): Quantità}
    request_map = {}
    for _, row in df_req.iterrows():
        art = row['COD ARTICOLO']
        for sz in size_cols:
            qty = row[sz]
            if qty > 0:
                request_map[(art, sz)] = request_map.get((art, sz), 0) + qty

    results = []
    
    # Finchè c'è qualcosa da chiedere...
    while sum(request_map.values()) > 0:
        stores = df_db['NEGOZIO'].unique()
        best_store = None
        best_coverage = -1
        best_total_stock = -1
        current_picks_for_best = {}

        # Cerchiamo il negozio "Migliore" in questo momento
        for store in stores:
            store_data = df_db[df_db['NEGOZIO'] == store]
            temp_coverage = 0
            temp_store_stock = 0
            temp_picks = {}

            for _, row in store_data.iterrows():
                art = row['COD ARTICOLO']
                for sz in size_cols:
                    needed = request_map.get((art, sz), 0)
                    if needed > 0:
                        can_take = min(row[sz], needed)
                        temp_coverage += can_take
                        if can_take > 0:
                            temp_picks[(art, sz)] = can_take
                
                # Calcolo stock totale del negozio per l'articolo (Tie-breaker)
                temp_store_stock += row[size_cols].sum()

            # Logica di selezione del Negozio:
            # 1. Chi copre più pezzi totali della richiesta
            # 2. A parità, chi ha più stock totale (salute stock)
            if temp_coverage > best_coverage:
                best_coverage = temp_coverage
                best_store = store
                best_total_stock = temp_store_stock
                current_picks_for_best = temp_picks
            elif temp_coverage == best_coverage and temp_coverage > 0:
                if temp_store_stock > best_total_stock:
                    best_store = store
                    best_total_stock = temp_store_stock
                    current_picks_for_best = temp_picks

        # Se non troviamo più nessuno che copre nulla, usciamo
        if best_coverage <= 0:
            break

        # Confermiamo il prelievo dal miglior negozio trovato
        for (art, sz), qty in current_picks_for_best.items():
            results.append({
                "NEGOZIO": best_store,
                "COD ARTICOLO": art,
                "TAGLIA": sz,
                "QUANTITÀ": qty
            })
            # Sottraiamo dalla richiesta globale
            request_map[(art, sz)] -= qty
            # Sottraiamo dal DB (per non riprenderlo nello stesso negozio se ci sono loop)
            idx = df_db[(df_db['NEGOZIO'] == best_store) & (df_db['COD ARTICOLO'] == art)].index
            df_db.loc[idx, sz] -= qty

    # Formattazione risultati
    if not results:
        return pd.DataFrame(), pd.DataFrame()

    df_results_raw = pd.DataFrame(results)
    # Pivot per tornare al formato originale richiesto (Articolo, Negozio, XS, S, M...)
    df_final = df_results_raw.pivot_table(
        index=['COD ARTICOLO', 'NEGOZIO'], 
        columns='TAGLIA', 
        values='QUANTITÀ', 
        aggfunc='sum'
    ).reset_index().fillna(0)
    
    # Assicuriamoci che tutte le colonne taglia esistano
    for sz in size_cols:
        if sz not in df_final.columns:
            df_final[sz] = 0
    
    # Riordino colonne
    df_final = df_final[['COD ARTICOLO', 'NEGOZIO'] + size_cols]

    # Calcolo mancanze
    shortages = []
    for (art, sz), qty in request_map.items():
        if qty > 0:
            shortages.append({"Articolo": art, "Taglia": sz, "Quantità Mancante": qty})
    
    return df_final, pd.DataFrame(shortages)

# --- INTERFACCIA STREAMLIT ---
st.sidebar.header("📁 Caricamento File")
file_req = st.sidebar.file_uploader("1. Carica Richiesta (Articolo, XS, S...)", type=['xlsx'])
file_db = st.sidebar.file_uploader("2. Carica DB Stock (Articolo, Negozio, XS, S...)", type=['xlsx'])

if file_req and file_db:
    df_req = pd.read_excel(file_req)
    df_db = pd.read_excel(file_db)
    
    if st.button("🚀 Ottimizza Spedizioni", type="primary", use_container_width=True):
        with st.spinner("Ricerca della combinazione minima di negozi..."):
            df_out, df_miss = optimize_global_picking(df_req, df_db)
            
            if not df_out.empty:
                st.success("Ottimizzazione Completata!")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Negozi Totali Mittenti", df_out['NEGOZIO'].nunique())
                c2.metric("Pezzi Totali Smistati", int(df_out[ ['XS','S','M','L','XL','XXL'] ].sum().sum()))
                c3.metric("Copertura Richiesta", f"{ (1 - len(df_miss)/max(1,len(df_req)))*100 :.1f}%")

                st.subheader("📋 Piano di Prelievo (Raggruppato per Negozio)")
                st.dataframe(df_out.sort_values('NEGOZIO'), use_container_width=True)

                # Download
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_out.to_excel(writer, index=False, sheet_name='Piano_Prelievo')
                    if not df_miss.empty:
                        df_miss.to_excel(writer, index=False, sheet_name='Mancanze')
                
                st.download_button("📥 Scarica Excel Risultati", output.getvalue(), "smistamento_min_enti.xlsx", use_container_width=True)
            else:
                st.error("Impossibile evadere la richiesta con lo stock disponibile.")

            if not df_miss.empty:
                with st.expander("Visualizza Mancanze"):
                    st.table(df_miss)
else:
    st.info("Carica i file per vedere l'anteprima e avviare l'algoritmo.")
