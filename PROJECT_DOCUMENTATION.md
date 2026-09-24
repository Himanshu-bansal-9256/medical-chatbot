# 🏥 MediCare AI — Enterprise Medical RAG Chatbot Documentation

## 1. Executive Summary & Purpose
**MediCare AI** is a production-grade, privacy-focused medical assistant and question-answering system. It employs an **Advanced Hybrid Retrieval-Augmented Generation (RAG)** pipeline to answer user queries using verified medical literature (Gale Encyclopedia of Medicine / medical textbooks) with zero hallucination guardrails, source citations, real-time token streaming, user authentication, and persistent chat sessions.

---

## 2. High-Level Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18, Vite, Vanilla CSS | Fast, responsive UI with Dark/Light modes, resizable drawer, real-time SSE stream consumption |
| **Markdown & Formatting** | `react-markdown`, `remark-gfm` | Formats medical tables, lists, bold concepts, disclaimer blocks |
| **Backend API** | Python Flask, Flask-CORS, Flask-Limiter | RESTful & Server-Sent Events (SSE) streaming API with IP rate limiting |
| **Authentication & Security** | PyJWT (JSON Web Tokens), bcrypt | Secure password hashing (salted) + 24-hour stateless bearer token auth |
| **Database** | SQLite3 (`medicare.db`) | WAL mode enabled, foreign keys ON, stores users and chat sessions |
| **LLM Inference** | Groq Cloud API (`openai/gpt-oss-20b`) | Ultra-low latency, temperature=0 for clinical determinism |
| **Dense Vector Search** | FAISS (`faiss-cpu`) | Local vector index for sub-millisecond semantic similarity search |
| **Sparse Keyword Search** | BM25 (`rank-bm25`) | Lexical matching for exact medical terms, drug names, and symptoms |
| **Dense Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | 384-dimensional dense embeddings for document chunks |
| **Neural Re-ranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Deep cross-attention scoring between rewritten query and candidate docs |

---

## 3. System Architecture & End-to-End Workflow

```
[ User Input in React Frontend ]
              │
              ▼ (POST /api/chat/stream + Bearer Token)
[ Flask API: Auth & Rate Limiter ]
              │
              ▼
[ Query Rewriter (LLM) ] ◄── Uses previous conversation turns to resolve pronouns (e.g. "it", "they")
              │
        ┌─────┴─────────────────────────┐
        ▼                               ▼
 [ FAISS Vector Search ]         [ BM25 Keyword Search ]
 (Dense Semantic Top-5)          (Sparse Exact Match Top-5)
        └─────┬─────────────────────────┘
              ▼
   [ Deduplication & Merge ] (~6-10 unique docs)
              │
              ▼
 [ Cross-Encoder Re-ranker ] (Neural scoring -> filters to Top-3 most relevant)
              │
              ▼
 [ Clinical Prompt Construction ] (Strict guardrails + context injection)
              │
              ▼
 [ Groq LLM (Streaming) ]
              │
              ▼ (Server-Sent Events: text/event-stream)
[ Real-time Token Stream & Source Citations -> React UI ]
```

---

## 4. Ingestion Pipeline (`backend/create_memory_for_llm.py`)

This offline pipeline converts raw medical PDF books into searchable vector memory:

1. **PDF Loading**: `DirectoryLoader` and `PyPDFLoader` load medical textbooks from `backend/data/*.pdf`.
2. **Text Chunking**:
   - `RecursiveCharacterTextSplitter` cuts documents into manageable pieces.
   - `chunk_size = 700` characters.
   - `chunk_overlap = 100` characters (ensures continuous medical context across chunk boundaries).
3. **Embedding Computation**:
   - Model: `sentence-transformers/all-MiniLM-L6-v2` (runs via HuggingFaceEmbeddings).
   - Generates 384-dimensional dense vectors.
4. **FAISS Storage**:
   - Chunks and embeddings are indexed and saved to disk at `backend/vectorstore/db_faiss/` (`index.faiss` + `index.pkl`).

---

## 5. Advanced RAG Pipeline Deep-Dive (`backend/rag_pipeline.py`)

The query engine does **not** do naive vector retrieval. It follows an enterprise 6-step pipeline:

