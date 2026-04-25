import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "secreto_muy_seguro_mi_moto_app_macuil"

# ---------------------- BASE DE DATOS ----------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def rol(r):
    tipo = session.get("tipo")
    if not tipo: return False
    return tipo.strip().lower() == r.strip().lower()

def es_admin():
    return session.get("tipo") == "admin"

def crear_tablas():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        telefono TEXT,
        password TEXT,
        tipo TEXT,
        numero_unidad TEXT,
        color_vehiculo TEXT,
        lat REAL,
        lng REAL,
        activo INTEGER DEFAULT 1,
        fecha_pago TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS viajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        conductor_id INTEGER,
        estado TEXT,
        origen TEXT,
        destino TEXT,
        lat REAL,
        lng REAL,
        lat_destino REAL,
        lng_destino REAL
    )""")
    conn.commit()
    conn.close()

crear_tablas()

# ---------------------- LOGIN Y REGISTROS ----------------------

@app.route("/", methods=["GET", "POST"]) 
def login():
    error = None
    if request.method == "POST":
        telefono = request.form.get("telefono", "").strip()
        password = request.form.get("password", "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM usuarios WHERE telefono=?", (telefono,)).fetchone()
        if user:
            password_db = user["password"]
            if password_db.startswith("scrypt:") or password_db.startswith("pbkdf2:"):
                valido = check_password_hash(password_db, password)
            else:
                valido = (password_db == password)
                if valido:
                    conn.execute("UPDATE usuarios SET password=? WHERE id=?", (generate_password_hash(password), user["id"]))
                    conn.commit()
            if valido:
                session.clear()
                session["user_id"] = user["id"]
                session["nombre"] = user["nombre"]
                session["tipo"] = str(user["tipo"]).lower().strip()
                conn.close()
                if session["tipo"] == "admin": return redirect(url_for("admin"))
                elif session["tipo"] == "conductor": return redirect(url_for("conductor"))
                else: return redirect(url_for("cliente"))
        conn.close()
        error = "Teléfono o contraseña incorrectos"
    return render_template("login.html", error=error)

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre, tel, pwd, tipo = request.form.get("nombre"), request.form.get("telefono"), request.form.get("password"), request.form.get("tipo")
        conn = get_db()
        conn.execute("INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)", (nombre, tel, pwd, tipo))
        conn.commit(); conn.close()
        return redirect(url_for("login"))
    return render_template("registro.html")

@app.route("/registro_conductor", methods=["GET", "POST"])
def registro_conductor():
    if request.method == "POST":
        n, t, p, u, c = request.form.get("nombre"), request.form.get("telefono"), request.form.get("password"), request.form.get("numero_unidad"), request.form.get("color_vehiculo")
        conn = get_db()
        conn.execute("INSERT INTO usuarios (nombre, telefono, password, tipo, numero_unidad, color_vehiculo) VALUES (?, ?, ?, 'conductor', ?, ?)", (n, t, p, u, c))
        conn.commit(); conn.close()
        return redirect(url_for("login"))
    return render_template("registro_conductor.html")

# ---------------------- CLIENTE Y PEDIR VIAJE ----------------------

@app.route("/cliente")
def cliente():
    if not rol("cliente"): return redirect(url_for("login"))
    conn = get_db()
    viaje = conn.execute("SELECT id FROM viajes WHERE cliente_id=? AND estado NOT IN ('finalizado','cancelado') ORDER BY id DESC LIMIT 1", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("cliente.html", viaje_id=viaje["id"] if viaje else None)

@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    if not rol("cliente"): return redirect(url_for("login"))
    d = request.form
    try:
        lat, lng = float(d.get("lat",0)), float(d.get("lng",0))
        lat_d, lng_d = float(d.get("lat_destino",0)), float(d.get("lng_destino",0))
    except: lat = lng = lat_d = lng_d = 0.0
    conn = get_db()
    conn.execute("INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino) VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)",
                 (session["user_id"], d.get("origen"), d.get("destino"), lat, lng, lat_d, lng_d))
    conn.commit(); conn.close()
    return redirect(url_for("cliente"))

@app.route("/api_estado_viaje/<int:viaje_id>")
def api_estado_viaje(viaje_id):
    conn = get_db()
    viaje = conn.execute("""
        SELECT v.estado, u.nombre as conductor, u.numero_unidad as unidad, u.color_vehiculo as color
        FROM viajes v LEFT JOIN usuarios u ON v.conductor_id = u.id WHERE v.id = ?
    """, (viaje_id,)).fetchone()
    conn.close()
    return jsonify(dict(viaje) if viaje else {"estado": "no_encontrado"})

# ---------------------- CONDUCTOR ----------------------

@app.route("/conductor")
def conductor():
    if not rol("conductor"): return redirect(url_for("login"))
    conn = get_db()
    viaje = conn.execute("SELECT * FROM viajes WHERE conductor_id=? AND estado IN ('aceptado','en_camino','recogido') ORDER BY id DESC LIMIT 1", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)

@app.route("/aceptar_viaje/<int:id>")
def aceptar_viaje(id):
    if not rol("conductor"): return redirect(url_for("login"))
    conn = get_db()
    conn.execute("UPDATE viajes SET conductor_id=?, estado='aceptado' WHERE id=? AND estado='pendiente'", (session["user_id"], id))
    conn.commit(); conn.close()
    return redirect(url_for("conductor"))

# ---------------------- ADMIN Y RESETS (TODOS INCLUIDOS) ----------------------

@app.route("/admin")
def admin():
    if not es_admin(): return "Acceso denegado", 403
    conn = get_db()
    conds = conn.execute("SELECT * FROM usuarios WHERE tipo='conductor'").fetchall()
    lista, hoy = [], datetime.now()
    for c in conds:
        c = dict(c)
        if c["fecha_pago"]:
            fp = datetime.strptime(c["fecha_pago"], "%Y-%m-%d")
            dias = 7 - (hoy - fp).days
            if dias <= 0: conn.execute("UPDATE usuarios SET activo=0 WHERE id=?", (c["id"],))
            c["dias_restantes"] = dias if dias > 0 else "Vencido"
        else: c["dias_restantes"], c["activo"] = "Sin pago", 0
        lista.append(c)
    conn.commit(); conn.close()
    return render_template("admin.html", conductores=lista)

@app.route('/pagar_conductor/<int:id>')
def pagar_conductor(id):
    if not es_admin(): return redirect(url_for('login'))
    conn = get_db()
    conn.execute('UPDATE usuarios SET fecha_pago = ?, activo = 1 WHERE id = ?', (datetime.now().strftime("%Y-%m-%d"), id))
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route("/reset_conductores")
def reset_conductores():
    if not es_admin(): return "No autorizado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo = 'conductor'")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route("/reset_clientes")
def reset_clientes():
    if not es_admin(): return "No autorizado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo = 'cliente'")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route("/reset_usuarios")
def reset_usuarios():
    if not es_admin(): return "No autorizado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo != 'admin'")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route("/reset_viajes")
def reset_viajes():
    if not es_admin(): return "No autorizado", 403
    conn = get_db()
    conn.execute("DELETE FROM viajes")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

# ---------------------- AJAX Y UBICACIÓN ----------------------

@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" in session:
        conn = get_db()
        conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (request.form.get("lat"), request.form.get("lng"), session["user_id"]))
        conn.commit(); conn.close()
    return "", 200

@app.route("/verificar_viajes")
def verificar_viajes():
    u_id = request.args.get("ultimo_id", 0)
    conn = get_db()
    v = conn.execute("SELECT id FROM viajes WHERE estado='pendiente' AND id > ? LIMIT 1", (u_id,)).fetchone()
    conn.close()
    return jsonify({"nuevo_viaje": bool(v), "id": v["id"] if v else None})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)