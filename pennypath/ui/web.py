"""
web.py  —  PennyPath web app (Flask JSON API + single-page UI in templates/).
Run from the project root:  python run_web.py   →  http://localhost:5000
"""
import datetime, io, base64, json, os, re, secrets

import matplotlib
matplotlib.use('Agg')   # headless — must be before any pyplot import

from flask import Flask, Response, jsonify, request, session, render_template, stream_with_context

from pennypath import auth
from pennypath.paths import SECRET_KEY_FILE
from pennypath.assistant import chat_guard
from pennypath.assistant import tips
from pennypath.finance.affordability     import check as loan_check
from pennypath.finance.debt_planner      import Debt, compare
from pennypath.database          import Database, DatabaseNotConfigured
from pennypath.finance.expenses          import Needs, Wants, CATEGORIES, FREQUENCIES, from_rows, summarize
from pennypath.ml.budget            import BudgetAdvisor
from pennypath.ml.home_savings_plan import HomeSavingsPlan, REGIONS


def _secret_key() -> str:
    """SECRET_KEY env var if set; otherwise a random key persisted to a local
    (git-ignored) file so sessions survive restarts without a hard-coded secret."""
    if os.environ.get('SECRET_KEY'):
        return os.environ['SECRET_KEY']
    path = SECRET_KEY_FILE
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app = Flask(__name__)
app.secret_key = _secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

db        = Database()
advisor   = BudgetAdvisor()
advisor.train()          # loads cached models; trains (~30 s) only on first run
home_plan = HomeSavingsPlan()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _uid():
    return session.get('user_id')

def _monthly_income(weekly_wage: float) -> float:
    return weekly_wage * 52 / 12

def _load(uid: int) -> dict:
    s = db.load_session(uid)
    expenses = from_rows(s['expenses'])
    needs_total, wants_total = summarize(expenses)
    return dict(
        checking=s['checking'], savings=s['savings'],
        wage=s['wage'], debt=s['debt'],
        expenses=expenses, needs_total=needs_total, wants_total=wants_total,
    )

def _num(d, key, *, minimum=None, positive=False, integer=False, default=None):
    """Read a numeric field from a JSON body. Raises ValueError with a user-facing message."""
    v = d.get(key, default)
    if v is None or v == '':
        raise ValueError(f'{key.replace("_", " ").capitalize()} is required')
    try:
        n = int(v) if integer else float(v)
    except (ValueError, TypeError):
        raise ValueError(f'{key.replace("_", " ").capitalize()} must be a number')
    if n != n or n in (float('inf'), float('-inf')):
        raise ValueError(f'{key.replace("_", " ").capitalize()} must be a number')
    if positive and n <= 0:
        raise ValueError(f'{key.replace("_", " ").capitalize()} must be greater than zero')
    if minimum is not None and n < minimum:
        raise ValueError(f'{key.replace("_", " ").capitalize()} must be at least {minimum}')
    return n

def auth_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if not _uid():
            return jsonify(error='Not authenticated'), 401
        return f(*a, **kw)
    return wrapper

def _make_chart(col, target_year, savings_balance, down_pct):
    """Render the forecast chart and return it as a base64 PNG string."""
    import matplotlib.pyplot as plt
    fig = home_plan.figure(col, target_year, savings_balance, down_pct, dark=True)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ── SPA entry point ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ── Auth ───────────────────────────────────────────────────────────────────────

def _start_session(user: dict):
    session.clear()
    session['user_id'] = user['id']; session['username'] = user['username']
    return jsonify(id=user['id'], username=user['username'], onboarded=user['onboarded'])

@app.route('/api/auth/register', methods=['POST'])
def register():
    d = request.get_json(silent=True) or {}
    user, error = auth.register(db, str(d.get('username', '')),
                                str(d.get('password', '')), str(d.get('confirm', '')))
    if error:
        return jsonify(error=error), 409 if 'taken' in error else 400
    return _start_session(user)

@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json(silent=True) or {}
    user = auth.authenticate(db, str(d.get('username', '')).strip(), str(d.get('password', '')))
    if user is None:
        return jsonify(error=auth.LOGIN_FAILED), 401
    return _start_session(user)

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify(ok=True)

@app.route('/api/auth/me')
def me():
    if not _uid(): return jsonify(error='Not authenticated'), 401
    row = db.get_user(session.get('username'))
    onboarded = bool(row[3]) if row else False
    return jsonify(id=_uid(), username=session.get('username'), onboarded=onboarded)


# ── Session ────────────────────────────────────────────────────────────────────

@app.route('/api/session')
@auth_required
def get_session():
    st = _load(_uid())
    return jsonify(
        checking=st['checking'], savings=st['savings'],
        wage=st['wage'], monthly_income=_monthly_income(st['wage']), debt=st['debt'],
        needs_total=st['needs_total'], wants_total=st['wants_total'],
        expenses=[e.to_dict() for e in st['expenses']],
    )


