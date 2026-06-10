import os
import sys
import json
import datetime
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.environ.get("SECRET_KEY", "free_forever_enterprise_secret_token_2026")

# --- FIREBASE ATOMIC SAFE INITIALIZATION ---
db = None
firebase_error = None

# Track exactly what Vercel sees for diagnostic debugging
raw_env_check = os.environ.get("FIREBASE_CREDENTIALS", "NOT_FOUND_AT_ALL")

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    fb_creds_raw = raw_env_check.strip()

    if fb_creds_raw and fb_creds_raw != "NOT_FOUND_AT_ALL":
        try:
            cred_dict = json.loads(fb_creds_raw)
        except Exception:
            fixed_raw = fb_creds_raw.replace('\n', '\\n')
            cred_dict = json.loads(fixed_raw)

        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace('\\n', '\n')

        cred = credentials.Certificate(cred_dict)
        
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
    else:
        # If the environment variable is completely blank, raise a clear error to block standard boot
        raise ValueError("Vercel environment variable 'FIREBASE_CREDENTIALS' is completely empty or missing from this runtime container.")
            
    db = firestore.client()

    # ==============================================================================
    # AUTOMATED FIREBASE SEEDING LOGIC
    # ==============================================================================
    def verify_and_seed_firebase():
        emp_ref = db.collection("employees")
        if len(list(emp_ref.limit(1).stream())) == 0:
            
            # 1. Provision Staff Resources
            emp_ref.document("EMP001").set({"name": "Kamal Perera", "role": "Master Technician", "hourly_rate": 750.00})
            emp_ref.document("EMP002").set({"name": "Suresh Silva", "role": "Junior Mechanic", "hourly_rate": 450.00})
            
            # 2. Provision Chart of Accounts Matrix
            acc_ref = db.collection("chart_of_accounts")
            acc_ref.document("10100").set({"name": "Cash & Bank Accounts", "account_type": "Asset", "balance": 1250000.00})
            acc_ref.document("12000").set({"name": "Inventory Asset Account", "account_type": "Asset", "balance": 450000.00})
            acc_ref.document("21000").set({"name": "Accounts Payable (Suppliers)", "account_type": "Liability", "balance": 0.00})
            acc_ref.document("40000").set({"name": "Workshop Revenue", "account_type": "Revenue", "balance": 0.00})
            acc_ref.document("50000").set({"name": "Cost of Goods Sold (COGS)", "account_type": "Expense", "balance": 0.00})
            acc_ref.document("51000").set({"name": "Technician Labor Expenses", "account_type": "Expense", "balance": 0.00})
            
            # 3. Provision Stock Storage Levels
            inv_ref = db.collection("inventory")
            inv_ref.document("SKU-ENG-OIL").set({"name": "Fully Synthetic Engine Oil 5W-30", "stock": 45, "reorder": 10, "cost": 6200.00, "price": 8500.00})
            inv_ref.document("SKU-BRK-PAD").set({"name": "Ceramic Front Brake Pads Set", "stock": 8, "reorder": 5, "cost": 4100.00, "price": 6800.00})
            
            # 4. Issue Launch Job Order
            job_ref = db.collection("job_cards").document("JOB-2026-0001")
            job_ref.set({
                "vehicle": "WP CAD-9922",
                "technician_id": "EMP001",
                "status": "In Progress",
                "date_opened": "2026-06-10",
                "hours_logged": 2.5,
                "tasks": [
                    {"desc": "Full Engine Flushing & Synthetic Oil Replacement", "done": True},
                    {"desc": "Calibrate Front & Rear Brake Discs", "done": False}
                ],
                "parts_used": [
                    {"sku": "SKU-ENG-OIL", "qty": 1, "price": 8500.00}
                ]
            })

except Exception as ex:
    firebase_error = traceback.format_exc()

# ==============================================================================
# RECONCILIATION ENGINE (NO-SQL DOUBLE ENTRY UPDATE LOGIC)
# ==============================================================================
def execute_double_entry(description, reference, movements):
    total_debits = sum(m[1] for m in movements)
    total_credits = sum(m[2] for m in movements)
    if abs(total_debits - total_credits) > 0.001:
        raise ValueError("Ledger Imbalance! Debits must equal Credits exactly.")
    
    batch = db.batch()
    for code, debit, credit in movements:
        acc_ref = db.collection("chart_of_accounts").document(str(code))
        acc_snap = acc_ref.get()
        if acc_snap.exists:
            current_balance = acc_snap.to_dict().get("balance", 0.0)
            new_balance = current_balance + debit - credit
            batch.update(acc_ref, {"balance": new_balance})
            
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
# WEB MODULE CONTROLLERS
# ==============================================================================

