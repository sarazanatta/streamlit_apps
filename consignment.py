import streamlit as st
import pandas as pd
import io

# Configurazione della pagina
st.set_page_config(
    page_title="Assegnazione Pallet Avanzata",
    page_icon="📦",
    layout="wide"
)

st.title("📦 App Assegnazione Pallet ai Negozi")
st.markdown("Carica i file Excel **Negozi (Avanzamenti)** e **Pallet** per elaborare l'assegnazione automatica in base alla compatibilità e affinità.")

# --- Sezione Informativa Struttura e Template File ---
with st.expander("ℹ️ **Requisiti e Template Struttura File Excel (Doppia Intestazione)**", expanded=False):
    st.write("Entrambi i file **devono avere 2 righe di intestazione (Header su Righe 1 e 2)** per definire le categorie composte (es. `31_40`).")
    
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.markdown("### 📄 Template File Negozi (`avanzamenti.xlsx`)")
        # Ricostruzione visiva dell'header multilivello
        header_n = pd.MultiIndex.from_tuples([
            ("EnteBox", ""),
            ("31", "40"),
            ("31", "50"),
            ("32", "10")
        ])
        df_tpl_n = pd.DataFrame([
            ["NEG_01", 10, 5, 20],
            ["NEG_02", 0, 15, 10]
        ], columns=header_n)
        
        st.dataframe(df_tpl_n, use_container_width=True)
        st.caption("📌 *Prima riga header:* Deve contenere **`EnteBox`** per l'identificativo del negozio.")

    with col_info2:
        st.markdown("### 📄 Template File Pallet (`pallet.xlsx`)")
        header_p = pd.MultiIndex.from_tuples([
            ("ID_PRELIEVO", ""),
            ("31", "40"),
            ("31", "50"),
            ("32", "10")
        ])
        df_tpl_p = pd.DataFrame([
            ["PRL_1001", 5, 5, 10],
            ["PRL_1002", 2, 0, 5]
        ], columns=header_p)
        
        st.dataframe(df_tpl_p, use_container_width=True)
        st.caption("📌 *Prima riga header:* Deve contenere **`ID_PRELIEVO`** per l'identificativo del pallet.")

st.divider()

