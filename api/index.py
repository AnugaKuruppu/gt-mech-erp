import os
import sys
import json
import datetime
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.environ.get("SECRET_KEY", "gt_automech_level50_vault_key")

# --- FIREBASE SECURE CORE SYSTEM RUNTIME INITIALIZATION ---
db = None
firebase_error = None
raw_env_check = os.environ.get("FIREBASE_CREDENTIALS", "NOT_FOUND_AT_ALL").strip()

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if raw_env_check and raw_env_check != "NOT_FOUND_AT_ALL":
        try:
            cred_dict = json.loads(raw_env_check)
        except Exception:
            fixed_raw = raw_env_check.replace('\n', '\\n')
            cred_dict = json.loads(fixed_raw)

        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace('\\n', '\n')

        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
    else:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
            
    db = firestore.client()

    # ==============================================================================
    # THE 50-MODULE ENTERPRISE INITIAL SEEDING
    # ==============================================================================
    def verify_and_seed_firebase():
        sys_ref = db.collection("system_config")
        if len(list(sys_ref.limit(1).stream())) == 0:
            
            # Master Config
            sys_ref.document("core").set({"version": "50.0", "branch": "Main HQ", "currency": "LKR"})
            
            # 1-10: CRM & Customer Experience
            db.collection("customers").document("CUST001").set({"name": "Mahela Jayawardene", "phone": "0777123456", "loyalty_points": 450, "portal_access": True})
            db.collection("appointments").document("APT001").set({"customer_id": "CUST001", "date": "2026-06-15", "type": "Full Service", "sms_reminder_sent": False})
            db.collection("warranties").document("WAR001").set({"job_card_id": "JOB-001", "sku": "SKU-HYB-CELL", "expires": "2027-06-10", "status": "Active"})
            
            # 11-20: Plant Floor Management
            db.collection("employees").document("EMP001").set({"name": "Kamal Perera", "role": "Master Technician", "hourly_rate": 750.00, "commission_rate": 0.05, "status": "Active"})
            db.collection("bay_schedules").document("BAY1").set({"name": "Diagnostic Bay A", "current_job": "JOB-001", "equipment_status": "Operational"})
            db.collection("tool_checkout").document("TOOL-SCAN1").set({"name": "Snap-On OBD2 Scanner", "assigned_to": "EMP001", "condition": "Good"})
            
            # 21-30: Supply Chain & Inventory
            db.collection("inventory").document("SKU-ENG-OIL").set({"name": "Fully Synthetic Engine Oil 5W-30", "stock": 45, "reorder": 10, "cost": 6200.00, "price": 8500.00, "barcode": "890123456789"})
            db.collection("inventory").document("SKU-HYB-CELL").set({"name": "Hybrid Battery Core Module", "stock": 4, "reorder": 2, "cost": 22000.00, "price": 38000.00, "core_charge": 5000.00})
            db.collection("purchase_orders").document("PO-2026-001").set({"supplier_id": "SUP-UM", "status": "Pending", "total_value": 185000.00})
            
            # 31-40: Finance & Accounting (Extended Chart of Accounts)
            acc_ref = db.collection("chart_of_accounts")
            acc_ref.document("10100").set({"name": "Cash & Bank Accounts", "account_type": "Asset", "balance": 1250000.00})
            acc_ref.document("12000").set({"name": "Inventory Asset Account", "account_type": "Asset", "balance": 450000.00})
            acc_ref.document("13000").set({"name": "Accounts Receivable", "account_type": "Asset", "balance": 0.00})
            acc_ref.document("21000").set({"name": "Accounts Payable (Suppliers)", "account_type": "Liability", "balance": 0.00})
            acc_ref.document("22000").set({"name": "Tax Payable (VAT/SSCL)", "account_type": "Liability", "balance": 0.00})
            acc_ref.document("40000").set({"name": "Workshop Revenue", "account_type": "Revenue", "balance": 0.00})
            acc_ref.document("50000").set({"name": "Cost of Goods Sold (COGS)", "account_type": "Expense", "balance": 0.00})
            acc_ref.document("51000").set({"name": "Technician Labor & Payroll", "account_type": "Expense", "balance": 0.00})
            
            # 41-50: Operations & Analytics 
            db.collection("audit_logs").document("LOG001").set({"timestamp": "2026-06-10 08:00", "user": "System Admin", "action": "Initialized 50-Module Enterprise DB"})
            
            # Initialize Vehicles & Job Cards
            db.collection("vehicles").document("WP-CAD-9922").set({"customer_id": "CUST001", "make": "Toyota", "model": "Prius", "vin": "NHW20-776152", "dtc_fault_history": [{"code": "P0A80", "desc": "Replace Battery", "status": "Active"}]})
            db.collection("job_cards").document("JOB-2026-0001").set({
                "vehicle": "WP-CAD-9922", "technician_id": "EMP001", "status": "In Progress", "hours_logged": 3.0,
                "tasks": [{"desc": "Battery Swap", "done": False}], "parts_used": [{"sku": "SKU-HYB-CELL", "qty": 1, "price": 38000.00}]
            })

except Exception as ex:
    firebase_error = traceback.format_exc()

# ==============================================================================
# ACCUMULATED DOUBLE-ENTRY BALANCING PIPELINE ENGINE
# ==============================================================================
def execute_double_entry(description, reference, movements):
    total_debits = sum(m[1] for m in movements)
    total_credits = sum(m[2] for m in movements)
    if abs(total_debits - total_credits) > 0.001:
        raise ValueError("Ledger Imbalance Triggered! Intercepted multi-legged mismatch.")
    
    batch = db.batch()
    for code, debit, credit in movements:
        acc_ref = db.collection("chart_of_accounts").document(str(code))
        acc_snap = acc_ref.get()
        if acc_snap.exists:
            curr_bal = acc_snap.to_dict().get("balance", 0.0)
            batch.update(acc_ref, {"balance": curr_bal + debit - credit})
            
            log_ref = db.collection("journal_entries").document()
            batch.set(log_ref, {
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "reference": reference,
                "description": description,
                "account_code": code,
                "debit": debit,
                "credit": credit
            })
    batch.commit()

# ==============================================================================
# SYSTEM CONTROLLERS ENDPOINTS
# ==============================================================================

@app.route('/')
def global_dashboard():
    if firebase_error: return f"System Error: {firebase_error}"
    try:
        verify_and_seed_firebase()
        accounts = {doc.id: doc.to_dict() for doc in db.collection("chart_of_accounts").stream()}
        inventory = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
        jobs = {doc.id: doc.to_dict() for doc in db.collection("job_cards").stream()}
        journal = [doc.to_dict() for doc in db.collection("journal_entries").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()]
        
        total_cash = accounts.get("10100", {}).get("balance", 0.0)
        total_revenue = accounts.get("40000", {}).get("balance", 0.0)
        asset_valuation = sum(i.get("stock", 0) * i.get("cost", 0) for i in inventory.values())
        active_jobs_count = sum(1 for j in jobs.values() if j.get("status") != "Completed")

        return render_template('erp_dashboard.html', 
                               cash=total_cash, assets=asset_valuation, revenue=total_revenue,
                               active_jobs=active_jobs_count, jobs=jobs, journal_entries=journal)
    except Exception as e:
        return f"Runtime Error: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True, port=8000)
