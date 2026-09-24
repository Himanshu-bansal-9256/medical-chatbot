import os
import sys
import json
import logging
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("medicare.api")

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Validate Environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY is not set in environment! RAG calls will fail without it.")

from rag_pipeline import ask_question, ask_question_stream, generate_title
from database import (
    create_user, get_user_by_email, get_user_by_id, get_user_with_password,
    update_user_password, create_chat_session, get_user_sessions, get_session,
    update_session, delete_session, create_or_get_share_token, get_shared_session_by_token
)
from auth import (
    hash_password, check_password, create_token, auth_required
)

app = Flask(__name__)

# Configure CORS with specific origins
CORS(
    app,
    resources={r"/api/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]}},
    supports_credentials=True
)

# Configure Rate Limiter (in-memory)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300 per day", "100 per hour"],
    storage_uri="memory://"
)


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "success": False,
        "error": "Rate limit exceeded. Please slow down and try again shortly.",
        "detail": str(e.description)
    }), 429


# Health Check
@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "message": "MediCare AI Backend is running",
        "models": {
            "rag": "ready",
            "llm": "groq/gpt-oss-20b"
        }
    })


# Authentication
@app.route("/api/auth/signup", methods=["POST"])
@limiter.limit("10 per minute")
def signup():
    """Register a new user."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    # Validation
    if not name or len(name) < 2:
        return jsonify({"error": "Name must be at least 2 characters"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "Valid email is required"}), 400
    if not password or len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Check if email already exists
    existing = get_user_by_email(email)
    if existing:
        return jsonify({"error": "Email already registered"}), 409

    # Create user
    pw_hash = hash_password(password)
    user = create_user(name, email, pw_hash)

    if not user:
        return jsonify({"error": "Could not create account"}), 500

    token = create_token(user["id"])
    logger.info(f"New user registered: {email}")

    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"]
        }
    }), 201


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    """Login with email and password."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = get_user_by_email(email)
    if not user or not check_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_token(user["id"])
    logger.info(f"User logged in: {email}")

    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"]
        }
    })


@app.route("/api/auth/me", methods=["GET"])
@auth_required
def get_me(user_id):
    """Get current user info."""
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"]
        }
    })


@app.route("/api/auth/change-password", methods=["POST"])
@auth_required
@limiter.limit("5 per minute")
def change_password(user_id):
    """Change current user's password."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password or not new_password:
        return jsonify({"error": "Old and new passwords are required"}), 400

    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400

    user = get_user_with_password(user_id)
    if not user or not check_password(old_password, user["password_hash"]):
        return jsonify({"error": "Incorrect current password"}), 400

    new_hash = hash_password(new_password)
    update_user_password(user_id, new_hash)
    logger.info(f"Password updated for user ID: {user_id}")

    return jsonify({"message": "Password updated successfully"})

# Chat History
@app.route("/api/history", methods=["GET"])
@auth_required
def list_sessions(user_id):
    """List all chat sessions for the current user."""
    sessions = get_user_sessions(user_id)
    return jsonify({"sessions": sessions})


@app.route("/api/history", methods=["POST"])
@auth_required
def save_session(user_id):
    """Create or update a chat session."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    session_id = data.get("session_id")
    title = data.get("title", "New Chat")
    messages = data.get("messages", [])

    if session_id:
        existing = get_session(session_id, user_id)
        if not existing:
            return jsonify({"error": "Session not found"}), 404
        update_session(session_id, user_id, title=title, messages=messages)
        updated = get_session(session_id, user_id)
        return jsonify({"session": updated})
    else:
        session = create_chat_session(user_id, title)
        update_session(session["id"], user_id, messages=messages)
        updated = get_session(session["id"], user_id)
        return jsonify({"session": updated}), 201


@app.route("/api/history/<int:session_id>", methods=["GET"])
@auth_required
def get_session_detail(session_id, user_id):
    """Get a specific chat session."""
    session = get_session(session_id, user_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"session": session})


@app.route("/api/history/<int:session_id>", methods=["DELETE"])
@auth_required
def delete_session_route(session_id, user_id):
    """Delete a chat session."""
    existing = get_session(session_id, user_id)
    if not existing:
        return jsonify({"error": "Session not found"}), 404
    delete_session(session_id, user_id)
    return jsonify({"message": "Session deleted"})


@app.route("/api/history/auto-title", methods=["POST"])
@auth_required
def auto_title_route(user_id):
    """Generate a clean title for a chat session from first exchange."""
    data = request.get_json()
    if not data or "question" not in data or "answer" not in data:
        return jsonify({"error": "question and answer required"}), 400

    title = generate_title(data["question"], data["answer"])
    return jsonify({"title": title})


@app.route("/api/history/<int:session_id>/share", methods=["POST"])
@auth_required
def share_session_route(session_id, user_id):
    """Generate or retrieve a unique public share token for a chat session."""
    share_token = create_or_get_share_token(session_id, user_id)
    if not share_token:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "success": True,
        "share_token": share_token
    })


@app.route("/api/share/<share_token>", methods=["GET"])
@limiter.limit("60 per minute")
def get_shared_session_route(share_token):
    """Public read-only endpoint to view a shared medical consultation."""
    session = get_shared_session_by_token(share_token)
    if not session:
        return jsonify({"error": "Shared conversation not found or expired"}), 404

    return jsonify({
        "success": True,
        "session": session
    })

# Chat (Standard & Streaming)
@app.route("/api/chat", methods=["POST"])
@auth_required
@limiter.limit("20 per minute")
def chat(user_id):
    """
    Standard synchronous chat endpoint.
    Expects JSON: { "question": "...", "chat_history": [...] }
    """
    try:
        data = request.get_json()

        if not data or "question" not in data:
            return jsonify({
                "error": "Missing 'question' in request body"
            }), 400

        question = data["question"]
        chat_history = data.get("chat_history", [])

        # Call RAG pipeline
        response = ask_question(question, chat_history)

        sources = []
        for doc in response["source_documents"]:
            sources.append({
                "page": doc.metadata.get(
                    "page_label",
                    doc.metadata.get("page", "Unknown")
                ),
                "source": doc.metadata.get("source", "Unknown")
            })

        return jsonify({
            "answer": response["answer"],
            "rewritten_question": response["rewritten_question"],
            "sources": sources
        })

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
@auth_required
@limiter.limit("20 per minute")
def chat_stream(user_id):
    """
    Real-time streaming SSE chat endpoint.
    Streams tokens as they are generated by LLM.
    """
    try:
        data = request.get_json()
        if not data or "question" not in data:
            return jsonify({"error": "Missing 'question' in request body"}), 400

        question = data["question"]
        chat_history = data.get("chat_history", [])

        def event_stream():
            try:
                for chunk in ask_question_stream(question, chat_history):
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as e:
                logger.error(f"Stream generation error: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        return Response(
            stream_with_context(event_stream()),
            mimetype="text/event-stream",
            headers={
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive"
            }
        )
    except Exception as e:
        logger.error(f"Stream setup error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("  MediCare AI Backend Server")
    print("  Running on http://localhost:5000")
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
