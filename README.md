# 🏥 Medical Chatbot

A medical question-answering chatbot built using **RAG (Retrieval-Augmented Generation)**.

The project uses a medical encyclopedia PDF as its knowledge source. The PDF is converted into searchable vector embeddings, relevant information is retrieved for each user question, and a Groq LLM generates the final answer using that retrieved medical context.

---

## 1. Project Goal

The main goal of this project is to build a chatbot that can answer medical questions from a fixed medical knowledge base instead of relying only on the LLM's internal knowledge.

The chatbot should:

- Answer questions using information from the medical PDF.
- Handle follow-up questions using conversation history.
- Retrieve relevant information before generating an answer.
- Reduce hallucinations by grounding answers in retrieved content.
- Show the source page information used for the answer.
- Provide a simple chat interface using Streamlit.

---

# 2. Overall Project Flow

The project has two major parts:

### Part A — Creating the Knowledge Base

```text
Medical PDF
    ↓
PDF Loader
    ↓
Text Extraction
    ↓
Text Chunking
    ↓
HuggingFace Embeddings
    ↓
FAISS Vector Database
```

This part is performed by:

```text
create_memory_for_llm.py
```

---

### Part B — Answering User Questions

```text
User Question
    ↓
Conversation History
    ↓
Question Rewriting
    ↓
FAISS Retrieval
    ↓
Top 5 Relevant Chunks
    ↓
Cross-Encoder Reranking
    ↓
Top 3 Best Chunks
    ↓
Groq LLM
    ↓
Grounded Medical Answer
    ↓
Source Pages
    ↓
Streamlit UI
```

This part is mainly handled by:

```text
rag_pipeline.py
```

and displayed through:

```text
app.py
```

---

# 3. Project Structure

```text
Medical_chatbot/
│
├── data/
│   └── The_GALE_ENCYCLOPEDIA_of_MEDICINE_SECOND (1).pdf
│
├── vectorstore/
│   └── db_faiss/
│       ├── index.faiss
│       └── index.pkl
│
├── .streamlit/
│   └── config.toml
│
├── .env
├── .gitignore
├── app.py
├── create_memory_for_llm.py
├── rag_pipeline.py
├── requirements.txt
├── README.md
├── Pipfile
└── Pipfile.lock
```

---

# 4. What Each File Does

## `data/`

Contains the medical PDF.

This PDF is the main knowledge source for the chatbot.

---

## `create_memory_for_llm.py`

Responsible for creating the vector database.

It performs:

```text
PDF Loading
→ Chunking
→ Embeddings
→ FAISS
```

This file normally needs to be run when the source PDF or embedding/chunking configuration changes.

---

## `vectorstore/`

Contains the generated FAISS vector database.

The database stores the vector representations of the PDF chunks along with their associated information.

The current vector database was created using:

```text
chunk_size = 700
chunk_overlap = 100
```

It does not need to be rebuilt every time the application starts.

---

## `rag_pipeline.py`

This is the main backend of the chatbot.

It handles:

- Loading environment variables.
- Loading the Groq LLM.
- Loading the embedding model.
- Loading FAISS.
- Retrieving documents.
- Reranking documents.
- Rewriting follow-up questions.
- Sending context to the LLM.
- Generating the final answer.
- Returning source documents.
- Measuring pipeline timings.

---

## `app.py`

This is the Streamlit frontend.

It handles:

- Chat interface.
- Conversation history.
- New Chat functionality.
- Sending questions to the RAG pipeline.
- Displaying answers.
- Displaying source pages.
- Error messages.
- Medical disclaimer.

---

## `.env`

Stores the API key locally.

Example:

```text
GROQ_API_KEY=your_api_key
```

The actual API key should never be committed to GitHub.

---

## `requirements.txt`

Contains the Python packages required by the project.

---

## `.streamlit/config.toml`

Contains the Streamlit configuration.

The project uses:

```toml
[server]
fileWatcherType = "none"
```

This disables Streamlit's file watcher, which avoids the local `torch`/`torchvision` watcher issue encountered during development.

---

# 5. Knowledge Base Creation

Before the chatbot can answer questions, the medical PDF needs to be converted into a searchable vector database.

This happens in `create_memory_for_llm.py`.

---

## Step 1 — Load the PDF

The project uses `PyPDFLoader` through LangChain.

```text
PDF
 ↓
PyPDFLoader
 ↓
Documents
```

The loader extracts text page by page.

The page metadata is retained, which later allows the application to show source page information.

---

## Step 2 — Split the Text

The complete PDF is too large to search and send to the LLM as one block.

So the extracted text is divided into smaller chunks.

The project uses:

```text
RecursiveCharacterTextSplitter
```

Configuration:

```text
chunk_size = 700
chunk_overlap = 100
```

### Why chunks?

Instead of searching through the entire PDF, the system can find the smaller sections that are relevant to the user's question.