@app.route('/')
def global_dashboard():
    if firebase_error:
        return render_recovery_screen(firebase_error, raw_env_check)
        
    try:
        verify_and_seed_firebase()
        
        accounts = {doc.id: doc.to_dict() for doc in db.collection("chart_of_accounts").stream()}
        total_cash = accounts.get("10100", {}).get("balance", 0.0)
        total_revenue = accounts.get("40000", {}).get("balance", 0.0)
        
        inventory = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
        asset_valuation = sum(item.get("stock", 0) * item.get("cost", 0) for item in inventory.values())
        
        jobs = {doc.id: doc.to_dict() for doc in db.collection("job_cards").stream()}
        active_jobs_count = sum(1 for j in jobs.values() if j.get("status") != "Completed")
        employees = {doc.id: doc.to_dict() for doc in db.collection("employees").stream()}
        
        journal_docs = db.collection("journal_entries").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        journal_stream = [doc.to_dict() for doc in journal_docs]

        return render_template('erp_dashboard.html', 
                               cash=total_cash, assets=asset_valuation, revenue=total_revenue,
                               active_jobs=active_jobs_count, jobs=jobs, inventory=inventory,
                               accounts=accounts, employees=employees, journal_entries=journal_stream)
                               
    except Exception as run_err:
        return render_recovery_screen(traceback.format_exc(), raw_env_check)

@app.route('/production/job/<job_id>', methods=['GET', 'POST'])
def view_job_card(job_id):
    if firebase_error: return render_recovery_screen(firebase_error, raw_env_check)
    
    job_ref = db.collection("job_cards").document(job_id)
    job_snap = job_ref.get()
    if not job_snap.exists: return "Target System Reference Missing", 404
    job = job_snap.to_dict()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_tasks':
            updated_tasks = []
            for idx, task in enumerate(job.get("tasks", [])):
                is_done = request.form.get(f"task_{idx}") == "on"
                updated_tasks.append({"desc": task["desc"], "done": is_done})
                
            hours = float(request.form.get("hours_logged", job.get("hours_logged", 0.0)))
            job_ref.update({"tasks": updated_tasks, "hours_logged": hours})
            flash("Production floor operation cards processed.", "success")
            
        elif action == 'allocate_part':
            sku = request.form.get('sku')
            qty = int(request.form.get('qty', 1))
            
            part_ref = db.collection("inventory").document(sku)
            part_snap = part_ref.get()
            
            if part_snap.exists:
                part_data = part_snap.to_dict()
                current_stock = part_data.get("stock", 0)
                if current_stock >= qty:
                    part_ref.update({"stock": current_stock - qty})
                    current_parts = job.get("parts_used", [])
                    current_parts.append({"sku": sku, "qty": qty, "price": part_data["price"]})
                    job_ref.update({"parts_used": current_parts})
                    flash(f"Material released from stores: {qty} units of {sku}.", "success")
                else:
                    flash("Insufficient physical quantities available to process release.", "danger")
        return redirect(url_for('view_job_card', job_id=job_id))

    inventory = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
    parts_cost = sum(p["qty"] * p["price"] for p in job.get("parts_used", []))
    
    tech_snap = db.collection("employees").document(job.get("technician_id", "")).get()
    hourly_rate = tech_snap.to_dict().get("hourly_rate", 0.0) if tech_snap.exists else 0.0
    labor_cost = job.get("hours_logged", 0.0) * hourly_rate
    
    return render_template('erp_job_detail.html', job_id=job_id, job=job, 
                           parts_cost=parts_cost, labor_cost=labor_cost, 
                           total_estimation=(parts_cost + labor_cost), inventory=inventory)

@app.route('/billing/invoice/<job_id>', methods=['POST'])
def finalize_and_invoice_job(job_id):
    if firebase_error: return render_recovery_screen(firebase_error, raw_env_check)
    
    job_ref = db.collection("job_cards").document(job_id)
    job_snap = job_ref.get()
    if not job_snap.exists or job_snap.to_dict().get("status") == "Completed":
        return "Operational action locked.", 400
        
    job = job_snap.to_dict()
    tech_snap = db.collection("employees").document(job.get("technician_id", "")).get()
    hourly_rate = tech_snap.to_dict().get("hourly_rate", 0.0) if tech_snap.exists else 0.0
    labor_cost = job.get("hours_logged", 0.0) * hourly_rate
    
    parts_cost = 0
    cogs_valuation = 0
    inventory_cache = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
    
    for p in job.get("parts_used", []):
        parts
