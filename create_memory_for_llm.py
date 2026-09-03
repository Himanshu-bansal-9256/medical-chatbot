from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# Step 1 -- Load raw data

data_path = "data/"

def load_pdf_data(data):
    loader = DirectoryLoader(
        data,
        glob="*.pdf",
        loader_cls=PyPDFLoader
    )
    
    documents = loader.load()
    return documents

documents = load_pdf_data(data_path)

print("length of pdf pages", len(documents))

# step 2 -- create chunks
def create_chunks(extracted_data):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=100,
    )
    
    text_chunk = text_splitter.split_documents(extracted_data)
    return text_chunk

text_chunk = create_chunks(documents)
print("length of text chunks", len(text_chunk))


# step 3 -- create vector database
def get_embeddings_model(text_chunk):
    embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return embedding_model
embedding_model = get_embeddings_model(text_chunk)

# step 4 -- store embeddings in FAISS
DB_FAISS_PATH = "vectorstore/db_faiss"
db = FAISS.from_documents(text_chunk, embedding_model)
db.save_local(DB_FAISS_PATH)
print("FAISS vector database created successfully!")