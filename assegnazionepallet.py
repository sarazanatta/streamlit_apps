import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import warnings

# Silencing warnings
warnings.filterwarnings('ignore')

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Assegnazione pallet",
    page_icon="📦",
    layout="wide"
)

# --- FUNZIONI DI UTILITÀ (Ottimizzate) ---
@st.cache_data
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Risultati')
    return output.getvalue()

def clean_st_dataframe(uploaded_file):
    df = pd.read_excel(uploaded_file, header=0)
    numeri_colonne = df.iloc[0, 1::3].values
    nuove_intestazioni = ['Des Negozio']
    for numero in numeri_colonne:
        nuove_intestazioni.extend([
            f"{numero} Somma di Total Delivered",
            f"{numero} Somma di Total Sales",
            f"{numero} Media di ST value"
        ])
    df.columns = nuove_intestazioni
    df = df.drop(index=[0, 1]).reset_index(drop=True)
    df = df.dropna(subset=["Des Negozio"])
    return df.fillna(0)

def ensure_all_shops_present(df_target, shop_list):
    missing_shops = list(set(shop_list) - set(df_target['Des Negozio']))
    if missing_shops:
        new_rows = pd.DataFrame({'Des Negozio': missing_shops})
        df_target = pd.concat([df_target, new_rows], ignore_index=True)
    return df_target.fillna(0)

# --- UI PRINCIPALE ---
st.title("📦 Sistema di Assegnazione Pallet (un pallet per negozio con eventuale riassegnazione dei pallet mancanti)")
st.markdown("---")

if 'df_results' not in st.session_state:
    st.session_state.df_results = None

# --- SIDEBAR CON TUTTI GLI HELP ORIGINALI ---
st.sidebar.header("📁 Caricamento File")

uploaded_st = st.sidebar.file_uploader(
    "Carica tabella ST (Excel)",
    type=['xlsx', 'xls'],
    help="File contenente i dati dei negozi con Total Delivered, Total Sales e ST value"
)

uploaded_avanzamenti = st.sidebar.file_uploader(
    "Carica tabella AVANZAMENTI (Excel)",
    type=['xlsx', 'xls'],
    help="File contenente i dati degli avanzamenti per negozio"
)

uploaded_prelievi = st.sidebar.file_uploader(
    "Carica file PRELIEVI (Excel)",
    type=['xlsx', 'xls'],
    help="File contenente gli ID_PRELIEVO e le funzioni"
)

uploaded_stock = st.sidebar.file_uploader(
    "Carica file STOCK (Excel)",
    type=['xlsx', 'xls'],
    help="File contenente i dati dello stock per negozio"
)

st.sidebar.header("⚙️ Parametri")

I1 = st.sidebar.slider(
    "I1 - Peso media ponderata (%)",
    min_value=0,
    max_value=100,
    value=70,
    help="Importanza della media ponderata nel calcolo finale"
)

I2 = 100 - I1
st.sidebar.write(f"I2 - Peso media avanzamenti (%): {I2}")

alpha = st.sidebar.slider(
    "Alpha (α)",
    min_value=0.0,
    max_value=1.0,
    value=0.7,
    step=0.05,
    help="Parametro per il calcolo del punteggio P"
)

soglia_delivered = st.sidebar.number_input(
    "Soglia Total Delivered",
    min_value=0.0,
    value=100000.0,
    step=100.0,
    help="Soglia minima per il totale delivered dei negozi"
)

soglia_massima_moltiplicatore = st.sidebar.slider(
    "Moltiplicatore soglia massima per riassegnazione",
    min_value=1.0,
    max_value=10.0,
    value=2.0,
    step=0.1,
    help="Il valore massimo assegnabile per negozio sarà: valore_max_pallet * questo moltiplicatore"
)

