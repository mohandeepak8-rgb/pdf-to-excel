import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="ANZ Precision Converter", layout="wide")
st.title("🏦 ANZ Bank Statement Converter")

def clean_money(text_list):
    val = "".join(text_list).strip()
    if not val: return 0.0
    clean = re.sub(r'[^\d.]', '', val.replace(',', ''))
    try:
        if clean.isdigit() and len(clean) >= 6: return 0.0
        return float(clean) if clean else 0.0
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_data = []
    valid_months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for page in pdf.pages:
            # Get the page height to calculate the 30% cutoff
            page_height = page.height
            top_cutoff = page_height * 0.30 
            
            words = page.extract_words()
            lines = {}
            for w in words:
                # 1. BLOCK THE ADDRESS BAR: Ignore any text in the top 30% of the page
                if w['top'] < top_cutoff: continue
                
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_text = " ".join([w['text'] for w in line_words])
                
                # 2. STRICT DATE CHECK: Must be a valid month
                date_match = re.search(r'^(\d{1,2}\s+([A-Z]{3}))', full_text)
                
                if date_match:
                    month_part = date_match.group(2)
                    if month_part not in valid_months: continue
                    
                    desc_text = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 340])
                    
                    # 3. IGNORE HEADERS AND OPENING BALANCE
                    if any(k in desc_text.upper() for k in ["TRANSACTION DETAILS", "OPENING BALANCE"]):
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
                    if extra_desc and not any(k in extra_desc for k in ["Page", "Total", "Balance"]):
                        all_data[-1]["Description"] += " " + extra_desc.strip()

    if all_data:
        df = pd.DataFrame(all_data)
        st.success("Successfully filtered out address and headers.")
        st.dataframe(df, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "ANZ_Clean_Data.xlsx")
