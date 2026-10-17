
import re
from io import BytesIO

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="CleanMyCSV",
    page_icon="🧹",
    layout="wide",
)

st.title("🧹 CleanMyCSV")
st.write("Upload, clean, validate, analyze, and download your data.")

# ---------- Helper functions ----------

def standardize_column(name):
    name = str(name).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "column"


def unique_column_names(columns):
    result = []
    counts = {}

    for column in columns:
        base = standardize_column(column)
        counts[base] = counts.get(base, 0) + 1

        if counts[base] == 1:
            result.append(base)
        else:
            result.append(f"{base}_{counts[base]}")

    return result


def read_file(file):
    if file.name.lower().endswith(".csv"):
        try:
            return pd.read_csv(file)
        except UnicodeDecodeError:
            file.seek(0)
            return pd.read_csv(file, encoding="latin-1")

    return pd.read_excel(file)


def excel_download(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="CleanedData")

    return output.getvalue()


def get_quality_report(df):
    report = pd.DataFrame({
        "Column": df.columns,
        "Data Type": [str(df[c].dtype) for c in df.columns],
        "Missing Values": [int(df[c].isna().sum()) for c in df.columns],
        "Missing Percent": [
            round(float(df[c].isna().mean() * 100), 2)
            for c in df.columns
        ],
        "Unique Values": [int(df[c].nunique()) for c in df.columns],
    })

    return report


# ---------- Upload ----------

uploaded_file = st.file_uploader(
    "Upload your CSV or Excel file",
    type=["csv", "xlsx", "xls"],
)

if uploaded_file is None:
    st.info("Upload a file to start cleaning.")
    st.stop()

try:
    original = read_file(uploaded_file)
except Exception as error:
    st.error(f"Unable to read file: {error}")
    st.stop()

if original.empty:
    st.warning("Your file contains no data rows.")
    st.stop()

original = original.copy()

st.subheader("1. Original data")

a, b, c = st.columns(3)
a.metric("Rows", len(original))
b.metric("Columns", len(original.columns))
c.metric("Duplicate rows", int(original.duplicated().sum()))

st.dataframe(original.head(100), use_container_width=True)

# ---------- Cleaning options ----------

st.subheader("2. Choose cleaning options")

col1, col2 = st.columns(2)

with col1:
    clean_names = st.checkbox(
        "Standardize column names",
        value=True,
    )

    trim_spaces = st.checkbox(
        "Trim extra spaces from text",
        value=True,
    )

    blank_to_missing = st.checkbox(
        "Treat blank text as missing",
        value=True,
    )

    text_case = st.selectbox(
        "Standardize text case",
        ["Keep unchanged", "lowercase", "UPPERCASE", "Title Case"],
    )

with col2:
    remove_duplicates = st.checkbox(
        "Remove duplicate rows",
        value=True,
    )

    missing_method = st.selectbox(
        "Handle missing values",
        [
            "Leave unchanged",
            "Drop rows with missing values",
            "Fill with custom value",
            "Fill numeric values with mean",
            "Fill numeric values with median",
            "Fill with mode",
        ],
    )

    custom_value = st.text_input(
        "Custom missing-value replacement",
        value="Unknown",
        disabled=missing_method != "Fill with custom value",
    )

    convert_numbers = st.checkbox(
        "Convert numeric-looking text columns",
        value=True,
    )

    convert_dates = st.checkbox(
        "Convert columns named like dates",
        value=True,
    )

st.caption(
    "Mean and median are suitable for numeric columns. "
    "Review the results before using cleaned data."
)

# ---------- Run cleaning ----------

