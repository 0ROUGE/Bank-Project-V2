import sqlite3
import os
import random
import string
import smtplib
import cloudinary
import cloudinary.uploader
import urllib.request
import json
import urllib.parse
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GMAIL_ADDRESS = "jeffersonchirp@gmail.com"
GMAIL_APP_PASSWORD = "Kithome2024@"
SECRET_KEY = "cjmbanking-super-secret-key-2024"
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

cloudinary.config(
    cloud_name="dvsvapebg",
    api_key="139417474571381",
    api_secret="HWCiOzE19GaszI1dImxB6jlemUc"
)

security = HTTPBearer()

def create_token(user_id: int, username: str):
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Please log in again.")

RECAPTCHA_SECRET = "6LdBpP8sAAAAAGcZ6cRXkvpV8BVtk7Ict8WlRXy4"

# ── RECAPTCHA ─────────────────────────────────────────────────────────────────
def verify_recaptcha(token: str) -> bool:
    if not token:
        return True
    try:
        url = "https://www.google.com/recaptcha/api/siteverify"
        data = urllib.parse.urlencode({
            "secret": RECAPTCHA_SECRET,
            "response": token
        }).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read())
            return result.get("success", False)
    except:
        return False

# ── DATABASE ──────────────────────────────────────────────────────────────────
# THE FIX: CREATE TABLE IF NOT EXISTS — never drop tables on startup
def init_db():
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    cursor.execute("""
	CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL,
            terms_accepted INTEGER DEFAULT 0,
            full_name TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            surname TEXT DEFAULT '',
            id_number TEXT UNIQUE DEFAULT '',
            dob TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            balance REAL DEFAULT 0.0,
            email_verified INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recovery_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            purpose TEXT DEFAULT 'reset'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
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
        CREATE TABLE IF NOT EXISTS allowances (
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
def send_email(to_email: str, subject: str, body: str):
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

def send_recovery_email(to_email: str, code: str):
    send_email(to_email, "CJ M-Banking — Your Recovery Code", f"""Hello,

Your password recovery code is:

    {code}

This code expires in 60 seconds.
If you did not request this, ignore this email.

— CJ M-Banking Support""")

def send_verification_email(to_email: str, code: str):
    send_email(to_email, "CJ M-Banking — Verify Your Email", f"""Welcome to CJ M-Banking!

Your email verification code is:

    {code}

This code expires in 10 minutes.
Enter it on the verification page to activate your account.

— CJ M-Banking Support""")

# ── STATIC + PAGES ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
async def read_index():
    return FileResponse("index.html")

@app.get("/dashboard")
async def read_dashboard():
    return FileResponse("dashboard.html")

# ── /me — validates JWT and returns fresh user data ───────────────────────────
@app.get("/me")
async def get_me(payload: dict = Depends(verify_token)):
    username = payload.get("username")
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
    return {"id": user[0], "username": user[1], "email": user[2], "phone": user[3],
            "full_name": user[4], "bio": user[5], "photo_url": user[6], "balance": user[7]}

# ── CREATE ACCOUNT ────────────────────────────────────────────────────────────
# ── CREATE ACCOUNT ────────────────────────────────────────────────────────────
@app.post("/create-account")
async def register_user(
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    terms_accepted: str = Form(...),
    first_name: str = Form(...),
    surname: str = Form(...),
    id_number: str = Form(...),
    dob: str = Form(...),
    recaptcha_token: str = Form("")
):
    if not verify_recaptcha(recaptcha_token):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if terms_accepted != "true":
        raise HTTPException(status_code=400, detail="You must accept the terms and conditions")

    # Phone validation — strip +254 prefix if present
    clean_phone = phone.replace("+254", "").replace(" ", "")
    if not clean_phone.isdigit() or len(clean_phone) != 9:
        raise HTTPException(status_code=400, detail="Enter a valid Kenyan phone number")

    # ID number validation — 8, 9, or 14 digits
    if not id_number.isdigit() or len(id_number) not in [8, 9, 14]:
        raise HTTPException(status_code=400, detail="ID number must be 8, 9, or 14 digits")

    # Age validation — must be 18+
    try:
        dob_date = datetime.strptime(dob, "%Y-%m-%d")
        today = datetime.utcnow()
        age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
        if age < 18:
            raise HTTPException(status_code=400, detail="You must be at least 18 years old to register")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date of birth format")

    # Password strength — must have uppercase, number, and symbol
    import re
    if not re.search(r'[A-Z]', password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not re.search(r'[0-9]', password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number")
    if not re.search(r'[^A-Za-z0-9]', password):
        raise HTTPException(status_code=400, detail="Password must contain at least one symbol")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    full_name = f"{first_name} {surname}"
    full_phone = f"+254{clean_phone}"

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    # Check ID number not already registered
    cursor.execute("SELECT id FROM users WHERE id_number=?", (id_number,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="This ID number is already registered")

    try:
        cursor.execute(
            """INSERT INTO users
               (username, email, phone, password, terms_accepted, email_verified,
                full_name, first_name, surname, id_number, dob)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (username, email, full_phone, password, 1, 0,
             full_name, first_name, surname, id_number, dob)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already exists")

    # Generate verification code
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    cursor.execute(
        "INSERT INTO recovery_codes (email, code, expires_at, attempts, purpose) VALUES (?, ?, ?, ?, ?)",
        (email, code, expires_at, 0, 'verify')
    )
    conn.commit()
    conn.close()

    # Send verification email
    send_verification_email(email, code)

    return {
        "message": "Account created! Check your email for your verification code.",
        "needs_verification": True,
        "email": email
    }
# ── VERIFY EMAIL ──────────────────────────────────────────────────────────────
@app.post("/verify-email")
async def verify_email(email: str = Form(...), code: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT code, expires_at FROM recovery_codes WHERE email=? AND purpose='verify'", (email,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="No verification code found.")
    stored_code, expires_at = row
    if datetime.utcnow() > datetime.fromisoformat(expires_at):
        conn.close()
        raise HTTPException(status_code=400, detail="Code has expired.")
    if code != stored_code:
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect verification code.")

    cursor.execute("UPDATE users SET email_verified=1 WHERE email=?", (email,))
    cursor.execute("DELETE FROM recovery_codes WHERE email=? AND purpose='verify'", (email,))
    conn.commit()
    conn.close()
    return {"message": "Email verified! You can now log in."}

# ── LOGIN ─────────────────────────────────────────────────────────────────────
@app.post("/login")
async def login_user(
    username: str = Form(...),
    password: str = Form(...),
    recaptcha_token: str = Form("")
):
    if not verify_recaptcha(recaptcha_token):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, email, phone, full_name, bio, photo_url, balance, email_verified FROM users WHERE username=? AND password=?",
        (username, password)
    )
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid username or password")
    if user[8] == 0:
        raise HTTPException(status_code=403, detail="EMAIL_NOT_VERIFIED")

    token = create_token(user[0], user[1])
    return {
        "message": "LOGIN SUCCESSFUL",
        "token": token,
        "user": {"id": user[0], "username": user[1], "email": user[2], "phone": user[3],
                 "full_name": user[4], "bio": user[5], "photo_url": user[6], "balance": user[7]}
    }

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
        result = cloudinary.uploader.upload(contents, folder="cjmbanking/profiles",
                                            public_id=f"user_{username}", overwrite=True, resource_type="image")
        photo_url = result["secure_url"]

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    if photo_url:
        cursor.execute("UPDATE users SET full_name=?, bio=?, photo_url=? WHERE username=?",
                       (full_name, bio, photo_url, username))
    else:
        cursor.execute("UPDATE users SET full_name=?, bio=? WHERE username=?", (full_name, bio, username))
    conn.commit()

    cursor.execute("SELECT id, username, email, phone, full_name, bio, photo_url, balance FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    conn.close()
    return {"message": "Profile updated", "user": {"id": user[0], "username": user[1], "email": user[2],
            "phone": user[3], "full_name": user[4], "bio": user[5], "photo_url": user[6], "balance": user[7]}}

# ── DEPOSIT ───────────────────────────────────────────────────────────────────
@app.post("/deposit")
async def deposit(username: str = Form(...), amount: float = Form(...), description: str = Form("Deposit")):
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
    cursor.execute("INSERT INTO transactions (user_id, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)",
                   (user[0], "deposit", amount, description, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"message": "Deposit successful", "new_balance": new_balance}

# ── WITHDRAW ──────────────────────────────────────────────────────────────────
@app.post("/withdraw")
async def withdraw(username: str = Form(...), amount: float = Form(...), description: str = Form("Withdrawal")):
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
    cursor.execute("INSERT INTO transactions (user_id, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)",
                   (user[0], "withdrawal", amount, description, datetime.utcnow().isoformat()))
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
    cursor.execute("SELECT type, amount, description, created_at FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user[0],))
    rows = cursor.fetchall()
    conn.close()
    return {"transactions": [{"type": r[0], "amount": r[1], "description": r[2], "created_at": r[3]} for r in rows]}

# ── SET ALLOWANCE ─────────────────────────────────────────────────────────────
@app.post("/set-allowance")
async def set_allowance(username: str = Form(...), amount: float = Form(...), frequency: str = Form("weekly")):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    next_date = (datetime.utcnow() + timedelta(days=7)).isoformat()
    cursor.execute("DELETE FROM allowances WHERE user_id=?", (user[0],))
    cursor.execute("INSERT INTO allowances (user_id, amount, frequency, next_date, created_at) VALUES (?, ?, ?, ?, ?)",
                   (user[0], amount, frequency, next_date, datetime.utcnow().isoformat()))
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
    cursor.execute("SELECT amount, frequency, next_date FROM allowances WHERE user_id=?", (user[0],))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"allowance": None}
    return {"allowance": {"amount": row[0], "frequency": row[1], "next_date": row[2]}}

# ── FORGOT PASSWORD ───────────────────────────────────────────────────────────
@app.post("/forgot-password")
async def forgot_password(email: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="No account found with that email")
    cursor.execute("SELECT attempts FROM recovery_codes WHERE email=? AND purpose='reset'", (email,))
    existing = cursor.fetchone()
    if existing and existing[0] >= 3:
        conn.close()
        raise HTTPException(status_code=429, detail="Maximum attempts reached. Please contact support.")
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = (datetime.utcnow() + timedelta(seconds=60)).isoformat()
    cursor.execute("DELETE FROM recovery_codes WHERE email=? AND purpose='reset'", (email,))
    cursor.execute("INSERT INTO recovery_codes (email, code, expires_at, attempts, purpose) VALUES (?, ?, ?, ?, ?)",
                   (email, code, expires_at, 1, 'reset'))
    conn.commit()
    conn.close()
    send_recovery_email(email, code)
    return {"message": "Recovery code sent to your email."}

# ── RESEND CODE ───────────────────────────────────────────────────────────────
@app.post("/resend-code")
async def resend_code(email: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT attempts FROM recovery_codes WHERE email=? AND purpose='reset'", (email,))
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
    cursor.execute("UPDATE recovery_codes SET code=?, expires_at=?, attempts=? WHERE email=? AND purpose='reset'",
                   (code, expires_at, attempts + 1, email))
    conn.commit()
    conn.close()
    send_recovery_email(email, code)
    return {"message": f"New code sent. {3 - (attempts + 1)} attempt(s) remaining."}

# ── RESET PASSWORD ────────────────────────────────────────────────────────────
@app.post("/reset-password")
async def reset_password(email: str = Form(...), code: str = Form(...),
                         new_password: str = Form(...), confirm_new_password: str = Form(...)):
    if new_password != confirm_new_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT code, expires_at FROM recovery_codes WHERE email=? AND purpose='reset'", (email,))
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
    cursor.execute("UPDATE users SET password=? WHERE email=?", (new_password, email))
    cursor.execute("DELETE FROM recovery_codes WHERE email=? AND purpose='reset'", (email,))
    conn.commit()
    conn.close()
    return {"message": "Password updated successfully!"}

# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.get("/profile/{username}")
async def get_profile(username: str):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, phone, full_name, bio, photo_url, balance FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user[0], "username": user[1], "email": user[2], "phone": user[3],
            "full_name": user[4], "bio": user[5], "photo_url": user[6], "balance": user[7]}