### Why overlap?

The overlap helps preserve context when an important sentence or piece of information is close to a chunk boundary.

---

# 6. Creating Embeddings

After chunking, every text chunk is converted into a numerical vector.

The project uses:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Flow:

```text
Text Chunk
    ↓
Embedding Model
    ↓
Numerical Vector
```

These vectors allow the system to perform semantic similarity search.

For example, a question about:

```text
"signs of high blood sugar"
```

can retrieve content related to diabetes symptoms even if the wording is not exactly the same.

---

# 7. Creating the FAISS Database

The generated embeddings are stored in FAISS.

```text
PDF Chunks
    ↓
Embeddings
    ↓
FAISS
```

The database is saved locally at:

```text
vectorstore/db_faiss
```

The main files are:

```text
index.faiss
index.pkl
```

The application later loads this database instead of processing the complete PDF again.

---

# 8. User Question Flow

Once the vector database is ready, the chatbot can answer questions.

Suppose the user asks:

```text
What are the symptoms of diabetes?
```

The question enters `ask_question()` in `rag_pipeline.py`.

The pipeline then processes it step by step.

---

# 9. Conversation History

The application stores previous messages in Streamlit session state.

The conversation is represented approximately as:

```text
User → Question
Assistant → Answer
User → Follow-up
Assistant → Answer
```

This allows the chatbot to understand follow-up questions.

For example:

```text
User: What is diabetes?

User: What are its symptoms?
```

The second question contains the reference:

```text
"its"
```

The system uses the previous conversation to understand what `"its"` refers to.

---

# 10. Question Rewriting

For follow-up questions, the project uses a question-rewriting step.

The LLM receives:

```text
Conversation History
+
Latest Question
```

and creates a standalone question.

Example:

```text
Conversation:
User: What is diabetes?

Latest Question:
What are its symptoms?

        ↓

Rewritten Question:
What are the symptoms of diabetes?
```

The rewritten question is then used for retrieval.

For the first question, there is no previous conversation, so the original question is used directly.

---

# 11. FAISS Retrieval

The rewritten question is passed to the FAISS retriever.

The retriever is configured with:

```text
k = 5
```

So FAISS initially retrieves:

```text
User Question
     ↓
FAISS
     ↓
5 Relevant Chunks
```

These 5 chunks are candidates for the final answer.

---

# 12. Cross-Encoder Reranking

FAISS provides an initial semantic search.

The project then performs another relevance check using:

```text
cross-encoder/ms-marco-MiniLM-L-6-v2
```

The retrieved question and each chunk are evaluated together.

Flow:

```text
Top 5 FAISS Chunks
       ↓
Cross-Encoder
       ↓
Relevance Scores
       ↓
Sort by Score
       ↓
Top 3 Chunks
```

So the retrieval process is:

```text
FAISS → Top 5
CrossEncoder → Best 3
```

This gives the LLM a smaller and more relevant context.

---

# 13. Building the Context

The final 3 reranked documents are combined into one context.

```text
Chunk 1
+
Chunk 2
+
Chunk 3
```

This becomes the medical information supplied to the answer-generation prompt.

---

# 14. Groq LLM

The project uses Groq through LangChain.

Model:

```text
openai/gpt-oss-20b
```

The LLM receives:

```text
Conversation History
+
Medical Context
+
User Question
```

and generates the final answer.

---

# 15. Grounded Answer Generation

The answer prompt tells the LLM to use the provided medical information as the primary source.

Important rules in the project include:

- Answer the question clearly.
- Use the provided medical information.
- Do not invent unsupported facts.
- Say when the information is not available in the knowledge base.
- Do not diagnose the user.
- Do not recommend a specific medicine or treatment for an individual patient.

The basic idea is:

```text
Retrieved Medical Information
             ↓
           LLM
             ↓
     Grounded Answer
```

This is the **RAG** part of the project.

---

# 16. Source Information

The retrieved documents contain metadata from the original PDF.

The application uses this metadata to display source information such as:

```text
Page: XX
```

This gives the user an indication of where the relevant information came from in the medical PDF.

---

# 17. Streamlit Application

`app.py` provides the user interface.

The overall interaction is:

```text
User
 ↓
Streamlit Chat UI
 ↓
ask_question()
 ↓
RAG Pipeline
 ↓
Answer + Sources
 ↓
Streamlit
 ↓
User
```

---

# 18. Chat History in Streamlit

The application stores messages using:

```python
st.session_state.messages
```

This keeps the conversation available while the user continues chatting.

When the user clicks **New Chat**, the existing conversation is cleared and a new conversation starts.

---

# 19. Complete Example Flow

Example:

```text
User:
What is diabetes?
```

### Backend

```text
Question
 ↓
No history → no rewriting
 ↓
FAISS retrieval
 ↓
Top 5 chunks
 ↓
CrossEncoder
 ↓
Top 3 chunks
 ↓
Groq LLM
 ↓
Answer
```

