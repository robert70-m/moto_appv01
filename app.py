import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "secreto_muy_seguro_mi_moto_app_macuil"

# ---------------------- DB ----------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def rol(r):
    tipo = session.get("tipo")
    if not tipo:
        return False
    return tipo.strip().lower() == r.strip().lower()

def es_admin():
    return str(session.get("telefono", "")).strip() == "9513928223"

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

# ---------------------- LOGIN ----------------------
# ... (todo el inicio igual)

# ---------------------- LOGIN (Optimizado) ----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        telefono = request.form["telefono"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=? AND password=?",
            (telefono, password)
        ).fetchone()
        conn.close() # Cerramos aquí para liberar recursos rápido

        if user:
            tipo = str(user["tipo"]).lower().strip()
            session.update({
                "user_id": user["id"],
                "tipo": tipo,
                "telefono": user["telefono"],
                "nombre": user["nombre"]
            })

            if tipo == "admin":
                return redirect(url_for("admin"))
            elif tipo == "conductor":
                return redirect(url_for("conductor"))
            else:
                return redirect(url_for("cliente"))
        else:
            error = "Datos incorrectos"

    return render_template("login.html", error=error)

# ... (el resto de tus rutas corregidas que ya tienes)

# ---------------------- REGISTRO CLIENTE ----------------------
@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        tel = request.form.get("telefono")
        pwd = request.form.get("password")
        tipo = request.form.get("tipo")

        conn = get_db()

        if conn.execute("SELECT id FROM usuarios WHERE telefono=?", (tel,)).fetchone():
            conn.close()
            return "Teléfono ya registrado"

        conn.execute(
            "INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)",
            (nombre, tel, pwd, tipo)
        )

        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    return render_template("registro.html")

# ---------------------- REGISTRO CONDUCTOR ----------------------
@app.route("/registro_conductor", methods=["GET", "POST"])
def registro_conductor():
    if request.method == "POST":
        n = request.form.get("nombre")
        t = request.form.get("telefono")
        p = request.form.get("password")
        u = request.form.get("numero_unidad")
        c = request.form.get("color_vehiculo")

        conn = get_db()

        if conn.execute("SELECT id FROM usuarios WHERE telefono=?", (t,)).fetchone():
            conn.close()
            return "Teléfono ya registrado"

        conn.execute("""
            INSERT INTO usuarios (nombre, telefono, password, tipo, numero_unidad, color_vehiculo)
            VALUES (?, ?, ?, 'conductor', ?, ?)
        """, (n, t, p, u, c))

        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    return render_template("registro_conductor.html")

# ---------------------- CLIENTE ----------------------
@app.route("/cliente")
def cliente():
    if not rol("cliente"):
        return redirect(url_for("login"))

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE cliente_id=? AND estado != 'finalizado'
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("cliente.html", viaje_id=viaje["id"] if viaje else None)

@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    if not rol("cliente"):
        return redirect(url_for("login"))

    conn = get_db()

    existente = conn.execute("""
        SELECT id FROM viajes
        WHERE cliente_id=? AND estado NOT IN ('finalizado','cancelado')
    """, (session["user_id"],)).fetchone()

    if existente:
        conn.close()
        return redirect(url_for("cliente"))

    d = request.form
    
    # Manejo de errores en conversión numérica
    try:
        lat = float(d.get("lat", 0))
        lng = float(d.get("lng", 0))
        lat_d = float(d.get("lat_destino", 0))
        lng_d = float(d.get("lng_destino", 0))
    except ValueError:
        lat, lng, lat_d, lng_d = 0.0, 0.0, 0.0, 0.0

    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        d.get("origen", ""),
        d.get("destino", ""),
        lat, lng, lat_d, lng_d
    ))

    conn.commit()
    conn.close()
    return redirect(url_for("cliente"))
@app.route("/cancelar_viaje/<int:viaje_id>")
def cancelar_viaje(viaje_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()
    # Solo permitimos cancelar si el viaje es del cliente y no ha finalizado
    conn.execute("""
        UPDATE viajes 
        SET estado='cancelado' 
        WHERE id=? AND cliente_id=? AND estado NOT IN ('finalizado', 'cancelado')
    """, (viaje_id, session["user_id"]))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for("cliente"))

