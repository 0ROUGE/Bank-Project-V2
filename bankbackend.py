import sqlite3
import os
import random
import string
import smtplib
import cloudinary
import cloudinary.uploader
import requests
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from jose import JWTError, jwt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── GMAIL ─────────────────────────────────────────────────────────────────────
GMAIL_ADDRESS = "jeffersonchirp@gmail.com"
GMAIL_APP_PASSWORD = "Kithome2024@"

# ── JWT ───────────────────────────────────────────────────────────────────────
SECRET_KEY = "cjmbanking-super-secret-key-2024"
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

# ── CLOUDINARY ────────────────────────────────────────────────────────────────
cloudinary.config(
    cloud_name="dvsvapebg",
    api_key="139417474571381",
    api_secret="HWCiOzE19GaszI1dImxB6jlemUc"
)

# ── JWT HELPER ────────────────────────────────────────────────────────────────
def create_token(user_id: int, username: str):
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ── DATABASE ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS recovery_codes")
    cursor.execute("DROP TABLE IF EXISTS transactions")
    cursor.execute("DROP TABLE IF EXISTS allowances")

    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL,
            terms_accepted INTEGER DEFAULT 0,
            full_name TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            balance REAL DEFAULT 0.0
        )
    """)

    cursor.execute("""
        CREATE TABLE recovery_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE allowances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            frequency TEXT DEFAULT 'weekly',
            next_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ── EMAIL ─────────────────────────────────────────────────────────────────────
def send_recovery_email(to_email: str, code: str):
    subject = "CJ M-Banking — Your Recovery Code"
    body = f"""
Hello,

Your password recovery code is:

    {code}

This code expires in 60 seconds.
If you did not request this, ignore this email.

— CJ M-Banking Support
"""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email sending failed: {str(e)}")

# ── STATIC + PAGES ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
async def read_index():
    return FileResponse("index.html")

@app.get("/dashboard")
async def read_dashboard():
    return FileResponse("dashboard.html")

# ── CREATE ACCOUNT ────────────────────────────────────────────────────────────
@app.post("/create-account")
async def register_user(
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    terms_accepted: str = Form(...)
):
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if terms_accepted != "true":
        raise HTTPException(status_code=400, detail="You must accept the terms and conditions")
    if not phone.isdigit() or not (10 <= len(phone) <= 13):
        raise HTTPException(status_code=400, detail="Enter a valid phone number (10–13 digits)")

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, email, phone, password, terms_accepted) VALUES (?, ?, ?, ?, ?)",
            (username, email, phone, password, 1)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already exists")
    conn.close()
    return {"message": "Account created successfully! Please log in."}

