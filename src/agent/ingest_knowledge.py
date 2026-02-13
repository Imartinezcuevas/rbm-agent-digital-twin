import os
import shutil
import glob
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

RAW_DATA_DIR = "data/raw/"
# Where the database will be stored on disk
DB_PATH = "data/vector_db_local"
# The Local Model for Embeddings
EMBEDDING_MODEL = "nomic-embed-text"

def ingest_knowledge_base():
    print("Starting ingestion pipeline...")

    all_documents = []
    files = glob.glob(os.path.join(RAW_DATA_DIR, "*.*"))
    print(f"Found {len(files)} files in {RAW_DATA_DIR}")

    for file_path in files:
        print(f"    - Processing: {os.path.basename(file_path)}...")

        try:
            if file_path.endswith(".pdf"):
                loader = PyPDFLoader(file_path)
            elif file_path.endswith(".md") or file_path.endswith(".txt"):
                loader = TextLoader(file_path, encoding="utf-8")
            else:
                print(f"        Skipping unknown file type")
                continue

            docs = loader.load()
            all_documents.extend(docs)
            print(f"    Loaded {len(docs)} pages/docs.")
        except Exception as e:
            print(f"    Error loading file: {e}")
        
    print(f"Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True
    )
    chunks = text_splitter.split_documents(all_documents)
    print(f"    - Created {len(chunks)} total chunks from all files.")

    if os.path.exists(DB_PATH):
        print(f"Clearing old database...")
        shutil.rmtree(DB_PATH)

    print(f"Generating embeddings with Ollama ({EMBEDDING_MODEL})...")
    embedding_fn = OllamaEmbeddings(model=EMBEDDING_MODEL)

    vector_db = Chroma.from_documents(
        documents=chunks, 
        embedding=embedding_fn,
        persist_directory=DB_PATH
    )

    print(f"SUCCESS: Knowledge Base saved to {DB_PATH}")

if __name__ == "__main__":
    ingest_knowledge_base()