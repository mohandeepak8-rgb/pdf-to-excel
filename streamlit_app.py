import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="ANZ Precision Converter", layout="wide")
st.title("🏦 ANZ Bank Statement Converter")
st.write("v2.0: Header Filtering & Strict Date Validation")

def clean_money(text_list):
    """Filters out Reference IDs and cleans currency strings."""
    val = "".join(text_list).strip()
    if not val: return 0.0
    # Remove commas and non-numeric junk
    clean = re.sub(r'[^\d.]', '', val.replace(',', ''))
    try:
        # ANZ Ref IDs are typically 6 digits with no decimals.
        if clean.isdigit() and len(clean) >= 6: return 0.0
        return float(clean) if clean else 0.0
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_data = []
    # Strict month list to avoid matching address lines like '88 ROSEDALE'
    valid_months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            
            # --- STEP 1: FIND THE TABLE HEADER ---
            # We look for the Y-coordinate of "Transaction Details" to skip the header info
            y_header = 0
            for w in words:
                if "Transaction" in w['text'] and "Details" in [x['text'] for x in words if abs(x['top'] - w['top']) < 2]:
                    y_header = w['top']
                    break
            
            # Group words by their vertical position (Y coordinate)
            lines = {}
            for w in words:
                # Only process text BELOW the header
                if w['top'] <= y_header: continue
                
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_text = " ".join([w['text'] for w in line_words])
                
                # --- STEP 2: STRICT DATE MATCHING ---
                # Pattern: 1-2 digits + space + 3-letter month (e.g. 01 JUL)
                date_match = re.search(r'^(\d{1,2}\s+([A-Z]{3}))', full_text)
                
                if date_match:
                    day_part = date_match.group(1)
                    month_part = date_match.group(2)
                    
                    # Only proceed if the 3-letter month is a REAL month
                    if month_part not in valid_months:
                        continue
                    
                    # COORDINATE GATES (Fine-tuned for ANZ Business Layout)
                    desc_text = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 340])
                    
                    # Skip the 'Opening Balance' row itself
                    if "OPENING BALANCE" in desc_text.upper():
                        continue
                    
                    row = {
                        "Date": day_part,
                        "Description": desc_text.strip(),
                        "Withdrawals": clean_money([w['text'] for w in line_words if 340 <= w['x0'] < 430]),
                        "Deposits": clean_money([w['text'] for w in line_words if 430 <= w['x0'] < 510]),
                        "Balance": clean_money([w['text'] for w in line_words if 510 <= w['x0']])
                    }
                    all_data.append(row)
                
                elif all_data and len(full_text) > 3:
                    # Catch multi-line descriptions (stitching)
                    extra_desc = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 340])
                    # Stop stitching if we hit footer text
                    if extra_desc and not any(k in extra_desc for k in ["Page", "Total", "Balance"]):
                        all_data[-1]["Description"] += " " + extra_desc.strip()

    if all_data:
        df = pd.DataFrame(all_data)
        st.success(f"Processed {len(df)} transactions. Header and address info ignored.")
        st.dataframe(df, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "ANZ_Clean_Data.xlsx")
    else:
        st.error("No transactions found below the header.")