# ── LOGIN ─────────────────────────────────────────────────────────────────────
@app.post("/login")
async def login_user(
    username: str = Form(...),
    password: str = Form(...)
):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, email, phone, full_name, bio, photo_url, balance FROM users WHERE username = ? AND password = ?",
        (username, password)
    )
    user = cursor.fetchone()
    conn.close()

    if user:
        token = create_token(user[0], user[1])
        return {
            "message": "LOGIN SUCCESSFUL",
            "token": token,
            "user": {
                "id": user[0],
                "username": user[1],
                "email": user[2],
                "phone": user[3],
                "full_name": user[4],
                "bio": user[5],
                "photo_url": user[6],
                "balance": user[7]
            }
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid username or password")

# ── UPDATE PROFILE ────────────────────────────────────────────────────────────
@app.post("/update-profile")
async def update_profile(
    username: str = Form(...),
    full_name: str = Form(""),
    bio: str = Form(""),
    photo: UploadFile = File(None)
):
    photo_url = None

    if photo and photo.filename:
        contents = await photo.read()
        result = cloudinary.uploader.upload(
            contents,
            folder="cjmbanking/profiles",
            public_id=f"user_{username}",
            overwrite=True,
            resource_type="image"
        )
        photo_url = result["secure_url"]

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    if photo_url:
        cursor.execute(
            "UPDATE users SET full_name=?, bio=?, photo_url=? WHERE username=?",
            (full_name, bio, photo_url, username)
        )
    else:
        cursor.execute(
            "UPDATE users SET full_name=?, bio=? WHERE username=?",
            (full_name, bio, username)
        )

    conn.commit()

    cursor.execute(
        "SELECT id, username, email, phone, full_name, bio, photo_url, balance FROM users WHERE username=?",
        (username,)
    )
    user = cursor.fetchone()
    conn.close()

    return {
        "message": "Profile updated",
        "user": {
            "id": user[0],
            "username": user[1],
            "email": user[2],
            "phone": user[3],
            "full_name": user[4],
            "bio": user[5],
            "photo_url": user[6],
            "balance": user[7]
        }
    }

# ── DEPOSIT ───────────────────────────────────────────────────────────────────
@app.post("/deposit")
async def deposit(
    username: str = Form(...),
    amount: float = Form(...),
    description: str = Form("Deposit")
):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, balance FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    new_balance = user[1] + amount
    cursor.execute("UPDATE users SET balance=? WHERE username=?", (new_balance, username))
    cursor.execute(
        "INSERT INTO transactions (user_id, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)",
        (user[0], "deposit", amount, description, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    return {"message": "Deposit successful", "new_balance": new_balance}

# ── WITHDRAW ──────────────────────────────────────────────────────────────────
@app.post("/withdraw")
async def withdraw(
    username: str = Form(...),
    amount: float = Form(...),
    description: str = Form("Withdrawal")
):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, balance FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    if user[1] < amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Insufficient funds")

    new_balance = user[1] - amount
    cursor.execute("UPDATE users SET balance=? WHERE username=?", (new_balance, username))
    cursor.execute(
        "INSERT INTO transactions (user_id, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)",
        (user[0], "withdrawal", amount, description, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    return {"message": "Withdrawal successful", "new_balance": new_balance}

# ── TRANSACTIONS ──────────────────────────────────────────────────────────────
@app.get("/transactions/{username}")
async def get_transactions(username: str):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    cursor.execute(
        "SELECT type, amount, description, created_at FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (user[0],)
    )
    rows = cursor.fetchall()
    conn.close()

    return {
        "transactions": [
            {"type": r[0], "amount": r[1], "description": r[2], "created_at": r[3]}
            for r in rows
        ]
    }

# ── SET ALLOWANCE ─────────────────────────────────────────────────────────────
@app.post("/set-allowance")
async def set_allowance(
    username: str = Form(...),
    amount: float = Form(...),
    frequency: str = Form("weekly")
):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    next_date = (datetime.utcnow() + timedelta(days=7)).isoformat()

    cursor.execute("DELETE FROM allowances WHERE user_id=?", (user[0],))
    cursor.execute(
        "INSERT INTO allowances (user_id, amount, frequency, next_date, created_at) VALUES (?, ?, ?, ?, ?)",
        (user[0], amount, frequency, next_date, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    return {"message": f"Allowance of KES {amount} set successfully"}

# ── GET ALLOWANCE ─────────────────────────────────────────────────────────────
@app.get("/allowance/{username}")
async def get_allowance(username: str):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    cursor.execute(
        "SELECT amount, frequency, next_date FROM allowances WHERE user_id=?",
        (user[0],)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"allowance": None}

    return {
        "allowance": {
            "amount": row[0],
            "frequency": row[1],
            "next_date": row[2]
        }
    }

# ── FORGOT PASSWORD ───────────────────────────────────────────────────────────
@app.post("/forgot-password")
async def forgot_password(email: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=400, detail="No account found with that email")

    cursor.execute("SELECT * FROM recovery_codes WHERE email = ? AND attempts >= 3", (email,))
    maxed_out = cursor.fetchone()

    if maxed_out:
        conn.close()
        raise HTTPException(status_code=429, detail="Maximum attempts reached. Please contact support.")

    code = ''.join(random.choices(string.digits, k=6))
    expires_at = (datetime.utcnow() + timedelta(seconds=60)).isoformat()

    cursor.execute("DELETE FROM recovery_codes WHERE email = ?", (email,))
    cursor.execute(
        "INSERT INTO recovery_codes (email, code, expires_at, attempts) VALUES (?, ?, ?, ?)",
        (email, code, expires_at, 1)
    )
    conn.commit()
    conn.close()

    send_recovery_email(email, code)
    return {"message": "Recovery code sent to your email."}

# ── RESEND CODE ───────────────────────────────────────────────────────────────
@app.post("/resend-code")
async def resend_code(email: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT attempts FROM recovery_codes WHERE email = ?", (email,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Request a code first")

    attempts = row[0]
    if attempts >= 3:
        conn.close()
        raise HTTPException(status_code=429, detail="Maximum attempts reached.")

    code = ''.join(random.choices(string.digits, k=6))
    expires_at = (datetime.utcnow() + timedelta(seconds=60)).isoformat()

    cursor.execute(
        "UPDATE recovery_codes SET code = ?, expires_at = ?, attempts = ? WHERE email = ?",
        (code, expires_at, attempts + 1, email)
    )
    conn.commit()
    conn.close()

    send_recovery_email(email, code)
    return {"message": f"New code sent. {3 - (attempts + 1)} attempt(s) remaining."}

# ── RESET PASSWORD ────────────────────────────────────────────────────────────
@app.post("/reset-password")
async def reset_password(
    email: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    confirm_new_password: str = Form(...)
):
    if new_password != confirm_new_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT code, expires_at FROM recovery_codes WHERE email = ?", (email,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="No recovery code found.")

    stored_code, expires_at = row

    if datetime.utcnow() > datetime.fromisoformat(expires_at):
        conn.close()
        raise HTTPException(status_code=400, detail="Code has expired.")

    if code != stored_code:
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect recovery code")

    cursor.execute("UPDATE users SET password = ? WHERE email = ?", (new_password, email))
    cursor.execute("DELETE FROM recovery_codes WHERE email = ?", (email,))
    conn.commit()
    conn.close()

    return {"message": "Password updated successfully!"}

# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.get("/profile/{username}")
async def get_profile(username: str):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, email, phone, full_name, bio, photo_url, balance FROM users WHERE username=?",
        (username,)
    )
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user[0],
        "username": user[1],
        "email": user[2],
        "phone": user[3],
        "full_name": user[4],
        "bio": user[5],
        "photo_url": user[6],
        "balance": user[7]
    }
def verify_recaptcha(token):
    secret = "6LfCIf0sAAAAADfpOhaFMFnf9S-g0cnJVXcxdrLud"
    response = requests.post(
        'https://www.google.com/recaptcha/api/siteverify',
        data={'secret': secret, 'response': token}
    )
    return response.json().get('success', False)