### Step 1: Contextual Query Rewriting (`rewriter_chain`)
- If conversation history exists, the user's latest question is transformed into a standalone query.
- *Example*:
  - User turn 1: *"What is Diabetes?"*
  - User turn 2: *"What are its symptoms?"*
  - Rewritten query: *"What are the symptoms of diabetes?"*
- Eliminates retrieval failures caused by pronouns (*"its"*, *"they"*, *"that disease"*).

### Step 2: Hybrid Retrieval (FAISS + BM25)
- **FAISS (Dense Retriever)**: Retrieves 5 chunks based on conceptual semantic meaning.
- **BM25 (Sparse Retriever)**: Retrieves 5 chunks using BM25Okapi token frequency (catches exact disease names, dosages, latin names).
- Both result sets are merged and deduplicated using content hashes.

### Step 3: Neural Cross-Encoder Re-Ranking (`rerank_documents`)
- Standard bi-encoders calculate similarity independently. 
- The Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) performs full cross-attention on `(query, document)` pairs simultaneously.
- Scores all candidate chunks and picks the **top 3 most contextually accurate chunks**.

### Step 4: Clinical Prompting & Medical Safety Guardrails
The prompt enforces strict medical guidelines:
- **No Direct Diagnosis**: Assistant never diagnoses individual users.
- **No Treatment Prescriptions**: Never prescribes specific drugs or dosages for personal use.
- **Hallucination Protection**: If the provided medical context doesn't contain the answer, it explicitly states that the knowledge base lacks the information.
- **Structured Formatting**: Uses clean markdown bullet points for causes, symptoms, and treatments.

### Step 5: Real-Time SSE Token Streaming (`ask_question_stream`)
Yields JSON events over HTTP SSE:
- `{"type": "status", "content": "Searching medical knowledge base..."}`
- `{"type": "status", "content": "Analyzing medical literature..."}`
- `{"type": "status", "content": "Generating clinical answer..."}`
- `{"type": "token", "content": "Diabetes is a..."}` (streamed word-by-word)
- `{"type": "sources", "content": [{"page": 42, "source": "medical_book.pdf"}]}`
- `{"type": "done", "content": "<rewritten_question>"}`

### Step 6: Auto Title Generation (`generate_title`)
- After the first question-answer exchange, `title_chain` generates a concise 3-5 word title (e.g., *"Diabetes Symptoms & Causes"*) and saves it to the session.

---

## 6. Database & Authentication Architecture

### Database Schema (`backend/database.py`)
Uses SQLite in **WAL (Write-Ahead Logging) mode** for concurrency and performance:

1. **`users` Table**:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `name`: TEXT NOT NULL
   - `email`: TEXT UNIQUE NOT NULL
   - `password_hash`: TEXT NOT NULL (bcrypt hashed with salt)
   - `created_at`: TEXT

2. **`chat_sessions` Table**:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `user_id`: INTEGER (Foreign key &rarr; `users.id` ON DELETE CASCADE)
   - `title`: TEXT DEFAULT 'New Chat'
   - `messages`: TEXT (JSON stringified array of messages with citations & timestamps)
   - `share_token`: TEXT UNIQUE (Hex token for public read-only consultation sharing)
   - `created_at`, `updated_at`: Timestamps

### Security & Rate Limiting (`backend/auth.py` & `backend/app.py`)
- **Passwords**: Salted & hashed using `bcrypt.hashpw`.
- **JWT**: Stateless tokens issued on login/signup with a 24-hour expiration, validated on protected routes via `@auth_required` decorator.
- **Rate Limiting**: `Flask-Limiter` protects against DDoS & brute force:
  - Auth routes (`/signup`, `/login`): max 10 requests/minute.
  - Chat streaming (`/chat/stream`): max 20 requests/minute.
  - Public share viewing (`/share/<token>`): max 60 requests/minute.
  - Global: 300 per day / 100 per hour per IP.

---

## 7. Backend API Specification

