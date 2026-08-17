import streamlit as st
import pandas as pd
import numpy as np
from warnings import simplefilter

simplefilter(action="ignore", category=pd.errors.PerformanceWarning)

# Configurazione pagina Streamlit
st.set_page_config(
    page_title="SARA",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Algoritmo di Assegnazione SARA")
st.markdown("""
Questa applicazione automatizza la distribuzione dei prelievi/pallet verso i punti vendita 
utilizzando un modello decisionale basato su performance storica (Sell Through), avanzamenti e pressione dello stock.
""")

# --- SIDEBAR: CARICAMENTO FILE ---
st.sidebar.header("📁 1. Caricamento File Excel")

file_st = st.sidebar.file_uploader("Tabella Sell Through (ST)", type=["xlsx", "xls"])
file_avanzamenti = st.sidebar.file_uploader("Tabella Avanzamenti", type=["xlsx", "xls"])
file_pallet = st.sidebar.file_uploader("Tabella Pallet / Prelievi", type=["xlsx", "xls"])
file_stock = st.sidebar.file_uploader("Tabella Stock Residuo", type=["xlsx", "xls"])

# --- SIDEBAR: PARAMETRI ALGORITMO ---
st.sidebar.header("⚙️ 2. Parametri Algoritmo")

col_i1, col_i2 = st.sidebar.columns(2)
with col_i1:
    I1 = st.slider("Peso ST (%)", min_value=0, max_value=100, value=70, step=1)
with col_i2:
    I2 = st.slider("Peso Avanzamenti (%)", min_value=0, max_value=100, value=30, step=1)

if I1 + I2 != 100:
    st.sidebar.error("⚠️ La somma dei pesi I1 e I2 deve essere esattamente 100!")

alpha = st.sidebar.number_input("Valore Alpha (Bilanciamento)", min_value=0.0, max_value=1.0, value=0.7, step=0.05)
ASSEGNAZIONI = st.sidebar.number_input("Max Pallet per Negozio", min_value=1, max_value=50, value=1, step=1)

st.sidebar.header("💶 3. Soglie Economiche")
soglia_delivered = st.sidebar.number_input("Soglia Minima Delivered", min_value=0.0, value=100.0, step=10.0)
SOGLIA_MASSIMA = st.sidebar.number_input("Capacità Max Valore (€)", min_value=0.0, value=12100.0, step=500.0)


# --- FUNZIONI DI ELABORAZIONE DATI ---
@st.cache_data
def processa_df_st(df_raw):
    df = df_raw.copy()
    numeri_colonne = df.iloc[0, 1::3].values
    nuove_intestazioni = ['Des Negozio']

    for numero in numeri_colonne:
        nuove_intestazioni.append(f"{numero} Somma di Total Delivered")
        nuove_intestazioni.append(f"{numero} Somma di Total Sales")
        nuove_intestazioni.append(f"{numero} Media di ST value")

    df.columns = nuove_intestazioni
    df = df.drop(index=[0, 1]).reset_index(drop=True)
    df = df.dropna(subset=["Des Negozio"])
    df = df.fillna(0)
    return df

@st.cache_data
def processa_altri_df(df_st, df_avanz, df_pallet, df_stock_raw):
    # Avanzamenti
    df_avanzamenti = df_avanz.fillna(0)
    codici_mancanti_AV = set(df_st['Des Negozio']) - set(df_avanzamenti['Des Negozio'])
    if codici_mancanti_AV:
        nuove_righe = pd.DataFrame({'Des Negozio': list(codici_mancanti_AV), 'Valore': 0})
        df_avanzamenti = pd.concat([df_avanzamenti, nuove_righe], ignore_index=True).fillna(0)

    # Prelievi / Pallet
    df_prelievi = df_pallet.fillna(0)
    cols_to_drop = ['ID_PRELIEVO'] if 'ID_PRELIEVO' in df_prelievi.columns else []
    df_prelievi['Valore Totale'] = df_prelievi.drop(columns=cols_to_drop, errors='ignore').sum(axis=1)

    # Stock Residuo
    df_stock = df_stock_raw.fillna(0)
    codici_mancanti_ST = set(df_st['Des Negozio']) - set(df_stock['Des Negozio'])
    if codici_mancanti_ST:
        nuove_righe_st = pd.DataFrame({'Des Negozio': list(codici_mancanti_ST), 'Valore': 0})
        df_stock = pd.concat([df_stock, nuove_righe_st], ignore_index=True).fillna(0)

    return df_avanzamenti, df_prelievi, df_stock


# --- MAIN LOGIC ---
if file_st and file_avanzamenti and file_pallet and file_stock:
    if I1 + I2 != 100:
        st.stop()

    with st.spinner("Caricamento ed elaborazione dati in corso..."):
        df_st_raw = pd.read_excel(file_st, header=0)
        df_st = processa_df_st(df_st_raw)

        df_avanz_raw = pd.read_excel(file_avanzamenti)
        df_pallet_raw = pd.read_excel(file_pallet)
        df_stock_raw = pd.read_excel(file_stock)

        df_avanzamenti, df_prelievi, df_stock = processa_altri_df(df_st, df_avanz_raw, df_pallet_raw, df_stock_raw)

    st.success("✅ File caricati e pre-elaborati con successo!")

    # Filtro Delivered
    delivered_cols = [c for c in df_st.columns if "Total Delivered" in c]
    df_st["Totale Delivered"] = df_st[delivered_cols].sum(axis=1)
    df_negozi_validi = df_st[df_st["Totale Delivered"] >= soglia_delivered].copy()

    negozi_dict = df_negozi_validi.set_index("Des Negozio").to_dict(orient='index')
    negozi_list = list(negozi_dict.keys())

    media_avanzamenti_lookup = df_avanzamenti.set_index("Des Negozio").to_dict(orient='index')
    stock_per_funzione = df_stock.drop(columns=['Des Negozio'], errors='ignore').sum().to_dict()
    stock_negozio_lookup = df_stock.set_index("Des Negozio").to_dict(orient='index')

    def get_punteggio_veloce(negozio, codici_funzione):
        n_data = negozi_dict[negozio]

        total_weighted_st, total_delivered = 0, 0
        for codice in codici_funzione:
            deliv = n_data.get(f"{codice} Somma di Total Delivered", 0)
            st_val = n_data.get(f"{codice} Media di ST value", 0)
            if deliv > 0:
                total_weighted_st += st_val * deliv
                total_delivered += deliv

        media_ponderata = total_weighted_st / total_delivered if total_delivered > 0 else 0

        n_avanz = media_avanzamenti_lookup.get(negozio, {})
        media_avanz = sum(n_avanz.get(c, 0) for c in codici_funzione) / len(codici_funzione) if codici_funzione else 0

        combinata = (I1 * media_ponderata + I2 * media_avanz) / 100
        stock_tot_funz = sum(stock_per_funzione.get(c, 0) for c in codici_funzione)
        n_stock_data = stock_negozio_lookup.get(negozio, {})
        stock_negozio_funz = sum(n_stock_data.get(c, 0) for c in codici_funzione)

        ps = stock_negozio_funz / stock_tot_funz if stock_tot_funz > 0 else 0
        punteggio = (max(0, combinata)**alpha) / (1 + ps**(1 - alpha))

        return punteggio, ps, combinata, media_ponderata, media_avanz

    # Button Esegui
    if st.button("🚀 Esegui Assegnazione Pallet", type="primary"):
        results = []
        conteggio_assegnazioni = {n: 0 for n in negozi_list}
        valori_caricati = {n: 0 for n in negozi_list}

        prelievi_list = df_prelievi.to_dict(orient='records')
        progress_bar = st.progress(0)

        for idx, row in enumerate(prelievi_list):
            id_prelievo = row['ID_PRELIEVO']
            valore_totale = row['Valore Totale']
            codici_funzione = [k for k, v in row.items() if k not in ['ID_PRELIEVO', 'Valore Totale'] and v > 0]

            funzioni_valide = [c for c in codici_funzione if f"{c} Somma di Total Delivered" in df_st.columns]

            if not funzioni_valide:
                results.append([id_prelievo, "Nessun negozio (FUNZIONI MANCANTI)", 0, 0, 0, 0, 0, "N/A", valore_totale])
                continue

            candidati = []
            for n in negozi_list:
                if conteggio_assegnazioni[n] < ASSEGNAZIONI and (valori_caricati[n] + valore_totale <= SOGLIA_MASSIMA):
                    n_data = negozi_dict[n]
                    if all(n_data.get(f"{c} Somma di Total Delivered", 0) >0 for c in funzioni_valide):
                        res_p = get_punteggio_veloce(n, funzioni_valide)
                        candidati.append((n, *res_p))

            if candidati:
                candidati.sort(key=lambda x: x[1].real, reverse=True)
                best = candidati[0]
                negozio_scelto = best[0]

                conteggio_assegnazioni[negozio_scelto] += 1
                valori_caricati[negozio_scelto] += valore_totale

                results.append([id_prelievo, negozio_scelto, best[1], best[2], best[3], best[4], best[5], ",".join(map(str, funzioni_valide)), valore_totale])
            else:
                results.append([id_prelievo, "Nessun negozio disponibile (Limiti raggiunti)", 0, 0, 0, 0, 0, ",".join(map(str, funzioni_valide)), valore_totale])

            progress_bar.progress((idx + 1) / len(prelievi_list))

        df_results = pd.DataFrame(results, columns=[
            "ID_PRELIEVO", "Negozio Assegnato", "Punteggio", "Percentuale Stock", 
            "Media Ponderata Combinata", "Media Ponderata", "Media Avanzamenti", 
            "Funzioni presenti", "Valore Totale"
        ])
        df_results['ID_PRELIEVO'] = df_results['ID_PRELIEVO'].apply(lambda x: str(x).split('.')[0] if '.' in str(x) else str(x))
        df_results['Punteggio'] = df_results['Punteggio'].apply(lambda x: x.real if hasattr(x, 'real') else x)

        # --- RISULTATI & METRICHE ---
        st.subheader("📊 Sintesi dell'Assegnazione")

        valore_input = df_prelievi['Valore Totale'].sum()
        valore_output = df_results[df_results['Negozio Assegnato'].isin(negozi_list)]['Valore Totale'].sum()
        perc_distribuita = (valore_output / valore_input * 100) if valore_input > 0 else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Valore Totale Originale", f"€ {valore_input:,.2f}")
        m2.metric("Valore Distribuito", f"€ {valore_output:,.2f}")
        m3.metric("% Distribuita", f"{perc_distribuita:.2f}%")
        m4.metric("Non Assegnato", f"€ {(valore_input - valore_output):,.2f}")

        # TAB
        tab1, tab2 = st.tabs(["📋 Dettaglio Assegnazioni", "🏪 Riepilogo per Negozio"])

        with tab1:
            st.dataframe(df_results, use_container_width=True)

        with tab2:
            df_riepilogo = pd.DataFrame([
                {"Des Negozio": k, "Pallet Assegnati": conteggio_assegnazioni[k], "Valore Totale (€)": v}
                for k, v in valori_caricati.items() if v > 0
            ]).sort_values(by="Valore Totale (€)", ascending=False)

            st.dataframe(df_riepilogo, use_container_width=True)

        # Download Excel
        @st.cache_data
        def convert_df_to_excel(df):
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Assegnazioni')
            return buffer.getvalue()

        excel_data = convert_df_to_excel(df_results)
        st.download_button(
            label="📥 Scarica Risultati Excel",
            data=excel_data,
            file_name="risultati_assegnazione.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("👆 Carica tutti e 4 i file Excel dalla barra laterale per iniziare.")
