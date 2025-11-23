# Import necessary libraries
from datetime import datetime
from typing import Optional, List, Dict, Any
from openai import OpenAI
import json

# Initialize local LLM client (Llama 3.2)
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# Type aliases for readability: Attachment and Transaction are dictionaries with arbitrary data
Attachment = Dict[str, Any]
Transaction = Dict[str, Any]

# Track used attachments and transactions to avoid duplicate matches
used_attachment_ids: set[int] = set()
used_transaction_ids: set[int] = set()

# -----------------------------------------------------
# Utility Helper Functions to identify relevant matches 
# -----------------------------------------------------
def normalize_reference(reference: Optional[str]) -> Optional[str]:
    """
    Normalize a reference string by removing spaces, 'RF' prefix, and leading zeros.
    Returns None if the input is None or empty.
    """
    if not reference:
        return None
    return "".join(reference.replace(" ", "").replace("RF", "").lstrip("0"))

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Convert a date string in 'YYYY-MM-DD' format to a datetime object.
    Returns None if the input is None or empty.
    """
    if not date_str:
        return None
    return datetime.strptime(date_str, "%Y-%m-%d")

def similar_name(transaction_contact: Optional[str], attachment_party: Optional[str]) -> bool:
    """
    Check if the transaction contact name is similar to the attachment counterparty name.
    Matching logic: returns True if either string is a substring of the other, it is case-insensitive.
    Returns False if either input is None.
    """
    if not transaction_contact or not attachment_party:
        return False

    transaction_contact = transaction_contact.lower()
    attachment_party = attachment_party.lower()

    return transaction_contact in attachment_party or attachment_party in transaction_contact

def get_counterparty(attachment: Attachment) -> Optional[str]:
    """
    Extract the counterparty name from an attachment.
    Checks for issuer, recipient, or supplier fields in order.
    It returns the value of the first key that exist.
    Returns None if none exist.
    """
    data = attachment.get("data", {})
    return (
        data.get("issuer")
        or data.get("recipient")
        or data.get("supplier")
    )

def get_attachment_amount(attachment: Attachment) -> Optional[float]:
    """
    Retrieve the total amount from an attachment, which could either be an invoice (to be paid) or a receipt (already paid).
    Returns None if the amount is missing.
    """
    return attachment.get("data", {}).get("total_amount")

# -----------------------------------------------------------------
# Heuristic scoring of how well a transaction matches an attachment 
# -----------------------------------------------------------------
def compute_match_score(transaction: Transaction, attachment: Attachment) -> int:
    """
    Compute a heuristic match score between a transaction and an attachment.
    Scoring criteria:
        - Amount match (+3 points): The transaction amount is the same as the attachment amount.
        - Counterparty name match (+2 points): The transaction’s contact name matches the attachment’s counterparty (issuer/recipient/supplier).
        - Date proximity (+1 point): The transaction date is within 7 days of the attachment’s invoice or due date.
    Returns the total score as an integer.
    """
    score = 0
    attachment_data = attachment["data"]

    # Match the amount; if it matches, add 3 points to the score
    transaction_amount = abs(transaction["amount"])
    attachment_amount = attachment_data.get("total_amount")
    if attachment_amount and abs(transaction_amount - attachment_amount) < 1e-6:
        score += 3

    # Match counterparty names; if similar, add 2 points to the score
    transaction_contact = transaction.get("contact")
    attachment_counterparty = get_counterparty(attachment)
    if similar_name(transaction_contact, attachment_counterparty):
        score += 2

    # Match transaction and attachment dates; if within 7 days, add 1 point
    transaction_date = parse_date(transaction.get("date"))
    due_date = parse_date(attachment_data.get("due_date"))
    invoicing_date = parse_date(attachment_data.get("invoicing_date"))
    # Collect available reference dates from the attachment (due date and invoicing date)
    candidate_dates = [d for d in [due_date, invoicing_date] if d]

    # If transaction date exists, find the closest attachment date
    if transaction_date and candidate_dates:
        min_days_diff = min(abs((transaction_date - d).days) for d in candidate_dates)
        if min_days_diff <= 7:
            score += 1

    return score

# --------------------------------------------------------------
# Programs Main Functions to Find Matched Attachment/Transaction 
# --------------------------------------------------------------
def find_attachment(
    transaction: Transaction,
    attachments: List[Attachment],
) -> Optional[Attachment]:
    """
    Find the best matching attachment for a given transaction.
    Steps:
    1. Try perfect reference number match.
    2. If no perfect reference number match, compute heuristic scores and select the best.
    3. Skip attachments already matched to other transactions with the help of used attachment and transaction ids.
    4. Only return an attachment if score >= 4 in total.
    Returns the matched attachment or None if no confident match exists.
    """
    transaction_ref = normalize_reference(transaction.get("reference"))

    # 1. Perfect reference number match
    if transaction_ref:
        for attachment in attachments:
            # Skip attachments that have already been matched
            if attachment["id"] in used_attachment_ids:
                continue
            attachment_ref = normalize_reference(attachment.get("data", {}).get("reference"))
            if attachment_ref and attachment_ref == transaction_ref:
                # Mark this attachment as used to prevent duplicate matching
                used_attachment_ids.add(attachment["id"])
                return attachment

    # 2. Heuristic score-based match
    best_attachment = None
    highest_score = 0
    for attachment in attachments:
        # Skip attachments that have already been matched
        if attachment["id"] in used_attachment_ids:
            continue
        score = compute_match_score(transaction, attachment)
        if score > highest_score:
            highest_score = score
            best_attachment = attachment

    if best_attachment and highest_score >= 4:
        # Mark the best-scoring attachment as used to prevent duplicate matching
        used_attachment_ids.add(best_attachment["id"])
        return best_attachment
         
    return None

def find_transaction(
    attachment: Attachment,
    transactions: List[Transaction],
) -> Optional[Transaction]:
    """
    Find the best matching transaction for a given attachment.
    Steps:
    1. Try perfect reference number match.
    2. If no perfect match, compute heuristic scores and select the best.
    3. Skip transactions already matched to other attachments.
    4. Only return a transaction if score >= 4.
    Returns the matched transaction or None if no confident match exists.
    """
    attachment_ref = normalize_reference(attachment.get("data", {}).get("reference"))

    # 1. Perfect reference number match
    if attachment_ref:
        for transaction in transactions:
            # Skip transactions that have already been matched
            if transaction["id"] in used_transaction_ids:
                continue
            transaction_ref = normalize_reference(transaction.get("reference"))
            if transaction_ref and transaction_ref == attachment_ref:
                # Mark this transaction as used to prevent duplicate matching
                used_transaction_ids.add(transaction["id"])
                return transaction

    # 2. Heuristic score-based match
    best_transaction = None
    highest_score = 0
    for transaction in transactions:
        # Skip transactions that have already been matched
        if transaction["id"] in used_transaction_ids:
            continue
        score = compute_match_score(transaction, attachment)
        if score > highest_score:
            highest_score = score
            best_transaction = transaction

    if best_transaction and highest_score >= 4:
        # Mark the best-scoring transaction as used to prevent duplicate matching
        used_transaction_ids.add(best_transaction["id"])
        return best_transaction
   
    return None

# -----------------------
# LLM-based Data Analysis
# -----------------------
def run_matching(transactions: List[Transaction], attachments: List[Attachment]):
    """
    Perform matching between transactions and attachments,
    display results, and optionally allow the user to ask questions
    to a local LLM (Llama 3.2) about the results.
    Steps:
    1. Match all transactions using heuristic + reference logic.
    2. Print matched and unmatched results.
    3. Enter an interactive loop where the user can query the LLM.
    """
    matched_pairs = []
    unmatched_transactions = []
    # Start assuming all are unmatched
    unmatched_attachments = attachments.copy()  

    # 1. Match transactions to attachments
    for tx in transactions:
        att = find_attachment(tx, unmatched_attachments)
        if att:
            matched_pairs.append((tx, att))
            unmatched_attachments.remove(att)
        else:
            unmatched_transactions.append(tx)

    # 2. Display results to streamlit user for transparency
    print("=== Matched Transactions ===")
    for tx, att in matched_pairs:
        print(f"Transaction {tx['id']} ↔ Attachment {att['id']}")
    print("\n=== Unmatched Transactions ===")
    for tx in unmatched_transactions:
        print(f"Transaction {tx['id']}")
    print("\n=== Unmatched Attachments ===")
    for att in unmatched_attachments:
        print(f"Attachment {att['id']}")

    # 3. Keep asking questions until user wants to quit
    while True:
        ask = input("\nDo you want to ask questions about these matches/unmatched items? (yes/no): ").strip().lower()
        if ask != "yes":
            print("Exiting LLM interactive mode.")
            break
        user_question = input("Enter your question (or type 'exit' to quit): ").strip()
        if user_question.lower() == "exit":
            print("Exiting LLM interactive mode.")
            break
        # Send the question and the structured data to the LLM
        answer = llm_chatbot(matched_pairs, unmatched_transactions, unmatched_attachments, user_question)
        print("\nLLM Answer:\n", answer)

def llm_chatbot(matched, unmatched_tx, unmatched_att, question: str) -> str:
    """
    Ask the local LLM (Llama 3.2 via Ollama) a question about
    matched and unmatched transactions/attachments.
    The model is intentionally given *simplified* and *structured*
    data to minimize hallucinations.
    Parameters:
        matched (list): List of (transaction, attachment) tuples.
        unmatched_tx (list): List of unmatched transactions.
        unmatched_att (list): List of unmatched attachments.
        question (str): User's question.
    Returns:
        str: LLM's answer strictly based on provided data.
    """
    # Format simplified input so the LLM cannot hallucinate fields
    simplified_data = {
        "matched": [
            {"transaction_id": tx["id"], "attachment_id": att["id"], "amount": tx["amount"], "contact": tx.get("contact")} 
            for tx, att in matched
        ],
        "unmatched_transactions": [
            {"id": tx["id"], "amount": tx["amount"], "contact": tx.get("contact")} 
            for tx in unmatched_tx
        ],
        "unmatched_attachments": [
            {
                "id": att["id"], 
                "type": att.get("type"), 
                "amount": att["data"].get("total_amount"),
                "reference": att["data"].get("reference"),
                "counterparty": att["data"].get("issuer") or att["data"].get("recipient") or att["data"].get("supplier")
            } 
            for att in unmatched_att
        ],
        "question": question
    }

    # DEBUG llm context
    # import streamlit as st
    # st.write(simplified_data)

    # Construct a safe prompt with constraints:
    # - System message: do NOT invent any data
    # - User message: contains only structured JSON
    prompt = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a financial reconciliation assistant. "
                    "Answer ONLY using the information in the provided transactions and attachments. "
                    "Do NOT infer, guess, or hallucinate any missing data. "
                    "If the answer cannot be fully derived from the data, say so clearly."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Here is the reconciliation data:\n\n"
                    f"{json.dumps(simplified_data, indent=2)}\n\n"
                    "Now answer the user's question strictly based on this data."
                )
            }
        ],
        "model": "llama3.2:latest"
    }

    # Query local LLM via Ollama-compatible endpoint
    response = client.chat.completions.create(
        model=prompt["model"],
        messages=prompt["messages"]
    )

    # Extract and return the model output text
    return response.choices[0].message.content.strip()