# ── Onboarding ─────────────────────────────────────────────────────────────────

@app.route('/api/onboarding', methods=['POST'])
@auth_required
def onboarding():
    d = request.get_json(silent=True) or {}; uid = _uid()
    try:
        wage    = _num(d, 'wage', positive=True)
        savings = _num(d, 'savings', minimum=0, default=0)
        debt    = _num(d, 'debt', minimum=0, default=0)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db.save_wage(wage, uid)
    db.save_account('savings', savings, uid)
    db.save_debt(debt, uid)
    db.mark_onboarded(uid)
    return jsonify(ok=True)


# ── Accounts ───────────────────────────────────────────────────────────────────

@app.route('/api/accounts/<acct>', methods=['POST'])
@auth_required
def update_account(acct):
    if acct not in ('checking', 'savings'):
        return jsonify(error='Unknown account'), 400
    d = request.get_json(silent=True) or {}
    try:
        bal = _num(d, 'balance', minimum=0)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db.save_account(acct, bal, _uid())
    return jsonify(**{acct: bal})


# ── Account management ─────────────────────────────────────────────────────────

PAY_PERIODS_PER_YEAR = {'weekly': 52, 'biweekly': 26, 'monthly': 12, 'yearly': 1}
RISK_LEVELS = ('conservative', 'moderate', 'aggressive')
GOALS = ('build emergency fund', 'pay off debt', 'buy a home', 'save for retirement',
         'grow investments', 'save for education', 'other')

def _clean_text(d, key, max_len=100):
    return str(d.get(key) or '').strip()[:max_len]

def _opt_int(d, key, lo, hi, label):
    """Parse an optional integer field; blank means None. Raises ValueError with a message."""
    v = d.get(key)
    if v in (None, ''):
        return None
    try:
        n = int(v)
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be a whole number')
    if not lo <= n <= hi:
        raise ValueError(f'{label} must be between {lo} and {hi}')
    return n

@app.route('/api/profile')
@auth_required
def get_profile():
    uid = _uid()
    prof = db.load_profile(uid)
    weekly = db.load_wage(uid)
    periods = PAY_PERIODS_PER_YEAR.get(prof['pay_frequency'], 52)
    return jsonify(
        username=session.get('username'), profile=prof,
        finances=dict(pay_amount=weekly * 52 / periods, pay_frequency=prof['pay_frequency'],
                      weekly_wage=weekly, checking=db.load_account('checking', uid),
                      savings=db.load_account('savings', uid), debt=db.load_debt(uid),
                      debt_itemized=bool(db.load_debts(uid))),
    )

@app.route('/api/profile', methods=['PUT'])
@auth_required
def update_profile():
    d = request.get_json(silent=True) or {}
    try:
        fields = dict(
            full_name      = _clean_text(d, 'full_name'),
            email          = _clean_text(d, 'email', 254),
            occupation     = _clean_text(d, 'occupation'),
            state          = _clean_text(d, 'state', 50),
            age            = _opt_int(d, 'age', 13, 120, 'Age'),
            household_size = _opt_int(d, 'household_size', 1, 20, 'Household size'),
            primary_goal   = _clean_text(d, 'primary_goal'),
            risk_tolerance = _clean_text(d, 'risk_tolerance'),
        )
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if fields['email'] and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', fields['email']):
        return jsonify(error='Enter a valid email address'), 400
    if fields['primary_goal'] and fields['primary_goal'] not in GOALS:
        return jsonify(error='Unknown goal'), 400
    if fields['risk_tolerance'] and fields['risk_tolerance'] not in RISK_LEVELS:
        return jsonify(error='Unknown risk tolerance'), 400
    db.save_profile(_uid(), fields)
    return jsonify(ok=True, profile=db.load_profile(_uid()))

@app.route('/api/profile/finances', methods=['PUT'])
@auth_required
def update_finances():
    d = request.get_json(silent=True) or {}
    freq = d.get('pay_frequency', 'weekly')
    if freq not in PAY_PERIODS_PER_YEAR:
        return jsonify(error='Unknown pay frequency'), 400
    try:
        pay      = _num(d, 'pay_amount', positive=True)
        checking = _num(d, 'checking', minimum=0, default=0)
        savings  = _num(d, 'savings', minimum=0, default=0)
        debt     = _num(d, 'debt', minimum=0, default=0)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    uid = _uid()
    db.save_wage(pay * PAY_PERIODS_PER_YEAR[freq] / 52, uid)   # stored as weekly
    db.save_profile(uid, {'pay_frequency': freq})
    db.save_account('checking', checking, uid)
    db.save_account('savings', savings, uid)
    if not db.load_debts(uid):   # with itemized debts, the total comes from the Debt Plan
        db.save_debt(debt, uid)
    return jsonify(ok=True)

