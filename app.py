import os, hashlib, secrets, base64, io
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, send_file

import psycopg2-binary
import psycopg2.extras

# =============================
# APP
# =============================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False   # ⚠️ local OK, Render auto HTTPS
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# =============================
# DATABASE CONFIG (FIX MAJEUR)
# =============================
DATABASE_URL = os.environ.get("DATABASE_URL")

# FIX Render postgres:// → postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ⚠️ Fallback SQLite si pas PostgreSQL
USE_SQLITE = False
if not DATABASE_URL:
    USE_SQLITE = True
    import sqlite3

# =============================
# DB CONNECTION
# =============================
def get_db():
    if USE_SQLITE:
        conn = sqlite3.connect("app.db")
        conn.row_factory = sqlite3.Row
        return conn
    else:
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor
        )

# =============================
# UTILS
# =============================
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def row_to_dict(row):
    return dict(row) if row else None

# =============================
# INIT DB (FIX IMPORTANT)
# =============================
def init_db():
    conn = get_db()
    cur = conn.cursor()

    if USE_SQLITE:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT, prenom TEXT, email TEXT UNIQUE,
            mot_de_passe TEXT, role TEXT,
            departement TEXT, superviseur_id INT,
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS demandes_conge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employe_id INT, type_conge TEXT,
            date_debut TEXT, date_fin TEXT,
            nb_jours INT, motif TEXT,
            statut TEXT DEFAULT 'en_attente',
            document_nom TEXT, document_data BLOB,
            document_type TEXT,
            commentaire_superviseur TEXT,
            date_demande TEXT DEFAULT CURRENT_TIMESTAMP,
            date_traitement TEXT,
            superviseur_id INT
        )
        """)
    else:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id SERIAL PRIMARY KEY,
            nom VARCHAR(100),
            prenom VARCHAR(100),
            email VARCHAR(200) UNIQUE,
            mot_de_passe VARCHAR(255),
            role VARCHAR(50) DEFAULT 'employe',
            departement VARCHAR(100),
            superviseur_id INT,
            date_creation TIMESTAMP DEFAULT NOW()
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS demandes_conge (
            id SERIAL PRIMARY KEY,
            employe_id INT,
            type_conge VARCHAR(100),
            date_debut DATE,
            date_fin DATE,
            nb_jours INT,
            motif TEXT,
            statut VARCHAR(50) DEFAULT 'en_attente',
            document_nom VARCHAR(255),
            document_data BYTEA,
            document_type VARCHAR(100),
            commentaire_superviseur TEXT,
            date_demande TIMESTAMP DEFAULT NOW(),
            date_traitement TIMESTAMP,
            superviseur_id INT
        )
        """)

    # comptes par défaut
    users = [
        ("Admin", "Systeme", "admin@entreprise.com", "Admin123!", "admin"),
        ("Dupont", "Marie", "superviseur@entreprise.com", "Super123!", "superviseur"),
        ("Martin", "Jean", "employe@entreprise.com", "Employe123!", "employe")
    ]

    for u in users:
        try:
            cur.execute("""
            INSERT INTO utilisateurs (nom, prenom, email, mot_de_passe, role)
            VALUES (?, ?, ?, ?, ?)
            """ if USE_SQLITE else """
            INSERT INTO utilisateurs (nom, prenom, email, mot_de_passe, role)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            """,
            (u[0], u[1], u[2], hash_password(u[3]), u[4]))
        except:
            pass

    conn.commit()
    cur.close()
    conn.close()

# 👉 IMPORTANT : exécuté aussi sur Render
with app.app_context():
    init_db()

# =============================
# AUTH
# =============================
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Non authentifié"}), 401
        return fn(*args, **kwargs)
    return wrapper

def get_current_user():
    conn = get_db()
    cur = conn.cursor()

    query = "SELECT * FROM utilisateurs WHERE id=? " if USE_SQLITE else "SELECT * FROM utilisateurs WHERE id=%s"
    cur.execute(query, (session["user_id"],))
    row = cur.fetchone()

    cur.close()
    conn.close()
    return row_to_dict(row)

# =============================
# ROUTES
# =============================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    pw = hash_password(data.get("mot_de_passe"))

    conn = get_db()
    cur = conn.cursor()

    query = "SELECT * FROM utilisateurs WHERE email=? AND mot_de_passe=?" \
        if USE_SQLITE else \
        "SELECT * FROM utilisateurs WHERE email=%s AND mot_de_passe=%s"

    cur.execute(query, (email, pw))
    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user:
        return jsonify({"error": "Login incorrect"}), 401

    session["user_id"] = user["id"]
    return jsonify(row_to_dict(user))

# =============================
# MAIN
# =============================
if __name__ == "__main__":
    app.run(debug=True)
