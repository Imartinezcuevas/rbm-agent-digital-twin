import os
from operator import itemgetter
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

DB_PATH = "data/vector_db_local"
EMBEDDING_MODEL = "nomic-embed-text"
CHAT_MODEL = "llama3.1"

class Assistant:
    """
    RAG-based agent that answers technical questions using the RBM-500 manual.
    """

    def __init__(self):
        # Initialize embedding function
        self.embedding_fn = OllamaEmbeddings(model=EMBEDDING_MODEL)

        # Load Vector DB
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError(f"Vector DB not found at {DB_PATH}. Run ingestion first.")
        
        self.vector_db = Chroma(
            persist_directory=DB_PATH,
            embedding_function=self.embedding_fn
        )

        # Retriever
        self.retriever = self.vector_db.as_retriever(search_kwargs={"k": 3})

        # Setup LLM
        self.llm = ChatOllama(model=CHAT_MODEL, temperature=0.2)

        self.prompt = ChatPromptTemplate.from_template(
            """
            You are an expert industrial maintenance engineer.
            You are assisting an operator with the LFA RBM-500 ribbon blender.
            You are capable of handling critical industrial situations.

            Your goal is to provide IMMEDIATE, ACTIONABLE solutions based on the Manual and Live Data.

            -- LIVE MACHINE STATUS --
            {live_data}
            -------------------------

            -- INSTRUCTIONS --
            1. Analyze the Live Telemetry against the Manual Context.
            2. If there is a CRITICAL FAULT (e.g., Temp > 95C, Vib > 6mm/s):
               - FIRST: State the specific diagnosis clearly (e.g., "Thermal Trip Active").
               - SECOND: Provide the EXACT steps to fix it from the manual immediately.
               - DO NOT refuse to answer. DO NOT ask for safety confirmation. Give the solution.
            
            3. Use the context below to find the specific reset procedures or troubleshooting steps.

            <context>
            {context}
            </context>

            User question: {question}

            Your answer:
            """
        )

        # Pipeline
        self.chain = (
            {
                "context": itemgetter("question") | self.retriever, 
                "question": itemgetter("question"),
                "live_data": itemgetter("live_data")
            }
            | self.prompt
            | self.llm
            | StrOutputParser()
        )

    def ask(self, query: str, telemetry_str: str = "No telemetry available") -> str:
        """
        Processes a natural language query and returns the technical answer.
        """
        response = self.chain.invoke({
            "question": query,
            "live_data": telemetry_str
        })
        return response
    
if __name__ == "__main__":
    try:
        agent = Assistant()

        q1 = "What should I do if the vibration is 7 mm/s?"
        print(f"\n Q: {q1}")
        print(f" A: {agent.ask(q1)}")

        q2 = "How do I reset the thermal relay?"
        print(f"\n Q: {q2}")
        print(f" A: {agent.ask(q2)}")

        q3 = "What should I do right now?"
        telemetry_mock = "STATUS: CRITICAL | Temp: 98°C | Vibration: 1.2 mm/s | Lid: Closed"
        print(f"\n Q: {q3}")
        print(f" A: {agent.ask(q3, telemetry_mock)}")

    except Exception as e:
        print(f"Critical error: {e}")