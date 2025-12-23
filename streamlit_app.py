import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="ANZ Business Converter", layout="wide")
st.title("🏦 ANZ Precision Statement Converter")

def clean_money(text_list):
    """Filters out Reference IDs and cleans currency strings."""
    val = " ".join(text_list).strip()
    if not val: return 0.0
    # Remove commas and non-numeric junk
    clean = re.sub(r'[^\d.]', '', val.replace(',', ''))
    try:
        # ANZ Ref IDs are typically 6 digits with no decimals.
        # This check ignores them so they don't end up in your totals.
        if clean.isdigit() and len(clean) >= 6: return 0.0
        return float(clean) if clean else 0.0
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_data = []
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            # Group words by their vertical position (Y coordinate)
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_text = " ".join([w['text'] for w in line_words])
                
                # Match ANZ date format: e.g., '01 JUL'
                date_match = re.search(r'^(\d{1,2}\s+[A-Z]{3})', full_text)
                
                if date_match:
                    # COORDINATE GATES (Calibrated for ANZ Business Layout)
                    # Date: x < 70
                    # Details: 70 <= x < 340
                    # Withdrawals: 340 <= x < 430
                    # Deposits: 430 <= x < 510
                    # Balance: x >= 510
                    
                    row = {
                        "Date": date_match.group(1),
                        "Description": " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 340]),
                        "Withdrawals": clean_money([w['text'] for w in line_words if 340 <= w['x0'] < 430]),
                        "Deposits": clean_money([w['text'] for w in line_words if 430 <= w['x0'] < 510]),
                        "Balance": clean_money([w['text'] for w in line_words if 510 <= w['x0']])
                    }
                    if "OPENING BALANCE" not in row["Description"].upper():
                        all_data.append(row)
                
                elif all_data and len(full_text) > 3:
                    # Catch multi-line descriptions (e.g., 'FROM QUADSOL 3561')
                    extra_desc = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 340])
                    # Ensure we aren't accidentally catching footer text or page numbers
                    if extra_desc and not any(x in extra_desc for x in ["Page", "Total", "Balance"]):
                        all_data[-1]["Description"] += " " + extra_desc.strip()

    if all_data:
        df = pd.DataFrame(all_data)
        st.success(f"Successfully cleaned {len(df)} transactions.")
        st.dataframe(df, use_container_width=True) # Live preview
        
        # Download Link
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "ANZ_Clean_Data.xlsx")
    else:
        st.error("Could not find data. Ensure this is a digital ANZ PDF.")