# --- Funzione Principale di Elaborazione ---
def assegna_pallet_finale(file_negozi, file_pallet):
    # 1. Caricamento: leggiamo le prime due righe come intestazione
    df_n = pd.read_excel(file_negozi, header=[0, 1])
    df_p = pd.read_excel(file_pallet, header=[0, 1])

    # Funzione per pulire e unire le intestazioni (31 + 40 -> 31_40)
    def prepara_colonne(df, nome_id):
        nuove_cols = []
        for col in df.columns:
            l0, l1 = str(col[0]).strip(), str(col[1]).strip()
            # Cerca la colonna identificativa (EnteBox o ID_PRELIEVO)
            if nome_id.lower() in l0.lower() or nome_id.lower() in l1.lower():
                nuove_cols.append(nome_id)
            elif "Unnamed" in l0 or l0 == "nan":
                nuove_cols.append(l1)
            else:
                nuove_cols.append(f"{l0}_{l1}")
        df.columns = me_cols = nuove_cols
        return df

    df_n = prepara_colonne(df_n, 'EnteBox')
    df_p = prepara_colonne(df_p, 'ID_PRELIEVO')

    # Identificazione colonne di confronto comuni
    cols_confronto = [c for c in df_n.columns if c in df_p.columns and c not in ['EnteBox', 'ID_PRELIEVO']]

    if not cols_confronto:
        st.error("❌ Nessuna colonna di confronto compatibile trovata tra i due file. Verificare le intestazioni.")
        return pd.DataFrame()

    # Riempie le celle vuote con 0 per evitare errori nei calcoli
    df_n[cols_confronto] = df_n[cols_confronto].fillna(0)
    df_p[cols_confronto] = df_p[cols_confronto].fillna(0)

    # Ordinamento: processiamo prima i pallet con volume totale più alto
    df_p['peso_tot'] = df_p[cols_confronto].sum(axis=1)
    df_p = df_p.sort_values(by='peso_tot', ascending=False)

    negozi_liberi = df_n.copy()
    risultati = []

    for _, pallet in df_p.iterrows():
        if negozi_liberi.empty:
            break

        # Inizializziamo la maschera con tutti True
        mask = pd.Series([True] * len(negozi_liberi), index=negozi_liberi.index)

        # Affiniamo la maschera colonna per colonna
        for c in cols_confronto:
            mask = mask & (negozi_liberi[c] >= pallet[c])

        # Applichiamo il filtro
        negozi_validi = negozi_liberi[mask]

        if not negozi_validi.empty:
            # Calcolo affinità proporzionale
            punteggi = (negozi_validi[cols_confronto] * pallet[cols_confronto].values).sum(axis=1)

            idx_scelto = punteggi.idxmax()
            negozio_scelto = negozi_validi.loc[idx_scelto]

            risultati.append({
                'ID_PRELIEVO': str(pallet['ID_PRELIEVO']),
                'EnteBox': negozio_scelto['EnteBox']
            })

            # Rimuoviamo il negozio usato
            negozi_liberi = negozi_liberi.drop(idx_scelto)
        else:
            risultati.append({
                'ID_PRELIEVO': str(pallet['ID_PRELIEVO']),
                'EnteBox': 'NESSUN NEGOZIO COMPATIBILE'
            })

    df_res = pd.DataFrame(risultati)
    
    # Pulizia ID_PRELIEVO
    if not df_res.empty and 'ID_PRELIEVO' in df_res.columns:
        df_res['ID_PRELIEVO'] = df_res['ID_PRELIEVO'].apply(lambda x: str(x).split('.')[0] if '.' in str(x) else str(x))

    return df_res


# --- Sidebar Caricamento File ---
st.sidebar.header("📁 Caricamento File Excel")

uploaded_negozi = st.sidebar.file_uploader("Carica File Negozi/Avanzamenti (.xlsx)", type=["xlsx"])
uploaded_pallet = st.sidebar.file_uploader("Carica File Pallet (.xlsx)", type=["xlsx"])

if uploaded_negozi is not None and uploaded_pallet is not None:
    try:
        with st.spinner("Elaborazione e assegnazione pallet in corso..."):
            df_risultato = assegna_pallet_finale(uploaded_negozi, uploaded_pallet)

        if not df_risultato.empty:
            tab1, tab2 = st.tabs(["📊 Risultati Assegnazione", "📥 Download File"])

            with tab1:
                st.subheader("Esito dell'Assegnazione")
                
                # Metriche riassuntive
                tot_pallet = len(df_risultato)
                assegnati = len(df_risultato[df_risultato['EnteBox'] != 'NESSUN NEGOZIO COMPATIBILE'])
                non_assegnati = tot_pallet - assegnati

                col1, col2, col3 = st.columns(3)
                col1.metric("Totale Pallet Processati", tot_pallet)
                col2.metric("Pallet Assegnati", assegnati)
                col3.metric("Pallet Non Assegnati", non_assegnati, delta_color="inverse")

                st.markdown("**Tabella Risultati:**")
                st.dataframe(df_risultato, use_container_width=True)

            with tab3 if 'tab3' in locals() else tab2:
                st.subheader("Scarica il File finale")
                st.write("Puoi scaricare il file Excel generato pronto per l'uso.")

                # Generazione file Excel in memoria per il download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_risultato.to_excel(writer, index=False, sheet_name='Assegnazione')
                buffer.seek(0)

                st.download_button(
                    label="📥 Scarica assegnazione_finalissima.xlsx",
                    data=buffer,
                    file_name="assegnazione_finalissima.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"❌ Si è verificato un errore durante l'elaborazione del file: {e}")
else:
    st.info("👈 Carica entrambi i file Excel dalla barra laterale per avviare l'elaborazione.")
