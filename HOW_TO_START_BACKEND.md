# How to Start the Backend - Fixed

## Problem
The project uses a **virtual environment** (`.venv`), but dependencies need to be installed there.

## Solution

### Option 1: Start Backend (Easiest)
```bash
cd "c:\Users\Asus\OneDrive\Desktop\Easy Company\backend"
..\\.venv\Scripts\python.exe interpreter.py
```

### Option 2: Activate venv then start
```bash
cd "c:\Users\Asus\OneDrive\Desktop\Easy Company"
.venv\Scripts\activate
cd backend
python interpreter.py
```

### Option 3: One-liner
```bash
cd "c:\Users\Asus\OneDrive\Desktop\Easy Company" && .\.venv\Scripts\python.exe backend\interpreter.py
```

## Verify Installation

```bash
cd "c:\Users\Asus\OneDrive\Desktop\Easy Company"
.\.venv\Scripts\pip.exe list | findstr trafilatura
```

Should show: `trafilatura 2.0.0`

## What's Installed in .venv
✅ trafilatura (2.0.0)
✅ beautifulsoup4 (4.14.3)
✅ spacy (3.8.13)
✅ All other dependencies

## Expected Output When Backend Starts
```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

## Verify Backend is Running
In another terminal:
```bash
curl http://localhost:8000/agents
```

Should return JSON list of agents.

## Success!
✅ Backend running on localhost:8000
✅ All imports working
✅ Ready to use UI
