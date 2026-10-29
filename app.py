import os, sqlite3, csv, io
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-deploying")
DB = os.environ.get("FINWISE_DB_PATH", os.path.join(BASE_DIR, "finwise.db"))

def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings(
      user_id INTEGER PRIMARY KEY, monthly_budget REAL NOT NULL DEFAULT 10000,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS transactions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      type TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL,
      note TEXT DEFAULT '', created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS goals(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      name TEXT NOT NULL, target REAL NOT NULL, saved REAL NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    c.commit(); c.close()

def current_user():
    return session.get("user_id")

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in first."), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/")
def home():
    if not current_user(): return redirect(url_for("login"))
    return render_template("index.html", name=session.get("name", "there"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not name or not email or len(password) < 8:
            flash("Enter your name and email, and use a password with at least 8 characters.", "error")
            return render_template("auth.html", mode="signup")
        c=connect()
        try:
            cur=c.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                (name,email,generate_password_hash(password),datetime.now().isoformat(timespec="seconds")))
            uid=cur.lastrowid
            c.execute("INSERT INTO settings(user_id,monthly_budget) VALUES(?,10000)",(uid,))
            c.commit()
            session["user_id"]=uid; session["name"]=name
            return redirect(url_for("home"))
        except sqlite3.IntegrityError:
            flash("An account with this email already exists. Please log in.", "error")
        finally: c.close()
    return render_template("auth.html", mode="signup")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        c=connect(); user=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone(); c.close()
        if user and check_password_hash(user["password_hash"],password):
            session["user_id"]=user["id"]; session["name"]=user["name"]
            return redirect(url_for("home"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/api/summary")
@login_required
def summary():
    c=connect(); uid=current_user()
    income=c.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='income'",(uid,)).fetchone()[0]
    expense=c.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='expense'",(uid,)).fetchone()[0]
    row=c.execute("SELECT monthly_budget FROM settings WHERE user_id=?",(uid,)).fetchone()
    budget=float(row["monthly_budget"]) if row else 10000
    c.close()
    return jsonify(income=income,expense=expense,budget=budget,remaining=budget-expense,used=(expense/budget*100 if budget else 0))

@app.get("/api/transactions")
@login_required
def list_transactions():
    c=connect()
    rows=c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 200",(current_user(),)).fetchall()
    c.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/transactions")
@login_required
def add_transaction():
    d=request.get_json(silent=True) or {}
    typ=d.get("type"); category=(d.get("category") or "Other").strip()
    try: amount=float(d.get("amount",0))
    except (TypeError,ValueError): amount=0
    if typ not in ("income","expense") or amount<=0 or amount>1000000000:
        return jsonify(error="Enter a valid transaction type and amount."),400
    c=connect(); c.execute("INSERT INTO transactions(user_id,type,category,amount,note,created_at) VALUES(?,?,?,?,?,?)",
        (current_user(),typ,category,amount,(d.get("note") or "").strip()[:180],datetime.now().isoformat(timespec="seconds")))
    c.commit(); c.close()
    return jsonify(ok=True)

@app.delete("/api/transactions/<int:tid>")
@login_required
def delete_transaction(tid):
    c=connect(); c.execute("DELETE FROM transactions WHERE id=? AND user_id=?",(tid,current_user()))
    c.commit(); c.close(); return jsonify(ok=True)

@app.post("/api/budget")
@login_required
def set_budget():
    try: amount=float((request.get_json(silent=True) or {}).get("amount",0))
    except (TypeError,ValueError): amount=0
    if amount<=0 or amount>1000000000:return jsonify(error="Enter a valid budget."),400
    c=connect(); c.execute("INSERT INTO settings(user_id,monthly_budget) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET monthly_budget=excluded.monthly_budget",(current_user(),amount))
    c.commit(); c.close(); return jsonify(ok=True)

@app.get("/api/advisor")
@login_required
def advisor():
    uid=current_user(); c=connect()
    rows=c.execute("SELECT category,SUM(amount) total FROM transactions WHERE user_id=? AND type='expense' GROUP BY category ORDER BY total DESC",(uid,)).fetchall()
    income=c.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='income'",(uid,)).fetchone()[0]
    expense=c.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='expense'",(uid,)).fetchone()[0]
    budget=c.execute("SELECT monthly_budget FROM settings WHERE user_id=?",(uid,)).fetchone()["monthly_budget"]
    c.close(); remaining=budget-expense; tips=[]
    if not rows:
        return jsonify(headline="Your money coach is ready",message="Add a few transactions to get insights based on your own records.",tips=["Set a realistic monthly budget.","Record expenses consistently to spot patterns."])
    top=rows[0]; ratio=expense/income*100 if income else None
    tips.append(f"Budget remaining: ₹{remaining:,.0f}." if remaining>=0 else f"You are ₹{abs(remaining):,.0f} over budget. Review {top['category']} spending first.")
    tips.append(f"Your largest recorded expense category is {top['category']} (₹{top['total']:,.0f}).")
    if ratio is not None: tips.append(f"Recorded expenses are {ratio:.0f}% of recorded income.")
    else: tips.append("Add income entries too, so you can compare spending with income.")
    return jsonify(headline="Your personal finance snapshot",message="These suggestions are generated from your own recorded transactions.",tips=tips)

@app.get("/api/goals")
@login_required
def list_goals():
    c=connect(); rows=c.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC",(current_user(),)).fetchall(); c.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/goals")
@login_required
def add_goal():
    d=request.get_json(silent=True) or {}; name=(d.get("name") or "").strip()
    try: target=float(d.get("target",0))
    except (TypeError,ValueError): target=0
    if not name or target<=0:return jsonify(error="Enter a goal name and positive target."),400
    c=connect(); c.execute("INSERT INTO goals(user_id,name,target,saved,created_at) VALUES(?,?,?,0,?)",(current_user(),name[:80],target,datetime.now().isoformat(timespec="seconds"))); c.commit(); c.close()
    return jsonify(ok=True)

@app.post("/api/goals/<int:gid>/contribute")
@login_required
def contribute(gid):
    d=request.get_json(silent=True) or {}
    try: amount=float(d.get("amount",0))
    except (TypeError,ValueError): amount=0
    if amount<=0:return jsonify(error="Enter a positive amount."),400
    c=connect(); row=c.execute("SELECT id,target,saved FROM goals WHERE id=? AND user_id=?",(gid,current_user())).fetchone()
    if not row: c.close(); return jsonify(error="Goal not found."),404
    c.execute("UPDATE goals SET saved=? WHERE id=? AND user_id=?",(row["saved"]+amount,gid,current_user()))
    c.commit(); c.close(); return jsonify(ok=True)

@app.delete("/api/goals/<int:gid>")
@login_required
def delete_goal(gid):
    c=connect(); c.execute("DELETE FROM goals WHERE id=? AND user_id=?",(gid,current_user())); c.commit(); c.close()
    return jsonify(ok=True)

@app.post("/api/import-csv")
@login_required
def import_csv():
    f=request.files.get("file")
    if not f: return jsonify(error="Choose a CSV file."),400
    try:
        text=f.stream.read().decode("utf-8-sig")
        reader=csv.DictReader(io.StringIO(text))
        if not reader.fieldnames: return jsonify(error="CSV needs a header row."),400
        fields={x.strip().lower():x for x in reader.fieldnames}
        amount_col=next((fields[k] for k in ("amount","value","debit","credit") if k in fields),None)
        type_col=next((fields[k] for k in ("type","transaction type","kind") if k in fields),None)
        category_col=next((fields[k] for k in ("category","merchant","description","details") if k in fields),None)
        date_col=next((fields[k] for k in ("date","transaction date","created_at") if k in fields),None)
        if not amount_col: return jsonify(error="CSV needs an Amount column. Optional columns: Type, Category/Description, Date, Note."),400
        c=connect(); count=0
        for r in reader:
            try: amount=abs(float((r.get(amount_col) or "").replace(",","").strip()))
            except (ValueError,AttributeError): continue
            if amount<=0: continue
            rawtype=(r.get(type_col) or "").strip().lower() if type_col else ""
            typ="income" if rawtype in ("income","credit","cr") else "expense"
            category=(r.get(category_col) or "Other").strip()[:80] if category_col else "Other"
            category=category.title() if category else "Other"
            dt=(r.get(date_col) or "").strip() if date_col else ""
            c.execute("INSERT INTO transactions(user_id,type,category,amount,note,created_at) VALUES(?,?,?,?,?,?)",
                (current_user(),typ,category,amount,"Imported from CSV",dt or datetime.now().isoformat(timespec="seconds")))
            count+=1
        c.commit(); c.close()
        return jsonify(ok=True,imported=count)
    except Exception:
        return jsonify(error="Could not read this CSV. Please save it as UTF-8 CSV and try again."),400

init_db()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5000")), debug=False)