# --- LOGICA DI ELABORAZIONE ---
if all([uploaded_st, uploaded_avanzamenti, uploaded_prelievi, uploaded_stock]):
    try:
        # Caricamento e preparazione dati
        df_negozi = clean_st_dataframe(uploaded_st)
        all_shops = df_negozi['Des Negozio'].unique()

        df_avanzamenti = ensure_all_shops_present(pd.read_excel(uploaded_avanzamenti), all_shops)
        df_prelievi = pd.read_excel(uploaded_prelievi).fillna(0)
        df_stock = ensure_all_shops_present(pd.read_excel(uploaded_stock), all_shops)

        df_prelievi['Valore Totale'] = df_prelievi.drop(columns=['ID_PRELIEVO']).sum(axis=1)

        # Dizionari per accesso ultra-rapido O(1)
        negozi_map = df_negozi.set_index('Des Negozio').to_dict('index')
        avanzamenti_map = df_avanzamenti.set_index('Des Negozio').to_dict('index')
        stock_map = df_stock.set_index('Des Negozio').to_dict('index')
        
        # Filtro negozi validi basato sulla soglia delivered
        delivered_cols = [c for c in df_negozi.columns if "Total Delivered" in c]
        df_negozi['Total_Delivered_Sum'] = df_negozi[delivered_cols].sum(axis=1)
        lista_negozi_validi = df_negozi[df_negozi['Total_Delivered_Sum'] >= soglia_delivered]['Des Negozio'].tolist()

        # Anteprima
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Anteprima Dati Negozi")
            st.dataframe(df_negozi.head(), use_container_width=True)
        with col2:
            st.subheader("📦 Anteprima Prelievi")
            st.dataframe(df_prelievi.head(), use_container_width=True)

        if st.button("🚀 Avvia Assegnazione Pallet", type="primary", use_container_width=True):
            results = []
            negozi_assegnati = set()
            valori_assegnati = {n: 0 for n in lista_negozi_validi}
            
            pb = st.progress(0)
            total_rows = len(df_prelievi)

            for idx, row in df_prelievi.iterrows():
                pb.progress((idx + 1) / total_rows)
                
                id_pre = str(row['ID_PRELIEVO']).split('.')[0]
                val_tot = row['Valore Totale']
                f_cols = [c for c in row.index if c not in ['ID_PRELIEVO', 'Valore Totale'] and row[c] > 0]
                
                # Check funzioni
                f_missing = [f for f in f_cols if f"{f} Somma di Total Delivered" not in df_negozi.columns]
                if len(f_missing) == len(f_cols):
                    results.append([id_pre, "Nessun negozio disponibile (TUTTE FUNZIONI NON PRESENTI)", 0, 0, 0, 0, 0, ",".join(map(str, f_missing)), val_tot])
                    continue
                
                f_valid = [f for f in f_cols if f not in f_missing]
                
                # Calcolo stock totale per ps (vettorizzato)
                stk_tot_f = sum(df_stock[str(f)].sum() if str(f) in df_stock.columns else 0 for f in f_valid)

                candidati = []
                for neg in lista_negozi_validi:
                    if neg in negozi_assegnati: continue
                    
                    n_data = negozi_map[neg]
                    if all(n_data.get(f"{f} Somma di Total Delivered", 0) > 0 for f in f_valid):
                        # Media Ponderata
                        t_w_st = sum(n_data[f"{f} Media di ST value"] * n_data[f"{f} Somma di Total Delivered"] for f in f_valid)
                        t_del = sum(n_data[f"{f} Somma di Total Delivered"] for f in f_valid)
                        m_pond = t_w_st / t_del if t_del > 0 else 0
                        
                        # Media Avanzamenti
                        m_avz = np.mean([avanzamenti_map[neg].get(f, 0) for f in f_valid])
                        
                        # Combinata e Score
                        m_comb = (I1 * m_pond + I2 * m_avz) / 100
                        stk_neg = sum(stock_map[neg].get(f, 0) for f in f_valid)
                        ps = stk_neg / stk_tot_f if stk_tot_f > 0 else 0
                        
                        score = (max(0, m_comb)**alpha) / (1 + ps**(1 - alpha))
                        candidati.append((neg, score, ps, m_comb, m_pond, m_avz))

                if candidati:
                    candidati.sort(key=lambda x: x[1], reverse=True)
                    best = candidati[0]
                    negozi_assegnati.add(best[0])
                    valori_assegnati[best[0]] += val_tot
                    results.append([id_pre, *best, ",".join(map(str, f_valid)), val_tot])
                else:
                    results.append([id_pre, "Nessun negozio disponibile", 0, 0, 0, 0, 0, ",".join(map(str, f_valid)), val_tot])

            pb.empty()
            df_res = pd.DataFrame(results, columns=["ID_PRELIEVO", "Negozio Assegnato", "Punteggio", "Percentuale Stock", "Media Ponderata Combinata", "Media Ponderata", "Media Avanzamenti", "Funzioni presenti", "Valore Totale"])

            # --- RIASSEGNAZIONE ---
            non_ass = df_res[df_res["Negozio Assegnato"] == "Nessun negozio disponibile"]
            if not non_ass.empty:
                soglia_max = df_prelievi['Valore Totale'].max() * soglia_massima_moltiplicatore
                st.info(f"🔄 Riassegnazione... Soglia massima: {soglia_max:.2f}")
                
                riass_ok = set()
                for idx, row in non_ass.iterrows():
                    f_list = [int(f) for f in str(row['Funzioni presenti']).split(',') if f.strip().isdigit()]
                    stk_tot_f = sum(df_stock[str(f)].sum() if str(f) in df_stock.columns else 0 for f in f_list)
                    
                    candidati_r = []
                    for neg in lista_negozi_validi:
                        if (valori_assegnati[neg] + row['Valore Totale'] <= soglia_max) and (neg not in riass_ok):
                            n_data = negozi_map[neg]
                            if all(n_data.get(f"{f} Somma di Total Delivered", 0) > 0 for f in f_list):
                                m_pond = sum(n_data[f"{f} Media di ST value"] * n_data[f"{f} Somma di Total Delivered"] for f in f_list) / sum(n_data[f"{f} Somma di Total Delivered"] for f in f_list)
                                m_avz = np.mean([avanzamenti_map[neg].get(f, 0) for f in f_list])
                                m_comb = (I1 * m_pond + I2 * m_avz) / 100
                                ps = sum(stock_map[neg].get(f, 0) for f in f_list) / stk_tot_f if stk_tot_f > 0 else 0
                                score = (max(0, m_comb)**alpha) / (1 + ps**(1 - alpha))
                                candidati_r.append((neg, score, ps, m_comb, m_pond, m_avz))
                    
                    if candidati_r:
                        candidati_r.sort(key=lambda x: x[1], reverse=True)
                        b = candidati_r[0]
                        df_res.loc[df_res['ID_PRELIEVO'] == row['ID_PRELIEVO'], ["Negozio Assegnato", "Punteggio", "Percentuale Stock", "Media Ponderata Combinata", "Media Ponderata", "Media Avanzamenti"]] = [b[0], b[1], b[2], b[3], b[4], b[5]]
                        valori_assegnati[b[0]] += row['Valore Totale']
                        riass_ok.add(b[0])

            st.session_state.df_results = df_res

    except Exception as e:
        st.error(f"Errore nel processamento: {str(e)}")
        st.stop()