if st.button("🧹 Clean data", type="primary"):
    df = original.copy()
    actions = []

    # Standardize names
    if clean_names:
        old_names = list(df.columns)
        df.columns = unique_column_names(df.columns)

        if old_names != list(df.columns):
            actions.append("Standardized column names.")

    # Trim text
    if trim_spaces:
        for col in df.select_dtypes(include=["object", "string"]).columns:
            df[col] = df[col].map(
                lambda value: value.strip()
                if isinstance(value, str)
                else value
            )

        actions.append("Trimmed extra spaces.")

    # Convert blank strings into missing values
    if blank_to_missing:
        for col in df.select_dtypes(include=["object", "string"]).columns:
            df[col] = df[col].replace(r"^\s*$", pd.NA, regex=True)

        actions.append("Converted blank text to missing values.")

    # Standardize text case
    if text_case != "Keep unchanged":
        for col in df.select_dtypes(include=["object", "string"]).columns:
            values = df[col].astype("string")

            if text_case == "lowercase":
                df[col] = values.str.lower()
            elif text_case == "UPPERCASE":
                df[col] = values.str.upper()
            else:
                df[col] = values.str.title()

        actions.append(f"Applied {text_case} to text columns.")

    # Convert numeric-looking columns
    if convert_numbers:
        converted = []

        for col in df.select_dtypes(include=["object", "string"]).columns:
            non_missing = df[col].dropna()

            if non_missing.empty:
                continue

            cleaned = non_missing.astype(str).str.replace(
                r"[$₹€£,\s]", "", regex=True
            )

            numeric = pd.to_numeric(cleaned, errors="coerce")

            if numeric.notna().mean() >= 0.85:
                df[col] = pd.to_numeric(
                    df[col].astype("string").str.replace(
                        r"[$₹€£,\s]", "", regex=True
                    ),
                    errors="coerce",
                )
                converted.append(col)

        actions.append(
            "Numeric columns converted: "
            + (", ".join(converted) if converted else "none")
        )

    # Convert date-like columns
    if convert_dates:
        converted_dates = []

        for col in df.columns:
            if any(word in col.lower() for word in
                   ["date", "time", "created", "updated"]):
                parsed = pd.to_datetime(
                    df[col], errors="coerce", dayfirst=True
                )

                original_nonmissing = int(df[col].notna().sum())

                if (
                    original_nonmissing > 0
                    and parsed.notna().sum() / original_nonmissing >= 0.6
                ):
                    df[col] = parsed
                    converted_dates.append(col)

        actions.append(
            "Date columns converted: "
            + (", ".join(converted_dates) if converted_dates else "none")
        )

    # Remove exact duplicate rows
    if remove_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        actions.append(f"Removed {before - len(df)} duplicate rows.")

    # Handle missing values
    if missing_method == "Drop rows with missing values":
        before = len(df)
        df = df.dropna()
        actions.append(f"Removed {before - len(df)} rows with missing values.")

    elif missing_method == "Fill with custom value":
        df = df.fillna(custom_value)
        actions.append("Filled missing cells with the custom value.")

    elif missing_method in [
        "Fill numeric values with mean",
        "Fill numeric values with median",
    ]:
        for col in df.select_dtypes(include="number").columns:
            if df[col].notna().any():
                if missing_method.endswith("mean"):
                    df[col] = df[col].fillna(df[col].mean())
                else:
                    df[col] = df[col].fillna(df[col].median())

        actions.append("Filled missing numeric values.")

    elif missing_method == "Fill with mode":
        for col in df.columns:
            modes = df[col].mode(dropna=True)

            if not modes.empty:
                df[col] = df[col].fillna(modes.iloc[0])

        actions.append("Filled missing cells using each column's mode.")

    else:
        actions.append("Left missing values unchanged.")

    # Save results across Streamlit reruns
    st.session_state["original_df"] = original
    st.session_state["cleaned_df"] = df
    st.session_state["cleaning_actions"] = actions

# ---------- Display results ----------

if "cleaned_df" in st.session_state:
    original = st.session_state["original_df"]
    cleaned = st.session_state["cleaned_df"]
    actions = st.session_state["cleaning_actions"]

    st.subheader("3. Cleaning results")

    a, b, c, d = st.columns(4)
    a.metric("Original rows", len(original))
    b.metric("Cleaned rows", len(cleaned))
    c.metric("Remaining missing cells", int(cleaned.isna().sum().sum()))
    d.metric("Remaining duplicate rows", int(cleaned.duplicated().sum()))

    with st.expander("Cleaning activity report", expanded=True):
        for action in actions:
            st.write("✅ " + action)

    tab1, tab2, tab3 = st.tabs([
        "Cleaned Data",
        "Data Quality",
        "Outlier Detection",
    ])

    with tab1:
        st.dataframe(cleaned, use_container_width=True)

    with tab2:
        report = get_quality_report(cleaned)
        st.dataframe(report, use_container_width=True)

        st.bar_chart(
            report.set_index("Column")["Missing Values"]
        )

        if cleaned.isna().sum().sum() == 0:
            st.success("No missing values remain.")
        else:
            st.warning("Some missing values remain. Review the report.")

    with tab3:
        numeric_columns = list(
            cleaned.select_dtypes(include="number").columns
        )

        if not numeric_columns:
            st.info("No numeric columns found.")
        else:
            selected_column = st.selectbox(
                "Choose a numeric column",
                numeric_columns,
            )

            values = cleaned[selected_column].dropna()

            if len(values) < 4:
                st.info("At least four values are needed.")
            else:
                q1 = values.quantile(0.25)
                q3 = values.quantile(0.75)
                iqr = q3 - q1

                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr

                outliers = cleaned[
                    (cleaned[selected_column] < lower)
                    | (cleaned[selected_column] > upper)
                ]

                st.write(f"Lower boundary: {lower:.2f}")
                st.write(f"Upper boundary: {upper:.2f}")
                st.metric("Potential outliers", len(outliers))
                st.caption(
                    "Outliers are flagged, not deleted automatically. "
                    "Investigate them before deciding what to do."
                )
                st.dataframe(outliers, use_container_width=True)

    # ---------- Downloads ----------

    st.subheader("4. Download your results")

    left, middle, right = st.columns(3)

    with left:
        st.download_button(
            "Download cleaned CSV",
            data=cleaned.to_csv(index=False).encode("utf-8-sig"),
            file_name="cleanmycsv_cleaned.csv",
            mime="text/csv",
        )

    with middle:
        st.download_button(
            "Download cleaned Excel",
            data=excel_download(cleaned),
            file_name="cleanmycsv_cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with right:
        report = get_quality_report(cleaned)

        st.download_button(
            "Download quality report",
            data=report.to_csv(index=False).encode("utf-8-sig"),
            file_name="cleanmycsv_quality_report.csv",
            mime="text/csv",
        )

st.divider()
st.caption(
    "CleanMyCSV: Always keep a backup of the original data. "
    "Review the cleaned output before using it for decisions."
)
