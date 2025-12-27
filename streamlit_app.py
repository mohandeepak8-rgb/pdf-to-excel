import streamlit as st
import pdfplumber
import pandas as pd
import altair as alt
from PyPDF2 import PdfReader
from pdfminer.pdfparser import PDFSyntaxError
import io
import gspread
import os
from dotenv import load_dotenv
import re
from google.oauth2.service_account import Credentials
import streamlit as st

# Use credentials from Streamlit secrets
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"]
)
load_dotenv()  # Load environment variables from .env

CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_PATH")

# ----------------------------- HELPER FUNCTIONS -----------------------------

def is_pdf_encrypted(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        return reader.is_encrypted
    except Exception:
        return False

def extract_text_from_pdf(uploaded_file, password=None):
    try:
        if password:
            with pdfplumber.open(uploaded_file, password=password) as pdf:
                return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
        else:
            with pdfplumber.open(uploaded_file) as pdf:
                return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
    except PDFSyntaxError:
        st.error("Unable to read the PDF. It might be corrupted or improperly decrypted.")
        return None
    except Exception as e:
        st.error(f"PDF error: {e}")
        return None

def parse_transactions(text):
    lines = text.splitlines()
    data = []

    for line in lines:
        line = line.strip()
        st.write(f"LINE: '{line}'")  # Debug output

        # Match format like:
        # 24-Mar-2025 S86158462 FIP:PCM/... 23-Mar-2025 0.00 5,000.00 641,932.52
        match = re.match(
            r"(\d{2}-[A-Za-z]{3}-\d{4})\s+(\S+)\s+(.*?)\s+(\d{2}-[A-Za-z]{3}-\d{4})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
            line
        )

        if match:
            try:
                date = match.group(1)
                ref = match.group(2)
                details = match.group(3).strip()
                value_date = match.group(4)
                withdrawal = match.group(5)
                deposit = match.group(6)
                balance = match.group(7)

                # Parse amounts
                withdrawal_val = float(withdrawal.replace(",", ""))
                deposit_val = float(deposit.replace(",", ""))
                balance_val = float(balance.replace(",", ""))

                # Calculate net amount
                amount = deposit_val - withdrawal_val
                description = f"{ref}, {details}, {value_date}"

                data.append({
                    "Date": date,
                    "Description": description,
                    "Amount": amount,
                    "Balance": balance_val
                })
            except ValueError:
                continue

    return pd.DataFrame(data)

def categorize_transaction(description):
    desc = description.lower()
    if "supermarket" in desc or "grocery" in desc:
        return "Groceries"
    elif "salary" in desc or "income" in desc:
        return "Income"
    elif "restaurant" in desc or "eat" in desc:
        return "Dining"
    elif "transfer" in desc:
        return "Transfers"
    else:
        return "Uncategorized"

# ----------------------------- STREAMLIT APP -----------------------------

st.title("📄 Bank Statement Analyzer")

uploaded_file = st.file_uploader("Upload Bank Statement (PDF)", type=["pdf"])

if uploaded_file:
    uploaded_file.seek(0)
    if is_pdf_encrypted(uploaded_file):
        password = st.text_input("🔐 Enter PDF password", type="password")
    else:
        password = None

    if st.button("🔍 Extract Transactions"):
        uploaded_file.seek(0)
        text = extract_text_from_pdf(uploaded_file, password)
        if text:
            st.text_area("📄 Extracted PDF Text", text[:5000], height=300)  # Preview first 5000 characters
            df = parse_transactions(text)
        if text:
            df = parse_transactions(text)

            if not df.empty:
                df["Category"] = df["Description"].apply(categorize_transaction)
                st.session_state.df = df
                st.success(f"{len(df)} transactions extracted.")
            else:
                st.warning("No transactions found.")

# ----------------------------- DISPLAY AND EXPORT -----------------------------

if 'df' in st.session_state and not st.session_state.df.empty:
    df = st.session_state.df

    # Filter
    category_filter = st.selectbox("📂 Filter by Category", ["All"] + sorted(df["Category"].unique()))
    if category_filter != "All":
        df = df[df["Category"] == category_filter]

    st.dataframe(df)

    # Chart
    chart = alt.Chart(df).mark_bar().encode(
        x='Category',
        y='sum(Amount)',
        color='Category'
    ).properties(title="Total Spending by Category")
    st.altair_chart(chart, use_container_width=True)

    # Export CSV
    filename = st.text_input("💾 Enter filename for CSV export (without extension)", value="transactions")
    if st.button("Export CSV Locally"):
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"{filename}.csv",
            mime='text/csv'
        )

# ----------------------------- GOOGLE SHEETS UPLOAD -----------------------------

with st.expander("☁️ Upload to Google Sheets"):
    sheet_name = st.text_input("Google Sheet Name", value="Bank Transactions")
    if st.button("Upload to Google Sheets"):
        if 'df' in st.session_state and not st.session_state.df.empty:
            df = st.session_state.df
            try:
                credentials = Credentials.from_service_account_file(CLIENT_SECRET_FILE)
                client = gspread.authorize(credentials)

                sheet = client.open(sheet_name).sheet1
                sheet.clear()
                sheet.update([df.columns.values.tolist()] + df.values.tolist())
                st.success("Uploaded to Google Sheets!")
            except Exception as e:
                st.error(f"Upload failed: {e}")
        else:
            st.warning("⚠️ No data available to upload. Please extract transactions first.")
