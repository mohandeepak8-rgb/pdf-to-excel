import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from dateutil import parser

st.set_page_config(page_title="ANZ Bank Converter", layout="centered")
st.title("🏦 ANZ PDF to Excel Converter")

def normalize_money(val):
    if not val: return 0.0
    clean = str(val).replace('$', '').replace(',', '').strip()
    if "(" in clean: clean = "-" + clean.replace("(", "").replace(")", "")
    try:
        if clean.isdigit() and len(clean) >= 6: return 0.0
        return float(clean)
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF Statement", type="pdf")

if uploaded_file:
    all_data = []
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for page in pdf.pages:
            table = page.extract_table({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_y_tolerance": 4,
            })
            if not table: continue
            for row in table:
                if not row or len(row) < 4: continue
                date_str = str(row[0]).strip()
                if re.search(r'\d{1,2}\s+[A-Z]{3}', date_str):
                    try:
                        all_data.append({
                            "Date": date_str,
                            "Description": str(row[1]).replace('\n', ' '),
                            "Withdrawals": normalize_money(row[-3]),
                            "Deposits": normalize_money(row[-2]),
                            "Balance": normalize_money(row[-1])
                        })
                    except: continue
                elif all_data and row[1]:
                    extra = str(row[1]).replace('\n', ' ').strip()
                    if extra and not any(char.isdigit() for char in extra[:2]):
                        all_data[-1]["Description"] += " " + extra

    if all_data:
        df = pd.DataFrame(all_data)
        df = df[~df['Description'].str.contains('OPENING BALANCE', case=False, na=False)]
        
        st.success(f"Found {len(df)} transactions!")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 Download Excel File",
            data=output.getvalue(),
            file_name="ANZ_Converted.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Could not find transactions. Ensure the PDF is not a scanned image.")
