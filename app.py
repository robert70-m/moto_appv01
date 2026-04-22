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
            tipo = str(user["tipo"]).lower().strip()
            session.update({
                "user_id": user["id"],
                "tipo": tipo,
                "nombre": user["nombre"],
                "telefono": user["telefono"]
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

        conn.execute("INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)", 
                     (nombre, tel, pwd, tipo))
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
        numero_unidad = request.form.get("numero_unidad")
        color_vehiculo = request.form.get("color_vehiculo")

        conn = get_db()

        if conn.execute("SELECT id FROM usuarios WHERE telefono=?", (t,)).fetchone():
            conn.close()
            return "Teléfono ya registrado"

        conn.execute("""
            INSERT INTO usuarios (nombre, telefono, password, tipo, numero_unidad, color_vehiculo)
            VALUES (?, ?, ?, 'conductor', ?, ?)
        """, (n, t, p, numero_unidad, color_vehiculo))

        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("registro_conductor.html")

# ---------------------- CLIENTE ----------------------
@app.route("/cliente")
def cliente():
    if session.get("tipo") != "cliente":
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
    user_id = session.get("user_id")
    conn = get_db()

    viaje_activo = conn.execute("""
        SELECT id FROM viajes 
        WHERE cliente_id = ? AND estado NOT IN ('finalizado', 'cancelado')
    """, (user_id,)).fetchone()

    if viaje_activo:
        conn.close()
        return redirect(url_for("cliente", error="Ya tienes un viaje en curso."))

    d = request.form

    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        d.get("origen", "N/A"),
        d.get("destino", "N/A"),
        float(d.get("lat", 0)),
        float(d.get("lng", 0)),
        float(d.get("lat_destino", 0)),
        float(d.get("lng_destino", 0))
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("cliente"))

# ---------------------- CONDUCTOR ----------------------
@app.route("/conductor")
def conductor():
    if "conductor" not in str(session.get("tipo", "")).lower():
        return redirect(url_for("login"))

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes 
        WHERE conductor_id = ? 
        AND estado IN ('aceptado','en_camino','recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)

@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor":
        return redirect("/")

    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes WHERE estado='pendiente'").fetchall()
    conn.close()

    return render_template("viajes.html", viajes=[dict(v) for v in viajes])

@app.route("/aceptar_viaje/<int:viaje_id>")
def aceptar_viaje(viaje_id):
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    conn = get_db()

    ocupado = conn.execute("""
        SELECT id FROM viajes 
        WHERE conductor_id=? 
        AND estado IN ('aceptado','en_camino','recogido')
    """, (session["user_id"],)).fetchone()

    if ocupado:
        conn.close()
        return redirect(url_for("viajes_disponibles"))

    conn.execute("""
        UPDATE viajes 
        SET conductor_id=?, estado='aceptado'
        WHERE id=? AND estado='pendiente'
    """, (session["user_id"], viaje_id))

    conn.commit()
    conn.close()

    return redirect(url_for("conductor"))

@app.route("/cambiar_estado_viaje/<int:id>/<nuevo_estado>")
def cambiar_estado_viaje(id, nuevo_estado):
    conn = get_db()
    conn.execute("UPDATE viajes SET estado=? WHERE id=?", (nuevo_estado, id))
    conn.commit()
    conn.close()

    return redirect(url_for("viajes_disponibles" if nuevo_estado == 'finalizado' else "conductor"))

# ---------------------- ADMIN ----------------------
@app.route("/admin")
def admin():
    if str(session.get("telefono", "")).strip() != '9513928223':
        return "Acceso denegado", 403

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
            except:
                dias = "Error fecha"

        c_dict["dias_restantes"] = dias
        lista.append(c_dict)

    conn.close()

    return render_template("admin.html", conductores=lista)

# ---------------------- RESET ----------------------
def es_admin():
    return str(session.get("telefono", "")).strip() == "9513928223"

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

# ---------------------- OTROS ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)