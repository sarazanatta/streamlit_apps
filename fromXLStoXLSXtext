import io
import pandas as pd
import streamlit as st

st.title("Convertitore Excel in Testo")
st.write(
    "Carica un file Excel per convertire automaticamente tutte le colonne in"
    " formato testo."
)

# 1. Componente per il caricamento del file
uploaded_file = st.file_uploader(
    "Scegli un file Excel (.xls o .xlsx)", type=["xls", "xlsx"]
)

if uploaded_file is not None:
  try:
    # Legge il file caricato direttamente dal buffer in memoria
    df = pd.read_excel(uploaded_file)

    # Converti tutte le colonne in stringa (testo)
    for col in df.columns:
      df[col] = df[col].astype(str)

    st.success("Conversione completata!")

    # Mostra un'anteprima dei dati
    st.subheader("Anteprima dei dati:")
    st.dataframe(df.head())

    # 2. Salva il DataFrame in un buffer in memoria per consentire il download
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
      df.to_excel(writer, index=False)
    processed_data = output.getvalue()

    # Nome suggerito per il file scaricato
    original_filename = uploaded_file.name.rsplit(".", 1)[0]
    output_filename = f"{original_filename}_testo.xlsx"

    # 3. Bottone per scaricare il file convertito
    st.download_button(
      label="📥 Scarica file XLSX",
      data=processed_data,
      file_name=output_filename,
      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

  except Exception as e:
    st.error(f"Si è verificato un errore durante l'elaborazione del file: {e}")
