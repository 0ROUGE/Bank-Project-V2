import sqlite3
import os
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
app = FastAPI()

# Enable CORS so your frontend can communicate with it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database mapping layout
def init_db():
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            pin TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
async def read_index():
    return FileResponse("index.html")

@app.post("/register")
def register_user(username: str = Form(...), email: str = Form(...), pin: str = Form(...)):
    # 1. Enforce strict Kenyan bank account parameters (9 to 16 digits only)
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
        raise HTTPException(status_code=400, detail="Username or email already exists")
    
    conn.close()
    return {"message": "REGISTRATION SUCCESSFUL✅"}

@app.post("/login")
def login_user(username: str = Form(...), pin: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND pin = ?", (username, pin))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {"message": "LOGIN SUCCESSFUL✅"}
    else:
        raise HTTPException(status_code=400, detail="Invalid account number or PIN")

@app.post("/forgot-pin")
def forgot_pin(email: str = Form(...)):
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {"message": "Recovery code sent to your email! (Use code: 123456 to reset)"}
    else:
        raise HTTPException(status_code=400, detail="Email address not found")

@app.post("/reset-pin")
def reset_pin(email: str = Form(...), code: str = Form(...), new_pin: str = Form(...)):
    if code != "123456":
        raise HTTPException(status_code=400, detail="Invalid recovery code")
        
    conn = sqlite3.connect("bank.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pin = ? WHERE email = ?", (new_pin, email))
    conn.commit()
    changes = cursor.rowcount
    conn.close()
    
    if changes > 0:
        return {"message": "PIN updated successfully! Please log in."}
    else:
        raise HTTPException(status_code=400, detail="User mapping update failed")

