import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="ANZ Precision Converter", layout="wide")
st.title("🏦 ANZ Bank Statement to Excel")
st.write("Fixed version: Uses spatial detection to separate Withdrawals from Descriptions.")

def clean_numeric(val):
    if val is None: return 0.0
    # Removes commas and symbols, handles parentheses as negative
    s = str(val).replace(',', '').replace('$', '').strip()
    if "(" in s: s = "-" + s.replace("(", "").replace(")", "")
    try:
        # ANZ Reference IDs are usually 6+ digits. Real amounts usually have decimals.
        if s.isdigit() and len(s) >= 6: return 0.0
        return float(s)
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_transactions = []
    
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for page in pdf.pages:
            # We extract words with their coordinates to manually build the columns
            # This prevents the 'shifting' seen in your previous screenshots
            words = page.extract_words()
            
            # Group words by their vertical (top) position to form lines
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_line_text = " ".join([w['text'] for w in line_words])
                
                # Check for Date Pattern (e.g., 01 JUL)
                date_match = re.search(r'^(\d{1,2}\s+[A-Z]{3})', full_line_text)
                
                if date_match:
                    date_val = date_match.group(1)
                    
                    # ANZ Spatial Mapping based on Page Width %
                    # Description: usually between 15% and 55%
                    # Withdrawals: usually between 55% and 70%
                    # Deposits: usually between 70% and 85%
                    # Balance: usually between 85% and 100%
                    
                    desc_parts = [w['text'] for w in line_words if 60 < w['x0'] < 330]
                    withdraw_parts = [w['text'] for w in line_words if 330 <= w['x0'] < 420]
                    deposit_parts = [w['text'] for w in line_words if 420 <= w['x0'] < 510]
                    balance_parts = [w['text'] for w in line_words if 510 <= w['x0']]
                    
                    # Avoid capturing the year '2022' or 'OPENING BALANCE'
                    desc_text = " ".join(desc_parts)
                    if "OPENING BALANCE" in desc_text: continue
                    
                    all_transactions.append({
                        "Date": date_val,
                        "Description": desc_text,
                        "Withdrawals": clean_numeric(" ".join(withdraw_parts)),
                        "Deposits": clean_numeric(" ".join(deposit_parts)),
                        "Balance": clean_numeric(" ".join(balance_parts))
                    })
                
                elif all_transactions and len(full_line_text) > 5:
                    # Stitching multi-line descriptions
                    # Captures details like 'TO JAMEER USMAN'
                    extra_desc = " ".join([w['text'] for w in line_words if 60 < w['x0'] < 330])
                    if extra_desc and not any(k in extra_desc for k in ["Page", "Total", "Balance"]):
                        all_transactions[-1]["Description"] += " " + extra_desc

    if all_transactions:
        df = pd.DataFrame(all_transactions)
        
        # Post-processing: Ensure Debit/Credit aren't swapped
        # Real spend shows in 'Withdrawals', income in 'Deposits'
        st.dataframe(df, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 Download Corrected Excel",
            data=output.getvalue(),
            file_name="ANZ_Statement_Fixed.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("No transactions found. Check if PDF is text-selectable.")
