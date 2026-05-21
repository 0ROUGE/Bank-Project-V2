
from fastapi import FastAPI , HTTPException
app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows your WSL file to connect!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# This is our hidden internal data store (Variables in memory)
# We have two simulated customers setup here

BANK_DATABASE = {

"1001": {
 "Name":"One",
 "Pin":"1112",
 "Balance": 2400,
 "Loan":0,
"History":["Deposit: 5000","Withdrawal:2600"]
  },

"1002": {
"Name":"Two",
"Pin":"2221",
"Balance":2000,
"Loan":1500,
"History":["Deposit: 1000","Investments:500"]
}
}


# Connection to the database
@app.get("/view_account")
def view_account(account_number: str, Pin: str):
    
    if account_number not in BANK_DATABASE:
        
        raise HTTPException(status_code=404, detail="Account number not found!")

    
    customer_account = BANK_DATABASE[account_number]

    
    if customer_account["Pin"] != Pin:
        
        raise HTTPException(status_code=401, detail="Pin Invalid!!")

    
    return {
        "Customer Name": customer_account["Name"],
        "Account Number": account_number,
        "Available Balance": f"${customer_account['Balance']}",
        "Active Loans": f"${customer_account['Loan']}",
        "Recent Transactions": customer_account["History"]
   }

from fastapi.responses import FileResponse

@app.get("/")
def read_index():
    return FileResponse("index.html")
