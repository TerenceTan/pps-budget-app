# APAC Marketing Budget Tracker

Flask + Google Sheets budget tracking app for APAC regional marketing teams.

---

## Setup (5 steps, ~10 minutes)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a Google Cloud service account

1. Go to https://console.cloud.google.com
2. Create a new project (or use an existing one)
3. Enable these two APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Go to **IAM & Admin → Service Accounts**
5. Click **Create Service Account** — name it anything (e.g. `budget-tracker`)
6. Click the service account → **Keys** tab → **Add Key → Create new key → JSON**
7. Save the downloaded file as **`credentials.json`** in this folder

### 3. Create the Google Spreadsheet

1. Go to https://sheets.google.com and create a new spreadsheet
2. Name it exactly: **`APAC Budget Tracker`** (must match `SHEET_NAME` in `.env`)
3. Open your `credentials.json` and copy the `client_email` value
4. In the spreadsheet, click **Share** and share it with that email address (Editor access)

The app will auto-create the three worksheets (`BudgetConfig`, `Channels`, `Entries`) on first run.

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — the defaults work as long as `credentials.json` is in the same folder and your spreadsheet is named `APAC Budget Tracker`.

### 5. Run

```bash
python app.py
```

Open http://localhost:5000

---

## Usage

### Login
- Select your market from the dropdown and click Enter
- Select **APAC** for admin access (all markets, budget config, full export)

### Admin workflow (APAC)
1. Go to **Budget Config**
2. Select a market + quarter
3. Set the country total budget
4. Add channels (e.g. Performance, Campaigns, Sales) with individual budgets
5. Save — channel budgets must not exceed country total (you'll see a warning)
6. Share the URL with market users

### Market user workflow
1. Log in with your market
2. See your channels and current budget usage
3. Click **+ Add** on any channel to log a line item
4. Fill in all required fields (marked with *)
5. Attach invoices (JPG/PDF/PNG) for Finance reconciliation
6. Approval toggle only becomes active once a JIRA link is entered

### Month-end export
- Any user can export their own market's data as CSV
- APAC admin exports all markets in one file
- Click **Export CSV** in the top right of the dashboard

---

## File structure

```
budget-flask/
  app.py              — Flask routes and auth
  sheets.py           — All Google Sheets read/write logic
  requirements.txt    — Python dependencies
  .env.example        — Environment variable template
  .env                — Your actual config (never commit this)
  credentials.json    — Google service account key (never commit this)
  templates/
    login.html        — Login page
    app.html          — Main single-page application
```

---

## Moving to AWS

When you're ready to host on AWS:

1. **EC2**: Upload the folder, install dependencies, run with `gunicorn app:app`
2. **Elastic Beanstalk**: Add a `Procfile` with `web: gunicorn app:app` and deploy
3. **Auth**: Replace the simple market selector login with Flask-Login + AWS Cognito
4. **Invoices**: Replace base64 storage with S3 uploads (one function to change in `app.py`)
5. **Database**: If you outgrow Google Sheets, swap `sheets.py` for SQLAlchemy + RDS Postgres

---

## Security notes (for production)

- Change `SECRET_KEY` in `.env` to a long random string
- Never commit `credentials.json` or `.env` to git (already in `.gitignore`)
- Add `.gitignore`:
  ```
  credentials.json
  .env
  __pycache__/
  *.pyc
  ```
