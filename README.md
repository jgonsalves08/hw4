# Campus Customs — HW4

A Yale-apparel storefront with an AI shopping assistant.

- **Frontend:** React + Vite + TypeScript website with products, filters, accounts, favorites, and a floating chat.
- **Backend:** a FastAPI backend running a **PydanticAI agent** (`gpt-5.6-luna` via Portkey) that looks up real prices and stock in the store database.

Full system documentation is in [`output/harness.md`](output/harness.md).

## File layout

```
hw4/
├── AI_prompts.md            # prompts used for each problem
├── requirements.txt         # Python dependencies
├── .env.example             # placeholder settings (copy to .env)
├── .gitignore
├── README.md
├── frontend/                # Vite React TypeScript app
├── backend/
│   ├── main.py              # FastAPI app — run with: uvicorn main:app --reload --port 8000
│   ├── agent.py             # agent entry and wiring (model, prompt, limits)
│   ├── models.py            # Pydantic / PydanticAI structured types
│   ├── tools.py             # tools the agent can call
│   └── prompts/
│       └── prompt.md        # system prompt (voice, tool rules, safety rules)
└── output/
    ├── harness.md           # how the whole system works
    ├── design.md
    ├── usability.md
    ├── app_check.html
    ├── app_check_images/    # screenshots linked from app_check.html
    └── audit_trail.json     # append-only log of agent-loop activity
```

The agent is `backend/prompts/prompt.md`, `backend/agent.py`, `backend/tools.py`, and `backend/models.py`. `backend/main.py` is the FastAPI app, including accounts, chat-history storage, and the audit-trail writer.

## 1. Place the data pack (local only, not in git)

The database and product photos are **not** in this repository. Put the data pack in a `data/` folder inside `hw4/`:

```
hw4/
└── data/
    ├── campus_customs.db
    └── products/            # images referenced by the catalogue (*.jpg)
```

`data/` is listed in `.gitignore`, so it's never committed.

## 2. Set up your `.env`

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder with your own **Portkey API key** (`PORTKEY_API_KEY`). `SESSION_SECRET` is optional; set it to any long random string if you want logins to survive server restarts. Never commit `.env`.

## 3. Install

Requirements: **Python 3.11+** and **Node.js 20+**. From the `hw4/` folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm --prefix frontend install
```

## 4. Run the backend (terminal 1)

```bash
cd backend
source ../.venv/bin/activate
uvicorn main:app --reload --port 8000
```

The API runs at http://localhost:8000; `GET /api/health` returns `{"status":"ok"}`. On first start the backend adds two columns to `chat_messages` (`mentioned_products`, `conversation_id`) if they're missing. This is safe to repeat and deletes nothing.

## 5. Run the frontend (terminal 2)

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. The Vite dev server forwards `/api` and `/images` requests to the backend on port 8000, so both must be running.

## Try it

- **Products:** filter by category, price, and color; click a card for sizes and stock.
- **Chat** (bottom-right): ask "What hoodies do you have?" or, on a product page, "Do you have this in medium?" Answers come from the database.
- **Accounts:** create an account to save chat history, start new chats, and reopen past chats.
- Every agent run is appended to `output/audit_trail.json` (time, tool calls with short args/results, stop reason).

## Troubleshooting

| Problem | Fix |
|---|---|
| Products page is empty or images are missing | Check that the data pack is at `hw4/data/campus_customs.db` and `hw4/data/products/`. |
| Chat says "assistant is unavailable" | Check `PORTKEY_API_KEY` in `.env` and that the backend terminal is running. |
| `uvicorn: command not found` | Activate the virtual environment first (`source ../.venv/bin/activate` from `backend/`). |
| Logged out after restarting the backend | Expected unless `SESSION_SECRET` is set in `.env`. |
