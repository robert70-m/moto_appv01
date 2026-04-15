import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "secreto_muy_seguro"

# ---------------------- DB ----------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        lat REAL,
        lng REAL,
        activo INTEGER DEFAULT 1,
        fecha_pago TEXT
    )
    """)

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
    )
    """)

    conn.commit()
    conn.close()

crear_tablas()

# ---------------------- LOGIN ----------------------

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
            session["user_id"] = user["id"]
            session["tipo"] = user["tipo"]
            session["nombre"] = user["nombre"]
            session["telefono"] = user["telefono"]  # 🔥 CLAVE PARA ADMIN

            if user["tipo"] == "cliente":
                return redirect(url_for("cliente"))
            else:
                return redirect(url_for("conductor"))
        else:
            error = "Datos incorrectos"

    return render_template("login.html", error=error)
# ---------------------- REGISTRO ----------------------

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]
        password = request.form["password"]
        tipo = request.form["tipo"]

        conn = get_db()

        existe = conn.execute(
            "SELECT id FROM usuarios WHERE telefono=?",
            (telefono,)
        ).fetchone()

        if existe:
            return "Teléfono ya registrado"

        conn.execute(
            "INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)",
            (nombre, telefono, password, tipo)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("registro.html")

# ---------------------- CLIENTE ----------------------

@app.route("/cliente")
def cliente():
    if session.get("tipo") != "cliente":
        return redirect(url_for("login"))
    return render_template("cliente.html")

@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    if session.get("tipo") != "cliente":
        return redirect(url_for("login"))

    origen = request.form.get("origen")
    destino = request.form.get("destino")
    lat = request.form.get("lat")
    lng = request.form.get("lng")
    lat_destino = request.form.get("lat_destino")
    lng_destino = request.form.get("lng_destino")

    conn = get_db()
    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (session["user_id"], origen, destino, lat, lng, lat_destino, lng_destino))
    conn.commit()
    conn.close()

    return redirect(url_for("cliente"))

# ---------------------- CONDUCTOR ----------------------

@app.route("/conductor")
def conductor():
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    conn = get_db()

    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=? AND estado!='finalizado'
    """, (session["user_id"],)).fetchone()

    conn.close()

    return render_template("conductor.html", viaje=viaje)

@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes WHERE estado='pendiente'").fetchall()
    conn.close()

    return render_template("viajes.html", viajes=viajes)

@app.route("/aceptar_viaje/<int:id>")
def aceptar_viaje(id):
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("""
        UPDATE viajes
        SET conductor_id=?, estado='aceptado'
        WHERE id=?
    """, (session["user_id"], id))
    conn.commit()
    conn.close()

    return redirect(url_for("conductor"))

@app.route("/finalizar_viaje/<int:id>")
def finalizar_viaje(id):
    conn = get_db()
    conn.execute("UPDATE viajes SET estado='finalizado' WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("conductor"))

# ---------------------- API ----------------------

@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes WHERE estado='pendiente'").fetchall()
    conn.close()

    return jsonify([dict(v) for v in viajes])

# ---------------------- UBICACIÓN ----------------------

@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" not in session:
        return "No autorizado", 401

    lat = request.form.get("lat")
    lng = request.form.get("lng")

    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET lat=?, lng=? WHERE id=?",
        (lat, lng, session["user_id"])
    )
    conn.commit()
    conn.close()

    return "OK"
# ------------------------------------------------

@app.route("/admin")
def admin():
    MI_NUMERO_ADMIN = '9513928223'

    telefono = str(session.get("telefono", "")).strip()

    if telefono != MI_NUMERO_ADMIN:
        return f"Acceso denegado. Tu teléfono es: [{telefono}]", 403

    return "Bienvenido admin"

# -------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----------------------

if __name__ == "__main__":
    app.run(debug=True)