@app.route('/api/auth/password', methods=['POST'])
@auth_required
def change_password():
    d = request.get_json(silent=True) or {}
    cur, new, conf = (str(d.get(k, '')) for k in ('current', 'new', 'confirm'))
    if not auth.verify_password(cur, db.get_password_hash(_uid()) or ''):
        return jsonify(error='Current password is incorrect'), 400
    error = auth.validate_new_password(new, conf)
    if error:
        return jsonify(error=error), 400
    db.update_password(_uid(), auth.hash_password(new))
    return jsonify(ok=True)


# ── Expenses ───────────────────────────────────────────────────────────────────

@app.route('/api/expenses', methods=['GET'])
@auth_required
def get_expenses():
    st = _load(_uid())
    return jsonify(expenses=[e.to_dict() for e in st['expenses']])

def _parse_expense(d: dict) -> tuple:
    """Validate an expense body → (category, subcategory, name, amount, frequency)."""
    name = str(d.get('name', '')).strip()[:100]
    cat  = d.get('category')
    sub  = d.get('subcategory', 'other')
    freq = d.get('frequency', 'Monthly')
    if not name:                        raise ValueError('Name is required')
    if cat not in CATEGORIES:           raise ValueError('Category must be needs or wants')
    if sub not in CATEGORIES[cat].SUBCATEGORIES: raise ValueError('Unknown subcategory')
    if freq not in FREQUENCIES:         raise ValueError('Unknown frequency')
    return cat, sub, name, _num(d, 'amount', positive=True), freq

