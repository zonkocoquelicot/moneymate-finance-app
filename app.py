# app.py - MoneyMate Finance App - FIXED VERSION
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
import os
from dotenv import load_dotenv
import pandas as pd
from io import BytesIO

load_dotenv()

app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
app.config['SECRET_KEY'] = 'moneymate-secret-key-2024'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ── Optional: Google Gemini AI ──────────────────────────────────────────────
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        print("✅ Google Gemini AI configured successfully!")
    except ImportError:
        print("⚠️  google-generativeai not installed. AI features disabled.")
        genai = None
else:
    print("⚠️  GEMINI_API_KEY not found. AI features disabled.")

# ── Optional: Email ─────────────────────────────────────────────────────────
MAIL_CONFIGURED = False
mail = None
try:
    from flask_mail import Mail, Message
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
        mail = Mail(app)
        MAIL_CONFIGURED = True
        print("✅ Email configured successfully!")
    else:
        print("⚠️  Email credentials not found. Email features disabled.")
except ImportError:
    print("⚠️  flask-mail not installed. Email features disabled.")


# ============================================================
# DATABASE MODELS
# ============================================================

# FIX 1: Only ONE User class — with UserMixin AND password_hash
class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    monthly_income= db.Column(db.Float, default=0)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Expense(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    category    = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    date        = db.Column(db.DateTime, default=datetime.utcnow)

class Income(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    source      = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    date        = db.Column(db.DateTime, default=datetime.utcnow)

class Budget(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount   = db.Column(db.Float, nullable=False)
    month    = db.Column(db.String(7), nullable=False)

class SavingsGoal(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    goal_name      = db.Column(db.String(100), nullable=False)
    target_amount  = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0)
    deadline       = db.Column(db.DateTime)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

class RecurringExpense(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    category    = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    frequency   = db.Column(db.String(20), nullable=False)
    start_date  = db.Column(db.DateTime, default=datetime.utcnow)
    next_date   = db.Column(db.DateTime, nullable=False)
    active      = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class BillReminder(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bill_name      = db.Column(db.String(100), nullable=False)
    amount         = db.Column(db.Float, nullable=False)
    due_date       = db.Column(db.DateTime, nullable=False)
    category       = db.Column(db.String(50), default='Bills')
    is_paid        = db.Column(db.Boolean, default=False)
    reminder_sent  = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_current_month():
    return datetime.now().strftime('%Y-%m')

def calculate_category_totals(user_id, month=None):
    if month is None:
        month = get_current_month()
    expenses = Expense.query.filter_by(user_id=user_id).filter(
        func.strftime('%Y-%m', Expense.date) == month
    ).all()
    totals = {}
    for e in expenses:
        totals[e.category] = totals.get(e.category, 0) + e.amount
    return totals

def get_user_financial_summary(user_id):
    current_month = get_current_month()
    expenses       = Expense.query.filter_by(user_id=user_id).all()
    month_expenses = Expense.query.filter_by(user_id=user_id).filter(
        func.strftime('%Y-%m', Expense.date) == current_month).all()
    incomes        = Income.query.filter_by(user_id=user_id).all()
    month_income   = Income.query.filter_by(user_id=user_id).filter(
        func.strftime('%Y-%m', Income.date) == current_month).all()

    month_exp_total = sum(e.amount for e in month_expenses)
    month_inc_total = sum(i.amount for i in month_income)

    return {
        'total_expenses':  sum(e.amount for e in expenses),
        'total_income':    sum(i.amount for i in incomes),
        'month_expenses':  month_exp_total,
        'month_income':    month_inc_total,
        'balance':         month_inc_total - month_exp_total,
        'category_totals': calculate_category_totals(user_id, current_month),
        'budgets':         Budget.query.filter_by(user_id=user_id, month=current_month).all(),
        'goals':           SavingsGoal.query.filter_by(user_id=user_id).all(),
        'expense_count':   len(expenses)
    }


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email    = request.form['email']
        password = request.form['password']

        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already registered')
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Username already taken')

        new_user = User(
            username      = username,
            email         = email,
            password_hash = generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        user     = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))

        return render_template('login.html', error='Invalid email or password')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ============================================================
# MAIN ROUTES  (FIX 2: every route uses current_user.id + @login_required)
# ============================================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required          # FIX 3: protected
def dashboard():
    try:
        user_id       = current_user.id
        current_month = get_current_month()

        month_expenses = Expense.query.filter_by(user_id=user_id).filter(
            func.strftime('%Y-%m', Expense.date) == current_month).all()
        month_income   = Income.query.filter_by(user_id=user_id).filter(
            func.strftime('%Y-%m', Income.date) == current_month).all()

        total_expenses = sum(e.amount for e in month_expenses)
        total_income   = sum(i.amount for i in month_income)
        balance        = total_income - total_expenses

        category_totals  = calculate_category_totals(user_id, current_month)
        recent_expenses  = Expense.query.filter_by(user_id=user_id).order_by(
            Expense.date.desc()).limit(5).all()
        goals = SavingsGoal.query.filter_by(user_id=user_id).all()

        return render_template('dashboard.html',
            total_expenses=total_expenses, total_income=total_income,
            balance=balance, category_totals=category_totals,
            recent_expenses=recent_expenses, goals=goals,
            current_month=current_month)
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/expenses')
@login_required
def expenses():
    try:
        all_expenses = Expense.query.filter_by(user_id=current_user.id).order_by(
            Expense.date.desc()).all()
        return render_template('expenses.html', expenses=all_expenses)
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/income')
@login_required
def income():
    try:
        all_incomes = Income.query.filter_by(user_id=current_user.id).order_by(
            Income.date.desc()).all()
        return render_template('income.html', incomes=all_incomes)
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/add-expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        try:
            expense = Expense(
                user_id     = current_user.id,
                amount      = float(request.form['amount']),
                category    = request.form['category'],
                description = request.form.get('description', ''),
                date        = datetime.strptime(request.form['date'], '%Y-%m-%d')
                              if request.form.get('date') else datetime.now()
            )
            db.session.add(expense)
            db.session.commit()
            return redirect(url_for('dashboard'))
        except Exception as e:
            return render_template('add_expense.html', error=str(e))
    return render_template('add_expense.html')


@app.route('/add-income', methods=['GET', 'POST'])
@login_required
def add_income():
    if request.method == 'POST':
        try:
            inc = Income(
                user_id     = current_user.id,
                amount      = float(request.form['amount']),
                source      = request.form['source'],
                description = request.form.get('description', ''),
                date        = datetime.strptime(request.form['date'], '%Y-%m-%d')
                              if request.form.get('date') else datetime.now()
            )
            db.session.add(inc)
            db.session.commit()
            return redirect(url_for('dashboard'))
        except Exception as e:
            return render_template('add_income.html', error=str(e))
    return render_template('add_income.html')


@app.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    current_month = get_current_month()

    if request.method == 'POST':
        try:
            category = request.form['category']
            amount   = float(request.form['amount'])
            existing = Budget.query.filter_by(
                user_id=current_user.id, category=category, month=current_month).first()
            if existing:
                existing.amount = amount
            else:
                db.session.add(Budget(
                    user_id=current_user.id, category=category,
                    amount=amount, month=current_month))
            db.session.commit()
            return redirect(url_for('budget'))
        except Exception as e:
            print(f"Error saving budget: {e}")

    budgets          = Budget.query.filter_by(user_id=current_user.id, month=current_month).all()
    category_spending = calculate_category_totals(current_user.id, current_month)

    budget_data = []
    for b in budgets:
        spent      = category_spending.get(b.category, 0)
        remaining  = b.amount - spent
        percentage = (spent / b.amount * 100) if b.amount > 0 else 0
        budget_data.append({
            'category': b.category, 'budgeted': b.amount,
            'spent': spent, 'remaining': remaining, 'percentage': percentage
        })

    return render_template('budget.html', budget_data=budget_data)


@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    if request.method == 'POST':
        try:
            goal = SavingsGoal(
                user_id        = current_user.id,
                goal_name      = request.form['goal_name'],
                target_amount  = float(request.form['target_amount']),
                current_amount = float(request.form.get('current_amount', 0)),
                deadline       = datetime.strptime(request.form['deadline'], '%Y-%m-%d')
                                 if request.form.get('deadline') else None
            )
            db.session.add(goal)
            db.session.commit()
            return redirect(url_for('goals'))
        except Exception as e:
            print(f"Error adding goal: {e}")

    all_goals  = SavingsGoal.query.filter_by(user_id=current_user.id).all()
    goals_data = []
    for g in all_goals:
        progress  = (g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 0
        remaining = g.target_amount - g.current_amount
        goals_data.append({
            'id': g.id, 'name': g.goal_name,
            'target': g.target_amount, 'current': g.current_amount,
            'remaining': remaining, 'progress': progress, 'deadline': g.deadline
        })

    return render_template('goals.html', goals=goals_data)


@app.route('/analytics')
@login_required
def analytics():
    try:
        user_id    = current_user.id
        months_data = []
        for i in range(5, -1, -1):
            month_date = datetime.now() - timedelta(days=30 * i)
            month_str  = month_date.strftime('%Y-%m')
            m_exp = Expense.query.filter_by(user_id=user_id).filter(
                func.strftime('%Y-%m', Expense.date) == month_str).all()
            m_inc = Income.query.filter_by(user_id=user_id).filter(
                func.strftime('%Y-%m', Income.date) == month_str).all()
            months_data.append({
                'month':    month_date.strftime('%b %Y'),
                'expenses': sum(e.amount for e in m_exp),
                'income':   sum(i.amount for i in m_inc)
            })

        category_totals = calculate_category_totals(user_id)
        return render_template('analytics.html',
            months_data=months_data, category_totals=category_totals)
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/ai-assistant')
@login_required
def ai_assistant():
    return render_template('ai_assistant.html', ai_enabled=(genai is not None))


# ============================================================
# RECURRING EXPENSES
# ============================================================

@app.route('/recurring')
@login_required
def recurring():
    try:
        recurring_expenses = RecurringExpense.query.filter_by(
            user_id=current_user.id, active=True).all()
        return render_template('recurring.html', recurring_expenses=recurring_expenses)
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/add-recurring', methods=['GET', 'POST'])
@login_required
def add_recurring():
    if request.method == 'POST':
        try:
            frequency  = request.form['frequency']
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            delta      = {'daily': timedelta(days=1), 'weekly': timedelta(weeks=1),
                          'monthly': timedelta(days=30)}.get(frequency, timedelta(days=0))
            next_date  = start_date + delta

            db.session.add(RecurringExpense(
                user_id     = current_user.id,
                amount      = float(request.form['amount']),
                category    = request.form['category'],
                description = request.form.get('description', ''),
                frequency   = frequency,
                start_date  = start_date,
                next_date   = next_date
            ))
            db.session.commit()
            return redirect(url_for('recurring'))
        except Exception as e:
            return render_template('add_recurring.html', error=str(e))
    return render_template('add_recurring.html')


# ============================================================
# BILL REMINDERS
# ============================================================

@app.route('/reminders')
@login_required
def reminders():
    try:
        upcoming = BillReminder.query.filter_by(
            user_id=current_user.id, is_paid=False).order_by(BillReminder.due_date).all()
        return render_template('reminders.html', reminders=upcoming)
    except Exception as e:
        return render_template('error.html', error=str(e)), 500


@app.route('/add-reminder', methods=['GET', 'POST'])
@login_required
def add_reminder():
    if request.method == 'POST':
        try:
            db.session.add(BillReminder(
                user_id   = current_user.id,
                bill_name = request.form['bill_name'],
                amount    = float(request.form['amount']),
                due_date  = datetime.strptime(request.form['due_date'], '%Y-%m-%d'),
                category  = request.form.get('category', 'Bills')
            ))
            db.session.commit()
            return redirect(url_for('reminders'))
        except Exception as e:
            return render_template('add_reminder.html', error=str(e))
    return render_template('add_reminder.html')


# ============================================================
# CURRENCY CONVERTER
# ============================================================

EXCHANGE_RATES = {
    'INR': 1.0, 'USD': 0.012, 'EUR': 0.011,
    'GBP': 0.0095, 'JPY': 1.8, 'AED': 0.044, 'SGD': 0.016
}

@app.route('/currency-converter')
@login_required
def currency_converter():
    return render_template('currency_converter.html', currencies=EXCHANGE_RATES.keys())


@app.route('/api/convert-currency', methods=['POST'])
@login_required
def convert_currency():
    try:
        data         = request.get_json()
        amount       = float(data.get('amount', 0))
        from_cur     = data.get('from', 'INR')
        to_cur       = data.get('to', 'USD')
        inr_amount   = amount / EXCHANGE_RATES.get(from_cur, 1.0)
        converted    = inr_amount * EXCHANGE_RATES.get(to_cur, 1.0)
        return jsonify({'success': True, 'original': amount,
            'converted': round(converted, 2), 'from': from_cur, 'to': to_cur})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============================================================
# AI ENDPOINTS
# ============================================================

@app.route('/api/ai-insights', methods=['POST'])
@login_required
def ai_insights():
    try:
        if not genai:
            return jsonify({'success': False,
                'error': 'AI not configured. Add GEMINI_API_KEY to .env'}), 500

        summary = get_user_financial_summary(current_user.id)
        context = (
            f"Monthly Income: ₹{summary['month_income']:.2f}\n"
            f"Monthly Expenses: ₹{summary['month_expenses']:.2f}\n"
            f"Balance: ₹{summary['balance']:.2f}\n\nSpending:\n"
        )
        for cat, amt in summary['category_totals'].items():
            pct = (amt / summary['month_expenses'] * 100) if summary['month_expenses'] > 0 else 0
            context += f"- {cat}: ₹{amt:.2f} ({pct:.1f}%)\n"
        context += "\nProvide 3 practical money-saving tips (each under 25 words)."

        model_names = ['models/gemini-2.5-flash', 'models/gemini-2.0-flash',
                       'gemini-2.0-flash', 'gemini-2.5-flash']
        last_error = None
        for name in model_names:
            try:
                response = genai.GenerativeModel(name).generate_content(context)
                return jsonify({'success': True, 'insights': response.text})
            except Exception as e:
                last_error = str(e)
        return jsonify({'success': False, 'error': f'All AI models failed: {last_error}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ask-ai', methods=['POST'])
@login_required
def ask_ai():
    try:
        if not genai:
            return jsonify({'success': False, 'error': 'AI not configured'}), 500

        question = request.get_json().get('question', '')
        if not question:
            return jsonify({'success': False, 'error': 'No question provided'}), 400

        summary = get_user_financial_summary(current_user.id)
        context = (
            f"You are a friendly finance assistant. Answer in under 100 words.\n"
            f"User monthly income: ₹{summary['month_income']:.2f}, "
            f"expenses: ₹{summary['month_expenses']:.2f}, "
            f"balance: ₹{summary['balance']:.2f}\n\nQuestion: {question}"
        )

        model_names = ['models/gemini-2.5-flash', 'models/gemini-2.0-flash',
                       'gemini-2.0-flash', 'gemini-2.5-flash']
        last_error = None
        for name in model_names:
            try:
                response = genai.GenerativeModel(name).generate_content(context)
                return jsonify({'success': True, 'answer': response.text})
            except Exception as e:
                last_error = str(e)
        return jsonify({'success': False, 'error': f'AI failed: {last_error}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# EXPORT
# ============================================================

@app.route('/export/expenses-csv')
@login_required
def export_expenses_csv():
    try:
        expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
        df = pd.DataFrame([{
            'Date': e.date.strftime('%Y-%m-%d'), 'Category': e.category,
            'Description': e.description or '', 'Amount': e.amount
        } for e in expenses])
        output = BytesIO()
        df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)
        return send_file(output, mimetype='text/csv', as_attachment=True,
                         download_name='expenses.csv')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/export/expenses-excel')
@login_required
def export_expenses_excel():
    try:
        expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
        df = pd.DataFrame([{
            'Date': e.date.strftime('%Y-%m-%d'), 'Category': e.category,
            'Description': e.description or '', 'Amount': f'₹{e.amount:.2f}'
        } for e in expenses])
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Expenses')
        output.seek(0)
        return send_file(output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name='expenses.xlsx')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/export/full-report-excel')
@login_required
def export_full_report():
    try:
        expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
        # FIX 4: was "_incomes" (typo) — now "incomes" used consistently
        incomes  = Income.query.filter_by(user_id=current_user.id).order_by(Income.date.desc()).all()

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if expenses:
                pd.DataFrame([{
                    'Date': e.date.strftime('%Y-%m-%d'), 'Category': e.category,
                    'Description': e.description or '', 'Amount': e.amount
                } for e in expenses]).to_excel(writer, sheet_name='Expenses', index=False)

            if incomes:
                pd.DataFrame([{
                    'Date': i.date.strftime('%Y-%m-%d'), 'Source': i.source,
                    'Description': i.description or '', 'Amount': i.amount
                } for i in incomes]).to_excel(writer, sheet_name='Income', index=False)

            pd.DataFrame([
                {'Metric': 'Total Income',   'Value': f'₹{sum(i.amount for i in incomes):.2f}'},
                {'Metric': 'Total Expenses', 'Value': f'₹{sum(e.amount for e in expenses):.2f}'}
            ]).to_excel(writer, sheet_name='Summary', index=False)

        output.seek(0)
        return send_file(output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name='financial_report.xlsx')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# EMAIL
# ============================================================

@app.route('/api/email-report', methods=['POST'])
@login_required
def email_report():
    try:
        if not MAIL_CONFIGURED:
            return jsonify({'success': False,
                'error': 'Email not configured. Add MAIL_USERNAME and MAIL_PASSWORD to .env'}), 500

        recipient = request.get_json().get('email')
        if not recipient:
            return jsonify({'success': False, 'error': 'Email required'}), 400

        summary = get_user_financial_summary(current_user.id)
        msg = Message('MoneyMate – Your Financial Report',
            sender=app.config['MAIL_USERNAME'], recipients=[recipient])
        msg.body = (
            f"Hello {current_user.username}!\n\n"
            f"💰 Monthly Income:   ₹{summary['month_income']:.2f}\n"
            f"💸 Monthly Expenses: ₹{summary['month_expenses']:.2f}\n"
            f"💵 Balance:          ₹{summary['balance']:.2f}\n\n"
            "Keep tracking with MoneyMate!"
        )
        mail.send(msg)
        return jsonify({'success': True, 'message': 'Report sent!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# DELETE / UPDATE API
# ============================================================

@app.route('/api/delete-expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    try:
        db.session.delete(Expense.query.get_or_404(expense_id))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/delete-income/<int:income_id>', methods=['POST'])
@login_required
def delete_income(income_id):
    try:
        db.session.delete(Income.query.get_or_404(income_id))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/delete-goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_goal(goal_id):
    try:
        db.session.delete(SavingsGoal.query.get_or_404(goal_id))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/delete-recurring/<int:recurring_id>', methods=['POST'])
@login_required
def delete_recurring(recurring_id):
    try:
        db.session.delete(RecurringExpense.query.get_or_404(recurring_id))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/delete-reminder/<int:reminder_id>', methods=['POST'])
@login_required
def delete_reminder(reminder_id):
    try:
        db.session.delete(BillReminder.query.get_or_404(reminder_id))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/update-goal/<int:goal_id>', methods=['POST'])
@login_required
def update_goal(goal_id):
    try:
        goal = SavingsGoal.query.get_or_404(goal_id)
        data = request.get_json()
        if 'current_amount' not in data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        goal.current_amount = float(data['current_amount'])
        db.session.commit()
        progress = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
        return jsonify({'success': True, 'progress': progress,
                        'remaining': goal.target_amount - goal.current_amount})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mark-paid/<int:reminder_id>', methods=['POST'])
@login_required
def mark_paid(reminder_id):
    try:
        reminder = BillReminder.query.get_or_404(reminder_id)
        reminder.is_paid = True
        db.session.add(Expense(
            user_id=reminder.user_id, amount=reminder.amount,
            category=reminder.category,
            description=f"Bill: {reminder.bill_name}", date=datetime.now()
        ))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/process-recurring', methods=['POST'])
@login_required
def process_recurring():
    try:
        today    = datetime.now().date()
        recurrings = RecurringExpense.query.filter_by(
            user_id=current_user.id, active=True).all()
        processed = 0
        for r in recurrings:
            if r.next_date.date() <= today:
                db.session.add(Expense(
                    user_id=current_user.id, amount=r.amount,
                    category=r.category,
                    description=f"[Recurring] {r.description}", date=datetime.now()
                ))
                delta = {'daily': timedelta(days=1), 'weekly': timedelta(weeks=1),
                         'monthly': timedelta(days=30)}.get(r.frequency, timedelta(days=0))
                r.next_date += delta
                processed += 1
        db.session.commit()
        return jsonify({'success': True, 'processed': processed})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error='Internal server error'), 500


# ============================================================
# STARTUP
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # FIX 5: demo user now includes a proper password_hash
        if not User.query.filter_by(username='demo').first():
            db.session.add(User(
                username      = 'demo',
                email         = 'demo@moneymate.com',
                password_hash = generate_password_hash('demo1234'),
                monthly_income= 50000
            ))
            db.session.commit()
            print("✅ Demo user created! Login: demo@moneymate.com / demo1234")

    print("\n" + "="*50)
    print("🚀 MoneyMate starting on http://localhost:5000")
    print("🤖 AI:    " + ("Enabled ✅" if genai else "Disabled ⚠️"))
    print("💌 Email: " + ("Configured ✅" if MAIL_CONFIGURED else "Not configured ⚠️"))
    print("="*50 + "\n")

    app.run(debug=True, port=5000)