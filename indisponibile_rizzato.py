import streamlit as st
import pandas as pd
import io

# Configurazione della pagina
st.set_page_config(
    page_title="Assegnazione Pallet",
    page_icon="📦",
    layout="wide"
)

st.title("📦 App Assegnazione e Riassegnazione Pallet")
st.markdown("Carica i file Excel **Esclusi** e **Dati** per elaborare le assegnazioni e riassegnazioni automatiche dei pallet.")

# --- Sezione Informativa Struttura File ---
with st.expander("ℹ️ **Requisiti e Struttura delle colonne per i file Excel**", expanded=False):
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.markdown("### 📄 File Esclusi (`.xlsx`)")
        st.write("Il file **Esclusi** deve contenere almeno la seguente colonna:")
        df_tpl_esclusi = pd.DataFrame({'Cod Neg': ['101', '102', '205']})
        st.dataframe(df_tpl_esclusi, use_container_width=True)
        st.caption("📌 *Colonna obbligatoria:* **`Cod Neg`**")

    with col_info2:
        st.markdown("### 📄 File Dati (`.xlsx`)")
        st.write("Il file **Dati** deve contenere **esattamente** le seguenti colonne obbligatorie:")
        df_tpl_dati = pd.DataFrame({
            'ID_PRELIEVO': ['PRL001', 'PRL001', 'PRL002'],
            'ENTE_EMIT': ['101', '103', '104'],
            'DES_ENTE': ['Deposito Nord', 'Store Milano', 'Store Roma'],
            'VAL_ORIG': [10.5, 25.0, 15.0],
            'COD_CATEGORY': ['CAT_A', 'CAT_A', 'CAT_B']
        })
        st.dataframe(df_tpl_dati, use_container_width=True)
        st.caption("📌 *Colonne obbligatorie:* **`ID_PRELIEVO`**, **`ENTE_EMIT`**, **`DES_ENTE`**, **`VAL_ORIG`**, **`COD_CATEGORY`**")

st.divider()

# --- Sidebar per Upload File ---
st.sidebar.header("📁 Caricamento File Excel")

uploaded_esclusi = st.sidebar.file_uploader("Carica File Esclusi (.xlsx)", type=["xlsx"])
uploaded_dati = st.sidebar.file_uploader("Carica File Dati (.xlsx)", type=["xlsx"])

