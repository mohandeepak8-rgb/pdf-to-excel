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
                    # COORDINATE GATES
                    desc_text = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 340])
                    
                    # --- HEADER FILTER ---
                    # Ignore rows that contain header labels instead of real data
                    header_keywords = ["TRANSACTION DETAILS", "WITHDRAWALS", "DEPOSITS", "BALANCE", "OPENING BALANCE"]
                    if any(key in desc_text.upper() for key in header_keywords):
                        continue
                    
                    row = {
                        "Date": date_match.group(1),
                        "Description": desc_text.strip(),
                        "Withdrawals": clean_money([w['text'] for w in line_words if 340 <= w['x0'] < 430]),
                        "Deposits": clean_money([w['text'] for w in line_words if 430 <= w['x0'] < 510]),
                        "Balance": clean_money([w['text'] for w in line_words if 510 <= w['x0']])
                    }
                    all_data.append(row)
                
                elif all_data and len(full_text) > 3:
                    extra_desc = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 340])
                    # Ensure we aren't catching footer/header noise in descriptions
                    noise_keywords = ["Page", "Total", "Balance", "Continued", "Details"]
                    if extra_desc and not any(k in extra_desc for k in noise_keywords):
                        all_data[-1]["Description"] += " " + extra_desc.strip()

    if all_data:
        df = pd.DataFrame(all_data)
        st.success(f"Successfully cleaned {len(df)} transactions (Headers removed).")
        st.dataframe(df, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Clean Excel", output.getvalue(), "ANZ_Clean_Statement.xlsx")
    else:
        st.error("No valid transactions found.")
