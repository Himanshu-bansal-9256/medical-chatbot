import streamlit as st
from rag_pipeline import ask_question

# Page Configuration
st.set_page_config(
    page_title="MediCare AI",
    layout="wide"
)
# Custom CSS
st.markdown(
    """
    <style>
    .stApp { background:#f7f9fc; color:#1f2937; }
    .main .block-container { max-width:1120px; padding-top:2rem; padding-bottom:2rem; }
    .main-title { text-align:center; font-size:34px; font-weight:700; color:#12355b !important; margin-bottom:5px; }
    .subtitle { text-align:center; color:#718096 !important; font-size:14px; margin-bottom:10px; }
    .status-wrap { text-align:center; margin-bottom:22px; }
    .status { display:inline-block; padding:5px 12px; border-radius:20px; background:#eef7f2; border:1px solid #d6eadf; color:#35745a !important; font-size:12px; font-weight:600; }
    [data-testid="stChatMessage"] { border:1px solid #e5eaf0; border-radius:12px; padding:8px 14px; margin-bottom:10px; background:#fff; box-shadow:0 2px 8px rgba(15,40,70,.03); }
    [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] span, [data-testid="stChatMessage"] div { color:#26374a !important; line-height:1.65; }
    .source-title { color:#17608e !important; font-size:13px; font-weight:700; margin-top:14px; margin-bottom:8px; border-top:1px solid #edf0f3; padding-top:12px; }
    .source-box { background:#f7fafc; color:#374151 !important; padding:10px 12px; border-radius:8px; margin-top:7px; font-size:12px; border:1px solid #e5ebf0; }
    .source-box b { color:#334e68 !important; }
    .disclaimer { background:#f1f6fa; padding:12px 15px; border-radius:9px; font-size:12px; color:#60758a !important; margin-top:20px; border:1px solid #dce8f0; }
    .disclaimer b { color:#334e68 !important; }
    section[data-testid="stSidebar"] { background:#fff; border-right:1px solid #e5eaf0; }
    section[data-testid="stSidebar"] > div { padding:1.5rem 1.2rem; }
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] div, section[data-testid="stSidebar"] label { color:#334155 !important; }
    .brand-title { font-size:24px; font-weight:700; color:#12355b !important; margin-bottom:3px; }
    .brand-subtitle { font-size:12px; color:#718096 !important; }
    .sidebar-heading { font-size:11px; font-weight:700; color:#718096 !important; text-transform:uppercase; letter-spacing:.7px; margin-top:20px; margin-bottom:8px; }
    .example-item { padding:9px 11px; border-radius:8px; margin-bottom:6px; background:#f8fafc; border:1px solid #e7edf3; color:#475569 !important; font-size:12px; }
    .about-box { margin-top:18px; padding:13px; border-radius:9px; background:#f7fafc; border:1px solid #e5ebf0; font-size:12px; line-height:1.55; color:#718096 !important; }
    section[data-testid="stSidebar"] .stButton > button { width:100%; height:40px; border-radius:8px; border:none; background:#164e78; color:#fff !important; font-weight:600; }
    section[data-testid="stSidebar"] .stButton > button:hover { background:#123f61; color:#fff !important; }
    [data-testid="stChatInput"] textarea { color:#1f2937 !important; background:#fff !important; border:1px solid #dce4eb; }
    [data-testid="stChatInput"] textarea::placeholder { color:#718096 !important; }
    .welcome-box { background:#fff; border:1px solid #e5eaf0; border-radius:14px; padding:42px 25px; text-align:center; margin-top:10px; margin-bottom:15px; box-shadow:0 2px 8px rgba(15,40,70,.03); }
    .welcome-title { font-size:21px; font-weight:600; color:#12355b !important; margin-bottom:8px; }
    .welcome-text { font-size:13px; color:#718096 !important; }
    </style>
    """,
    unsafe_allow_html=True
)

# Header
st.markdown(
    '<div class="main-title">MediCare AI</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Medical information assistant powered by Retrieval-Augmented Generation'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="status-wrap"><span class="status">AI Assistant Online</span></div>',
    unsafe_allow_html=True
)

# Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar
with st.sidebar:

    st.markdown(
        """
        <div style="margin-bottom:22px;">
            <div class="brand-title">MediCare AI</div>
            <div class="brand-subtitle">Medical Information Assistant</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown(
        '<div class="sidebar-heading">Example Questions</div>',
        unsafe_allow_html=True
    )

    examples = [
        "What is diabetes?",
        "What are the symptoms of diabetes?",
        "What causes hypertension?",
        "What are the symptoms of anemia?",
        "What is asthma?",
        "What is pneumonia?"
    ]

    for example in examples:
        st.markdown(
            f'<div class="example-item">{example}</div>',
            unsafe_allow_html=True
        )

    st.markdown(
        """
        <div class="about-box">
            <b>About</b><br><br>
            MediCare AI uses Retrieval-Augmented Generation
            to retrieve relevant information from a medical
            knowledge base and generate concise answers.
        </div>
        """,
        unsafe_allow_html=True
    )

# Display Previous Messages
for message in st.session_state.messages:

    with st.chat_message(message["role"]):

        st.markdown(message["content"])

        # Display sources if available
        if (
            message["role"] == "assistant"
            and "sources" in message
        ):

            st.markdown(
                '<div class="source-title">Sources</div>',
                unsafe_allow_html=True
            )

            for source in message["sources"]:

                st.markdown(
                    f"""
                    <div class="source-box">
                        <b>Page:</b> {source["page"]}<br>
                        <b>Source:</b> {source["source"]}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# Welcome Message
if len(st.session_state.messages) == 0:

    st.markdown(
        """
        <div class="welcome-box">
            <div class="welcome-title">How can I help you?</div>
            <div class="welcome-text">
                Ask a question about diseases, symptoms,
                causes, or other medical information
                available in the knowledge base.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# Chat Input
user_question = st.chat_input(
    "Ask a medical question..."
)

# Process User Question
if user_question:

    # Show User Message
    st.chat_message("user").markdown(
        user_question
    )
    # Add User Message to History
    st.session_state.messages.append({
        "role": "user",
        "content": user_question
    })
    # Prepare Chat History for RAG
    chat_history = []

    for message in st.session_state.messages[:-1]:

        chat_history.append({
            "role": message["role"],
            "content": message["content"]
        })

    # Generate Answer
    with st.chat_message("assistant"):

        with st.spinner(
            "Searching medical knowledge..."
        ):

            try:

                response = ask_question(
                    user_question,
                    chat_history
                )

                answer = response["answer"]

                sources = []

                for doc in response["source_documents"]:

                    sources.append({
                        "page": doc.metadata.get(
                            "page_label",
                            doc.metadata.get(
                                "page",
                                "Unknown"
                            )
                        ),
                        "source": doc.metadata.get(
                            "source",
                            "Unknown"
                        )
                    })
                # Display Answer
                st.markdown(answer)
                # Display Sources
                st.markdown(
                    '<div class="source-title">Sources</div>',
                    unsafe_allow_html=True
                )

                for source in sources:

                    st.markdown(
                        f"""
                        <div class="source-box">
                            <b>Page:</b> {source["page"]}<br>
                            <b>Source:</b> {source["source"]}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                # Save Assistant Response
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources
                })

            except Exception as e:

                st.error(
                    f"Something went wrong: {str(e)}"
                )
# Disclaimer
st.markdown(
    """
    <div class="disclaimer">
        <b>Medical Disclaimer:</b>
        This chatbot provides educational information
        from its knowledge base and is not a substitute
        for professional medical advice.
    </div>
    """,
    unsafe_allow_html=True
)