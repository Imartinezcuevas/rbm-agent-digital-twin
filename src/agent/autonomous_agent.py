import os
import json
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Config
DB_PATH = "data/vector_db_local"
EMBEDDING_MODEL = "nomic-embed-text"
CHAT_MODEL = "llama3.1" 

class AutonomousManager:
    """
    Hybrid Agent: Uses heuristics for monitoring (Fast Loop) 
    and LLM for decision making (Slow Loop).
    Saves tokens/compute by only invoking LLM on anomalies.
    """
    
    def __init__(self):
        # Inicialización costosa (solo una vez)
        self.embedding_fn = OllamaEmbeddings(model=EMBEDDING_MODEL)
        
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError("Vector DB not found.")
            
        self.vector_db = Chroma(persist_directory=DB_PATH, embedding_function=self.embedding_fn)
        self.retriever = self.vector_db.as_retriever(search_kwargs={"k": 2})
        
        # LLM para decisiones complejas
        self.llm = ChatOllama(model=CHAT_MODEL, temperature=0.0) 

        self.prompt = ChatPromptTemplate.from_template(
            """
            You are the AUTONOMOUS SAFETY CONTROLLER.
            Your job is to monitor live telemetry and trigger actions ONLY if critical rules are violated.
            
            -- TELEMETRY --
            {telemetry}
            ---------------
            -- MANUAL RULES --
            {context}
            ------------------
            
            Return JSON:
            {{
                "action": "EMERGENCY_STOP" | "RESET_RELAY" | "LOG_TICKET" | "MONITOR",
                "reason": "Brief explanation"
            }}
            """
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    def evaluate_system(self, telemetry_dict: dict) -> dict:
        """
        Runs the Hybrid Control Loop.
        """
        
        is_running = telemetry_dict['status'] == "RUNNING"
        temp = telemetry_dict['motor_temp_c']
        vib = telemetry_dict['vibration_mm_s']
        trip = telemetry_dict['thermal_trip']
        lid = telemetry_dict['lid_open']

        # 1. Warning zone
        vib_warning = vib > 5.0 
        temp_warning = temp > 90.0
        is_tripped = trip
        lid_risk = lid and is_running

        if not (vib_warning or temp_warning or is_tripped or lid_risk):
            return {
                "action": "MONITOR", 
                "reason": "Heuristics: System Nominal (Tokens Saved)"
            }

        print(f"Anomaly Detected! Waking up AI Brain...")
        
        telemetry_str = str(telemetry_dict)
        
        query = f"limits for vibration {vib} and temp {temp}"
        docs = self.retriever.invoke(query)
        context_text = "\n".join([d.page_content for d in docs])

        try:
            response = self.chain.invoke({
                "telemetry": telemetry_str,
                "context": context_text
            })
            
            clean_json = response.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
            
        except Exception as e:
            print(f"Agent Error: {e}")
            return {"action": "MONITOR", "reason": "LLM Error"}