@app.route('/api/expenses', methods=['POST'])
@auth_required
def add_expense():
    try:
        fields = _parse_expense(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify(error=str(e)), 400
    db.save_expense(*fields, _uid())
    return jsonify(ok=True)

@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
@auth_required
def edit_expense(expense_id):
    try:
        fields = _parse_expense(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not db.update_expense(expense_id, _uid(), *fields):
        return jsonify(error='Expense not found'), 404
    return jsonify(ok=True)

@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
@auth_required
def delete_expense(expense_id):
    if not db.delete_expense(expense_id, _uid()):
        return jsonify(error='Expense not found'), 404
    return jsonify(ok=True)

@app.route('/api/expenses', methods=['DELETE'])
@auth_required
def clear_expenses():
    db.clear_expenses(_uid())
    return jsonify(ok=True)


# ── Budget AI ──────────────────────────────────────────────────────────────────

@app.route('/api/advisor')
@auth_required
def run_advisor():
    st = _load(_uid())
    income = _monthly_income(st['wage'])
    if income <= 0:
        return jsonify(error='Set your weekly wage first'), 400
    prof = db.load_profile(_uid())
    rec = advisor.recommend(income, st['needs_total'], st['wants_total'], st['expenses'],
                            household_size=prof['household_size'], age=prof['age'])
    if not rec:
        return jsonify(error='Could not generate recommendation'), 500
    return jsonify(rec)

@app.route('/api/models')
@auth_required
def model_cards():
    """Evaluation metrics for both ML models, for the in-app model cards."""
    return jsonify(budget=advisor.model_card(),
                   home=home_plan.model_card() if home_plan.trained else None)


# ── Debt Plan ──────────────────────────────────────────────────────────────────

@app.route('/api/debts')
@auth_required
def list_debts():
    return jsonify(debts=db.load_debts(_uid()))

@app.route('/api/debts', methods=['POST'])
@auth_required
def add_debt():
    d = request.get_json(silent=True) or {}
    name = str(d.get('name', '')).strip()[:60]
    try:
        if not name:
            raise ValueError('Name is required')
        balance = _num(d, 'balance', positive=True)
        apr     = _num(d, 'apr', minimum=0)
        minimum = _num(d, 'min_payment', positive=True)
        if apr > 100:
            raise ValueError('APR must be 100% or less')
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if len(db.load_debts(_uid())) >= 25:
        return jsonify(error='You can track up to 25 debts'), 400
    return jsonify(id=db.add_debt(_uid(), name, balance, apr, minimum))

@app.route('/api/debts/<int:debt_id>', methods=['DELETE'])
@auth_required
def delete_debt(debt_id):
    if not db.delete_debt(debt_id, _uid()):
        return jsonify(error='Debt not found'), 404
    return jsonify(ok=True)

@app.route('/api/debts/plan', methods=['POST'])
@auth_required
def debt_plan():
    d = request.get_json(silent=True) or {}
    try:
        extra = _num(d, 'extra', minimum=0, default=0)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    debts = [Debt(x['name'], x['balance'], x['apr'], x['min_payment'])
             for x in db.load_debts(_uid())]
    if not debts:
        return jsonify(error='Add at least one debt first'), 400
    return jsonify(compare(debts, extra))


# ── Tips ───────────────────────────────────────────────────────────────────────

@app.route('/api/tips')
@auth_required
def search_tips():
    q = request.args.get('q', '').strip()[:200]
    lib = tips.library()
    if not q:
        return jsonify(results=[{**t, 'score': None} for t in lib.tips[:8]], total=len(lib.tips))
    return jsonify(results=lib.search(q, k=8), total=len(lib.tips))


# ── Affordability ──────────────────────────────────────────────────────────────

@app.route('/api/affordability', methods=['POST'])
@auth_required
def affordability():
    d = request.get_json(silent=True) or {}
    try:
        inc  = _num(d, 'income', positive=True)
        ammt = _num(d, 'amount', positive=True)
        rate = _num(d, 'rate', minimum=0)
        mnth = _num(d, 'months', positive=True, integer=True)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if mnth > 600:
        return jsonify(error='Loan duration must be 600 months or fewer'), 400
    return jsonify(loan_check(inc, ammt, rate, mnth))


# ── Home Savings Plan ──────────────────────────────────────────────────────────

def _parse_home_inputs(d: dict) -> tuple:
    """Validate region/year/down payment/savings shared by the plan and chart routes."""
    col = d.get('region')
    if col not in REGIONS:
        raise ValueError('Unknown region')
    year = _num(d, 'year', integer=True)
    this_year = datetime.date.today().year
    if not this_year <= year <= this_year + 30:
        raise ValueError(f'Target year must be between {this_year} and {this_year + 30}')
    down_pct = _num(d, 'down_pct', positive=True)
    if down_pct > 1:
        raise ValueError('Down payment must be a fraction between 0 and 1')
    return col, year, down_pct, _num(d, 'savings', minimum=0, default=0)

@app.route('/api/home-plan', methods=['POST'])
@auth_required
def home_plan_route():
    if not home_plan.trained:
        return jsonify(error='fredgraph.csv not found — feature unavailable'), 503
    d = request.get_json(silent=True) or {}
    try:
        col, year, down_pct, savings = _parse_home_inputs(d)
        rate      = _num(d, 'rate', minimum=0) / 100
        loan_term = _num(d, 'loan_term', integer=True, positive=True)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if rate > 0.3 or loan_term > 50:
        return jsonify(error='Interest rate or loan term is out of range'), 400

    months = home_plan.months_until(year)
    fc     = home_plan.forecast(col, year)
    plan   = home_plan.savings_plan(fc['price'], down_pct, savings, months, rate, loan_term)
    latest, as_of = home_plan.latest(col)
    income = _monthly_income(db.load_wage(_uid()))
    return jsonify(price=fc['price'], low=fc['low'], high=fc['high'], model=fc['model'],
                   latest_price=latest, latest_date=as_of, plan=plan, months=months,
                   region=REGIONS[col], year=year, savings=savings, monthly_income=income)

@app.route('/api/home-plan/chart', methods=['POST'])
@auth_required
def home_plan_chart():
    if not home_plan.trained:
        return jsonify(error='Chart unavailable'), 503
    try:
        col, year, down_pct, savings = _parse_home_inputs(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(image=_make_chart(col, year, savings, down_pct))


# ── Finance Chat (Ollama streaming) ───────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
@auth_required
def chat():
    d        = request.get_json(silent=True) or {}
    messages = chat_guard.sanitize_history(d.get('messages', []))
    if not messages or messages[-1]['role'] != 'user':
        return jsonify(error='No question provided'), 400

    # System prompt is built here from the DB — never trusted from the client.
    st = _load(_uid())
    snapshot = dict(income=_monthly_income(st['wage']), needs=st['needs_total'], wants=st['wants_total'],
                    checking=st['checking'], savings=st['savings'], debt=st['debt'],
                    profile=db.load_profile(_uid()), debts=db.load_debts(_uid()))

    def generate():
        try:
            for token in chat_guard.stream_reply(messages, snapshot):
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            # Full details go to the server log; the user gets a friendly message.
            app.logger.exception('Chat failed')
            yield f"data: {json.dumps({'error': 'The assistant hit a problem mid-answer. Please try again.'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Errors ─────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify(error='Not found'), 404
    return e

@app.errorhandler(500)
def server_error(e):
    # Never leak stack traces to the client; details stay in the server log.
    return jsonify(error='Something went wrong on our end. Please try again.'), 500


def main():
    try:
        db.ensure_ready()
    except DatabaseNotConfigured as e:
        raise SystemExit(f"\n{e}\n")
    # The Werkzeug debugger allows arbitrary code execution — opt in explicitly, never by default.
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    main()
