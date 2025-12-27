import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="ANZ Final Precision", layout="wide")
st.title("🏦 ANZ Clean Statement Converter")

# 1. ADDED: Year selector to ensure Excel dates are correct
statement_year = st.sidebar.number_input("Enter Statement Year", min_value=2000, max_value=2030, value=2024)

def clean_money(text_list):
    # Join list items (handling cases where a number is split across words)
    val = "".join(text_list).strip()
    if not val: return 0.0
    
    # Remove commas and currency symbols, keep digits and dots
    clean = re.sub(r'[^\d.]', '', val.replace(',', ''))
    
    try:
        return float(clean) if clean else 0.0
    except ValueError:
        return 0.0

uploaded_file = st.file_uploader("Upload ANZ PDF", type="pdf")

if uploaded_file:
    all_data = []
    valid_months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    with pdfplumber.open(io.BytesIO(uploaded_file.getvalue())) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            words = page.extract_words()
            
            # --- THE "TABLE ANCHOR" ---
            table_top_y = 0
            for i, w in enumerate(words):
                if "Transaction" in w['text'] and i+1 < len(words) and "Details" in words[i+1]['text']:
                    table_top_y = w['top']
                    break
            
            # Fallback if header not found on subsequent pages
            if table_top_y == 0:
                table_top_y = page.height * 0.10 if p_idx > 0 else 50 # Lowered safety margin for pages 2+

            lines = {}
            for w in words:
                if w['top'] <= table_top_y: continue 
                
                # Rounding Y helps group words on the same line even if slightly misaligned
                y = round(w['top'], 0)
                if y not in lines: lines[y] = []
                lines[y].append(w)
            
            for y in sorted(lines.keys()):
                line_words = sorted(lines[y], key=lambda x: x['x0'])
                full_text = " ".join([w['text'] for w in line_words])
                
                # Regex for "DD MMM"
                date_match = re.search(r'^(\d{1,2}\s+([A-Z]{3}))', full_text)
                
                if date_match:
                    month_part = date_match.group(2)
                    if month_part not in valid_months: continue
                    
                    # Columns mapped by exact X-coordinates (ANZ Specific)
                    desc_text = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 330])
                    
                    # Skip header noise that might slip through
                    if any(k in desc_text.upper() for k in ["OPENING BALANCE", "SUB TOTAL", "PAGE"]):
                        continue
                    
                    # Construct clean date string
                    clean_date_str = f"{date_match.group(1)} {statement_year}"

                    all_data.append({
                        "Date": clean_date_str, 
                        "Description": desc_text.strip(),
                        "Withdrawals": clean_money([w['text'] for w in line_words if 330 <= w['x0'] < 425]),
                        "Deposits": clean_money([w['text'] for w in line_words if 425 <= w['x0'] < 515]),
                        "Balance": clean_money([w['text'] for w in line_words if 515 <= w['x0']])
                    })
                
                # Handle Multi-line descriptions
                elif all_data and len(full_text) > 3:
                    # Only grab text in the Description column
                    extra_desc = " ".join([w['text'] for w in line_words if 70 <= w['x0'] < 330])
                    
                    # Safety check to avoid merging footer text
                    if extra_desc and not any(k in extra_desc for k in ["Page", "Total", "Balance"]):
                        all_data[-1]["Description"] += " " + extra_desc.strip()

    if all_data:
        df = pd.DataFrame(all_data)
        
        # Convert Date column to actual DateTime objects for Excel sorting
        df['Date'] = pd.to_datetime(df['Date'], format='%d %b %Y', errors='coerce').dt.date

        st.success(f"Successfully processed {len(df)} transactions.")
        st.dataframe(df, use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button("📥 Download Clean Excel", output.getvalue(), "ANZ_Clean_Data.xlsx")
    else:
        st.warning("No transactions found. Check if the PDF is a standard ANZ statement.")
