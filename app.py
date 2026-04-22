import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "secreto_muy_seguro"

# ---------------------- DB (Rutas Absolutas para Servidor) ----------------------
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
        nombre TEXT, telefono TEXT, password TEXT, tipo TEXT,
        lat REAL, lng REAL, activo INTEGER DEFAULT 1, fecha_pago TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS viajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
        conductor_id INTEGER, estado TEXT, origen TEXT, destino TEXT,
        lat REAL, lng REAL, lat_destino REAL, lng_destino REAL
    )""")
    conn.commit()
    conn.close()

crear_tablas()
# -------------------------------------------------------------


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

##
        print("USER ENCONTRADO:", user)
        if user:
            session.update({
                "user_id": user["id"],
                "tipo": str(user["tipo"]).lower().strip(),
                "nombre": user["nombre"],
                "telefono": user["telefono"]
            })

##
            print("SESSION DESPUÉS DE LOGIN:", dict(session))  # 👈 AQUÍ
            # 🔥 REDIRECCIÓN CORRECTA
            if session["tipo"] == "cliente":
                return redirect(url_for("cliente"))
            elif session["tipo"] == "conductor":
                return redirect(url_for("conductor"))
            else:
                return redirect(url_for("login"))

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
    
    # 1. VALIDACIÓN: ¿Ya tiene un viaje activo?
    # Buscamos cualquier viaje que NO esté finalizado ni cancelado
    viaje_activo = conn.execute("""
        SELECT id FROM viajes 
        WHERE cliente_id = ? AND estado NOT IN ('finalizado', 'cancelado')
    """, (user_id,)).fetchone()

    if viaje_activo:
        conn.close()
        # Si ya tiene uno, lo regresamos a su panel con un aviso
        # Nota: Asegúrate de que tu base.html o cliente.html maneje mensajes 'error'
        return redirect(url_for("cliente", error="Ya tienes un viaje en curso."))

    # 2. PROCESO DE GUARDADO (Si no tiene viajes activos)
    try:
        # Convertimos a float() para que el mapa pueda leer los números
        lat = float(d.get("lat", 0))
        lng = float(d.get("lng", 0))
        lat_d = float(d.get("lat_destino", 0))
        lng_d = float(d.get("lng_destino", 0))
        
        conn.execute("""
            INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
            VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
        """, (user_id, d.get("origen", "N/A"), d.get("destino", "N/A"), 
              lat, lng, lat_d, lng_d))
        
        conn.commit()
    except Exception as e:
        print(f"Error al guardar viaje: {e}")
    finally:
        conn.close()
        
    return redirect(url_for("cliente"))
# ---------------------- CONDUCTOR ----------------------
@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor": return redirect("/")
    conn = get_db()
    cursor = conn.execute("SELECT * FROM viajes WHERE estado = 'pendiente'")
    viajes_query = [dict(row) for row in cursor.fetchall()]
    conn.close()
##
    print("VIAJES:", viajes_query)
    return render_template("viajes.html", viajes=viajes_query)

@app.route("/registro_conductor", methods=["GET", "POST"])
def registro_conductor():
    if request.method == "POST":
        n = request.form.get("nombre")
        t = request.form.get("telefono")
        p = request.form.get("password")

        # 🆕 nuevos campos
        numero_unidad = request.form.get("numero_unidad")
        color_vehiculo = request.form.get("color_vehiculo")

        conn = get_db()

        existe = conn.execute(
            "SELECT id FROM usuarios WHERE telefono=?",
            (t,)
        ).fetchone()

        if existe:
            conn.close()
            return "Teléfono ya registrado"

        # 🆕 INSERT actualizado
        conn.execute(
            """INSERT INTO usuarios 
            (nombre, telefono, password, tipo, numero_unidad, color_vehiculo) 
            VALUES (?, ?, ?, 'conductor', ?, ?)""",
            (n, t, p, numero_unidad, color_vehiculo)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("registro_conductor.html")

@app.route("/conductor")
def conductor():
##
    print("SESSION EN /conductor:", dict(session))  # 👈 DEBUG

    if "conductor" not in str(session.get("tipo", "")).lower():
        return redirect(url_for("login"))
    conn = get_db()

    viaje = conn.execute("""
        SELECT * FROM viajes 
        WHERE conductor_id = ? 
        AND estado IN ('aceptado', 'en_camino', 'recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()

    conn.close()

    if viaje:
        return render_template("conductor.html", viaje=dict(viaje))
    else:
        return render_template("conductor.html", viaje=None)

@app.route("/aceptar_viaje/<int:viaje_id>")
def aceptar_viaje(viaje_id):

    # 🔒 0. Validar sesión
    if not session.get("user_id") or "conductor" not in str(session.get("tipo", "")).lower():
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()

    try:
        # 🔴 1. Verificar si ya tiene viaje activo
        ocupado = conn.execute("""
            SELECT id FROM viajes 
            WHERE conductor_id = ? 
            AND estado IN ('aceptado', 'en_camino', 'recogido')
        """, (user_id,)).fetchone()

        if ocupado:
            return redirect(url_for(
                "viajes_disponibles",
                error="Ya tienes un viaje activo. Termínalo primero."
            ))

        # 🔴 2. Verificar que el viaje siga disponible
        viaje = conn.execute("""
            SELECT id FROM viajes 
            WHERE id = ? AND estado = 'pendiente'
        """, (viaje_id,)).fetchone()

        if not viaje:
            return redirect(url_for(
                "viajes_disponibles",
                error="Este viaje ya fue tomado por otro conductor"
            ))

        # 🟢 3. Aceptar viaje
        conn.execute("""
            UPDATE viajes 
            SET conductor_id = ?, estado = 'aceptado' 
            WHERE id = ?
        """, (user_id, viaje_id))

        conn.commit()

    except Exception as e:
        print("ERROR aceptar_viaje:", e)
        return redirect(url_for(
            "viajes_disponibles",
            error="Error al aceptar el viaje"
        ))

    finally:
        conn.close()

    return redirect(url_for("conductor"))
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

# ---------------------- API & AJAX (RESTAURADOS) ----------------------
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

# ---------------------- UBICACIÓN ----------------------
@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" in session:
        conn = get_db()
        conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (request.form.get("lat"), request.form.get("lng"), session["user_id"]))
        conn.commit()
        conn.close()
    return "OK"

# ---------------------- ADMIN ----------------------
@app.route("/admin")
def admin():
    if str(session.get("telefono", "")).strip() != '9513928223': return "Acceso denegado", 403
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

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/api_estado_viaje/<int:id>")
def api_estado_viaje(id):
    conn = get_db()
    # Buscamos el viaje y el nombre del conductor unido a la tabla usuarios
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
            "conductor": viaje["conductor_nombre"] if viaje["conductor_nombre"] else "Buscando..."
        })
    return jsonify({"error": "No encontrado"}), 404
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
if __name__ == "__main__":
    app.run(debug=True)