import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="ANZ Precision Converter", layout="wide")
st.title("🏦 ANZ Bank Statement to Excel")

def clean_money(val):
    if not val: return 0.0
    # Removes everything except digits and dots
    s = re.sub(r'[^\d.]', '', str(val).replace(',', ''))
    try:
        # ANZ Ref IDs are long integers (e.g., 860211). 
        # Money almost always has a decimal or is smaller.
        if s.isdigit() and len(s) >= 5: return 0.0
        return float(s) if s else 0.0
    except: return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_rows = []
    
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for page in pdf.pages:
            # We extract every word with its exact X/Y position
            words = page.extract_words()
            
            # Group words into lines based on their vertical 'top' position
            lines = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                # Sort words in each line from left to right
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                line_text = " ".join([w['text'] for w in line_words])
                
                # Check for the ANZ Date Pattern (e.g., 01 JUL)
                date_match = re.search(r'^(\d{1,2}\s+[A-Z]{3})', line_text)
                
                if date_match:
                    date_val = date_match.group(1)
                    
                    # --- ANZ SPATIAL BOUNDARIES (Manual Gates) ---
                    # Description: Text between x=65 and x=350
                    # Withdrawals: Text between x=350 and x=435
                    # Deposits:    Text between x=435 and x=515
                    # Balance:     Text between x=515 and end
                    
                    desc = " ".join([w['text'] for w in line_words if 65 <= w['x0'] < 350])
                    withdraw = " ".join([w['text'] for w in line_words if 350 <= w['x0'] < 435])
                    deposit = " ".join([w['text'] for w in line_words if 435 <= w['x0'] < 515])
                    balance = " ".join([w['text'] for w in line_words if 515 <= w['x0']])
                    
                    if "OPENING BALANCE" in desc.upper(): continue
                    
                    all_rows.append({
                        "Date": date_val,
                        "Description": desc.strip(),
                        "Withdrawals": clean_money(withdraw),
                        "Deposits": clean_money(deposit),
                        "Balance": clean_money(balance)
                    })
                
                elif all_rows and len(line_text) > 5:
                    # Capture multi-line description continuation
                    # (Text in the same horizontal 'Description' gate but no new date)
                    extra_desc = " ".join([w['text'] for w in line_words if 65 <= w['x0'] < 350])
                    if extra_desc and not any(k in extra_desc for k in ["Page", "Total", "Balance"]):
                        all_rows[-1]["Description"] += " " + extra_desc.strip()

    if all_rows:
        df = pd.DataFrame(all_rows)
        st.success(f"Processed {len(df)} transactions.")
        st.dataframe(df) # Preview in browser
        
        # Excel Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 Download Corrected Excel",
            data=output.getvalue(),
            file_name="ANZ_Fixed_Statement.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("No transactions found. Make sure the PDF is text-selectable.")