Then the user asks:

```text
What are its symptoms?
```

### Backend

```text
Question + Previous Conversation
 ↓
Question Rewriter
 ↓
"What are the symptoms of diabetes?"
 ↓
FAISS
 ↓
Top 5
 ↓
CrossEncoder
 ↓
Top 3
 ↓
Groq LLM
 ↓
Answer
```

So the chatbot can maintain context across questions.

---

# 20. Why This Is Called RAG

RAG means:

```text
Retrieval-Augmented Generation
```

The project has two main stages:

### Retrieval

Find relevant information:

```text
Question
 ↓
FAISS
 ↓
Relevant Chunks
```

### Generation

Generate an answer using that information:

```text
Relevant Chunks
+
Question
 ↓
LLM
 ↓
Answer
```

Together:

```text
Retrieval + Generation = RAG
```

---

# 21. Main Technologies Used

| Technology | Purpose |
|---|---|
| Python | Main programming language |
| LangChain | Connects the different components |
| PyPDF | PDF text extraction |
| RecursiveCharacterTextSplitter | Text chunking |
| HuggingFace Embeddings | Converts text into vectors |
| FAISS | Vector storage and similarity search |
| CrossEncoder | Reranks retrieved chunks |
| Groq | LLM inference |
| Streamlit | Chat UI |
| python-dotenv | Loads API key from `.env` |
| Sentence Transformers | Embedding/reranking models |

---

# 22. Important Configuration

These are the main settings used in the current project:

```text
Embedding:
sentence-transformers/all-MiniLM-L6-v2

Chunk Size:
700

Chunk Overlap:
100

FAISS Retrieval:
Top 5

Reranking:
Top 3

Reranker:
cross-encoder/ms-marco-MiniLM-L-6-v2

LLM:
openai/gpt-oss-20b

Temperature:
0
```

---

# 23. How to Run the Project

## Install dependencies

```bash
pip install -r requirements.txt
```

## Add API key

Create `.env`:

```text
GROQ_API_KEY=your_api_key
```

## Create the vector database

Run:

```bash
python create_memory_for_llm.py
```

This creates:

```text
vectorstore/db_faiss/
```

You normally do not need to run this again unless the source PDF or relevant configuration changes.

## Start the chatbot

Run:

```bash
streamlit run app.py --server.fileWatcherType none
```

Then open the local Streamlit URL shown in the terminal.

---

# 24. Important Project Decisions

### Why PDF?

The medical encyclopedia provides a fixed knowledge source for the chatbot.

### Why chunking?

The PDF is too large to use as one context. Smaller chunks make retrieval practical.

### Why embeddings?

Embeddings allow semantic similarity search instead of depending only on exact keyword matching.

### Why FAISS?

FAISS provides fast local vector similarity search.

### Why CrossEncoder?

The first retrieval step can return several possible matches. The CrossEncoder helps rank those candidates more precisely.

### Why question rewriting?

It makes follow-up questions clearer for retrieval.

### Why RAG instead of only an LLM?

The chatbot can retrieve information from the project's medical knowledge base before generating the answer.

---

# 25. Current Limitations

The current system uses semantic vector retrieval followed by reranking.

Some questions may retrieve less precise information than others, especially when the wording of the question differs significantly from the source text.

The knowledge base is also limited to the information available in the provided medical PDF.

---

# 26. Future Improvements

Possible future improvements:

- Hybrid retrieval using keyword + vector search.
- Better document/source management.
- More medical documents.
- Better evaluation metrics.
- Improved source citations.
- Deployment to a cloud platform.
- More advanced conversation memory.
- Better retrieval tuning.

These are **future ideas**, not part of the current implementation.

---

# 27. Final Mental Model

If I forget how this project works in the future, remember this:

```text
                    KNOWLEDGE CREATION
                           │
                           ▼
                    Medical PDF
                           │
                           ▼
                    Load PDF Pages
                           │
                           ▼
                       Chunk Text
                           │
                           ▼
                      Embeddings
                           │
                           ▼
                       FAISS DB
                           │
                           │
                           ▼
                  USER ASKS QUESTION
                           │
                           ▼
                  Question Rewriting
                           │
                           ▼
                  FAISS → Top 5
                           │
                           ▼
               CrossEncoder Reranking
                           │
                           ▼
                       Top 3
                           │
                           ▼
                    Groq LLM
                           │
                           ▼
                Grounded Medical Answer
                           │
                           ▼
                  Source Page + Answer
                           │
                           ▼
                     Streamlit UI
```

## One-line summary

**I built a medical RAG chatbot that converts a medical PDF into a FAISS vector database, retrieves and reranks relevant information for each question, and uses a Groq LLM to generate a grounded answer through a Streamlit chat interface.**
