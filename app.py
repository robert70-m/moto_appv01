import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "this_are_a_secreto_muy_seguro_app "

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
        telefono = request.form.get("telefono", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=? AND password=?",
            (telefono, password)
        ).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["tipo"] = str(user["tipo"]).lower().strip()
            session["nombre"] = user["nombre"]
            session["telefono"] = user["telefono"]

            if session["tipo"] == "cliente":
                return redirect(url_for("cliente"))
            elif session["tipo"] == "conductor":
                return redirect(url_for("conductor"))

        else:
            error = "Datos incorrectos"

    return render_template("login.html", error=error)


# ---------------------- REGISTRO ----------------------
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
    if not session.get("user_id"):
        return redirect(url_for("login"))

    d = request.form
    user_id = session["user_id"]

    conn = get_db()

    viaje_activo = conn.execute("""
        SELECT id FROM viajes 
        WHERE cliente_id = ? 
        AND estado NOT IN ('finalizado', 'cancelado')
    """, (user_id,)).fetchone()

    if viaje_activo:
        conn.close()
        return redirect(url_for("cliente"))

    try:
        lat = float(d.get("lat", 0))
        lng = float(d.get("lng", 0))
        lat_d = float(d.get("lat_destino", 0))
        lng_d = float(d.get("lng_destino", 0))

        conn.execute("""
            INSERT INTO viajes 
            (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
            VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            d.get("origen", "N/A"),
            d.get("destino", "N/A"),
            lat, lng, lat_d, lng_d
        ))

        conn.commit()

    except Exception as e:
        print("Error al guardar viaje:", e)

    finally:
        conn.close()

    return redirect(url_for("cliente"))


# ---------------------- CONDUCTOR ----------------------
@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes WHERE estado='pendiente'").fetchall()
    conn.close()

    return render_template("viajes.html", viajes=[dict(v) for v in viajes])


@app.route("/conductor")
def conductor():
    if session.get("tipo") != "conductor":
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


@app.route("/aceptar_viaje/<int:viaje_id>")
def aceptar_viaje(viaje_id):
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()

    try:
        ocupado = conn.execute("""
            SELECT id FROM viajes 
            WHERE conductor_id=? 
            AND estado IN ('aceptado','en_camino','recogido')
        """, (user_id,)).fetchone()

        if ocupado:
            return redirect(url_for("viajes_disponibles"))

        viaje = conn.execute("""
            SELECT id FROM viajes 
            WHERE id=? AND estado='pendiente'
        """, (viaje_id,)).fetchone()

        if not viaje:
            return redirect(url_for("viajes_disponibles"))

        conn.execute("""
            UPDATE viajes 
            SET conductor_id=?, estado='aceptado'
            WHERE id=?
        """, (user_id, viaje_id))

        conn.commit()

    except Exception as e:
        print("ERROR aceptar_viaje:", e)

    finally:
        conn.close()

    return redirect(url_for("conductor"))


@app.route("/cambiar_estado_viaje/<int:id>/<nuevo_estado>")
def cambiar_estado_viaje(id, nuevo_estado):
    if session.get("tipo") != "conductor":
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("UPDATE viajes SET estado=? WHERE id=?", (nuevo_estado, id))
    conn.commit()
    conn.close()

    if nuevo_estado == "finalizado":
        return redirect(url_for("viajes_disponibles"))

    return redirect(url_for("conductor"))


# ---------------------- API ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes").fetchall()
    conn.close()

    return jsonify({"viajes": [dict(v) for v in viajes]})


@app.route("/api_estado_viaje/<int:id>")
def api_estado_viaje(id):
    conn = get_db()

    viaje = conn.execute("""
        SELECT v.estado, u.nombre as conductor_nombre 
        FROM viajes v 
        LEFT JOIN usuarios u ON v.conductor_id = u.id 
        WHERE v.id = ?
    """, (id,)).fetchone()

    conn.close()

    if viaje:
        return jsonify({
            "estado": viaje["estado"],
            "conductor": viaje["conductor_nombre"] or "Buscando..."
        })

    return jsonify({"error": "No encontrado"}), 404


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


# ---------------------- OTROS ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
# ---------------------------------------------------------

# ---------------------- RESET DATOS (ADMIN) ----------------------

def es_admin():
    return str(session.get("telefono", "")).strip() == "9513928223"


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


# ⚠️ OPCIONAL (BORRA TODO)
@app.route("/reset_todo")
def reset_todo():
    if not es_admin():
        return "Acceso denegado", 403

    conn = get_db()

    conn.execute("DELETE FROM viajes")
    conn.execute("DELETE FROM usuarios")

    conn.commit()
    conn.close()

    return "Base de datos completamente limpia"



if __name__ == "__main__":
    app.run(debug=True)
