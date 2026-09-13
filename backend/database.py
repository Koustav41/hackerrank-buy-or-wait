import os
import sqlite3
import csv
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "finance.db")
DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dataset")
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_reload: bool = False):
    if force_reload and os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        request_id TEXT PRIMARY KEY,
        user_id TEXT,
        request_date TEXT,
        request_type TEXT,
        requested_amount REAL,
        desired_completion_date TEXT,
        allows_partial_payment INTEGER,
        request_text TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS decisions (
        request_id TEXT PRIMARY KEY,
        amount_safe_to_pay REAL,
        affordability_status TEXT,
        recommended_payment_method TEXT,
        payment_plan TEXT,
        earliest_date_for_full_payment TEXT,
        spending_changes_needed TEXT,
        decision_explanation TEXT,
        FOREIGN KEY (request_id) REFERENCES requests(request_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        user_id TEXT PRIMARY KEY,
        home_currency TEXT,
        current_available_balance REAL,
        minimum_balance_to_keep REAL,
        financial_priorities TEXT,
        expense_categories_to_protect TEXT,
        expense_categories_user_is_willing_to_reduce TEXT,
        expense_categories_user_is_willing_to_stop TEXT,
        payment_methods_user_will_consider TEXT,
        max_installment_months REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_options (
        payment_option_id TEXT PRIMARY KEY,
        request_id TEXT,
        payment_method TEXT,
        payment_amount REAL,
        number_of_payments INTEGER,
        first_payment_date TEXT,
        payment_frequency_days INTEGER,
        financing_fee REAL,
        total_payable_amount REAL,
        FOREIGN KEY (request_id) REFERENCES requests(request_id)
    )
    """)
    conn.commit()

    # Populate tables
    cursor.execute("SELECT COUNT(*) FROM requests")
    if cursor.fetchone()[0] == 0 or force_reload:
        populate_from_csv(conn)
    
    conn.close()

def populate_from_csv(conn):
    cursor = conn.cursor()

    # 1. Profiles
    profiles_csv = os.path.join(DATASET_DIR, "financial_profiles.csv")
    if os.path.exists(profiles_csv):
        with open(profiles_csv, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                max_inst = float(row["max_installment_months"]) if row.get("max_installment_months") else None
                cursor.execute("""
                    INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["user_id"].strip(),
                    row.get("home_currency", "").strip(),
                    float(row.get("current_available_balance", 0.0) or 0.0),
                    float(row.get("minimum_balance_to_keep", 0.0) or 0.0),
                    row.get("financial_priorities", "").strip(),
                    row.get("expense_categories_to_protect", "").strip(),
                    row.get("expense_categories_user_is_willing_to_reduce", "").strip(),
                    row.get("expense_categories_user_is_willing_to_stop", "").strip(),
                    row.get("payment_methods_user_will_consider", "").strip(),
                    max_inst
                ))

    # 2. Sample Requests and Evaluation Requests
    for fname in ["sample_requests.csv", "requests.csv"]:
        fpath = os.path.join(DATASET_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rid = row["request_id"].strip()
                    allows_part = 1 if str(row.get("allows_partial_payment", "")).lower() == "true" else 0
                    cursor.execute("""
                        INSERT OR REPLACE INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rid,
                        row.get("user_id", "").strip(),
                        row.get("request_date", "").strip(),
                        row.get("request_type", "").strip(),
                        float(row.get("requested_amount", 0.0) or 0.0),
                        row.get("desired_completion_date", "").strip(),
                        allows_part,
                        row.get("request_text", "").strip()
                    ))

                    # Sample requests also have output ground truth
                    if "affordability_status" in row and row.get("affordability_status"):
                        cursor.execute("""
                            INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            rid,
                            float(row.get("amount_safe_to_pay", 0.0) or 0.0),
                            row.get("affordability_status", "").strip(),
                            row.get("recommended_payment_method", "").strip(),
                            row.get("payment_plan", "").strip(),
                            row.get("earliest_date_for_full_payment", "").strip(),
                            row.get("spending_changes_needed", "").strip(),
                            row.get("decision_explanation", "").strip()
                        ))

    # 3. Model Output Decisions (for evaluation requests)
    output_csv = os.path.join(ROOT_DIR, "output.csv")
    if not os.path.exists(output_csv):
        output_csv = os.path.join(DATASET_DIR, "output.csv")
    if os.path.exists(output_csv):
        with open(output_csv, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rid = row["request_id"].strip()
                cursor.execute("""
                    INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rid,
                    float(row.get("amount_safe_to_pay", 0.0) or 0.0),
                    row.get("affordability_status", "").strip(),
                    row.get("recommended_payment_method", "").strip(),
                    row.get("payment_plan", "").strip(),
                    row.get("earliest_date_for_full_payment", "").strip(),
                    row.get("spending_changes_needed", "").strip(),
                    row.get("decision_explanation", "").strip()
                ))

    # 4. Payment Options
    options_csv = os.path.join(DATASET_DIR, "request_payment_options.csv")
    if os.path.exists(options_csv):
        with open(options_csv, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                freq = None
                freq_val = row.get("payment_frequency_days", "")
                if freq_val and str(freq_val).strip() != "":
                    try:
                        freq = int(float(freq_val))
                    except Exception:
                        pass

                cursor.execute("""
                    INSERT OR REPLACE INTO payment_options VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("payment_option_id", "").strip(),
                    row.get("request_id", "").strip(),
                    row.get("payment_method", "").strip(),
                    float(row.get("payment_amount", 0.0) or 0.0),
                    int(row.get("number_of_payments", 1) or 1),
                    row.get("first_payment_date", "").strip(),
                    freq,
                    float(row.get("financing_fee", 0.0) or 0.0),
                    float(row.get("total_payable_amount", 0.0) or 0.0)
                ))

    conn.commit()

