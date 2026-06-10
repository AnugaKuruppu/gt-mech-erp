import os
import sys
import json
import datetime
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.environ.get("SECRET_KEY", "gt_automech_functional_core_2026")

# --- FIREBASE SECURE CORE INITIALIZATION ---
db = None
firebase_error = None
raw_env_check = os.environ.get("FIREBASE_CREDENTIALS", "").strip()

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if raw_env_check:
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
except Exception as ex:
    firebase_error = traceback.format_exc()

# ==============================================================================
# FUNCTIONAL FINANCIAL LEDGER ENGINE
# ==============================================================================
def execute_double_entry(description, reference, movements):
    total_debits = sum(m[1] for m in movements)
    total_credits = sum(m[2] for m in movements)
    if abs(total_debits - total_credits) > 0.001:
        raise ValueError("Ledger Imbalance. Debits must equal Credits.")
    
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
# FUNCTIONAL WEB ROUTING
# ==============================================================================

@app.route('/')
def global_dashboard():
    if firebase_error: return f"Configuration Error: {firebase_error}"
    try:
        # Live Data Fetching
        accounts = {doc.id: doc.to_dict() for doc in db.collection("chart_of_accounts").stream()}
        inventory = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
        jobs = {doc.id: doc.to_dict() for doc in db.collection("job_cards").stream()}
        employees = {doc.id: doc.to_dict() for doc in db.collection("employees").stream()}
        vehicles = {doc.id: doc.to_dict() for doc in db.collection("vehicles").stream()}
        journal = [doc.to_dict() for doc in db.collection("journal_entries").order_by("timestamp", direction=firestore.Query.DESCENDING).stream()]
        
        total_cash = accounts.get("10100", {}).get("balance", 0.0)
        total_revenue = accounts.get("40000", {}).get("balance", 0.0)
        asset_valuation = sum(i.get("stock", 0) * i.get("cost", 0) for i in inventory.values())
        active_jobs_count = sum(1 for j in jobs.values() if j.get("status") != "Completed")

        return render_template('erp_dashboard.html', 
                               cash=total_cash, assets=asset_valuation, revenue=total_revenue,
                               active_jobs=active_jobs_count, jobs=jobs, inventory=inventory,
                               vehicles=vehicles, employees=employees, journal_entries=journal)
    except Exception as e:
        return f"Runtime Exception: {str(e)}"

@app.route('/production/job/<job_id>', methods=['GET', 'POST'])
def view_job_card(job_id):
    if firebase_error: return f"Error: {firebase_error}"
    
    job_ref = db.collection("job_cards").document(job_id)
    job_snap = job_ref.get()
    if not job_snap.exists: return "Target System Operational Reference Missing", 404
    job = job_snap.to_dict()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_tasks':
            # Function: Update checklists and hours dynamically
            updated_tasks = [{"desc": t["desc"], "done": request.form.get(f"task_{i}") == "on"} for i, t in enumerate(job.get("tasks", []))]
            hours = float(request.form.get("hours_logged", job.get("hours_logged", 0.0)))
            job_ref.update({"tasks": updated_tasks, "hours_logged": hours})
            flash("Shop floor operations successfully synchronized.", "success")
            
        elif action == 'allocate_part':
            # Function: Secure part allocation without pricing inputs
            sku = request.form.get('sku')
            qty = int(request.form.get('qty', 1))
            
            part_ref = db.collection("inventory").document(sku)
            part_snap = part_ref.get()
            
            if part_snap.exists:
                part_data = part_snap.to_dict()
                if part_data.get("stock", 0) >= qty:
                    # Deduct physical stock
                    part_ref.update({"stock": part_data["stock"] - qty})
                    
                    # Log part to job card, securely fetching backend price
                    curr_parts = job.get("parts_used", [])
                    curr_parts.append({"sku": sku, "qty": qty, "price": part_data["price"]})
                    job_ref.update({"parts_used": curr_parts})
                    flash(f"Material allocated: {qty} units of {sku}.", "success")
                else:
                    flash("Allocation failed: Insufficient physical stock.", "danger")
        return redirect(url_for('view_job_card', job_id=job_id))

    # Live Calculations
    inventory = {doc.id: doc.to_dict() for doc in db.collection("inventory").stream()}
    parts_cost = sum(p["qty"] * p["price"] for p in job.get("parts_used", []))
    
    tech_snap = db.collection("employees").document(job.get("technician_id", "")).get()
    rate = tech_snap.to_dict().get("hourly_rate", 0.0) if tech_snap.exists else 0.0
    labor_cost = job.get("hours_logged", 0.0) * rate
    
    veh_snap = db.collection("vehicles").document(job.get("vehicle", "")).get()
    veh_data = veh_snap.to_dict() if veh_snap.exists else None

    return render_template('erp_job_detail.html', job_id=job_id, job=job, 
                           parts_cost=parts_cost, labor_cost=labor_cost, 
                           total_estimation=(parts_cost + labor_cost), inventory=inventory,
                           vehicle_data=veh_data)

@app.route('/billing/invoice/<job_id>', methods=['POST'])
def finalize_and_invoice_job(job_id):
    # Function: Secure financial lock and ledger execution
    job_ref = db.collection("job_cards").document(job_id)
    job_snap = job_ref.get()
    if not job_snap.exists or job_snap.to_dict().get("status") == "Completed": return "Action Blocked.", 400
        
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
            description=f"Job Settlement: File {job_id}",
            reference=f"INV-{job_id}",
            movements=[
                (10100, grand_total, 0.00), (40000, 0.00, grand_total),
                (50000, cogs_valuation, 0.00), (12000, 0.00, cogs_valuation),
                (51000, labor_cost, 0.00), (10100, 0.00, labor_cost)
            ]
        )
        job_ref.update({"status": "Completed"})
        flash(f"Invoice processed. Ledger balanced.", "success")
    except ValueError as e:
        flash(f"Accounting Fault: {str(e)}", "danger")
        
    return redirect(url_for('global_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=8000)
