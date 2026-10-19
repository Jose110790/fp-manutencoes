import os, sqlite3, secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import qrcode

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FP_DB_PATH", os.path.join(APP_DIR, "fp_manutencoes.db"))
UPLOAD_DIR = os.environ.get("FP_UPLOAD_DIR", os.path.join(APP_DIR, "static", "uploads"))
QR_DIR = os.environ.get("FP_QR_DIR", os.path.join(APP_DIR, "static", "qrcodes"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FP_SECRET_KEY", "dev-only-change-before-publishing")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FP_ENV", "development").lower() == "production"
if os.environ.get("FP_ENV", "development").lower() == "production" and not os.environ.get("FP_SECRET_KEY"):
    raise RuntimeError("FP_SECRET_KEY precisa ser definida no ambiente de produção.")
ALLOWED = {"png", "jpg", "jpeg", "webp", "pdf"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT DEFAULT '',
          role TEXT NOT NULL, email TEXT DEFAULT '', username TEXT, password_hash TEXT,
          active INTEGER DEFAULT 1, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS areas (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT NOT NULL,
          category TEXT NOT NULL, description TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT NOT NULL,
          category TEXT NOT NULL, area_id INTEGER, brand TEXT DEFAULT '', model TEXT DEFAULT '',
          serial_number TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT NOT NULL,
          FOREIGN KEY(area_id) REFERENCES areas(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS routines (
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, area_id INTEGER,
          frequency TEXT NOT NULL, procedure TEXT NOT NULL, assigned_to INTEGER,
          next_due TEXT DEFAULT '', active INTEGER DEFAULT 1, created_at TEXT NOT NULL,
          FOREIGN KEY(area_id) REFERENCES areas(id) ON DELETE SET NULL,
          FOREIGN KEY(assigned_to) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS work_orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, title TEXT NOT NULL,
          description TEXT DEFAULT '', area_id INTEGER, asset_id INTEGER, priority TEXT NOT NULL,
          status TEXT NOT NULL, requester TEXT DEFAULT '', assigned_to INTEGER,
          due_date TEXT DEFAULT '', created_at TEXT NOT NULL, completed_at TEXT DEFAULT '',
          FOREIGN KEY(area_id) REFERENCES areas(id) ON DELETE SET NULL,
          FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE SET NULL,
          FOREIGN KEY(assigned_to) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS quotes (
          id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE NOT NULL, work_order_id INTEGER NOT NULL,
          provider_name TEXT NOT NULL, provider_phone TEXT DEFAULT '', service_description TEXT NOT NULL,
          labor REAL DEFAULT 0, freight REAL DEFAULT 0, material_mode TEXT NOT NULL,
          lead_time TEXT DEFAULT '', validity TEXT DEFAULT '', warranty TEXT DEFAULT '', notes TEXT DEFAULT '',
          status TEXT DEFAULT 'Recebido', created_at TEXT NOT NULL,
          FOREIGN KEY(work_order_id) REFERENCES work_orders(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS quote_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id INTEGER NOT NULL, name TEXT NOT NULL,
          specification TEXT DEFAULT '', quantity REAL NOT NULL, unit TEXT NOT NULL,
          unit_price REAL NOT NULL, photo TEXT DEFAULT '',
          FOREIGN KEY(quote_id) REFERENCES quotes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS routine_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, routine_id INTEGER NOT NULL, done_by TEXT NOT NULL,
          notes TEXT DEFAULT '', completed_at TEXT NOT NULL,
          FOREIGN KEY(routine_id) REFERENCES routines(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS attachments (
          id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_id INTEGER, quote_id INTEGER,
          filename TEXT NOT NULL, original_name TEXT DEFAULT '', created_at TEXT NOT NULL,
          FOREIGN KEY(work_order_id) REFERENCES work_orders(id) ON DELETE CASCADE,
          FOREIGN KEY(quote_id) REFERENCES quotes(id) ON DELETE CASCADE
        );
        """)
        # Migrate existing installations without deleting user records.
        user_columns = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
        if "username" not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN username TEXT")
        if "password_hash" not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL AND username <> ''")
        if not c.execute("SELECT id FROM users LIMIT 1").fetchone():
            c.execute("INSERT INTO users(name,role,created_at) VALUES(?,?,?)",
                      ("Gestora do buffet","Gestora",datetime.now().isoformat(timespec="seconds")))
            c.execute("INSERT INTO users(name,role,created_at) VALUES(?,?,?)",
                      ("Zelador","Zelador",datetime.now().isoformat(timespec="seconds")))
        # Bootstrap the first individual manager account using the secret already configured in Render.
        admin_password = os.environ.get("FP_ADMIN_PASSWORD", "").strip()
        admin_username = os.environ.get("FP_ADMIN_USERNAME", "gestora").strip().lower()
        if admin_password and not c.execute("SELECT id FROM users WHERE password_hash IS NOT NULL LIMIT 1").fetchone():
            existing = c.execute("SELECT id FROM users WHERE role IN ('Gestora','Administrador') ORDER BY id LIMIT 1").fetchone()
            if existing:
                c.execute("UPDATE users SET username=?, password_hash=? WHERE id=?",
                          (admin_username, generate_password_hash(admin_password), existing["id"]))
            else:
                c.execute("INSERT INTO users(name,role,username,password_hash,created_at) VALUES(?,?,?,?,?)",
                          ("Gestora principal", "Gestora", admin_username, generate_password_hash(admin_password), datetime.now().isoformat(timespec="seconds")))
        if not c.execute("SELECT id FROM areas LIMIT 1").fetchone():
            defaults = [("Salão principal","Salão"),("Cozinha","Cozinha"),("Banheiro feminino","Banheiro"),("Área dos brinquedos","Recreação")]
            for i,(n,cat) in enumerate(defaults,1):
                code=f"AMB-{i:03d}"
                c.execute("INSERT INTO areas(code,name,category,created_at) VALUES(?,?,?,?)",
                          (code,n,cat,datetime.now().isoformat(timespec="seconds")))
        # Add codes/QRs to existing items if missing
        for table,prefix in (("areas","AMB"),("assets","EQP")):
            rows=c.execute(f"SELECT id,code FROM {table}").fetchall()
            for r in rows:
                if not r["code"]:
                    c.execute(f"UPDATE {table} SET code=? WHERE id=?",(f"{prefix}-{r['id']:03d}",r["id"]))

init_db()

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        current = getrow("SELECT id, name, role, username, active FROM users WHERE id=?", (session["user_id"],))
        if not current or not current["active"]:
            session.clear()
            return redirect(url_for("login"))
        session["logged_in"] = True
        session["role"] = current["role"]
        session["user_name"] = current["name"]
        return f(*args, **kwargs)
    return wrapped

def manager_required(f):
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("role") not in ("Gestora", "Administrador"):
            abort(403)
        return f(*args, **kwargs)
    return wrapped

def make_qr(code, path):
    # QR code links to the record page on the deployed/local server
    url = request.url_root.rstrip("/") + path
    img = qrcode.make(url)
    img.save(os.path.join(QR_DIR, f"{code}.png"))

def rowlist(query, args=()):
    with db() as c:
        return c.execute(query,args).fetchall()

def getrow(query,args=()):
    with db() as c:
        return c.execute(query,args).fetchone()

def save_upload(fileobj):
    if not fileobj or not fileobj.filename:
        return ""
    ext=fileobj.filename.rsplit(".",1)[-1].lower() if "." in fileobj.filename else ""
    if ext not in ALLOWED:
        raise ValueError("Formato de arquivo não permitido. Use JPG, PNG, WEBP ou PDF.")
    name=secrets.token_hex(8)+"_"+secure_filename(fileobj.filename)
    fileobj.save(os.path.join(UPLOAD_DIR,name))
    return name

@app.context_processor
def globals_for_templates():
    return {"today": date.today().isoformat(), "current_role": session.get("role"), "current_user_name": session.get("user_name")}

@app.route("/healthz")
def healthz():
    return {"status": "ok", "app": "FP Manutenções"}, 200

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = getrow("SELECT * FROM users WHERE lower(username)=? AND active=1", (username,))
        if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["logged_in"] = True
            session["role"] = user["role"]
            session["user_name"] = user["name"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Usuário ou senha inválidos. Confira seus dados ou peça ajuda à gestora.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    stats = {
        "users": getrow("SELECT COUNT(*) n FROM users")["n"],
        "areas": getrow("SELECT COUNT(*) n FROM areas")["n"],
        "assets": getrow("SELECT COUNT(*) n FROM assets")["n"],
        "open": getrow("SELECT COUNT(*) n FROM work_orders WHERE status NOT IN ('Concluído','Cancelado')")["n"],
        "quotes": getrow("SELECT COUNT(*) n FROM quotes WHERE status='Recebido'")["n"],
        "routines": getrow("SELECT COUNT(*) n FROM routines WHERE active=1")["n"],
    }
    recent = rowlist("""SELECT w.*, a.name area_name, s.name asset_name FROM work_orders w
      LEFT JOIN areas a ON a.id=w.area_id LEFT JOIN assets s ON s.id=w.asset_id
      ORDER BY w.id DESC LIMIT 6""")
    return render_template("dashboard.html", stats=stats, recent=recent)

@app.route("/users", methods=["GET","POST"])
@manager_required
def users():
    allowed_roles = {"Gestora", "Zelador", "Funcionário", "Técnico de manutenção"}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "Funcionário")
        email = request.form.get("email", "").strip().lower()
        if not name or not username or not password:
            flash("Preencha nome, usuário e senha inicial.")
        elif len(username) < 3 or any(ch.isspace() for ch in username):
            flash("O usuário deve ter pelo menos 3 caracteres e não pode conter espaços.")
        elif len(password) < 10:
            flash("A senha inicial precisa ter pelo menos 10 caracteres.")
        elif role not in allowed_roles:
            flash("Perfil inválido.")
        elif getrow("SELECT id FROM users WHERE lower(username)=?", (username,)):
            flash("Esse nome de usuário já está cadastrado.")
        else:
            with db() as c:
                c.execute("INSERT INTO users(name,phone,role,email,username,password_hash,created_at) VALUES(?,?,?,?,?,?,?)",
                    (name, request.form.get("phone", "").strip(), role, email, username,
                     generate_password_hash(password), datetime.now().isoformat(timespec="seconds")))
            flash(f"Acesso criado para {name}. Entregue o usuário e a senha inicial diretamente à pessoa.")
        return redirect(url_for("users"))
    return render_template("users.html", users=rowlist("SELECT * FROM users ORDER BY id DESC"))

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        user = getrow("SELECT * FROM users WHERE id=?", (session["user_id"],))
        if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], old):
            flash("A senha atual está incorreta.")
        elif len(new) < 10:
            flash("A nova senha precisa ter pelo menos 10 caracteres.")
        elif new != confirm:
            flash("A confirmação da nova senha não confere.")
        else:
            with db() as c:
                c.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), user["id"]))
            session.clear()
            flash("Senha alterada. Entre novamente com a nova senha.")
            return redirect(url_for("login"))
    return render_template("change_password.html")

@app.route("/areas", methods=["GET","POST"])
@login_required
def areas():
    if request.method == "POST" and session.get("role") not in ("Gestora", "Administrador"):
        abort(403)
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if not name: flash("Informe o nome do ambiente.")
        else:
            with db() as c:
                cur=c.execute("INSERT INTO areas(name,category,description,created_at) VALUES(?,?,?,?)",
                  (name,request.form.get("category","Outro"),request.form.get("description","").strip(),datetime.now().isoformat(timespec="seconds")))
                code=f"AMB-{cur.lastrowid:03d}"
                c.execute("UPDATE areas SET code=? WHERE id=?",(code,cur.lastrowid))
            flash("Ambiente cadastrado. QR Code disponível no cadastro.")
        return redirect(url_for("areas"))
    return render_template("areas.html", areas=rowlist("SELECT * FROM areas ORDER BY id DESC"))

@app.route("/areas/<int:area_id>")
@login_required
def area_detail(area_id):
    a=getrow("SELECT * FROM areas WHERE id=?",(area_id,))
    if not a: abort(404)
    make_qr(a["code"],url_for("area_detail",area_id=area_id))
    return render_template("area_detail.html", area=a, assets=rowlist("SELECT * FROM assets WHERE area_id=?",(area_id,)),
      orders=rowlist("SELECT * FROM work_orders WHERE area_id=? ORDER BY id DESC LIMIT 10",(area_id,)))

@app.route("/assets", methods=["GET","POST"])
@login_required
def assets():
    if request.method == "POST" and session.get("role") not in ("Gestora", "Administrador"):
        abort(403)
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if not name: flash("Informe o nome do equipamento.")
        else:
            with db() as c:
                cur=c.execute("""INSERT INTO assets(name,category,area_id,brand,model,serial_number,notes,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""",(name,request.form.get("category","Outro"),
                    request.form.get("area_id") or None,request.form.get("brand","").strip(),
                    request.form.get("model","").strip(),request.form.get("serial_number","").strip(),
                    request.form.get("notes","").strip(),datetime.now().isoformat(timespec="seconds")))
                code=f"EQP-{cur.lastrowid:03d}"
                c.execute("UPDATE assets SET code=? WHERE id=?",(code,cur.lastrowid))
            flash("Equipamento cadastrado. QR Code disponível no cadastro.")
        return redirect(url_for("assets"))
    return render_template("assets.html", assets=rowlist("""SELECT s.*,a.name area_name FROM assets s
      LEFT JOIN areas a ON a.id=s.area_id ORDER BY s.id DESC"""), areas=rowlist("SELECT * FROM areas ORDER BY name"))

@app.route("/assets/<int:asset_id>")
@login_required
def asset_detail(asset_id):
    a=getrow("SELECT s.*, ar.name area_name FROM assets s LEFT JOIN areas ar ON ar.id=s.area_id WHERE s.id=?",(asset_id,))
    if not a: abort(404)
    make_qr(a["code"],url_for("asset_detail",asset_id=asset_id))
    return render_template("asset_detail.html", asset=a,
      orders=rowlist("SELECT * FROM work_orders WHERE asset_id=? ORDER BY id DESC LIMIT 10",(asset_id,)))

@app.route("/orders", methods=["GET","POST"])
@login_required
def orders():
    if request.method=="POST":
        title=request.form.get("title","").strip()
        if not title:
            flash("Informe o serviço.")
            return redirect(url_for("orders"))
        with db() as c:
            cur=c.execute("""INSERT INTO work_orders(title,description,area_id,asset_id,priority,status,requester,assigned_to,due_date,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)""",(title,request.form.get("description","").strip(),request.form.get("area_id") or None,
              request.form.get("asset_id") or None,request.form.get("priority","Normal"),"Aberto",
              request.form.get("requester","Zelador").strip(),request.form.get("assigned_to") or None,
              request.form.get("due_date",""),datetime.now().isoformat(timespec="seconds")))
            code=f"OS-{datetime.now().year}-{cur.lastrowid:04d}"
            c.execute("UPDATE work_orders SET code=? WHERE id=?",(code,cur.lastrowid))
        flash("Ordem de serviço criada.")
        return redirect(url_for("orders"))
    return render_template("orders.html", orders=rowlist("""SELECT w.*,a.name area_name,s.name asset_name,u.name assigned_name
      FROM work_orders w LEFT JOIN areas a ON a.id=w.area_id LEFT JOIN assets s ON s.id=w.asset_id
      LEFT JOIN users u ON u.id=w.assigned_to ORDER BY w.id DESC"""),
      areas=rowlist("SELECT * FROM areas ORDER BY name"), assets=rowlist("SELECT * FROM assets ORDER BY name"),
      users=rowlist("SELECT * FROM users WHERE active=1 ORDER BY name"))

@app.route("/orders/<int:order_id>", methods=["GET","POST"])
@login_required
def order_detail(order_id):
    w=getrow("""SELECT w.*,a.name area_name,s.name asset_name FROM work_orders w
      LEFT JOIN areas a ON a.id=w.area_id LEFT JOIN assets s ON s.id=w.asset_id WHERE w.id=?""",(order_id,))
    if not w: abort(404)
    if request.method=="POST":
        with db() as c:
            c.execute("UPDATE work_orders SET status=?,priority=?,assigned_to=?,due_date=? WHERE id=?",
              (request.form.get("status",w["status"]),request.form.get("priority",w["priority"]),
               request.form.get("assigned_to") or None,request.form.get("due_date",""),order_id))
        flash("Ordem atualizada.")
        return redirect(url_for("order_detail",order_id=order_id))
    quotes=rowlist("SELECT * FROM quotes WHERE work_order_id=? ORDER BY id DESC",(order_id,))
    return render_template("order_detail.html", order=w, quotes=quotes,
      users=rowlist("SELECT * FROM users WHERE active=1 ORDER BY name"))

@app.route("/orders/<int:order_id>/quote-link")
@manager_required
def quote_link(order_id):
    w=getrow("SELECT * FROM work_orders WHERE id=?",(order_id,))
    if not w: abort(404)
    token=secrets.token_urlsafe(24)
    with db() as c:
        c.execute("""INSERT INTO quotes(token,work_order_id,provider_name,service_description,material_mode,status,created_at)
          VALUES(?,?,?,?,?,?,?)""",(token,order_id,"Aguardando preenchimento",w["title"],"prestador","Link gerado",datetime.now().isoformat(timespec="seconds")))
    link=url_for("provider_quote",token=token,_external=True)
    return render_template("quote_link.html", order=w, link=link, whatsapp="https://wa.me/?text="+__import__("urllib.parse").parse.quote(f"Olá! Solicito orçamento para {w['code']} — {w['title']}. Preencha neste link: {link}"))

@app.route("/orcamento/<token>", methods=["GET","POST"])
def provider_quote(token):
    q=getrow("""SELECT q.*,w.code order_code,w.title order_title,w.description order_description,
      a.name area_name,s.name asset_name FROM quotes q JOIN work_orders w ON w.id=q.work_order_id
      LEFT JOIN areas a ON a.id=w.area_id LEFT JOIN assets s ON s.id=w.asset_id WHERE q.token=?""",(token,))
    if not q: abort(404)
    if request.method=="POST":
        name=request.form.get("provider_name","").strip()
        service=request.form.get("service_description","").strip()
        if not name or not service:
            flash("Preencha nome/empresa e descrição do serviço.")
            return redirect(url_for("provider_quote",token=token))
        try:
            labor=float(request.form.get("labor") or 0)
            freight=float(request.form.get("freight") or 0)
            if labor<0 or freight<0: raise ValueError()
        except ValueError:
            flash("Valores de mão de obra e frete devem ser números iguais ou maiores que zero.")
            return redirect(url_for("provider_quote",token=token))
        mode=request.form.get("material_mode","prestador")
        items=[]
        names=request.form.getlist("item_name[]")
        specs=request.form.getlist("item_spec[]")
        qtys=request.form.getlist("item_qty[]")
        units=request.form.getlist("item_unit[]")
        prices=request.form.getlist("item_price[]")
        for i,n in enumerate(names):
            if not n.strip(): continue
            try:
                qty=float(qtys[i]); price=float(prices[i])
                if qty<=0 or price<0: raise ValueError()
            except (ValueError,IndexError):
                flash("Confira quantidade e preço de cada material.")
                return redirect(url_for("provider_quote",token=token))
            items.append((n.strip(),specs[i].strip() if i<len(specs) else "",qty,units[i] if i<len(units) else "un.",price))
        if mode=="prestador" and not items:
            flash("Adicione ao menos um material ou selecione que o buffet comprará os materiais.")
            return redirect(url_for("provider_quote",token=token))
        with db() as c:
            cur=c.execute("""UPDATE quotes SET provider_name=?,provider_phone=?,service_description=?,labor=?,freight=?,
              material_mode=?,lead_time=?,validity=?,warranty=?,notes=?,status='Recebido',created_at=? WHERE id=?""",
              (name,request.form.get("provider_phone","").strip(),service,labor,freight,mode,
               request.form.get("lead_time","").strip(),request.form.get("validity","").strip(),
               request.form.get("warranty","").strip(),request.form.get("notes","").strip(),
               datetime.now().isoformat(timespec="seconds"),q["id"]))
            c.execute("DELETE FROM quote_items WHERE quote_id=?",(q["id"],))
            for item in items: c.execute("""INSERT INTO quote_items(quote_id,name,specification,quantity,unit,unit_price)
                VALUES(?,?,?,?,?,?)""",(q["id"],*item))
            for f in request.files.getlist("photos"):
                if f and f.filename:
                    try: filename=save_upload(f)
                    except ValueError as e:
                        flash(str(e)); return redirect(url_for("provider_quote",token=token))
                    c.execute("INSERT INTO attachments(quote_id,filename,original_name,created_at) VALUES(?,?,?,?)",
                      (q["id"],filename,f.filename,datetime.now().isoformat(timespec="seconds")))
        return render_template("quote_sent.html", quote=getrow("SELECT * FROM quotes WHERE id=?",(q["id"],)))
    return render_template("provider_quote.html", quote=q)

@app.route("/quotes")
@login_required
def quotes():
    qs=rowlist("""SELECT q.*,w.code order_code,w.title order_title FROM quotes q JOIN work_orders w ON w.id=q.work_order_id
      ORDER BY q.id DESC""")
    return render_template("quotes.html", quotes=qs)

@app.route("/quotes/<int:quote_id>", methods=["GET","POST"])
@manager_required
def quote_detail(quote_id):
    q=getrow("""SELECT q.*,w.code order_code,w.title order_title FROM quotes q JOIN work_orders w ON w.id=q.work_order_id WHERE q.id=?""",(quote_id,))
    if not q: abort(404)
    if request.method=="POST":
        decision=request.form.get("status","Em análise")
        if decision not in ["Em análise","Ajustes solicitados","Aprovado","Recusado","Contratação de mão de obra"]:
            decision="Em análise"
        with db() as c: c.execute("UPDATE quotes SET status=? WHERE id=?",(decision,quote_id))
        flash("Decisão registrada.")
        return redirect(url_for("quote_detail",quote_id=quote_id))
    items=rowlist("SELECT * FROM quote_items WHERE quote_id=?",(quote_id,))
    files=rowlist("SELECT * FROM attachments WHERE quote_id=?",(quote_id,))
    total=sum(float(i["quantity"])*float(i["unit_price"]) for i in items if q["material_mode"]=="prestador")+float(q["labor"] or 0)+float(q["freight"] or 0)
    return render_template("quote_detail.html", quote=q, items=items, files=files, total=total)

@app.route("/routines", methods=["GET","POST"])
@login_required
def routines():
    if request.method=="POST":
        title=request.form.get("title","").strip()
        procedure=request.form.get("procedure","").strip()
        if not title or not procedure:
            flash("Informe o nome e o procedimento.")
        else:
            with db() as c: c.execute("""INSERT INTO routines(title,area_id,frequency,procedure,assigned_to,next_due,created_at)
              VALUES(?,?,?,?,?,?,?)""",(title,request.form.get("area_id") or None,request.form.get("frequency","Semanal"),
              procedure,request.form.get("assigned_to") or None,request.form.get("next_due",""),datetime.now().isoformat(timespec="seconds")))
            flash("Rotina cadastrada.")
        return redirect(url_for("routines"))
    rs=rowlist("""SELECT r.*,a.name area_name,u.name assigned_name FROM routines r
      LEFT JOIN areas a ON a.id=r.area_id LEFT JOIN users u ON u.id=r.assigned_to WHERE r.active=1 ORDER BY r.id DESC""")
    return render_template("routines.html", routines=rs, areas=rowlist("SELECT * FROM areas ORDER BY name"),
      users=rowlist("SELECT * FROM users WHERE active=1 ORDER BY name"))

@app.route("/routines/<int:routine_id>/done", methods=["POST"])
@login_required
def routine_done(routine_id):
    r=getrow("SELECT * FROM routines WHERE id=? AND active=1",(routine_id,))
    if not r: abort(404)
    with db() as c:
        c.execute("INSERT INTO routine_logs(routine_id,done_by,notes,completed_at) VALUES(?,?,?,?)",
          (routine_id,request.form.get("done_by","Zelador").strip() or "Zelador",request.form.get("notes","").strip(),datetime.now().isoformat(timespec="seconds")))
    flash("Execução da rotina registrada.")
    return redirect(url_for("routines"))

@app.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR,filename,as_attachment=False)

@app.route("/qrcodes/<filename>")
@login_required
def qrcode_file(filename):
    return send_from_directory(QR_DIR,filename,as_attachment=True)

@app.errorhandler(413)
def too_large(e):
    return "Arquivo muito grande. Limite total por envio: 12 MB.", 413

if __name__=="__main__":
    # Development server only. Do not expose directly to the public internet.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT","5000")), debug=False)