# --- DISPLAY RISULTATI ---
if st.session_state.df_results is not None:
    res = st.session_state.df_results
    total = len(res)
    pallet_non_assegnati = res[res["Negozio Assegnato"] == "Nessun negozio disponibile"]
    assigned = total - len(pallet_non_assegnati)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Totale Pallet", total)
    col2.metric("Pallet Assegnati", assigned)
    col3.metric("Pallet Non Assegnati", len(pallet_non_assegnati))
    col4.metric("Tasso di Assegnazione", f"{(assigned/total)*100:.1f}%" if total > 0 else "0%")

    st.subheader("📋 Risultati Assegnazione")
    st.dataframe(res, use_container_width=True)
    
    st.download_button(
        label="📥 Scarica Risultati (Excel)",
        data=convert_df_to_excel(res),
        file_name="risultati_assegnazione.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    # Messaggi di allerta finali
    if not pallet_non_assegnati.empty:
        st.warning("⚠️ Alcuni pallet rimangono ancora non assegnati dopo la riassegnazione automatica")
        with st.expander("Visualizza pallet ancora non assegnati"):
            st.dataframe(pallet_non_assegnati, use_container_width=True)

    senza_funzioni = res[res["Negozio Assegnato"].str.contains("TUTTE FUNZIONI NON PRESENTI", na=False)]
    if not senza_funzioni.empty:
        st.error("ATTENZIONE: ancora presenti pallet non assegnati (presenti pallet con tutte funzioni non presenti)")
else:
    st.info("👆 Carica tutti i file richiesti nella barra laterale per iniziare")
    st.subheader("📋 File Richiesti")
    file_requirements = {
        "Tabella ST": "Contiene dati dei negozi con colonne Total Delivered, Total Sales e ST value",
        "Tabella AVANZAMENTI": "Contiene dati degli avanzamenti per ogni negozio",
        "File PRELIEVI": "Contiene ID_PRELIEVO e codici funzione per ogni pallet",
        "File STOCK": "Contiene dati dello stock disponibile per negozio"
    }
    for f_name, desc in file_requirements.items():
        st.write(f"**{f_name}**: {desc}")

st.markdown("---")
st.markdown("*Sistema di Assegnazione Pallet - Versione Web App con Riassegnazione Automatica*")
