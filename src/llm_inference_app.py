# Import necessary libraries
import streamlit as st
import json
from pathlib import Path
from match import find_attachment, find_transaction, llm_chatbot, used_attachment_ids, used_transaction_ids

# Paths to default sample data
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_TRANSACTIONS_FILE = DATA_DIR / "transactions.json"
DEFAULT_ATTACHMENTS_FILE = DATA_DIR / "attachments.json"

# --------------------
# Streamlit Page Setup
# --------------------
st.set_page_config(page_title="Bank Transaction Reconciliation Assistant", layout="wide")
st.title("Bank Transaction Reconciliation Assistant")

# Upload files
uploaded_transactions = st.file_uploader("Upload transactions.json", type=["json"])
uploaded_attachments = st.file_uploader("Upload attachments.json", type=["json"])

def load_json(file, default_path):
    """
    Load JSON data from an uploaded file or fallback to a default file path.
    Args:
        file: Uploaded Streamlit file object or None
        default_path: Path to default JSON file
    Returns:
        Loaded list of dictionaries from JSON
    """
    if file is not None:
        return json.load(file)
    with open(default_path, "r", encoding="utf-8") as f:
        return json.load(f)

# Load transaction and attachment data
transactions_list = load_json(uploaded_transactions, DEFAULT_TRANSACTIONS_FILE)
attachments_list = load_json(uploaded_attachments, DEFAULT_ATTACHMENTS_FILE)

# Data Preview Section
st.subheader("Data Preview (First 5 rows)")
# Button to toggle preview
if st.button("Show Data Preview"):
    st.write("Transactions:", transactions_list[:5])
    st.write("Attachments:", attachments_list[:5])

# Initialize session state for storing matching results across Streamlit reruns
if "matched_pairs" not in st.session_state:
    st.session_state.matched_pairs = []
if "unmatched_tx" not in st.session_state:
    st.session_state.unmatched_tx = []
if "unmatched_att" not in st.session_state:
    st.session_state.unmatched_att = []

# Run matching section
if st.button("Run Matching"):
    # Clear previously used IDs to allow fresh matching
    used_attachment_ids.clear()
    used_transaction_ids.clear()

    matched_pairs = []
    unmatched_tx = []
    unmatched_att = attachments_list.copy()

    # Match transactions with attachments
    for tx in transactions_list:
        att = find_attachment(tx, unmatched_att)
        if att:
            matched_pairs.append((tx, att))
            unmatched_att.remove(att)
        else:
            unmatched_tx.append(tx)

    # Save results in session state for display and LLM use
    st.session_state.matched_pairs = matched_pairs
    st.session_state.unmatched_tx = unmatched_tx
    st.session_state.unmatched_att = unmatched_att

# ------------------------
# Display Matching Results
# ------------------------
if st.session_state.matched_pairs:
    st.subheader("🔗 Matched Transactions & Attachments")

    # Display matches using cards
    for tx, att in st.session_state.matched_pairs:
        with st.container():
            st.markdown(
                f"""
                <div style="
                    padding: 12px;
                    border-radius: 10px;
                    border: 1px solid #e0e0e0;
                    margin-bottom: 10px;
                    background-color: #f7faff;
                ">
                    <b>Transaction ID:</b> {tx['id']}  
                    <br>
                    <b>↕ Matched With</b>  
                    <br>
                    <b>Attachment ID:</b> {att['id']}
                </div>
                """,
                unsafe_allow_html=True
            )

    # Display unmatched transactions
    st.subheader("📄 Unmatched Transactions")

    if len(st.session_state.unmatched_tx) == 0:
        st.success("All transactions were matched! 🎉")
    else:
        for tx in st.session_state.unmatched_tx:
            st.markdown(
                f"""
                <div style="
                    padding: 10px;
                    border-radius: 10px;
                    border: 1px solid #ffe0e0;
                    background-color: #fff5f5;
                    margin-bottom: 8px;
                ">
                    <b>Transaction ID:</b> {tx['id']}
                </div>
                """,
                unsafe_allow_html=True
            )

    # Display unmatched attachments
    st.subheader("📄 Unmatched Attachments")

    if len(st.session_state.unmatched_att) == 0:
        st.success("All attachments were matched! 🎉")
    else:
        for att in st.session_state.unmatched_att:
            st.markdown(
                f"""
                <div style="
                    padding: 10px;
                    border-radius: 10px;
                    border: 1px solid #fff3cd;
                    background-color: #fffbea;
                    margin-bottom: 8px;
                ">
                    <b>Attachment ID:</b> {att['id']}
                </div>
                """,
                unsafe_allow_html=True
            )

# ---------------
# LLM Q&A Section
# ---------------
question = st.text_input("Ask a question about these matches:")

if st.button("Get Answer") and question.strip():
    if not st.session_state.matched_pairs:
        st.warning("Run matching first before asking a question.")
    else:
        # Query the LLM with the matched/unmatched data and user question
        answer = llm_chatbot(
            st.session_state.matched_pairs,
            st.session_state.unmatched_tx,
            st.session_state.unmatched_att,
            question
        )

        # Display LLM answer in a card
        st.markdown(
            f"""
            <div style="
                background-color: #eef6ff;
                border-left: 5px solid #7AB2D3;
                padding: 15px;
                border-radius: 8px;
                margin-top: 15px;
                font-size: 15px;
                line-height: 1.6;
                box-shadow: 0px 0px 8px rgba(0,0,0,0.3);
            ">
                <b>🤖 LLM Answer:</b><br><br>
                {answer}
            </div>
            """,
            unsafe_allow_html=True
        )

