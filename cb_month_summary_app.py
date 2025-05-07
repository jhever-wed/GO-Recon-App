import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="GI Reconciliation App", layout="wide")
st.title("📊 GI Reconciliation - 4-Way Summary Split")

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

    if df1 is not None and df2 is not None:
        df1.columns = df1.columns.str.strip()
        df2.columns = df2.columns.str.strip()

        df1 = df1[df1['RecordType'] == 'TP']

        df1 = df1.rename(columns={
            'ExchangeEBCode': 'CB',
            'TradeDate': 'Date',
            'Quantity': 'Qty',
            'GiveUpAmt': 'Fee',
            'ClearingAccount': 'Account'
        })

        
        # Normalize GMI column names to lowercase and strip spaces
        df2.columns = df2.columns.str.strip().str.lower()
        col_map = {col: orig for col, orig in zip(df2.columns, df2.columns)}

        if 'acct' in col_map:
            acct_col = col_map['acct']
            df2 = df2.rename(columns={
                col_map.get('tgivf#', 'tgivf#'): 'CB',
                col_map.get('tedate', 'tedate'): 'Date',
                col_map.get('tqty', 'tqty'): 'Qty',
                col_map.get('tfee5', 'tfee5'): 'Fee',
                acct_col: 'Account'
            })
        else:
            st.error("❌ GMI file is missing an 'Acct' column (case-insensitive, trimmed). Cannot continue.")
            st.stop()
    
        if 'Acct' in df2.columns:
            df2 = df2.rename(columns={
                'TGIVF#': 'CB',
                'TEDATE': 'Date',
                'TQTY': 'Qty',
                'TFEE5': 'Fee',
                'Acct': 'Account'
            })
        elif 'Account' in df2.columns:
            df2 = df2.rename(columns={
                'TGIVF#': 'CB',
                'TEDATE': 'Date',
                'TQTY': 'Qty',
                'TFEE5': 'Fee'
            })
            df2['Account'] = df2['Account']
        else:
            st.error("❌ GMI file is missing 'Acct' or 'Account' column. Cannot continue.")
            st.stop()

        df1['Date'] = pd.to_datetime(df1['Date'].astype(str), format='%Y%m%d', errors='coerce')
        df2['Date'] = pd.to_datetime(df2['Date'].astype(str), format='%Y%m%d', errors='coerce')

        df1['Qty'] = pd.to_numeric(df1['Qty'], errors='coerce')
        df1['Fee'] = pd.to_numeric(df1['Fee'], errors='coerce')
        df2['Qty'] = pd.to_numeric(df2['Qty'], errors='coerce')
        df2['Fee'] = pd.to_numeric(df2['Fee'], errors='coerce')

        required_df1_cols = ['CB', 'Date', 'Qty', 'Fee', 'Account']
        required_df2_cols = ['CB', 'Date', 'Qty', 'Fee', 'Account']
        missing1 = [col for col in required_df1_cols if col not in df1.columns]
        missing2 = [col for col in required_df2_cols if col not in df2.columns]

        if missing1:
            st.error(f"❌ Missing columns in Atlantis file: {missing1}")
        elif missing2:
            st.error(f"❌ Missing columns in GMI file: {missing2}")
        else:
            summary1 = df1.groupby(['CB', 'Date', 'Account'], dropna=False)[['Qty', 'Fee']].sum().reset_index()
            summary2 = df2.groupby(['CB', 'Date', 'Account'], dropna=False)[['Qty', 'Fee']].sum().reset_index()

            summary1['CB'] = summary1['CB'].astype(str).str.strip()
            summary2['CB'] = summary2['CB'].astype(str).str.strip()

            summary1 = summary1.rename(columns={'Qty': 'Qty_Atlantis', 'Fee': 'Fee_Atlantis'})
            summary2 = summary2.rename(columns={'Qty': 'Qty_GMI', 'Fee': 'Fee_GMI'})

            merged = pd.merge(summary1, summary2, on=['CB', 'Date', 'Account'], how='outer')

            for col in ['Qty_Atlantis', 'Fee_Atlantis', 'Qty_GMI', 'Fee_GMI']:
                merged[col] = merged[col].fillna(0)

            merged['Qty_Diff'] = merged['Qty_Atlantis'] - merged['Qty_GMI']
            merged['Fee_Diff'] = merged['Fee_Atlantis'] + merged['Fee_GMI']

            matched = merged[(merged['Qty_Diff'].round(2) == 0) & (merged['Fee_Diff'].round(2) == 0)]
            qty_match_only = merged[(merged['Qty_Diff'].round(2) == 0) & (merged['Fee_Diff'].round(2) != 0)]
            fee_match_only = merged[(merged['Qty_Diff'].round(2) != 0) & (merged['Fee_Diff'].round(2) == 0)]
            no_match = merged[(merged['Qty_Diff'].round(2) != 0) & (merged['Fee_Diff'].round(2) != 0)]

            st.success("✅ Reconciliation Completed!")

            st.header("✅ Full Matches (Qty + Fee)")
            st.dataframe(matched)

            st.header("🔍 Qty Match Only (Fee mismatch)")
            st.dataframe(qty_match_only)

            st.header("🔍 Fee Match Only (Qty mismatch)")
            st.dataframe(fee_match_only)

            st.header("⚠️ No Match (Qty + Fee mismatch)")
            st.dataframe(no_match)

            st.markdown("---")
            
            # ----- Rate Comparison -----
            rate_avg = df1.groupby(['CB', 'Date', 'Account'], dropna=False)['GiveUpRate'].mean().reset_index().rename(columns={'GiveUpRate': 'Rate_Atlantis'})
            rate_comparison = merged.merge(rate_avg, on=['CB', 'Date', 'Account'], how='left', suffixes=('', '_AtlantisMean'))
            rate_comparison['Rate_Atlantis'] = rate_comparison['Rate_Atlantis'].fillna(0)
            rate_comparison['Rate_GMI'] = rate_comparison.apply(lambda row: (row['Fee_GMI'] / row['Qty_GMI']) if row['Qty_GMI'] != 0 else 0, axis=1)
            rate_comparison['Rate_Diff'] = rate_comparison['Rate_Atlantis'] + rate_comparison['Rate_GMI']
            st.header("📈 Rate Comparison by Account")
            st.dataframe(rate_comparison[['CB', 'Date', 'Account', 'Rate_Atlantis', 'Rate_GMI', 'Rate_Diff']])


    
            st.subheader("📥 Export All Sections to Excel")

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                matched.to_excel(writer, sheet_name="Matched", index=False)
                qty_match_only.to_excel(writer, sheet_name="Qty_Match_Only", index=False)
                fee_match_only.to_excel(writer, sheet_name="Fee_Match_Only", index=False)
                no_match.to_excel(writer, sheet_name="No_Match", index=False)
                rate_comparison[['CB', 'Date', 'Account', 'Rate_Atlantis', 'Rate_GMI', 'Rate_Diff']].to_excel(writer, sheet_name="Rate_Comparison", index=False)
            buffer.seek(0)

            st.download_button(
                label="📥 Download Excel File (All 5 Sections)",
                data=buffer,
                file_name="reconciliation_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                matched.to_excel(writer, sheet_name="Matched", index=False)
                qty_match_only.to_excel(writer, sheet_name="Qty_Match_Only", index=False)
                fee_match_only.to_excel(writer, sheet_name="Fee_Match_Only", index=False)
                no_match.to_excel(writer, sheet_name="No_Match", index=False)

                rate_comparison[['CB', 'Date', 'Account', 'Rate_Atlantis', 'Rate_GMI', 'Rate_Diff']].to_excel(writer, sheet_name="Rate_Comparison", index=False)

            buffer.seek(0)

            st.download_button(
                label="📥 Download Excel File (All 4 Sections)",
                data=buffer,
                file_name="reconciliation_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )