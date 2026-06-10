import os
import sys
import json
import datetime
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.environ.get("SECRET_KEY", "free_forever_enterprise_secret_token_2026")

# --- FIREBASE CONNECTIONS ENGINE INITIALIZATION ---
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
    # AUTOMATED SYSTEM SEEDING SCRIPT
    # ==============================================================================
    def verify_and_seed_firebase():
        emp_ref = db.collection("employees")
        if len(list(emp_ref.limit(1).stream())) == 0:
            
            # Seed Staff Drivers
            emp_ref.document("EMP001").set({"name": "Kamal Perera", "role": "Master Technician", "hourly_rate": 750.00})
            emp_ref.document("EMP002").set({"name": "Suresh Silva", "role": "Junior Mechanic", "hourly_rate": 450.00})
            
            # Seed Financial Chart of Accounts
            acc_ref = db.collection("chart_of_accounts")
            acc_ref.document("10100").set({"name": "Cash & Bank Accounts", "account_type": "Asset", "balance": 1250000.00})
            acc_ref.document("12000").set({"name": "Inventory Asset Account", "account_type": "Asset", "balance": 450000.00})
            acc_ref.document("21000").set({"name": "Accounts Payable (Suppliers)", "account_type": "Liability", "balance": 0.00})
            acc_ref.document("40000").set({"name": "Workshop Revenue", "account_type": "Revenue", "balance": 0.00})
            acc_ref.document("50000").set({"name": "Cost of Goods Sold (COGS)", "account_type": "Expense", "balance": 0.00})
            acc_ref.document("51000").set({"name": "Technician Labor Expenses", "account_type": "Expense", "balance": 0.00})
            
            # Seed Materials Inventory
            inv_ref = db.collection("inventory")
            inv_ref.document("SKU-ENG-OIL").set({"name": "Fully Synthetic Engine Oil 5W-30", "stock": 45, "reorder": 10, "cost": 6200.00, "price": 8500.00})
            inv_ref.document("SKU-BRK-PAD").set({"name": "Ceramic Front Brake Pads Set", "stock": 8, "reorder": 5, "cost": 4100.00, "price": 6800.00})
            
            # Seed Core Vehicle Entity Registers
            db.collection("customers").document("CUST-001").set({"name": "Mahela Jayawardene", "phone": "0777123456", "email": "mahela@cricket.lk"})
            db.collection("vehicles").document("WP-CAD-9922").set({"customer_id": "CUST-001", "make": "Toyota", "model": "Prius", "year": 2018})
            
            # Seed Active Repair Orders Pipeline
            job_ref = db.collection("job_cards").document("JOB-2026-0001")
            job_ref.set({
                "vehicle": "WP-CAD-9922",
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
# FINANCIAL ATOMIC BALANCING PIPELINE ENGINE
# ==============================================================================
def execute_double_entry(description, reference, movements):
    total_debits = sum(m[1] for m in movements)
    total_credits = sum(m[2] for m in movements)
    if abs(total_debits - total_credits) > 0.001:
        raise ValueError("Ledger Imbalance Detected! Debits must equal Credits.")
    
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
# WEB REQUEST MODULE ENDPOINTS
# ==============================================================================

@app.route('/')
def global_dashboard():
    if firebase_error: return render_recovery_screen(firebase_error, raw_env_check)
    try:
        verify_and_seed_firebase()
        accounts = {doc.id: doc.to_dict() for doc in db.collection("chart_of_accounts").stream()}
        inventory = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
        jobs = {doc.id: doc.to_dict() for doc in db.collection("job_cards").stream()}
        employees = {doc.id: doc.to_dict() for doc in db.collection("employees").stream()}
        journal = [doc.to_dict() for doc in db.collection("journal_entries").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()]
        
        total_cash = accounts.get("10100", {}).get("balance", 0.0)
        total_revenue = accounts.get("40000", {}).get("balance", 0.0)
        asset_valuation = sum(i.get("stock", 0) * i.get("cost", 0) for i in inventory.values())
        active_jobs_count = sum(1 for j in jobs.values() if j.get("status") != "Completed")

        return render_template('erp_dashboard.html', 
                               cash=total_cash, assets=asset_valuation, revenue=total_revenue,
                               active_jobs=active_jobs_count, jobs=jobs, inventory=inventory,
                               accounts=accounts, employees=employees, journal_entries=journal)
    except Exception:
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
            updated_tasks = [{"desc": t["desc"], "done": request.form.get(f"task_{i}") == "on"} for i, t in enumerate(job.get("tasks", []))]
            hours = float(request.form.get("hours_logged", job.get("hours_logged", 0.0)))
            job_ref.update({"tasks": updated_tasks, "hours_logged": hours})
            flash("Production floor operations logs successfully synced.", "success")
            
        elif action == 'allocate_part':
            sku = request.form.get('sku')
            qty = int(request.form.get('qty', 1))
            part_ref = db.collection("inventory").document(sku)
            part_snap = part_ref.get()
            
            if part_snap.exists and part_snap.to_dict().get("stock", 0) >= qty:
                part_ref.update({"stock": part_snap.to_dict()["stock"] - qty})
                curr_parts = job.get("parts_used", [])
                curr_parts.append({"sku": sku, "qty": qty, "price": part_snap.to_dict()["price"]})
                job_ref.update({"parts_used": curr_parts})
                flash(f"Material released from storage: {qty} units of {sku}.", "success")
            else:
                flash("Insufficient parts quantities available to complete allocation.", "danger")
        return redirect(url_for('view_job_card', job_id=job_id))

    inventory = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
    parts_cost = sum(p["qty"] * p["price"] for p in job.get("parts_used", []))
    tech_snap = db.collection("employees").document(job.get("technician_id", "")).get()
    rate = tech_snap.to_dict().get("hourly_rate", 0.0) if tech_snap.exists else 0.0
    labor_cost = job.get("hours_logged", 0.0) * rate
    
    return render_template('erp_job_detail.html', job_id=job_id, job=job, 
                           parts_cost=parts_cost, labor_cost=labor_cost, 
                           total_estimation=(parts_cost + labor_cost), inventory=inventory)

@app.route('/billing/invoice/<job_id>', methods=['POST'])
def finalize_and_invoice_job(job_id):
    if firebase_error: return render_recovery_screen(firebase_error, raw_env_check)
    job_ref = db.collection("job_cards").document(job_id)
    job_snap = job_ref.get()
    if not job_snap.exists or job_snap.to_dict().get("status") == "Completed": return "Action Locked.", 400
        
    job = job_snap.to_dict()
    tech_snap = db.collection("employees").document(job.get("technician_id", "")).get()
    rate = tech_snap.to_dict().get("hourly_rate", 0.0) if tech_snap.exists else 0.0
    labor_cost = job.get("hours_logged", 0.0) * rate
    
    parts_cost = 0
    cogs_valuation = 0
    inv = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
    for p in job.get("parts_used", []):
        parts_cost += p["qty"] * p["price"]
        cogs_valuation += p["qty"] * inv.get(p["sku"], {}).get("cost", 0.0)
    grand_total = parts_cost + labor_cost
    
    try:
        execute_double_entry(
            description=f"Automated core ledger settlement run for Job {job_id}",
            reference=f"INV-{job_id}",
            movements=[
                (10100, grand_total, 0.00), (40000, 0.00, grand_total),
                (50000, cogs_valuation, 0.00), (12000, 0.00, cogs_valuation),
                (51000, labor_cost, 0.00), (10100, 0.00, labor_cost)
            ]
        )
        job_ref.update({"status": "Completed"})
        flash(f"Invoicing sequence completed. General balance sheets reconciled cleanly.", "success")
    except ValueError as e:
        flash(f"Critical accounting block: {str(e)}", "danger")
    return redirect(url_for('global_dashboard'))

def render_recovery_screen(stack_trace, current_env_state):
    safe_display = current_env_state[:30] + "..." if len(current_env_state) > 30 else current_env_state
    return f"<h2>⚠️ CONFIGURATION CONTEXT EXCEPTION</h2><pre>{stack_trace}</pre><br><b>Read Check:</b> <code>{safe_display}</code>"

if __name__ == '__main__':
    app.run(debug=True, port=8000)
