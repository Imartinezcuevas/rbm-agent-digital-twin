import os
import shutil
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

PDF_PATH = "data/raw/RBM_Ribbon_Blender_Range_Manual_v1.11.pdf"
# Where the database will be stored on disk
DB_PATH = "data/vector_db_local"
# The Local Model for Embeddings
EMBEDDING_MODEL = "nomic-embed-text"

def ingest_pdf():
    print("Starting ingestion pipeline...")

    if not os.path.exists(PDF_PATH):
        print(f"ERROR: PDF not found at {PDF_PATH}")
        return
    
    print(f"Loading PDF: {PDF_PATH}")
    loader = PyPDFLoader(PDF_PATH)
    pages = loader.load()
    print(f"    - Loaded {len(pages)} pages.")

    print(f"Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True
    )
    chunks = text_splitter.split_documents(pages)
    print(f"    - Created {len(chunks)} chunks.")

    if os.path.exists(DB_PATH):
        print(f"Clearing old database at {DB_PATH}...")
        shutil.rmtree(DB_PATH)
    
    print(f"Generating embeddings with Ollama ({EMBEDDING_MODEL})...")
    embedding_fn = OllamaEmbeddings(model=EMBEDDING_MODEL)

    vector_db = Chroma.from_documents(
        documents=chunks, 
        embedding=embedding_fn,
        persist_directory=DB_PATH
    )

    print(f"SUCCESS: Knowledge base saved to {DB_PATH}")
    print(f"    - Total chunks: {len(chunks)}")
    print(f"    - Embedding model: {EMBEDDING_MODEL}")

if __name__ == "__main__":
    ingest_pdf()