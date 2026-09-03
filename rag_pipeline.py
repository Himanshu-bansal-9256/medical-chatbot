import os

from dotenv import load_dotenv
import time

from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sentence_transformers import CrossEncoder
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# Load Environment Variables
load_dotenv()

# Configuration
DB_FAISS_PATH = "vectorstore/db_faiss"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set!")

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    groq_api_key=GROQ_API_KEY,
    temperature=0
)

# Load Embedding Model
embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

reranker = CrossEncoder(
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

# Load FAISS Vector Database

db = FAISS.load_local(
    DB_FAISS_PATH,
    embedding_model,
    allow_dangerous_deserialization=True
)

# Create Retriever

retriever = db.as_retriever(
    search_kwargs={"k": 5}
)

# Conversation History

def add_message(chat_history, role, content):

    chat_history.append({
        "role": role,
        "content": content
    })


def format_chat_history(chat_history):

    formatted_history = ""

    for message in chat_history:

        formatted_history += (
            f"{message['role'].capitalize()}: "
            f"{message['content']}\n"
        )

    return formatted_history

# Question Rewriter Prompt

rewriter_prompt = PromptTemplate(
    input_variables=[
        "chat_history",
        "question"
    ],

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

# Question Rewriter Chain
rewriter_chain = (
    rewriter_prompt
    | llm
    | StrOutputParser()
)

# Final Answer Prompt
answer_prompt = PromptTemplate(
    input_variables=[
        "chat_history",
        "context",
        "question"
    ],
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

# Final Answer Chain
answer_chain = (
    answer_prompt
    | llm
    | StrOutputParser()
)

# Format Retrieved Documents

def format_docs(docs):

    return "\n\n".join(
        doc.page_content
        for doc in docs
    )

def rerank_documents(question, documents):

    pairs = [
        [question, doc.page_content]
        for doc in documents
    ]

    scores = reranker.predict(pairs)

    ranked_documents = sorted(
        zip(scores, documents),
        key=lambda x: x[0],
        reverse=True
    )

    return [
        doc
        for score, doc in ranked_documents[:3]
    ]

# MAIN RAG FUNCTION
def ask_question(question, chat_history):

    total_start = time.time()

    # ==========================================
    # Step 1: Format history
    # ==========================================

    formatted_history = format_chat_history(chat_history)


    # ==========================================
    # Step 2: Rewrite only when history exists
    # ==========================================

    rewrite_start = time.time()

    if chat_history:

        rewritten_question = rewriter_chain.invoke({
            "chat_history": formatted_history,
            "question": question
        })

    else:

        rewritten_question = question

    rewrite_time = time.time() - rewrite_start

    # Step 3: FAISS Retrieval

    retrieval_start = time.time()

    retrieved_docs = retriever.invoke(
        rewritten_question
    )

    reranked_docs = rerank_documents(
        rewritten_question,
        retrieved_docs
    )

    context = format_docs(
        reranked_docs
    )

    retrieval_time = time.time() - retrieval_start


    print("\n==============================")
    print("RERANKED DOCUMENTS")
    print("==============================")

    for i, doc in enumerate(reranked_docs):

        print(f"\n--- Document {i + 1} ---")

        print(
            "Source:",
            doc.metadata.get("source", "Unknown")
        )

        print(
            "Page:",
            doc.metadata.get(
                "page_label",
                doc.metadata.get("page", "Unknown")
            )
        )

        print("\nContent:")
        print(doc.page_content[:500])
    # ==========================================
    # Step 5: Gemini Answer
    # ==========================================
    answer_start = time.time()

    final_answer = answer_chain.invoke({
        "chat_history": formatted_history,
        "context": context,
        "question": question
    })

    answer_time = time.time() - answer_start
    # ==========================================
    # Total time
    # ==========================================

    total_time = time.time() - total_start

    print("\n==============================")
    print("PERFORMANCE")
    print("==============================")
    print(f"Question Rewrite : {rewrite_time:.2f} sec")
    print(f"FAISS Retrieval  : {retrieval_time:.2f} sec")
    print(f"LLM Answer       : {answer_time:.2f} sec")
    print(f"Total Time       : {total_time:.2f} sec")
    print("==============================\n")


    return {
        "answer": final_answer,
        "rewritten_question": rewritten_question,
        "source_documents": reranked_docs
    }
# TEST
if __name__ == "__main__":

    test_questions = [
        "What is diabetes?",
        "What are the symptoms of diabetes?",
        "What causes diabetes?",
        "What is hypertension?",
        "What are the symptoms of hypertension?",
        "What is anemia?",
        "What are the symptoms of anemia?",
        "What is asthma?",
        "What are the symptoms of asthma?",
        "What is pneumonia?"
    ]

    for question in test_questions:

        print("\n\n")
        print("=" * 60)
        print("QUESTION")
        print("=" * 60)
        print(question)

        response = ask_question(
            question,
            []
        )

        print("\n" + "=" * 60)
        print("ANSWER")
        print("=" * 60)
        print(response["answer"])

        print("\n" + "=" * 60)
        print("SOURCES")
        print("=" * 60)

        for i, doc in enumerate(
            response["source_documents"]
        ):

            print(
                f"Source {i + 1}: "
                f"Page {doc.metadata.get('page_label', 'Unknown')}"
            )