# ---------------------- CONDUCTOR ----------------------
@app.route("/conductor")
def conductor():
    if not rol("conductor"):
        return redirect(url_for("login"))

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)
@app.route('/pagar_conductor/<int:id>')
def pagar_conductor(id):
    conn = get_db_connection()
    # Aquí pon la lógica que tenías (ejemplo: resetear saldo o estado de pago)
    conn.execute('UPDATE usuarios SET pago_pendiente = 0 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route("/viajes_disponibles")
def viajes_disponibles():
    if not rol("conductor"):
        return redirect("/")

    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes WHERE estado='pendiente'").fetchall()
    conn.close()

    return render_template("viajes.html", viajes=[dict(v) for v in viajes])

@app.route("/aceptar_viaje/<int:id>")
def aceptar_viaje(id):
    if not rol("conductor"):
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("""
        UPDATE viajes
        SET conductor_id=?, estado='aceptado'
        WHERE id=? AND estado='pendiente'
    """, (session["user_id"], id))
    conn.commit()
    conn.close()

    return redirect(url_for("conductor"))

@app.route("/cambiar_estado_viaje/<int:id>/<nuevo_estado>")
def cambiar_estado_viaje(id, nuevo_estado):
    if not rol("conductor"):
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("UPDATE viajes SET estado=? WHERE id=?", (nuevo_estado, id))
    conn.commit()
    conn.close()

    return redirect(url_for("viajes_disponibles" if nuevo_estado == "finalizado" else "conductor"))

# ---------------------- API ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes").fetchall()
    conn.close()
    return jsonify({"viajes": [dict(v) for v in viajes]})

@app.route("/api/viaje_cliente")
def api_viaje_cliente():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"viaje": None})

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE cliente_id=? AND estado != 'finalizado'
        ORDER BY id DESC LIMIT 1
    """, (user_id,)).fetchone()
    conn.close()

    return jsonify({"viaje": dict(viaje) if viaje else None})

@app.route("/aceptar_viaje_ajax/<int:id>", methods=["POST"])
def aceptar_viaje_ajax(id):
    if not rol("conductor"):
        return jsonify({"ok": False})

    conn = get_db()
    conn.execute("""
        UPDATE viajes
        SET conductor_id=?, estado='aceptado'
        WHERE id=? AND estado='pendiente'
    """, (session["user_id"], id))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})

@app.route('/toggle_conductor/<int:id>')
def toggle_conductor(id):
    if session.get('tipo') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    # Primero vemos el estado actual
    conductor = conn.execute('SELECT activo FROM usuarios WHERE id = ?', (id,)).fetchone()
    
    if conductor:
        # Si es 1 (activo) lo ponemos en 0, y viceversa
        nuevo_estado = 0 if conductor['activo'] == 1 else 1
        conn.execute('UPDATE usuarios SET activo = ? WHERE id = ?', (nuevo_estado, id))
        conn.commit()
    
    conn.close()
    return redirect(url_for('admin'))

# ---------------------- ADMIN ----------------------
@app.route("/admin")
def admin():
    if session.get("tipo") != "admin":
        return "Acceso denegado", 403

    conn = get_db()
    conductores = conn.execute("SELECT * FROM usuarios WHERE tipo='conductor'").fetchall()
    conn.close()

    return render_template("admin.html", conductores=[dict(c) for c in conductores])
# ---------------------- RESET ----------------------
@app.route("/reset_conductores")
def reset_conductores():
    if not es_admin(): return "Acceso denegado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo='conductor'")
    conn.commit()
    conn.close()
    return "Conductores eliminados"

@app.route("/reset_clientes")
def reset_clientes():
    if not es_admin(): return "Acceso denegado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo='cliente'")
    conn.commit()
    conn.close()
    return "Clientes eliminados"

@app.route("/reset_viajes")
def reset_viajes():
    if not es_admin(): return "Acceso denegado", 403
    conn = get_db()
    conn.execute("DELETE FROM viajes")
    conn.commit()
    conn.close()
    return "Viajes eliminados"

# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)