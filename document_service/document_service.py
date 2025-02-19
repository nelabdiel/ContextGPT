import os
import sqlite3
import PyPDF2
import chromadb
from flask import Flask, request, jsonify
from flask_cors import CORS


from sentence_transformers import SentenceTransformer

app = Flask(__name__)
CORS(app)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Initialize ChromaDB for vector storage
chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_or_create_collection(name="documents")

# Initialize SQLite Database
DB_PATH = "documents.db"

def init_db():
    """Create SQLite database and table if it doesn't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                filename TEXT,
                filepath TEXT,
                full_text TEXT
            )
        """)
        conn.commit()

init_db()  # Ensure DB is initialized on startup

# Extract text from PDFs
def extract_text_from_pdfs(pdf_paths):
    documents = []
    for pdf_path in pdf_paths:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            documents.append((os.path.basename(pdf_path), pdf_path, text))
    return documents

# Store metadata and embeddings
def store_in_db_and_chroma(documents):
    embeddings = []
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for title, filepath, text in documents:
            # Store in SQL
            cursor.execute("INSERT INTO documents (title, filename, filepath, full_text) VALUES (?, ?, ?, ?)",
                           (title, title, filepath, text))
            doc_id = cursor.lastrowid

            # Store in ChromaDB
            text_chunks = text.split("\n")  # Simple splitting (replace with smarter chunking if needed)
            chunk_embeddings = embedding_model.encode(text_chunks).tolist()
            for i, chunk in enumerate(text_chunks):
                collection.add(
                    ids=[f"{doc_id}_chunk_{i}"],
                    embeddings=[chunk_embeddings[i]],
                    metadatas=[{"text": chunk}]
                )
            embeddings.extend(chunk_embeddings)
        conn.commit()

@app.route('/upload', methods=['POST'])
def upload_files():
    files = request.files.getlist("files")
    pdf_paths = []
    for file in files:
        filepath = os.path.join("uploads", file.filename)
        file.save(filepath)
        pdf_paths.append(filepath)
    
    documents = extract_text_from_pdfs(pdf_paths)
    store_in_db_and_chroma(documents)
    return jsonify({"message": "Documents added to database and ChromaDB."})

@app.route('/status', methods=['GET'])
def status():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        doc_count = cursor.fetchone()[0]

    # Get number of stored ChromaDB chunks
    chroma_count = collection.count()

    return jsonify({
        "sqlite_documents_stored": doc_count,
        "chroma_db_chunks_stored": chroma_count
    })


if __name__ == "__main__":
    if not os.path.exists("uploads"):
        os.makedirs("uploads")
    app.run(port=5001, debug=True)