| Endpoint | Method | Auth Required | Description |
|---|---|:---:|---|
| `/api/health` | GET | No | Backend health check & active model status |
| `/api/auth/signup` | POST | No | Registers user, validates email & length, returns JWT |
| `/api/auth/login` | POST | No | Verifies bcrypt password, returns JWT token & user object |
| `/api/auth/me` | GET | Yes | Retrieves profile info for current authenticated user |
| `/api/auth/change-password` | POST | Yes | Verifies current password and sets new hashed password |
| `/api/history` | GET | Yes | Lists all past chat sessions for current user |
| `/api/history` | POST | Yes | Creates a new chat session or updates messages in existing |
| `/api/history/<id>` | GET | Yes | Retrieves full message history of a specific session |
| `/api/history/<id>` | DELETE | Yes | Deletes a session belonging to authenticated user |
| `/api/history/auto-title` | POST | Yes | Generates smart 3-5 word title using LLM |
| `/api/history/<id>/share` | POST | Yes | Generates a unique public share token |
| `/api/share/<token>` | GET | No | Public read-only view of a shared medical consultation |
| `/api/chat` | POST | Yes | Synchronous RAG answer endpoint |
| `/api/chat/stream` | POST | Yes | SSE streaming RAG endpoint (live tokens + source metadata) |

---

## 8. Frontend Architecture & Features (`frontend/src/`)

- **State Persistence**: User session and auth token stored securely in `localStorage`.
- **SSE Stream Reader**: Consumes HTTP chunked streams using the native browser `fetch` and `ReadableStreamDefaultReader` with UTF-8 decoding.
- **AbortController Support**: Allows the user to click **"Stop"** to immediately abort ongoing LLM generation.
- **Interactive Sidebar**:
  - Drag-to-resize sidebar width (190px - 460px), saved to `localStorage`.
  - Grouped chat sessions with rename, delete, and active session highlight.
- **Consultation Sharing**: One-click generation of sharable links (`/?share=<token>`) allowing doctors or patients to view a read-only consultation.
- **Message Actions**: One-click copy to clipboard for both user questions and assistant answers.
- **Theme Switcher**: Dark mode / Light mode with smooth CSS variables transition.

---

## 9. File & Folder Structure

```
Medical_chatbot/
├── .venv/                      # Python virtual environment (all dependencies)
├── .vscode/
│   └── settings.json           # VS Code configuration pointing to .venv interpreter
├── backend/
│   ├── app.py                  # Main Flask API server with all routes & middleware
│   ├── auth.py                 # JWT token generation, verification, and bcrypt hashing
│   ├── database.py             # SQLite database schemas and CRUD operations
│   ├── rag_pipeline.py         # 6-step Hybrid RAG engine (Groq, BM25, FAISS, CrossEncoder)
│   ├── create_memory_for_llm.py# Offline ingestion script (PDF -> Chunks -> FAISS index)
│   ├── medicare.db             # SQLite database file
│   ├── requirements.txt        # Backend dependencies
│   ├── data/                   # Medical textbook PDFs (source knowledge base)
│   └── vectorstore/db_faiss/   # Saved FAISS index files (index.faiss, index.pkl)
└── frontend/
    ├── package.json            # Frontend dependencies (React, Vite, remark-gfm)
    ├── vite.config.js          # Vite config with API proxy (/api -> http://localhost:5000)
    └── src/
        ├── main.jsx            # React root mount
        ├── App.jsx             # Main dashboard, chat manager, and stream consumer
        ├── App.css             # Core design system, glassmorphism, responsive styles
        └── pages/
            ├── Login.jsx       # Authentication login view
            ├── Signup.jsx      # User registration view
            └── Auth.css        # Auth forms styling
```

---

## 10. Local Setup & Execution Guide

### Backend:
```bash
cd backend
# 1. Activate Virtual Environment
..\.venv\Scripts\activate   # Windows
# source .venv/bin/activate # Mac/Linux

# 2. Set Groq API Key in .env
# GROQ_API_KEY="gsk_..."

# 3. Build Vector DB (Only needed once or when adding new PDFs)
python create_memory_for_llm.py

# 4. Start Backend Server (runs on http://localhost:5000)
python app.py
```

### Frontend:
```bash
cd frontend
# 1. Install packages
npm install

# 2. Start Vite Dev Server (runs on http://localhost:5173)
npm run dev
```
