import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="GO Reconciliation App", layout="wide")
st.title("📊 GO Reconciliation - 4-Way Summary Split")

def load_data(file):
    ext = file.name.split('.')[-1]
    if ext == 'csv':
        return pd.read_csv(file, low_memory=False)
    elif ext in ['xls', 'xlsx']:
        return pd.read_excel(file)
    else:
        st.error("Unsupported file type.")
        return None

st.sidebar.header("📄 Upload Files")
atlantis_file = st.sidebar.file_uploader("Upload Atlantis File", type=["csv", "xls", "xlsx"])
gmi_file = st.sidebar.file_uploader("Upload GMI File", type=["csv", "xls", "xlsx"])

if atlantis_file and gmi_file:
    df1 = load_data(atlantis_file)
    df2 = load_data(gmi_file)
    df1.columns = df1.columns.str.strip()
    df2.columns = df2.columns.str.strip()

    df1 = df1[df1['RecordType'] == 'TR']
    df2 = df2[df2['TGIVIO'] == 'GO']

    df1 = df1.rename(columns={
        'ExchangeEBCode': 'CB',
        'TradeDate': 'Date',
        'Quantity': 'Qty',
        'GiveUpAmt': 'Fee',
        'ClearingAccount': 'Account'
    })

    df2 = df2.rename(columns={
        'TGIVF#': 'CB',
        'TEDATE': 'Date',
        'TQTY': 'Qty',
        'TFEE5': 'Fee',
        'ACCT': 'Account'
    })

    df1['Date'] = pd.to_datetime(df1['Date'].astype(str), format='%Y%m%d', errors='coerce')
    df2['Date'] = pd.to_datetime(df2['Date'].astype(str), format='%Y%m%d', errors='coerce')

    df1['Qty'] = pd.to_numeric(df1['Qty'], errors='coerce')
    df1['Fee'] = pd.to_numeric(df1['Fee'], errors='coerce')
    df2['Qty'] = pd.to_numeric(df2['Qty'], errors='coerce')
    df2['Fee'] = pd.to_numeric(df2['Fee'], errors='coerce')

    summary1 = df1.groupby(['CB', 'Date', 'Account'], dropna=False)[['Qty', 'Fee']].sum().reset_index()
    summary2 = df2.groupby(['CB', 'Date', 'Account'], dropna=False)[['Qty', 'Fee']].sum().reset_index()

    summary1['CB'] = summary1['CB'].astype(str).str.strip()
    summary2['CB'] = summary2['CB'].astype(str).str.strip()

    summary1 = summary1.rename(columns={'Qty': 'Qty_Atlantis', 'Fee': 'Fee_Atlantis'})
    summary2 = summary2.rename(columns={'Qty': 'Qty_GMI', 'Fee': 'Fee_GMI'})

    merged = pd.merge(summary1, summary2, on=['CB', 'Date', 'Account'], how='outer')

    for col in ['Qty_Atlantis', 'Fee_Atlantis', 'Qty_GMI', 'Fee_GMI']:
        merged[col] = merged[col].fillna(0)

    merged['Qty_Diff'] = (merged['Qty_Atlantis'] - merged['Qty_GMI']).round(2)
    merged['Fee_Diff'] = (merged['Fee_Atlantis'] + merged['Fee_GMI']).round(2)

    matched = merged[(merged['Qty_Diff'] == 0) & (merged['Fee_Diff'] == 0)]
    qty_match_only = merged[(merged['Qty_Diff'] == 0) & (merged['Fee_Diff'] != 0)]
    fee_match_only = merged[(merged['Qty_Diff'] != 0) & (merged['Fee_Diff'] == 0)]
    no_match = merged[(merged['Qty_Diff'] != 0) & (merged['Fee_Diff'] != 0)]

    st.success("✅ Reconciliation Completed!")

    st.header("✅ Full Matches (Qty + Fee)")
    st.dataframe(matched)

    st.header("🔍 Qty Match Only (Fee mismatch)")
    st.dataframe(qty_match_only)

    st.header("🔍 Fee Match Only (Qty mismatch)")
    st.dataframe(fee_match_only)

    st.header("⚠️ No Match (Qty + Fee mismatch)")
    st.dataframe(no_match)