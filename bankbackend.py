from fastapi import FastAPI ,Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import sqlite3
import random
app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows your WSL file to connect!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#SET UP DATABASE
def init_db():
    conn=sqlite3.connect("bank.db")
    cursor=conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            recovery_code TEXT,
            pin TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

#SERVE THE SIGN IN OR LOGIN PAGE

@app.get("/", response_class=HTMLResponse)
def get_login_page():
    with open("index.html", "r") as f:
        return f.read()

#Store detailsa in DB
@app.post("/register")
def register_user(username: str = Form(...), email: str = Form(...), pin: str = Form(...)):
    # 1. Enforce Kenyan bank account length and numeric constraints
    if not username.isdigit() or not (9 <= len(username) <= 16):
        raise HTTPException(
            status_code=400, 
            detail="Invalid account number structure. Must be between 9 and 16 digits long."
        )

    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, email, pin) VALUES (?, ?, ?)",
            (username, email, pin)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="username or email already exists")

    conn.close()
    return {"Message": "REGISTRATION SUCCESSFUL✅"}
@app.post("/login")
def login_user(username: str = Form(...), pin: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    cursor.execute("SELECT pin FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0] == pin:
        # If successful, send them to the dashboard
        return {"message": f"Welcome to your Dashboard, {username}!"}
    else:
        # If conditions are NOT met, throw an error
        raise HTTPException(status_code=401, detail="Invalid Username or PIN")


from fastapi.responses import FileResponse

@app.get("/")
def read_index():
    return FileResponse("index.html")


import random # This tool lets us make random numbers

@app.post("/forgot-pin")
def forgot_pin(email: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    # Check if the email exists in our DB records
    cursor.execute("SELECT username FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Email not found!")

    # Generate a random 6-digit recovery code
    code = str(random.randint(100000, 999999))

    # Save this code in the database temporarily for verification later
    cursor.execute("UPDATE users SET recovery_code = ? WHERE email = ?", (code, email))
    conn.commit()
    conn.close()

    # For now, we will just return the code in the response so you can see it work!
    return {"message": f"Recovery code sent to your email! (Code: {code})"}


@app.post("/reset-pin")
def reset_pin(email: str = Form(...), code: str = Form(...), new_pin: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()

    # Look up the stored recovery code for this email
    cursor.execute("SELECT recovery_code FROM users WHERE email = ?", (email,))
    result = cursor.fetchone()

    # If no user found or the code typed doesn't match what we stored
    if not result or result[0] != code:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid recovery code!")

    # If it matches, update the PIN and wipe out the recovery code so it can't be used again
    cursor.execute(
        "UPDATE users SET pin = ?, recovery_code = NULL WHERE email = ?",
        (new_pin, email)
    )
    conn.commit()
    conn.close()

    return {"message": "PIN updated successfully! You can now log in with your new PIN."}
