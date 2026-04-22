import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "secreto_muy_seguro_hernandez_el mejor servicio"

# ---------------------- DB (Rutas Absolutas) ----------------------
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
        numero_unidad TEXT,
        color_vehiculo TEXT,
        lat REAL,
        lng REAL,
        activo INTEGER DEFAULT 1,
        fecha_pago TEXT
    )""")
    conn.commit()
    conn.close()

crear_tablas()

# ---------------------- LOGIN / REGISTRO ----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        telefono = request.form.get("telefono", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=? AND password=?",
            (telefono, password)
        ).fetchone()
        conn.close()

        if user:
            tipo_usuario = str(user["tipo"]).lower().strip()
            session.update({
                "user_id": user["id"],
                "tipo": tipo_usuario,
                "nombre": user["nombre"],
                "telefono": user["telefono"]
            })

            if tipo_usuario == "admin":
                return redirect(url_for("admin"))
            elif tipo_usuario == "conductor":
                return redirect(url_for("conductor"))
            else:
                return redirect(url_for("cliente"))
        else:
            error = "Datos incorrectos"
    return render_template("login.html", error=error)

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre, tel, pwd, tipo = request.form.get("nombre"), request.form.get("telefono"), request.form.get("password"), request.form.get("tipo")
        conn = get_db()
        if conn.execute("SELECT id FROM usuarios WHERE telefono=?", (tel,)).fetchone():
            conn.close()
            return "Teléfono ya registrado"
        conn.execute("INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)", (nombre, tel, pwd, tipo))
        conn.commit()
        conn.close()
        return redirect(url_for("login"))
    return render_template("registro.html")

@app.route("/registro_conductor", methods=["GET", "POST"])
def registro_conductor():
    if request.method == "POST":
        n = request.form.get("nombre")
        t = request.form.get("telefono")
        p = request.form.get("password")
        numero_unidad = request.form.get("numero_unidad")
        color_vehiculo = request.form.get("color_vehiculo")

        conn = get_db()
        existe = conn.execute("SELECT id FROM usuarios WHERE telefono=?", (t,)).fetchone()
        if existe:
            conn.close()
            return "Teléfono ya registrado"

        conn.execute("""INSERT INTO usuarios 
            (nombre, telefono, password, tipo, numero_unidad, color_vehiculo) 
            VALUES (?, ?, ?, 'conductor', ?, ?)""",
            (n, t, p, numero_unidad, color_vehiculo))
        conn.commit()
        conn.close()
        return redirect(url_for("login"))
    return render_template("registro_conductor.html")

# ---------------------- CLIENTE ----------------------
@app.route("/cliente")
def cliente():
    if session.get("tipo") != "cliente": return redirect(url_for("login"))
    conn = get_db()
    viaje = conn.execute("SELECT * FROM viajes WHERE cliente_id=? AND estado != 'finalizado' ORDER BY id DESC LIMIT 1", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("cliente.html", viaje_id=viaje["id"] if viaje else None)

@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    d = request.form
    user_id = session.get("user_id")
    conn = get_db()
    viaje_activo = conn.execute("SELECT id FROM viajes WHERE cliente_id = ? AND estado NOT IN ('finalizado', 'cancelado')", (user_id,)).fetchone()
    if viaje_activo:
        conn.close()
        return redirect(url_for("cliente", error="Ya tienes un viaje en curso."))
    try:
        conn.execute("""INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
            VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)""", 
            (user_id, d.get("origen", "N/A"), d.get("destino", "N/A"), float(d.get("lat", 0)), float(d.get("lng", 0)), float(d.get("lat_destino", 0)), float(d.get("lng_destino", 0))))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("cliente"))

# ---------------------- CONDUCTOR ----------------------
@app.route("/conductor")
def conductor():
    if "conductor" not in str(session.get("tipo", "")).lower(): return redirect(url_for("login"))
    conn = get_db()
    viaje = conn.execute("SELECT * FROM viajes WHERE conductor_id = ? AND estado IN ('aceptado', 'en_camino', 'recogido') ORDER BY id DESC LIMIT 1", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)

@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor": return redirect("/")
    conn = get_db()
    cursor = conn.execute("SELECT * FROM viajes WHERE estado = 'pendiente'")
    viajes_query = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template("viajes.html", viajes=viajes_query)

@app.route("/aceptar_viaje/<int:viaje_id>")
def aceptar_viaje(viaje_id):
    if not session.get("user_id") or "conductor" not in str(session.get("tipo", "")).lower(): return redirect(url_for("login"))
    conn = get_db()
    ocupado = conn.execute("SELECT id FROM viajes WHERE conductor_id = ? AND estado IN ('aceptado', 'en_camino', 'recogido')", (session["user_id"],)).fetchone()
    if ocupado:
        conn.close()
        return redirect(url_for("viajes_disponibles", error="Ya tienes un viaje activo."))
    conn.execute("UPDATE viajes SET conductor_id = ?, estado = 'aceptado' WHERE id = ? AND estado = 'pendiente'", (session["user_id"], viaje_id))
    conn.commit()
    conn.close()
    return redirect(url_for("conductor"))

@app.route("/cambiar_estado_viaje/<int:id>/<nuevo_estado>")
def cambiar_estado_viaje(id, nuevo_estado):
    conn = get_db()
    conn.execute("UPDATE viajes SET estado = ? WHERE id = ?", (nuevo_estado, id))
    conn.commit()
    conn.close()
    return redirect(url_for("viajes_disponibles" if nuevo_estado == 'finalizado' else "conductor"))

# ---------------------- ADMIN ----------------------
@app.route("/admin")
def admin():
    if session.get("tipo") != "admin": return redirect(url_for("login"))
    conn = get_db()
    conductores = conn.execute("SELECT * FROM usuarios WHERE tipo='conductor'").fetchall()
    lista = []
    ahora = datetime.now()
    for c in conductores:
        c_dict = dict(c)
        dias = "Sin pago"
        if c["fecha_pago"]:
            try:
                vencimiento = datetime.strptime(c["fecha_pago"], "%Y-%m-%d") + timedelta(days=7)
                diferencia = (vencimiento - ahora).days
                dias = "Vencido" if diferencia < 0 else diferencia
            except: dias = "Error fecha"
        c_dict["dias_restantes"] = dias
        lista.append(c_dict)
    conn.close()
    return render_template("admin.html", conductores=lista)

@app.route("/pagar_conductor/<int:id>")
def pagar_conductor(id):
    conn = get_db()
    conn.execute("UPDATE usuarios SET fecha_pago=? WHERE id=?", (datetime.now().strftime("%Y-%m-%d"), id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

# ---------------------- API & AJAX ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes").fetchall()
    conn.close()
    return jsonify({"viajes": [dict(v) for v in viajes]})

@app.route("/verificar_viajes")
def verificar_viajes():
    ultimo_id = int(request.args.get("ultimo_id", 0))
    conn = get_db()
    viaje = conn.execute("SELECT id FROM viajes WHERE estado = 'pendiente' AND id > ? ORDER BY id DESC LIMIT 1", (ultimo_id,)).fetchone()
    conn.close()
    return {"nuevo_viaje": bool(viaje), "id": viaje["id"] if viaje else None}

@app.route("/verificar_cancelaciones")
def verificar_cancelaciones():
    ultimo_id = int(request.args.get("ultimo_id", 0))
    conn = get_db()
    cancelado = conn.execute("SELECT id FROM viajes WHERE conductor_id = ? AND estado = 'cancelado' AND id > ?", (session.get("user_id"), ultimo_id)).fetchone()
    conn.close()
    return {"cancelado": bool(cancelado), "id": cancelado["id"] if cancelado else None}

@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" in session:
        conn = get_db()
        conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (request.form.get("lat"), request.form.get("lng"), session["user_id"]))
        conn.commit()
        conn.close()
    return "OK"

@app.route("/cancelar_viaje/<int:id>")
def cancelar_viaje(id):
    conn = get_db()
    conn.execute("UPDATE viajes SET estado = 'cancelado' WHERE id = ? AND cliente_id = ? AND estado = 'pendiente'", (id, session.get("user_id")))
    conn.commit()
    conn.close()
    return redirect(url_for("cliente"))

# ---------------------- RESET MODES ----------------------
@app.route("/reset_usuarios", methods=["POST"])
def reset_usuarios():
    if session.get("tipo") != "admin": return "No autorizado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE LOWER(TRIM(tipo)) != 'admin'")
    conn.commit()
    conn.close()
    return redirect("/admin")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)