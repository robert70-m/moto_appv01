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

def login_required():
    return "user_id" in session

def rol(ru):
    return session.get("tipo", "").strip().lower() == ru

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
    if request.method == "POST":

        telefono = request.form["telefono"]
        password = request.form["password"]

        conn = get_db()
        usuario = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=? AND password=?",
            (telefono, password)
        ).fetchone()
        conn.close()

        if usuario:
            session.clear()
            session["user_id"] = usuario["id"]
            session["tipo"] = usuario["tipo"].strip().lower()
            session["telefono"] = usuario["telefono"]

            if session["tipo"] == "admin":
                return redirect(url_for("admin"))
            if session["tipo"] == "cliente":
                return redirect(url_for("cliente"))
            if session["tipo"] == "conductor":
                return redirect(url_for("conductor"))

        return "Credenciales incorrectas"

    return render_template("login.html")

# ---------------------- REGISTROS ----------------------
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
    if not login_required():
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

    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        d.get("origen", ""),
        d.get("destino", ""),
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
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes").fetchall()
    conn.close()
    return jsonify({"viajes": [dict(v) for v in viajes]})

@app.route("/aceptar_viaje_ajax/<int:id>", methods=["POST"])
def aceptar_viaje_ajax(id):
    if session.get("tipo") != "conductor": return jsonify({"ok": False})
    conn = get_db()
    conn.execute("UPDATE viajes SET conductor_id=?, estado='aceptado' WHERE id=? AND estado='pendiente'", (session["user_id"], id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})
@app.route("/api/viaje_cliente")
def api_viaje_cliente():
    user_id = session.get("user_id")

    conn = get_db()

    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE cliente_id = ?
        AND estado != 'finalizado'
        ORDER BY id DESC LIMIT 1
    """, (user_id,)).fetchone()

    conn.close()

    return {"viaje": dict(viaje) if viaje else None}
@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" in session:
        conn = get_db()
        conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (request.form.get("lat"), request.form.get("lng"), session["user_id"]))
        conn.commit()
        conn.close()
    return "OK"

@app.route("/toggle_conductor/<int:id>")
def toggle_conductor(id):
    conn = get_db()
    u = conn.execute("SELECT activo FROM usuarios WHERE id=?", (id,)).fetchone()
    if u:
        conn.execute("UPDATE usuarios SET activo=? WHERE id=?", (0 if u["activo"] == 1 else 1, id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin"))
@app.route("/pagar_conductor/<int:id>")
def pagar_conductor(id):
    conn = get_db()
    conn.execute("UPDATE usuarios SET fecha_pago=? WHERE id=?", (datetime.now().strftime("%Y-%m-%d"), id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/api/viaje_actual")
def api_viaje_actual():
    if not session.get("user_id"):
        return {"viaje": None}

    conn = get_db()

    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id = ?
        AND estado IN ('aceptado', 'en_camino', 'recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()

    conn.close()

    if viaje:
        return {"viaje": dict(viaje)}
    else:
        return {"viaje": None}
@app.route("/cancelar_viaje/<int:id>")
def cancelar_viaje(id):

    # 🔒 validar sesión
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    try:
        # 🔴 Solo cancelar si es del cliente y está pendiente
        viaje = conn.execute("""
            SELECT * FROM viajes
            WHERE id = ? AND cliente_id = ? AND estado = 'pendiente'
        """, (id, session["user_id"])).fetchone()

        if not viaje:
            return redirect(url_for("cliente"))

        # 🟢 cancelar
        conn.execute("""
            UPDATE viajes
            SET estado = 'cancelado'
            WHERE id = ?
        """, (id,))
        conn.commit()

    except Exception as e:
        print("ERROR cancelar_viaje:", e)

    finally:
        conn.close()

    return redirect(url_for("cliente"))
@app.route("/verificar_viajes")
def verificar_viajes():
    try:
        ultimo_id = int(request.args.get("ultimo_id", 0))
    except:
        ultimo_id = 0

    conn = get_db()

    viaje = conn.execute("""
        SELECT id FROM viajes 
        WHERE estado = 'pendiente' AND id > ?
        ORDER BY id DESC LIMIT 1
    """, (ultimo_id,)).fetchone()

    conn.close()

    if viaje:
        return {"nuevo_viaje": True, "id": viaje["id"]}
    else:
        return {"nuevo_viaje": False}


@app.route("/verificar_cancelaciones")
def verificar_cancelaciones():
    user_id = session.get("user_id")

    try:
        ultimo_id = int(request.args.get("ultimo_id", 0))
    except:
        ultimo_id = 0

    conn = get_db()

    cancelado = conn.execute("""
        SELECT id FROM viajes
        WHERE conductor_id = ?
        AND estado = 'cancelado'
        AND id > ?
        ORDER BY id DESC LIMIT 1
    """, (user_id, ultimo_id)).fetchone()

    conn.close()

    if cancelado:
        return {"cancelado": True, "id": cancelado["id"]}
    else:
        return {"cancelado": False}


# ---------------------- ADMIN ----------------------
@app.route("/admin")
def admin():
    if not rol("admin"):
        return "Acceso denegado", 403

    conn = get_db()
    conductores = conn.execute("SELECT * FROM usuarios WHERE tipo='conductor'").fetchall()

    lista = []
    for c in conductores:
        lista.append(dict(c))

    conn.close()
    return render_template("admin.html", conductores=lista)
@app.route("/cambiar_estado_viaje/<int:id>/<nuevo_estado>")
def cambiar_estado_viaje(id, nuevo_estado):
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    conn = get_db()
    # Actualizamos el estado en la base de datos
    conn.execute("UPDATE viajes SET estado = ? WHERE id = ?", (nuevo_estado, id))
    conn.commit()
    conn.close()

    # Si el viaje terminó, lo mandamos a ver nuevos viajes
    if nuevo_estado == 'finalizado':
        return redirect(url_for("viajes_disponibles"))
    
    # Si no, regresamos al panel del conductor para ver el mapa
    return redirect(url_for("conductor"))

@app.route("/finalizar_viaje/<int:id>")
def finalizar_viaje(id):
    conn = get_db()
    conn.execute("UPDATE viajes SET estado='finalizado' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("conductor"))

# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------- RESET (RESTAURADO) ----------------------

def es_admin():
    return session.get("telefono", "").strip() == "9513928223"


@app.route("/reset_conductores")
def reset_conductores():
    if not es_admin():
        return "Acceso denegado", 403

    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo='conductor'")
    conn.commit()
    conn.close()

    return "Conductores eliminados"


@app.route("/reset_clientes")
def reset_clientes():
    if not es_admin():
        return "Acceso denegado", 403

    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo='cliente'")
    conn.commit()
    conn.close()

    return "Clientes eliminados"


@app.route("/reset_viajes")
def reset_viajes():
    if not es_admin():
        return "Acceso denegado", 403

    conn = get_db()
    conn.execute("DELETE FROM viajes")
    conn.commit()
    conn.close()

    return "Viajes eliminados"


if __name__ == "__main__":
    app.run(debug=True)