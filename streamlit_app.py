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
        # Ignore Ref IDs (usually 6 digits, no decimals)
        if clean.isdigit() and len(clean) >= 6: return 0.0
        return float(clean) if clean else 0.0
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_data = []
    valid_months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            words = page.extract_words()
            
            # --- THE "TABLE ANCHOR" ---
            # We find the exact vertical position of the words 'Transaction Details'
            # We will ignore everything above this line.
            table_top_y = 0
            for i, w in enumerate(words):
                if "Transaction" in w['text'] and i+1 < len(words) and "Details" in words[i+1]['text']:
                    table_top_y = w['top']
                    break
            
            # If we didn't find the header on this page, skip the top 40% as a safety
            if table_top_y == 0:
                table_top_y = page.height * 0.40 if p_idx == 0 else 50

            lines = {}
            for w in words:
                # 1. PHYSICAL BLOCK: Ignore text above the 'Transaction Details' anchor
                if w['top'] <= table_top_y: continue 
                
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_text = " ".join([w['text'] for w in line_words])
                
                # 2. PATTERN BLOCK: Must be a valid date
                date_match = re.search(r'^(\d{1,2}\s+([A-Z]{3}))', full_text)
                
                if date_match:
                    month_part = date_match.group(2)
                    if month_part not in valid_months: continue
                    
                    # Columns mapped by exact X-coordinates
                    desc_text = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 330])
                    
                    # 3. NOISE BLOCK: Filter leftover headings
                    if any(k in desc_text.upper() for k in ["OPENING BALANCE", "SUB TOTAL", "PAGE"]):
                        continue
                    
                    all_data.append({
                        "Date": date_match.group(1),
                        "Description": desc_text.strip(),
                        "Withdrawals": clean_money([w['text'] for w in line_words if 330 <= w['x0'] < 425]),
                        "Deposits": clean_money([w['text'] for w in line_words if 425 <= w['x0'] < 515]),
                        "Balance": clean_money([w['text'] for w in line_words if 515 <= w['x0']])
                    })
                
                elif all_data and len(full_text) > 3:
                    # Multi-line stitching for long descriptions
                    extra_desc = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 330])
                    if extra_desc and not any(k in extra_desc for k in ["Page", "Total", "Balance"]):
                        all_data[-1]["Description"] += " " + extra_desc.strip()

    if all_data:
        df = pd.DataFrame(all_data)
        st.success(f"Successfully filtered out all headers. {len(df)} transactions ready.")
        st.dataframe(df, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Clean Excel", output.getvalue(), "ANZ_Clean_Data.xlsx")
