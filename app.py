import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, jsonify

app = Flask(__name__)
app.secret_key = "secreto_muy_seguro"

# --- CONFIGURACIÓN DE BASE DE DATOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    return conn

def crear_tablas():
    conn = get_db()
    cursor = conn.cursor()
    # TABLA USUARIOS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        telefono TEXT,
        password TEXT,
        tipo TEXT,
        lat REAL,
        lng REAL,
        activo INTEGER DEFAULT 1,
        fecha_pago TEXT
    )
    """)
    # TABLA VIAJES
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS viajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        conductor_id INTEGER,
        nombre_conductor TEXT,
        estado TEXT,
        origen TEXT,
        destino TEXT,
        lat REAL,
        lng REAL,
        lat_destino REAL,
        lng_destino REAL
    )
    """)
    conn.commit()
    conn.close()

# Inicialización
crear_tablas()

# ---------------------- LOGIN Y REGISTRO ----------------------

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        telefono = request.form["telefono"].strip()
        password = request.form["password"].strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=? AND password=?",
            (telefono, password)
        ).fetchone()
        conn.close()

        if user:
            # Validación de cuenta activa para conductores
            if user["tipo"] == "conductor" and user["activo"] == 0:
                error = "Tu cuenta está suspendida o vencida. Contacta al admin ❌"
                return render_template("login.html", error=error)

            # GUARDAR DATOS EN SESIÓN
            session["user_id"] = user["id"]
            session["tipo"] = user["tipo"]
            session["nombre"] = user["nombre"]
            session["telefono"] = user["telefono"] # <--- IMPORTANTE PARA EL ADMIN

            return redirect("/cliente" if user["tipo"] == "cliente" else "/conductor")
        else:
            error = "Usuario o contraseña incorrectos ❌"

    return render_template("login.html", error=error)

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        telefono = request.form["telefono"].strip()
        password = request.form["password"].strip()
        tipo = request.form["tipo"].strip()

        conn = get_db()
        conn.execute("INSERT INTO usuarios (nombre, telefono, password, tipo, activo) VALUES (?, ?, ?, ?, 1)", 
                     (nombre, telefono, password, tipo))
        conn.commit()
        conn.close()
        return redirect("/")
    return render_template("registro.html")

# ---------------------- VISTAS CONDUCTOR ----------------------

@app.route("/conductor")
def conductor():
    if not session.get("user_id") or session.get("tipo") != "conductor":
        return redirect("/")

    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()

    # 🔥 VALIDACIÓN DE PAGO AUTOMÁTICA (CADA 7 DÍAS)
    if user["fecha_pago"]:
        fecha_pago = datetime.strptime(user["fecha_pago"], "%Y-%m-%d")
        if datetime.now() > fecha_pago + timedelta(days=7):
            conn.execute("UPDATE usuarios SET activo=0 WHERE id=?", (session["user_id"],))
            conn.commit()
            conn.close()
            session.clear() 
            return "Tu suscripción de 7 días ha vencido. Contacta al administrador para renovar."

    if user["activo"] == 0:
        conn.close()
        return "Tu cuenta está desactivada."

    # Buscar viaje activo
    viaje = conn.execute("""
        SELECT id FROM viajes 
        WHERE conductor_id = ? AND estado IN ('aceptado', 'en_camino', 'recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    if viaje:
        return render_template("conductor.html", viaje_id=viaje['id'])
    
    return redirect("/viajes_disponibles")

@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor":
        return redirect("/")
    return render_template("viajes.html")

# ---------------------- VISTAS ADMIN ----------------------

@app.route("/admin")
def admin():
    # 1. SEGURIDAD DINÁMICA: Cambia el número de abajo por el tuyo real
    MI_NUMERO_ADMIN = '9513928223' 
    
    if session.get("telefono") != MI_NUMERO_ADMIN:
        return "Acceso denegado. Solo Roberto puede entrar. ❌", 403

    conn = get_db()
    conductores = conn.execute("SELECT * FROM usuarios WHERE tipo='conductor'").fetchall()
    lista = []
    ahora = datetime.now()

    for c in conductores:
        c_dict = dict(c)
        dias_restantes = "Sin pago"
        prioridad = 1 

        if c["fecha_pago"]:
            fecha_pago = datetime.strptime(c["fecha_pago"], "%Y-%m-%d")
            vencimiento = fecha_pago + timedelta(days=7)
            diferencia = (vencimiento - ahora).days

            if diferencia < 0:
                dias_restantes = "Vencido"
                prioridad = 0 
            else:
                dias_restantes = f"{diferencia} días" if diferencia > 0 else "Vence hoy"
                prioridad = 2 
        
        if c["activo"] == 0 and dias_restantes != "Vencido":
            dias_restantes = "Bloqueado Manual"
            prioridad = -1 

        c_dict["dias_restantes"] = dias_restantes
        c_dict["prioridad"] = prioridad
        lista.append(c_dict)

    conn.close()
    lista.sort(key=lambda x: x["prioridad"]) 
    return render_template("admin.html", conductores=lista)

@app.route("/toggle_conductor/<int:id>")
def toggle_conductor(id):
    # Seguridad básica para que solo el admin use esta ruta
    MI_NUMERO_ADMIN = '9513928223'
    if session.get("telefono") != MI_NUMERO_ADMIN: return "No autorizado", 403

    conn = get_db()
    user = conn.execute("SELECT activo FROM usuarios WHERE id=?", (id,)).fetchone()
    nuevo_estado = 0 if user["activo"] == 1 else 1
    conn.execute("UPDATE usuarios SET activo=? WHERE id=?", (nuevo_estado, id))
    conn.commit()
    conn.close()
    return redirect("/admin")

@app.route("/pagar_conductor/<int:id>")
def pagar_conductor(id):
    # Seguridad básica
    MI_NUMERO_ADMIN = '9513928223'
    if session.get("telefono") != MI_NUMERO_ADMIN: return "No autorizado", 403

    conn = get_db()
    hoy = datetime.now().strftime("%Y-%m-%d")
    conn.execute("UPDATE usuarios SET activo=1, fecha_pago=? WHERE id=?", (hoy, id))
    conn.commit()
    conn.close()
    return redirect("/admin")

# ---------------------- APIS Y LOGOUT ----------------------

@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes WHERE estado='pendiente'").fetchall()
    conn.close()
    return jsonify({"viajes": [dict(v) for v in viajes]})

@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" not in session: return "Unauthorized", 401
    lat, lng = request.form.get("lat"), request.form.get("lng")
    conn = get_db()
    conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (lat, lng, session["user_id"]))
    conn.commit()
    conn.close()
    return "OK"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)