import streamlit as st
import pandas as pd
from io import BytesIO

# Configurazione della pagina
st.set_page_config(page_title="Concatenatore Excel", page_icon="📑")

# --- INTRODUZIONE E DESCRIZIONE ---
st.title("📑 Concatenatore di File Excel")

st.markdown("""
### Benvenuto!
Questo strumento ti permette di unire rapidamente molteplici file Excel in un unico documento finale. 

**Come funziona:**
1. **Seleziona o trascina** tutti i file Excel che desideri unire.
2. Il sistema leggerà ogni file e aggiungerà una colonna chiamata **'Sorgente'** per permetterti di rintracciare l'origine di ogni riga.
3. Una volta completata l'unione, potrai scaricare il file totale cliccando sul pulsante dedicato.

*Nota: Assicurati che i file abbiano le stesse colonne per un risultato ottimale.*
---
""")

# --- LOGICA DI CARICAMENTO ---
# accept_multiple_files=True permette di selezionare più file contemporaneamente
uploaded_files = st.file_uploader(
    "Carica i tuoi file Excel qui", 
    type=["xlsx"], 
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"File caricati: {len(uploaded_files)}")
    
    lista_fogli = []

    # Processiamo i file caricati
    with st.spinner('Lettura e unione dei file in corso...'):
        for f in uploaded_files:
            # Leggiamo il file Excel
            # f.name contiene il nome del file originale
            df = pd.read_excel(f)
            
            # Aggiungiamo la colonna sorgente
            df['Sorgente'] = f.name
            
            lista_fogli.append(df)

        # 3. Concatena tutti i dati
        if lista_fogli:
            df_finale = pd.concat(lista_fogli, ignore_index=True)
            
            st.success("Unione completata con successo!")
            
            # Mostriamo un'anteprima del risultato
            st.write("Anteprima del file unito (prime 5 righe):")
            st.dataframe(df_finale.head())

            # --- PREPARAZIONE DEL DOWNLOAD ---
            # Usiamo un buffer per creare il file Excel in memoria
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_finale.to_excel(writer, index=False, sheet_name='Unione_Totale')
            
            # Bottone per il download
            st.download_button(
                label="⬇️ Scarica il file totale unito (.xlsx)",
                data=output.getvalue(),
                file_name='file_totale_unito.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
else:
    st.warning("In attesa del caricamento dei file per procedere.")