if uploaded_esclusi is not None and uploaded_dati is not None:
    # 1. Caricamento File Esclusi
    try:
        df_esclusi = pd.read_excel(uploaded_esclusi)
        if 'Cod Neg' in df_esclusi.columns:
            codici_esclusi = df_esclusi['Cod Neg'].tolist()
            st.sidebar.success(f"✅ Codici esclusi caricati: {len(codici_esclusi)}")
        else:
            st.sidebar.error("❌ Colonna 'Cod Neg' non trovata nel file Esclusi!")
            codici_esclusi = []
    except Exception as e:
        st.error(f"Errore durante la lettura del file Esclusi: {e}")
        codici_esclusi = []

    # 2. Caricamento File Dati Principale
    try:
        df_dati = pd.read_excel(uploaded_dati, dtype={'ID_PRELIEVO': str})
        required_cols = ['ID_PRELIEVO', 'ENTE_EMIT', 'DES_ENTE', 'VAL_ORIG', 'COD_CATEGORY']
        missing_cols = [col for col in required_cols if col not in df_dati.columns]
        
        if missing_cols:
            st.error(f"❌ Errore nel File Dati: Mancano le seguenti colonne obbligatorie: **{', '.join(missing_cols)}**")
        else:
            tab1, tab2, tab3 = st.tabs(["📊 Dati Iniziali", "🔄 Logica & Assegnazione", "📥 Download Risultati"])

            with tab1:
                st.subheader("Anteprima Dati Iniziali")
                st.dataframe(df_dati.head(10), use_container_width=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Totale Righe Dati", len(df_dati))
                with col2:
                    st.metric("ID Prelievo Unici", df_dati['ID_PRELIEVO'].nunique())

            with tab2:
                st.subheader("1. Prima Assegnazione")
                
                df_grouped = df_dati.groupby(['ID_PRELIEVO', 'ENTE_EMIT', 'DES_ENTE'])['VAL_ORIG'].sum().reset_index()
                df_sorted = df_grouped.sort_values(by=['ID_PRELIEVO', 'VAL_ORIG'], ascending=[True, False])

                def trova_assegnatario(group):
                    for index, row in group.iterrows():
                        if row['ENTE_EMIT'] not in codici_esclusi:
                            return pd.Series({
                                'ENTE_ASSEGNATARIO_COD': row['ENTE_EMIT'],
                                'ENTE_ASSEGNATARIO_DES': row['DES_ENTE'],
                                'VAL_ORIG_ASSEGNATARIO': row['VAL_ORIG']
                            })
                    return pd.Series({
                        'ENTE_ASSEGNATARIO_COD': None,
                        'ENTE_ASSEGNATARIO_DES': 'Nessun Assegnatario Valido',
                        'VAL_ORIG_ASSEGNATARIO': 0
                    })

                risultati_assegnazione = df_sorted.groupby('ID_PRELIEVO').apply(trova_assegnatario).reset_index()

                st.markdown("**Risultati prima assegnazione (prime 10 righe):**")
                st.dataframe(risultati_assegnazione.head(10), use_container_width=True)

                # Riassegnazione
                risultati_assegnazione_reassigned = risultati_assegnazione.copy()
                unassigned_pallets_initial = risultati_assegnazione_reassigned[risultati_assegnazione_reassigned['ENTE_ASSEGNATARIO_COD'].isnull()]

                st.subheader("2. Riassegnazione Pallet Non Assegnati")
                st.info(f"Pallet inizialmente non assegnati: **{len(unassigned_pallets_initial)}**")

                if not unassigned_pallets_initial.empty:
                    pallet_details_per_category = df_dati.groupby(['ID_PRELIEVO', 'COD_CATEGORY'])['VAL_ORIG'].sum().reset_index().rename(columns={'VAL_ORIG': 'Pallet_Category_Value'})

                    unassigned_pallet_data = pd.merge(
                        unassigned_pallets_initial[['ID_PRELIEVO']],
                        pallet_details_per_category,
                        on='ID_PRELIEVO',
                        how='left'
                    )

                    total_ceded_cat = df_dati.groupby(['ENTE_EMIT', 'COD_CATEGORY'])['VAL_ORIG'].sum().reset_index().rename(columns={'VAL_ORIG': 'Ceded_Category_Value'})

                    assigned_pallets = risultati_assegnazione_reassigned[risultati_assegnazione_reassigned['ENTE_ASSEGNATARIO_COD'].notnull()]
                    assigned_pallets_with_cat = pd.merge(
                        assigned_pallets[['ID_PRELIEVO', 'ENTE_ASSEGNATARIO_COD']],
                        pallet_details_per_category,
                        on='ID_PRELIEVO',
                        how='left'
                    )

                    total_received_cat = assigned_pallets_with_cat.groupby(['ENTE_ASSEGNATARIO_COD', 'COD_CATEGORY'])['Pallet_Category_Value'].sum().reset_index().rename(columns={'Pallet_Category_Value': 'Received_Category_Value', 'ENTE_ASSEGNATARIO_COD': 'ENTE_EMIT'})

                    store_cat_balance = pd.merge(total_ceded_cat, total_received_cat, on=['ENTE_EMIT', 'COD_CATEGORY'], how='outer').fillna(0)
                    store_cat_balance['Balance_Category'] = store_cat_balance['Ceded_Category_Value'] - store_cat_balance['Received_Category_Value']
                    store_cat_balance = store_cat_balance[~store_cat_balance['ENTE_EMIT'].isin(codici_esclusi)]

                    st.markdown("**Bilancio per Ente e Categoria (prime 10 righe):**")
                    st.dataframe(store_cat_balance.head(10), use_container_width=True)

                    reassigned_records = []
                    for index, pallet_row in unassigned_pallet_data.iterrows():
                        pallet_id = pallet_row['ID_PRELIEVO']
                        pallet_category = pallet_row['COD_CATEGORY']
                        pallet_value = pallet_row['Pallet_Category_Value']

                        candidate_stores = store_cat_balance[
                            (store_cat_balance['COD_CATEGORY'] == pallet_category) &
                            (store_cat_balance['Balance_Category'] >= pallet_value)
                        ].sort_values(by='Balance_Category', ascending=False)

                        if not candidate_stores.empty:
                            chosen_assignee = candidate_stores.iloc[0]
                            chosen_ente_cod = chosen_assignee['ENTE_EMIT']
                            chosen_ente_des = df_dati[df_dati['ENTE_EMIT'] == chosen_ente_cod]['DES_ENTE'].iloc[0]

                            reassigned_records.append({
                                'ID_PRELIEVO': pallet_id,
                                'ENTE_ASSEGNATARIO_COD': chosen_ente_cod,
                                'ENTE_ASSEGNATARIO_DES': chosen_ente_des,
                                'VAL_ORIG_ASSEGNATARIO': pallet_value
                            })

                            store_cat_balance.loc[
                                (store_cat_balance['ENTE_EMIT'] == chosen_ente_cod) &
                                (store_cat_balance['COD_CATEGORY'] == pallet_category),
                                'Balance_Category'
                            ] -= pallet_value

                    if reassigned_records:
                        df_reassigned = pd.DataFrame(reassigned_records)
                        st.success(f"🎉 Riassegnati con successo **{len(df_reassigned)}** pallet!")
                        st.dataframe(df_reassigned, use_container_width=True)

                        for idx, row in df_reassigned.iterrows():
                            pallet_id = row['ID_PRELIEVO']
                            risultati_assegnazione_reassigned.loc[
                                risultati_assegnazione_reassigned['ID_PRELIEVO'] == pallet_id,
                                ['ENTE_ASSEGNATARIO_COD', 'ENTE_ASSEGNATARIO_DES', 'VAL_ORIG_ASSEGNATARIO']
                            ] = [row['ENTE_ASSEGNATARIO_COD'], row['ENTE_ASSEGNATARIO_DES'], row['VAL_ORIG_ASSEGNATARIO']]
                    else:
                        st.warning("Nessun pallet è stato riassegnato con la logica del bilancio.")

                st.metric("Pallet ancora non assegnati alla fine", risultati_assegnazione_reassigned['ENTE_ASSEGNATARIO_COD'].isnull().sum())

            with tab3:
                st.subheader("📥 Download File Finale")
                
                df_download = risultati_assegnazione_reassigned.rename(columns={
                    'ENTE_ASSEGNATARIO_COD': 'ENTE ass',
                    'ENTE_ASSEGNATARIO_DES': 'Desc ente ass'
                })[['ID_PRELIEVO', 'ENTE ass', 'Desc ente ass']]

                df_download['ID_PRELIEVO'] = df_download['ID_PRELIEVO'].astype(str)

                st.dataframe(df_download.head(15), use_container_width=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_download.to_excel(writer, index=False, sheet_name='Assegnazione_Finale')
                buffer.seek(0)

                st.download_button(
                    label="📥 Scarica risultati_assegnazione_finale.xlsx",
                    data=buffer,
                    file_name="risultati_assegnazione_finale.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"Errore durante l'elaborazione del file dati: {e}")
else:
    st.info("👈 Per iniziare, carica entrambi i file Excel (.xlsx) dalla barra laterale di sinistra.")
