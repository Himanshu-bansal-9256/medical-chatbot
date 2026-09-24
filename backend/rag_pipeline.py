import os
import logging
import time

import numpy as np
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sentence_transformers import CrossEncoder
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# Logging
logger = logging.getLogger("medicare.rag")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)

# Environment
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FAISS_PATH = os.path.join(BASE_DIR, "vectorstore", "db_faiss")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set!")

# Models
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    groq_api_key=GROQ_API_KEY,
    temperature=0
)

llm_streaming = ChatGroq(
    model="openai/gpt-oss-20b",
    groq_api_key=GROQ_API_KEY,
    temperature=0,
    streaming=True
)

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

reranker = CrossEncoder(
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

logger.info("Models loaded successfully")

# FAISS Vector Database
db = FAISS.load_local(
    DB_FAISS_PATH,
    embedding_model,
    allow_dangerous_deserialization=True
)

retriever = db.as_retriever(
    search_kwargs={"k": 5}
)

logger.info("FAISS database loaded")

# BM25 Index for Hybrid Retrieval
all_docs_dict = db.docstore._dict
all_docs = list(all_docs_dict.values())
all_doc_texts = [doc.page_content for doc in all_docs]

# Tokenize for BM25
tokenized_corpus = [doc.lower().split() for doc in all_doc_texts]
bm25 = BM25Okapi(tokenized_corpus)

logger.info(f"BM25 index built with {len(all_docs)} documents")

# Helpers
def format_chat_history(chat_history):
    formatted = ""
    for msg in chat_history:
        formatted += f"{msg['role'].capitalize()}: {msg['content']}\n"
    return formatted


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


# Prompts
rewriter_prompt = PromptTemplate(
    input_variables=["chat_history", "question"],
    template="""
Given the conversation history and the latest user question,
rewrite the latest question into a standalone question.

The rewritten question must:
- Preserve the original meaning.
- Use previous conversation context when necessary.
- Replace unclear references such as "it", "its", "they",
  "that", etc. with the correct entity from the conversation.
- Do not answer the question.
- Return only the rewritten question.

Conversation History:
{chat_history}

Latest Question:
{question}

Standalone Question:
"""
)

answer_prompt = PromptTemplate(
    input_variables=["chat_history", "context", "question"],
    template="""
You are a medical information assistant.

Answer the user's question using the medical information provided below.

Rules:
1. Answer the question directly and clearly.
2. Use the provided medical information as the primary source.
3. Use conversation history only to understand references like
   "it", "its", "they", or "this disease".
4. Do not invent facts that are not supported by the provided information.
5. If the information is not sufficient to answer the question,
   say that the information is not available in the provided
   medical knowledge base.
6. Do not diagnose the user.
7. Do not recommend a specific medicine or treatment for an
   individual patient.
8. If there are multiple symptoms, causes, or other points,
   use bullet points.
9. Keep the answer concise but informative.
10. Do not mention "retrieved context" in the answer.

Conversation History:
{chat_history}

Medical Information:
{context}

User Question:
{question}

Answer:
"""
)

title_prompt = PromptTemplate(
    input_variables=["question", "answer"],
    template="""
Generate a very short title (3-5 words max) for this medical chat conversation.
Do not use quotes. Return only the title text.

User Question: {question}
Assistant Answer: {answer}

Title:
"""
)

# Chains
rewriter_chain = rewriter_prompt | llm | StrOutputParser()
answer_chain = answer_prompt | llm | StrOutputParser()
answer_chain_streaming = answer_prompt | llm_streaming | StrOutputParser()
title_chain = title_prompt | llm | StrOutputParser()


# Hybrid Retrieval (BM25 + FAISS)
def hybrid_retrieve(query, k_faiss=5, k_bm25=5):
    """Combine FAISS vector search with BM25 keyword search."""

    # FAISS retrieval
    faiss_docs = retriever.invoke(query)
    logger.info(f"FAISS retrieved {len(faiss_docs)} docs")

    # BM25 retrieval
    tokenized_query = query.lower().split()
    bm25_scores = bm25.get_scores(tokenized_query)
    top_bm25_indices = np.argsort(bm25_scores)[::-1][:k_bm25]
    bm25_docs = [all_docs[i] for i in top_bm25_indices if bm25_scores[i] > 0]
    logger.info(f"BM25 retrieved {len(bm25_docs)} docs")

    # Merge and deduplicate
    seen_content = set()
    merged = []

    for doc in faiss_docs + bm25_docs:
        content_hash = hash(doc.page_content[:200])
        if content_hash not in seen_content:
            seen_content.add(content_hash)
            merged.append(doc)

    logger.info(f"Merged unique docs: {len(merged)}")
    return merged


def rerank_documents(question, documents):
    if not documents:
        return []

    pairs = [[question, doc.page_content] for doc in documents]
    scores = reranker.predict(pairs)

    ranked = sorted(
        zip(scores, documents),
        key=lambda x: x[0],
        reverse=True
    )

    top_docs = [doc for _, doc in ranked[:3]]
    logger.info(f"Reranked to top {len(top_docs)} docs")
    return top_docs


# MAIN RAG FUNCTION (Non-streaming)
def ask_question(question, chat_history):
    total_start = time.time()

    # Step 1: Format history
    formatted_history = format_chat_history(chat_history)

    # Step 2: Rewrite if history exists
    rewrite_start = time.time()
    if chat_history:
        rewritten_question = rewriter_chain.invoke({
            "chat_history": formatted_history,
            "question": question
        })
        logger.info(f"Rewritten: {rewritten_question}")
    else:
        rewritten_question = question
    rewrite_time = time.time() - rewrite_start

    # Step 3: Hybrid Retrieval
    retrieval_start = time.time()
    retrieved_docs = hybrid_retrieve(rewritten_question)
    reranked_docs = rerank_documents(rewritten_question, retrieved_docs)
    context = format_docs(reranked_docs)
    retrieval_time = time.time() - retrieval_start

    # Step 4: Generate Answer
    answer_start = time.time()
    final_answer = answer_chain.invoke({
        "chat_history": formatted_history,
        "context": context,
        "question": question
    })
    answer_time = time.time() - answer_start

    total_time = time.time() - total_start

    logger.info(
        f"Performance — Rewrite: {rewrite_time:.2f}s | "
        f"Retrieval: {retrieval_time:.2f}s | "
        f"Answer: {answer_time:.2f}s | "
        f"Total: {total_time:.2f}s"
    )

    return {
        "answer": final_answer,
        "rewritten_question": rewritten_question,
        "source_documents": reranked_docs
    }

# STREAMING RAG FUNCTION
def ask_question_stream(question, chat_history):
    """Generator that yields answer chunks for SSE streaming."""

    yield {"type": "status", "content": "Searching medical knowledge base..."}

    # Step 1: Format history
    formatted_history = format_chat_history(chat_history)

    # Step 2: Rewrite if history exists
    if chat_history:
        rewritten_question = rewriter_chain.invoke({
            "chat_history": formatted_history,
            "question": question
        })
        logger.info(f"Rewritten (stream): {rewritten_question}")
    else:
        rewritten_question = question

    yield {"type": "status", "content": "Analyzing medical literature..."}

    # Step 3: Hybrid Retrieval
    retrieved_docs = hybrid_retrieve(rewritten_question)
    reranked_docs = rerank_documents(rewritten_question, retrieved_docs)
    context = format_docs(reranked_docs)

    yield {"type": "status", "content": "Generating clinical answer..."}

    # Step 4: Stream Answer
    for chunk in answer_chain_streaming.stream({
        "chat_history": formatted_history,
        "context": context,
        "question": question
    }):
        if chunk:
            yield {"type": "token", "content": chunk}

    # Step 5: Yield sources at end
    sources = []
    for doc in reranked_docs:
        sources.append({
            "page": doc.metadata.get(
                "page_label",
                doc.metadata.get("page", "Unknown")
            ),
            "source": doc.metadata.get("source", "Unknown")
        })

    yield {"type": "sources", "content": sources}
    yield {"type": "done", "content": rewritten_question}


# AUTO TITLE GENERATION
def generate_title(question, answer):
    """Generate a short 3-5 word title for a conversation."""
    try:
        title = title_chain.invoke({
            "question": question,
            "answer": answer[:300]
        })
        clean = title.strip().strip('"').strip("'")
        return clean[:60] if clean else "Medical Chat"
    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        return "Medical Chat"
