import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import warnings

# Silencing warnings
warnings.filterwarnings('ignore')

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Pallet Assignment System",
    page_icon="📦",
    layout="wide"
)

# --- FUNZIONI DI UTILITÀ ---
@st.cache_data
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Risultati')
    return output.getvalue()

def clean_st_dataframe(uploaded_file):
    """Pulisce e normalizza il DataFrame ST mantenendo la logica originale."""
    df = pd.read_excel(uploaded_file, header=0)
    # Estrazione numeri colonne (celle 2, 5, 8...)
    numeri_colonne = df.iloc[0, 1::3].values
    nuove_intestazioni = ['Des Negozio']
    
    for numero in numeri_colonne:
        nuove_intestazioni.extend([
            f"{numero} Somma di Total Delivered",
            f"{numero} Somma di Total Sales",
            f"{numero} Media di ST value"
        ])
    
    df.columns = nuove_intestazioni
    # Drop righe tecniche originali
    df = df.drop(index=[0, 1]).reset_index(drop=True)
    df = df.dropna(subset=["Des Negozio"])
    return df.fillna(0)

def ensure_all_shops_present(df_target, shop_list):
    """Ottimizzazione: aggiunge i negozi mancanti in un colpo solo invece di un loop."""
    missing_shops = list(set(shop_list) - set(df_target['Des Negozio']))
    if missing_shops:
        new_rows = pd.DataFrame({'Des Negozio': missing_shops}).fillna(0)
        df_target = pd.concat([df_target, new_rows], ignore_index=True)
    return df_target.fillna(0)

# --- UI PRINCIPALE ---
st.title("📦 Sistema di Assegnazione Pallet")
st.markdown("---")

if 'df_results' not in st.session_state:
    st.session_state.df_results = None

# --- SIDEBAR ---
st.sidebar.header("📁 Caricamento File")
uploaded_st = st.sidebar.file_uploader("Tabella ST (Excel)", type=['xlsx', 'xls'])
uploaded_avanzamenti = st.sidebar.file_uploader("Tabella AVANZAMENTI (Excel)", type=['xlsx', 'xls'])
uploaded_prelievi = st.sidebar.file_uploader("File PRELIEVI (Excel)", type=['xlsx', 'xls'])
uploaded_stock = st.sidebar.file_uploader("File STOCK (Excel)", type=['xlsx', 'xls'])

st.sidebar.header("⚙️ Parametri")
I1 = st.sidebar.slider("I1 - Peso media ponderata (%)", 0, 100, 70)
I2 = 100 - I1
st.sidebar.info(f"I2 - Peso media avanzamenti: {I2}% (calcolato come 100-I1")

alpha = st.sidebar.slider("Alpha (α)", 0.0, 1.0, 0.7, 0.05)
soglia_delivered = st.sidebar.number_input("Soglia Total Delivered", min_value=0.0, value=100000.0)
soglia_mult = st.sidebar.slider("Moltiplicatore riassegnazione", 1.0, 10.0, 2.0, 0.1)

