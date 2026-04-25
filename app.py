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
from werkzeug.security import check_password_hash

@app.route("/", methods=["GET", "POST"]) 
def login():
    error = None
    if request.method == "POST":
        telefono = request.form.get("telefono", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=?",
            (telefono,)
        ).fetchone()
        conn.close()

        # 🔴 VALIDACIÓN CORRECTA
        if user and check_password_hash(user["password"], password):

            session.clear()

            session["user_id"] = user["id"]
            session["nombre"] = user["nombre"]
            session["telefono"] = user["telefono"]

            tipo_usuario = str(user["tipo"]).lower().strip()
            session["tipo"] = tipo_usuario

            if tipo_usuario == "admin":
                return redirect(url_for("admin"))
            elif tipo_usuario == "conductor":
                return redirect(url_for("conductor"))
            else:
                return redirect(url_for("cliente"))
        else:
            error = "Teléfono o contraseña incorrectos"

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
@app.route("/conductor")
def conductor():
    # Verificamos si hay usuario en sesión
    if "user_id" not in session:
        return redirect(url_for("login"))

    # IMPORTANTE: Verificamos el tipo usando session.get("tipo")
    # que es como lo guarda tu ruta de login corregida.
    if session.get("tipo") != "conductor":
        return "No autorizado: Se requiere perfil de conductor", 403

    conn = get_db()
    # Buscamos si tiene un viaje activo
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)

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
@app.route("/estado_conductor")
def estado_conductor():
    print("SESSION:", dict(session))

    if session.get("tipo") != "conductor":
        return "Acceso denegado", 403

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)
@app.route("/estado_conductor_v2")
def estado_conductor_v2():  # <--- CAMBIA ESTE NOMBRE
    print("SESSION:", dict(session))

    if session.get("tipo") != "conductor":
        return "Acceso denegado", 403

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
    if not es_admin():
        return redirect(url_for('login'))

    try:
        conn = get_db()
        # Actualizamos la fecha de pago al día de hoy y reseteamos el estado
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")

        conn.execute('''
            UPDATE usuarios
            SET fecha_pago = ?, activo = 1
            WHERE id = ?
        ''', (fecha_hoy, id))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error en pago: {e}")
        return "Error interno al procesar el pago", 500

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

    conn = get_db()

    conductor = conn.execute(
        'SELECT activo FROM usuarios WHERE id = ?', (id,)
    ).fetchone()

    if conductor:
        nuevo_estado = 0 if conductor['activo'] == 1 else 1
        conn.execute(
            'UPDATE usuarios SET activo = ? WHERE id = ?',
            (nuevo_estado, id)
        )
        conn.commit()

    conn.close()
    return redirect(url_for('admin'))

# ---------------------- ADMIN ----------------------
@app.route("/admin")
def admin():
    if session.get("tipo") != "admin":
        return "Acceso denegado", 403

    conn = get_db()
    conductores_db = conn.execute(
        "SELECT * FROM usuarios WHERE tipo='conductor'"
    ).fetchall()

    lista = []
    hoy = datetime.now()

    for c in conductores_db:
        c = dict(c)

        # -------- CALCULAR DÍAS --------
        if c["fecha_pago"]:
            fecha_pago = datetime.strptime(c["fecha_pago"], "%Y-%m-%d")
            dias = 7 - (hoy - fecha_pago).days  # semanal

            if dias <= 0:
                c["dias_restantes"] = "Vencido"
                c["activo"] = 0  # 🔴 BLOQUEAR AUTOMÁTICAMENTE

                # Guardar en BD
                conn.execute(
                    "UPDATE usuarios SET activo=0 WHERE id=?",
                    (c["id"],)
                )
            else:
                c["dias_restantes"] = dias
        else:
            c["dias_restantes"] = "Sin pago"
            c["activo"] = 0

        lista.append(c)

    conn.commit()
    conn.close()

    return render_template(
        "admin.html",
        conductores=lista
    )
# ---------------------- RESET ----------------------
# ---------------------- FUNCIONES DE ADMINISTRACIÓN ----------------------

def es_admin():
    """Verifica de forma segura si el usuario actual es administrador."""
    return session.get("tipo") == "admin"

@app.route("/reset_conductores")
def reset_conductores():
    if not es_admin():
        return "Acceso denegado: Se requiere perfil de administrador", 403

    conn = get_db()
    # Borramos solo a los usuarios marcados como conductores
    conn.execute("DELETE FROM usuarios WHERE tipo = 'conductor'")
    conn.commit()
    conn.close()

    # Redirige de vuelta al panel para ver la tabla vacía
    return redirect(url_for('admin'))

@app.route("/reset_clientes")
def reset_clientes():
    if not es_admin():
        return "Acceso denegado: Se requiere perfil de administrador", 403

    conn = get_db()
    # Borramos solo a los usuarios marcados como clientes
    conn.execute("DELETE FROM usuarios WHERE tipo = 'cliente'")
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

@app.route("/reset_viajes")
def reset_viajes():
    if not es_admin():
        return "Acceso denegado: Se requiere perfil de administrador", 403

    conn = get_db()
    # Borramos la tabla completa de viajes
    conn.execute("DELETE FROM viajes")
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" not in session:
        return "", 403

    lat = request.form.get("lat")
    lng = request.form.get("lng")

    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET lat=?, lng=? WHERE id=?",
        (lat, lng, session["user_id"])
    )
    conn.commit()
    conn.close()

    return "", 200
@app.route("/verificar_viajes")
def verificar_viajes():
    if not rol("conductor"):
        return jsonify({"nuevo_viaje": False})

    ultimo_id = request.args.get("ultimo_id", 0)

    conn = get_db()
    viaje = conn.execute("""
        SELECT id FROM viajes
        WHERE estado='pendiente' AND id > ?
        ORDER BY id DESC LIMIT 1
    """, (ultimo_id,)).fetchone()
    conn.close()

    if viaje:
        return jsonify({"nuevo_viaje": True, "id": viaje["id"]})
    else:
        return jsonify({"nuevo_viaje": False})
@app.route("/verificar_cancelaciones")
def verificar_cancelaciones():
    if not rol("conductor"):
        return jsonify({"cancelado": False})

    ultimo_id = request.args.get("ultimo_id", 0)

    conn = get_db()
    viaje = conn.execute("""
        SELECT id FROM viajes
        WHERE estado='cancelado' AND id > ?
        ORDER BY id DESC LIMIT 1
    """, (ultimo_id,)).fetchone()
    conn.close()

    if viaje:
        return jsonify({"cancelado": True, "id": viaje["id"]})
    else:
        return jsonify({"cancelado": False})
from werkzeug.security import generate_password_hash

@app.route("/admin/cambiar_password", methods=["POST"])
def cambiar_password():
    # 🔒 Verificar que sea admin
    if "user_id" not in session or session.get("tipo") != "admin":
        return redirect(url_for("login"))

    nueva = request.form.get("nueva_password", "").strip()
    confirmar = request.form.get("confirmar_password", "").strip()

    # 🔴 Validaciones
    if not nueva or not confirmar:
        return "Completa todos los campos"

    if nueva != confirmar:
        return "Las contraseñas no coinciden"

    if len(nueva) < 6:
        return "La contraseña debe tener al menos 6 caracteres"

    # 🔐 Generar hash
    hash_nuevo = generate_password_hash(nueva)

    # 💾 Guardar en BD
    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET password=? WHERE id=?",
        (hash_nuevo, session["user_id"])
    )
    conn.commit()
    conn.close()

    return redirect(url_for("admin"))
if __name__ == "__main__":
    app.run(debug=True)