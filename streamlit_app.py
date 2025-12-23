import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="ANZ Final Precision", layout="wide")
st.title("🏦 ANZ Clean Statement Converter")

def clean_money(text_list):
    val = "".join(text_list).strip()
    if not val: return 0.0
    clean = re.sub(r'[^\d.]', '', val.replace(',', ''))
    try:
        # Ignore Reference IDs (usually 6+ digits with no decimals)
        if clean.isdigit() and len(clean) >= 6: return 0.0
        return float(clean) if clean else 0.0
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_data = []
    # Valid Australian Months only
    valid_months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            words = page.extract_words()
            
            # --- COORDINATE GUARD ---
            # On Page 1, the table usually starts around Y=400.
            # We ignore everything above this to skip the address and summary.
            y_cutoff = 380 if p_idx == 0 else 100 
            
            lines = {}
            for w in words:
                if w['top'] < y_cutoff: continue  # Skip the 'garbage' at the top
                
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_text = " ".join([w['text'] for w in line_words])
                
                # Strict Date Match: '01 JUL'
                date_match = re.search(r'^(\d{1,2}\s+([A-Z]{3}))', full_text)
                
                if date_match:
                    month_part = date_match.group(2)
                    if month_part not in valid_months: continue
                    
                    # Columns are mapped by fixed X-coordinates (Page Width)
                    desc_text = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 330])
                    
                    # Skip noise rows
                    if any(k in desc_text.upper() for k in ["TRANSACTION DETAILS", "OPENING BALANCE", "SUB TOTAL"]):
                        continue
                    
                    all_data.append({
                        "Date": date_match.group(1),
                        "Description": desc_text.strip(),
                        "Withdrawals": clean_money([w['text'] for w in line_words if 330 <= w['x0'] < 425]),
                        "Deposits": clean_money([w['text'] for w in line_words if 425 <= w['x0'] < 515]),
                        "Balance": clean_money([w['text'] for w in line_words if 515 <= w['x0']])
                    })
                
                elif all_data and len(full_text) > 3:
                    # Multi-line stitching for descriptions
                    extra_desc = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 330])
                    if extra_desc and not any(k in extra_desc for k in ["Page", "Total", "Balance", "Continued"]):
                        all_data[-1]["Description"] += " " + extra_desc.strip()

    if all_data:
        df = pd.DataFrame(all_data)
        st.success(f"Extracted {len(df)} transactions. Address/Headers ignored.")
        st.dataframe(df, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Final Excel", output.getvalue(), "ANZ_Clean_Data.xlsx")