# --- LOGICA DI PROCESSAMENTO ---
if all([uploaded_st, uploaded_avanzamenti, uploaded_prelievi, uploaded_stock]):
    try:
        # Caricamento e pulizia rapida
        df_negozi = clean_st_dataframe(uploaded_st)
        all_shops = df_negozi['Des Negozio'].unique()

        df_avanzamenti = ensure_all_shops_present(pd.read_excel(uploaded_avanzamenti), all_shops)
        df_prelievi = pd.read_excel(uploaded_prelievi).fillna(0)
        df_stock = ensure_all_shops_present(pd.read_excel(uploaded_stock), all_shops)

        # Pre-calcolo Valore Totale Prelievi
        df_prelievi['Valore Totale'] = df_prelievi.drop(columns=['ID_PRELIEVO']).sum(axis=1)

        # Filtro Negozi Validi (Vettorizzato)
        delivered_cols = [c for c in df_negozi.columns if "Total Delivered" in c]
        df_negozi['Total_Delivered_Sum'] = df_negozi[delivered_cols].sum(axis=1)
        df_negozi_validi = df_negozi[df_negozi['Total_Delivered_Sum'] >= soglia_delivered].copy()
        
        # Dizionari per accesso rapido (O(1) invece di O(n) nei loop)
        negozi_map = df_negozi_validi.set_index('Des Negozio').to_dict('index')
        avanzamenti_map = df_avanzamenti.set_index('Des Negozio').to_dict('index')
        stock_map = df_stock.set_index('Des Negozio').to_dict('index')
        
        st.success("✅ File pronti per l'elaborazione")
        
        if st.button("🚀 Avvia Assegnazione Pallet", type="primary", use_container_width=True):
            results = []
            negozi_assegnati = set()
            valori_assegnati = {n: 0 for n in negozi_map.keys()}
            
            # Progress bar
            pb = st.progress(0)
            total_rows = len(df_prelievi)

            # --- LOOP ASSEGNAZIONE PRIMARIA ---
            for idx, row in df_prelievi.iterrows():
                pb.progress((idx + 1) / total_rows)
                
                id_pre = str(row['ID_PRELIEVO']).split('.')[0]
                val_tot = row['Valore Totale']
                f_cols = [c for c in row.index if c not in ['ID_PRELIEVO', 'Valore Totale'] and row[c] > 0]
                
                # Check funzioni esistenti
                f_missing = [f for f in f_cols if f"{f} Somma di Total Delivered" not in df_negozi.columns]
                if len(f_missing) == len(f_cols):
                    results.append([id_pre, "Nessun negozio disponibile (TUTTE FUNZIONI NON PRESENTI)", 0, 0, 0, 0, 0, ",".join(map(str, f_missing)), val_tot])
                    continue
                
                f_valid = [f for f in f_cols if f not in f_missing]
                candidati = []

                # Calcolo stock totale funzioni per il pallet (per ps)
                stk_tot_f = sum(df_stock[str(f)].sum() if str(f) in df_stock.columns else 0 for f in f_valid)

                for neg, n_data in negozi_map.items():
                    if neg in negozi_assegnati: continue
                    
                    # Controllo Delivered > 0 per tutte le funzioni del pallet
                    if all(n_data.get(f"{f} Somma di Total Delivered", 0) > 0 for f in f_valid):
                        # 1. Media Ponderata ST
                        t_w_st, t_del = 0, 0
                        for f in f_valid:
                            d_val = n_data[f"{f} Somma di Total Delivered"]
                            t_w_st += n_data[f"{f} Media di ST value"] * d_val
                            t_del += d_val
                        m_pond = t_w_st / t_del if t_del > 0 else 0
                        
                        # 2. Media Avanzamenti
                        m_avz = np.mean([avanzamenti_map[neg].get(f, 0) for f in f_valid])
                        
                        # 3. Combinata e Score
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
                soglia_max = df_prelievi['Valore Totale'].max() * soglia_mult
                st.info(f"🔄 Riassegnazione... Soglia: {soglia_max:.2f}")
                
                riass_ok = set()
                for idx, row in non_ass.iterrows():
                    f_list = [int(f) for f in str(row['Funzioni presenti']).split(',') if f.strip().isdigit()]
                    stk_tot_f = sum(df_stock[str(f)].sum() if str(f) in df_stock.columns else 0 for f in f_list)
                    
                    candidati_r = []
                    for neg, n_data in negozi_map.items():
                        if (valori_assegnati[neg] + row['Valore Totale'] <= soglia_max) and (neg not in riass_ok):
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
        st.error(f"Errore: {e}")
        st.stop()

# --- DISPLAY RISULTATI ---
if st.session_state.df_results is not None:
    res = st.session_state.df_results
    total = len(res)
    unassigned = len(res[res["Negozio Assegnato"].str.contains("Nessun", na=False)])
    assigned = total - unassigned

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Totale Pallet", total)
    m2.metric("Assegnati", assigned)
    m3.metric("Non Assegnati", unassigned)
    m4.metric("Rate", f"{(assigned/total)*100:.1f}%")

    st.subheader("📋 Risultati")
    st.dataframe(res, use_container_width=True)
    
    st.download_button("📥 Scarica Excel", convert_df_to_excel(res), "risultati.xlsx", use_container_width=True)

    if unassigned > 0:
        st.warning("⚠️ Alcuni pallet non sono stati assegnati per mancanza di negozi idonei o superamento soglie.")
else:
    st.info("👆 Carica i file per iniziare.")