def get_all_requests(query: str = None, status: str = None, limit: int = 250, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    
    sql = """
        SELECT r.request_id, r.user_id, r.request_date, r.requested_amount,
               r.request_type, r.request_text as purpose,
               COALESCE(p.home_currency, 'USD') as currency,
               COALESCE(d.amount_safe_to_pay, 0.0) as amount_safe_to_pay,
               COALESCE(d.affordability_status, 'unknown') as affordability_status,
               COALESCE(d.recommended_payment_method, 'unknown') as recommended_payment_method,
               d.earliest_date_for_full_payment
        FROM requests r
        LEFT JOIN decisions d ON r.request_id = d.request_id
        LEFT JOIN profiles p ON r.user_id = p.user_id
        WHERE 1=1
    """
    params = []
    if status:
        sql += " AND d.affordability_status = ?"
        params.append(status)
    if query:
        sql += " AND (r.request_id LIKE ? OR r.request_text LIKE ? OR r.request_type LIKE ? OR r.user_id LIKE ?)"
        q = f"%{query}%"
        params.extend([q, q, q, q])
    
    # Sort requests numerically by request id
    sql += " ORDER BY CAST(SUBSTR(r.request_id, 9) AS INTEGER) ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_stats() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            COUNT(r.request_id) as total_requests,
            SUM(CASE WHEN d.affordability_status = 'affordable_now' THEN 1 ELSE 0 END) as affordable_now,
            SUM(CASE WHEN d.affordability_status = 'affordable_with_plan' THEN 1 ELSE 0 END) as affordable_with_plan,
            SUM(CASE WHEN d.affordability_status = 'affordable_later' THEN 1 ELSE 0 END) as affordable_later,
            SUM(CASE WHEN d.affordability_status = 'not_affordable' THEN 1 ELSE 0 END) as not_affordable,
            SUM(COALESCE(d.amount_safe_to_pay, 0.0)) as total_safe_amount,
            SUM(COALESCE(r.requested_amount, 0.0)) as total_requested_amount
        FROM requests r
        LEFT JOIN decisions d ON r.request_id = d.request_id
    """)
    res = cursor.fetchone()
    conn.close()
    if res:
        return dict(res)
    return {
        "total_requests": 0, "affordable_now": 0, "affordable_with_plan": 0,
        "affordable_later": 0, "not_affordable": 0, "total_safe_amount": 0.0, "total_requested_amount": 0.0
    }

def get_request_detail(request_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT r.*, 
               COALESCE(p.home_currency, 'USD') as currency,
               COALESCE(p.current_available_balance, 0.0) as current_balance,
               COALESCE(p.minimum_balance_to_keep, 0.0) as minimum_balance_to_keep,
               COALESCE(p.financial_priorities, '') as financial_priorities,
               COALESCE(d.amount_safe_to_pay, 0.0) as amount_safe_to_pay,
               COALESCE(d.affordability_status, 'unknown') as affordability_status,
               COALESCE(d.recommended_payment_method, 'unknown') as recommended_payment_method,
               COALESCE(d.payment_plan, 'none') as payment_plan,
               d.earliest_date_for_full_payment,
               COALESCE(d.spending_changes_needed, 'none') as spending_changes_needed,
               COALESCE(d.decision_explanation, '') as decision_explanation
        FROM requests r
        LEFT JOIN decisions d ON r.request_id = d.request_id
        LEFT JOIN profiles p ON r.user_id = p.user_id
        WHERE r.request_id = ?
    """, (request_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    
    data = dict(row)
    data["allows_partial_payment"] = bool(data.get("allows_partial_payment"))
    
    # fetch payment options
    cursor.execute("""
        SELECT * FROM payment_options WHERE request_id = ?
    """, (request_id,))
    data["payment_options"] = [dict(opt) for opt in cursor.fetchall()]
    
    conn.close()
    return data
