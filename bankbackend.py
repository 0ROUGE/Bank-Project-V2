import sqlite3
import os
import random
import string
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── YOUR GMAIL CREDENTIALS ──────────────────────────────────────────────────
# Go to your Gmail → Settings → Security → App Passwords
# Generate one and paste it below. Do NOT use your real Gmail password.
GMAIL_ADDRESS = "jeffersonchirp@gmail.com"
GMAIL_APP_PASSWORD = "Kithome2024@"
# ────────────────────────────────────────────────────────────────────────────


# ── DATABASE SETUP ───────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()


    
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS recovery_codes")


    # Users table — added phone and terms_accepted
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL,
            terms_accepted INTEGER DEFAULT 0
        )
    """)

    # Recovery codes table — stores code, expiry, and attempt count
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recovery_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

init_db()
# ─────────────────────────────────────────────────────────────────────────────


# ── EMAIL HELPER ─────────────────────────────────────────────────────────────
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
        # If email fails, raise an error so user knows
        raise HTTPException(status_code=500, detail=f"Email sending failed: {str(e)}")
# ─────────────────────────────────────────────────────────────────────────────


# ── STATIC FILES + INDEX ──────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
async def read_index():
    return FileResponse("index.html")

@app.get("/dashboard")
async def read_dashboard():
    return FileResponse("dashboard.html")
# ─────────────────────────────────────────────────────────────────────────────


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
    # Password match check
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # Terms must be accepted
    if terms_accepted != "true":
        raise HTTPException(status_code=400, detail="You must accept the terms and conditions")

    # Basic phone validation — must be digits, 10–13 characters
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
# ─────────────────────────────────────────────────────────────────────────────


# ── LOGIN ─────────────────────────────────────────────────────────────────────
@app.post("/login")
async def login_user(
    username: str = Form(...),
    password: str = Form(...)
):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, email, phone FROM users WHERE username = ? AND password = ?",
        (username, password)
    )
    user = cursor.fetchone()
    conn.close()

    if user:
        return {
            "message": "LOGIN SUCCESSFUL",
            "user": {
                "id": user[0],
                "username": user[1],
                "email": user[2],
                "phone": user[3]
            }
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid username or password")
# ─────────────────────────────────────────────────────────────────────────────


# ── FORGOT PASSWORD — sends real email ───────────────────────────────────────
@app.post("/forgot-password")
async def forgot_password(email: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    # Check email exists
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=400, detail="No account found with that email")

    # Check how many codes already sent in last 60 seconds
    cursor.execute(
        "SELECT * FROM recovery_codes WHERE email = ? AND attempts >= 3",
        (email,)
    )
    maxed_out = cursor.fetchone()

    if maxed_out:
        conn.close()
        raise HTTPException(
            status_code=429,
            detail="Maximum attempts reached. Please contact support."
        )

    # Generate a random 6-digit code
    code = ''.join(random.choices(string.digits, k=6))

    # Set expiry 60 seconds from now
    expires_at = (datetime.utcnow() + timedelta(seconds=60)).isoformat()

    # Delete any old codes for this email first
    cursor.execute("DELETE FROM recovery_codes WHERE email = ?", (email,))

    # Count previous attempts to track the 3-attempt limit
    cursor.execute(
        "INSERT INTO recovery_codes (email, code, expires_at, attempts) VALUES (?, ?, ?, ?)",
        (email, code, expires_at, 1)
    )
    conn.commit()
    conn.close()

    # Send the real email
    send_recovery_email(email, code)

    return {"message": "Recovery code sent to your email. It expires in 60 seconds."}
# ─────────────────────────────────────────────────────────────────────────────


# ── RESEND CODE — increments attempt counter ──────────────────────────────────
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
        raise HTTPException(
            status_code=429,
            detail="Maximum attempts reached. Please contact support."
        )

    # Generate new code and reset expiry
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = (datetime.utcnow() + timedelta(seconds=60)).isoformat()

    cursor.execute(
        "UPDATE recovery_codes SET code = ?, expires_at = ?, attempts = ? WHERE email = ?",
        (code, expires_at, attempts + 1, email)
    )
    conn.commit()
    conn.close()

    send_recovery_email(email, code)

    return {"message": f"New code sent. You have {3 - (attempts + 1)} attempt(s) remaining."}
# ─────────────────────────────────────────────────────────────────────────────


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

    cursor.execute(
        "SELECT code, expires_at FROM recovery_codes WHERE email = ?",
        (email,)
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="No recovery code found. Request one first.")

    stored_code, expires_at = row

    # Check expiry
    if datetime.utcnow() > datetime.fromisoformat(expires_at):
        conn.close()
        raise HTTPException(status_code=400, detail="Code has expired. Request a new one.")

    # Check code matches
    if code != stored_code:
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect recovery code")

    # Update password
    cursor.execute(
        "UPDATE users SET password = ? WHERE email = ?",
        (new_password, email)
    )

    # Clean up used code
    cursor.execute("DELETE FROM recovery_codes WHERE email = ?", (email,))

    conn.commit()
    conn.close()

    return {"message": "Password updated successfully! Please log in."}
# ─────────────────────────────────────────────────────────────────────────────


# ── USER PROFILE ──────────────────────────────────────────────────────────────
@app.get("/profile/{username}")
async def get_profile(username: str):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, email, phone FROM users WHERE username = ?",
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
        "phone": user[3]
    }
# ─────────────────────────────────────────────────────────────────────────────
