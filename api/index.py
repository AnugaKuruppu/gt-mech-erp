import os
import sys
import traceback
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

# Initialize the Flask instance targeting the root template directory cleanly
app = Flask(__name__, template_folder='../templates')
app.secret_key = os.environ.get("SECRET_KEY", "free_forever_enterprise_secret_token_2026")

try:
    # Read database URL from environment variables; default to safe serverless in-memory simulation fallback
    db_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 280}
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)

    # ==============================================================================
    # DATABASE BLUEPRINTS
    # ==============================================================================
    class Employee(db.Model):
        __tablename__ = 'employees'
        id = db.Column(db.String(50), primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        role = db.Column(db.String(100), nullable=False)
        hourly_rate = db.Column(db.Float, default=0.0)

    class Account(db.Model):
        __tablename__ = 'chart_of_accounts'
        code = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        account_type = db.Column(db.String(50), nullable=False)
        balance = db.Column(db.Float, default=0.0)

    class JournalEntry(db.Model):
        __tablename__ = 'journal_entries'
        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        timestamp = db.Column(db.String(50), default=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        reference = db.Column(db.String(100))
        description = db.Column(db.Text)
        account_code = db.Column(db.Integer, db.ForeignKey('chart_of_accounts.code'))
        debit = db.Column(db.Float, default=0.0)
        credit = db.Column(db.Float, default=0.0)

    class InventoryItem(db.Model):
        __tablename__ = 'inventory'
        sku = db.Column(db.String(100), primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        stock = db.Column(db.Integer, default=0)
        reorder = db.Column(db.Integer, default=10)
        cost = db.Column(db.Float, nullable=False)
        price = db.Column(db.Float, nullable=False)

    class JobCard(db.Model):
        __tablename__ = 'job_cards'
        id = db.Column(db.String(50), primary_key=True)
        vehicle = db.Column(db.String(50), nullable=False)
        technician_id = db.Column(db.String(50), db.ForeignKey('employees.id'))
        status = db.Column(db.String(50), default="In Progress")
        date_opened = db.Column(db.String(50), default=lambda: datetime.datetime.now().strftime("%Y-%m-%d"))
        hours_logged = db.Column(db.Float, default=0.0)
        tasks = db.relationship('JobTask', backref='job_card', lazy=True, cascade="all, delete-orphan")
        parts_used = db.relationship('AllocatedPart', backref='job_card', lazy=True, cascade="all, delete-orphan")

    class JobTask(db.Model):
        __tablename__ = 'job_tasks'
        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        job_id = db.Column(db.String(50), db.ForeignKey('job_cards.id'))
        desc = db.Column(db.String(500), nullable=False)
        done = db.Column(db.Boolean, default=False)

    class AllocatedPart(db.Model):
        __tablename__ = 'allocated_parts'
        id = db.Column(db.Integer, primary_key=True, autoincrement=True)
        job_id = db.Column(db.String(50), db.ForeignKey('job_cards.id'))
        sku = db.Column(db.String(100), db.ForeignKey('inventory.sku'))
        qty = db.Column(db.Integer, default=1)
        price = db.Column(db.Float, nullable=False)
        item_details = db.relationship('InventoryItem')

    # ==============================================================================
    # INITIALIZATION ENGINE SEEDING
    # ==============================================================================
    def verify_and_seed_database():
        db.create_all()
        if Employee.query.count() == 0:
            db.session.add(Employee(id="EMP001", name="Kamal Perera", role="Master Technician", hourly_rate=750.00))
            db.session.add(Employee(id="EMP002", name="Suresh Silva", role="Junior Mechanic", hourly_rate=450.00))
            db.session.add(Account(code=10100, name="Cash & Bank Accounts", account_type="Asset", balance=1250000.00))
            db.session.add(Account(code=12000, name="Inventory Asset Account", account_type="Asset", balance=450000.00))
            db.session.add(Account(code=21000, name="Accounts Payable (Suppliers)", account_type="Liability", balance=0.00))
            db.session.add(Account(code=40000, name="Workshop Revenue", account_type="Revenue", balance=0.00))
            db.session.add(Account(code=50000, name="Cost of Goods Sold (COGS)", account_type="Expense", balance=0.00))
            db.session.add(Account(code=51000, name="Technician Labor Expenses", account_type="Expense", balance=0.00))
            db.session.add(InventoryItem(sku="SKU-ENG-OIL", name="Fully Synthetic Engine Oil 5W-30", stock=45, cost=6200.00, price=8500.00))
            db.session.add(InventoryItem(sku="SKU-BRK-PAD", name="Ceramic Front Brake Pads Set", stock=8, cost=4100.00, price=6800.00))
            initial_job = JobCard(id="JOB-2026-0001", vehicle="WP CAD-9922", technician_id="EMP001", hours_logged=2.5)
            db.session.add(initial_job)
            db.session.flush()
            db.session.add(JobTask(job_id=initial_job.id, desc="Full Engine Flushing & Synthetic Oil Replacement", done=True))
            db.session.add(JobTask(job_id=initial_job.id, desc="Calibrate Front & Rear Brake Discs", done=False))
            db.session.add(AllocatedPart(job_id=initial_job.id, sku="SKU-ENG-OIL", qty=1, price=8500.00))
            db.session.commit()

    def execute_double_entry(description, reference, movements):
        total_debits = sum(m[1] for m in movements)
        total_credits = sum(m[2] for m in movements)
        if abs(total_debits - total_credits) > 0.001:
            raise ValueError("Ledger Imbalance! Debits must equal Credits exactly.")
        for code, debit, credit in movements:
            acc = Account.query.get(code)
            if acc:
                acc.balance += debit
                acc.balance -= credit
                entry = JournalEntry(reference=reference, description=description, account_code=code, debit=debit, credit=credit)
                db.session.add(entry)

    # ==============================================================================
    # ROUTING VIEWS
    # ==============================================================================
    @app.route('/')
    def global_dashboard():
        verify_and_seed_database()
        cash_acc = Account.query.get(10100)
        rev_acc = Account.query.get(40000)
        total_cash = cash_acc.balance if cash_acc else 0.0
        total_revenue = rev_acc.balance if rev_acc else 0.0
        
        inventory_items = InventoryItem.query.all()
        asset_valuation = sum(i.stock * i.cost for i in inventory_items)
        active_jobs_count = JobCard.query.filter(JobCard.status != "Completed").count()
        
        all_jobs = {j.id: j for j in JobCard.query.all()}
        all_inventory = {i.sku: i for i in inventory_items}
        all_accounts = {a.code: a for a in Account.query.all()}
        all_employees = {e.id: e for e in Employee.query.all()}
        journal_stream = JournalEntry.query.order_by(JournalEntry.id.desc()).all()

        return render_template('erp_dashboard.html', 
                               cash=total_cash, assets=asset_valuation, revenue=total_revenue,
                               active_jobs=active_jobs_count, jobs=all_jobs, inventory=all_inventory,
                               accounts=all_accounts, employees=all_employees, journal_entries=journal_stream)

    @app.route('/production/job/<job_id>', methods=['GET', 'POST'])
    def view_job_card(job_id):
        job = JobCard.query.get(job_id)
        if not job: return "Target System Reference Missing", 404
        
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'update_tasks':
                for idx, task in enumerate(job.tasks):
                    task.done = request.form.get(f"task_{idx}") == "on"
                job.hours_logged = float(request.form.get("hours_logged", job.hours_logged))
                db.session.commit()
                flash("Production floor operation cards processed.", "success")
            elif action == 'allocate_part':
                sku = request.form.get('sku')
                qty = int(request.form.get('qty', 1))
                part = InventoryItem.query.get(sku)
                if part and part.stock >= qty:
                    part.stock -= qty
                    allocation = AllocatedPart(job_id=job_id, sku=sku, qty=qty, price=part.price)
                    db.session.add(allocation)
                    db.session.commit()
                    flash(f"Material released from stores: {qty} units of {sku}.", "success")
                else:
                    flash("Insufficient physical quantities available to process release.", "danger")
            return redirect(url_for('view_job_card', job_id=job_id))

        parts_cost = sum(p.qty * p.price for p in job.parts_used)
        tech = Employee.query.get(job.technician_id)
        labor_cost = job.hours_logged * (tech.hourly_rate if tech else 0.0)
        inventory_list = {i.sku: i for i in InventoryItem.query.all()}
        
        return render_template('erp_job_detail.html', job_id=job_id, job=job, 
                               parts_cost=parts_cost, labor_cost=labor_cost, 
                               total_estimation=(parts_cost + labor_cost), inventory=inventory_list)

    @app.route('/billing/invoice/<job_id>', methods=['POST'])
    def finalize_and_invoice_job(job_id):
        job = JobCard.query.get(job_id)
        if not job or job.status == "Completed": return "Operational action locked.", 400
        tech = Employee.query.get(job.technician_id)
        labor_cost = job.hours_logged * (tech.hourly_rate if tech else 0.0)
        parts_cost = 0
        cogs_valuation = 0
        for p in job.parts_used:
            parts_cost += p.qty * p.price
            cogs_valuation += p.qty * p.item_details.cost
            
        grand_total = parts_cost + labor_cost
        
        try:
            execute_double_entry(
                description=f"Automated settlement run for work card {job_id} / Vehicle {job.vehicle}",
                reference=f"INV-{job_id}",
                movements=[
                    (10100, grand_total, 0.00), (40000, 0.00, grand_total),
                    (50000, cogs_valuation, 0.00), (12000, 0.00, cogs_valuation),
                    (51000, labor_cost, 0.00), (10100, 0.00, labor_cost)
                ]
            )
            job.status = "Completed"
            db.session.commit()
            flash(f"Ledger balances updated successfully. Invoicing cycle ended.", "success")
        except ValueError as e:
            db.session.rollback()
            flash(f"Critical ledger failure: {str(e)}", "danger")

        return redirect(url_for('global_dashboard'))

except Exception as boot_error:
    error_trace = traceback.format_exc()
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def diagnostic_catcher(path):
        return f"<h2>🚨 BOOT FAILURE</h2><pre>{error_trace}</pre>"

if __name__ == '__main__':
    app.run(debug=True, port=8000)