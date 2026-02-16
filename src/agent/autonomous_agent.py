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
    """
    
    def __init__(self):
        print("Initializing Autonomous Manager...")
        
        # Embedding function for retrieval
        self.embedding_fn = OllamaEmbeddings(model=EMBEDDING_MODEL)
        
        # Load Vector DB
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError(f"Vector DB not found at {DB_PATH}. Run ingestion first.")
            
        self.vector_db = Chroma(
            persist_directory=DB_PATH, 
            embedding_function=self.embedding_fn
        )
        self.retriever = self.vector_db.as_retriever(search_kwargs={"k": 2})
        
        # LLM for complex decisions (only invoked on anomalies)
        self.llm = ChatOllama(model=CHAT_MODEL, temperature=0.0)

        # Decision-making prompt
        self.prompt = ChatPromptTemplate.from_template(
            """
            You are the AUTONOMOUS SAFETY CONTROLLER for the RBM-500 industrial mixer.
            Your job is to monitor live telemetry and decide on actions based on critical safety rules.
            
            -- LIVE TELEMETRY --
            {telemetry}
            --------------------
            
            -- SAFETY MANUAL CONTEXT --
            {context}
            ---------------------------
            
            RULES:
            - EMERGENCY_STOP: ONLY if machine is RUNNING and (vibration > 7 mm/s OR temp > 100°C OR lid open)
            - RESET_RELAY: If thermal trip is active AND temp < 70°C
            - LOG_TICKET: If vibration trending upward (but machine already stopped)
            - MONITOR: If system is nominal or warnings are manageable or machine is already stopped
            
            IMPORTANT: Do NOT issue EMERGENCY_STOP if the machine is already STOPPED (status: "STOPPED").
            
            Respond ONLY with valid JSON (no markdown, no explanation):
            {{
                "action": "EMERGENCY_STOP" | "RESET_RELAY" | "LOG_TICKET" | "MONITOR",
                "reason": "Brief technical explanation (one sentence)"
            }}
            """
        )
        
        # Create chain
        self.chain = self.prompt | self.llm | StrOutputParser()
        
        print("Autonomous Manager initialized successfully")

    def evaluate_system(self, telemetry_dict: dict) -> dict:
        """
        Runs the Hybrid Control Loop:
        1. Fast heuristics check (no LLM)
        2. If anomaly detected -> invoke LLM for decision
        3. Return action to execute
        
        Args:
            telemetry_dict: Current system telemetry
            
        Returns:
            dict with "action" and "reason" keys
        """
        
        # Extract critical parameters
        is_running = telemetry_dict['status'] == "RUNNING"
        temp = telemetry_dict['motor_temp_c']
        vib = telemetry_dict['vibration_mm_s']
        trip = telemetry_dict['thermal_trip']
        lid = telemetry_dict['lid_open']

        # FAST LOOP: Heuristic checks (no AI needed)
        
        # If machine is already stopped, don't keep issuing emergency stops
        if not is_running and not trip:
            # Machine is stopped and no thermal trip - just monitor
            if vib > 7.0:  # Only log ticket if vibration is VERY high
                return {
                    "action": "LOG_TICKET", 
                    "reason": f"Machine stopped but vibration critically high ({vib:.1f} mm/s) - maintenance needed (Fast Loop)",
                    "llm_used": False
                }
            return {
                "action": "MONITOR", 
                "reason": "Machine stopped - monitoring only (Fast Loop)",
                "llm_used": False
            }
        
        # Check for thermal trip reset opportunity
        if trip and temp < 70.0:
            return {
                "action": "RESET_RELAY",
                "reason": f"Thermal trip active but temperature cooled to {temp:.1f}°C - safe to reset (Fast Loop)",
                "llm_used": False
            }
        
        # Check for CRITICAL conditions on running machine (Fast Loop handles these)
        critical_vib = vib > 7.0  # Raised threshold - only emergency stop on CRITICAL vibration
        critical_temp = temp > 95.0  # Only emergency stop at very high temp
        critical_lid = lid and is_running  # Lid open while running is critical
        
        # Fast emergency stop for critical conditions
        if critical_vib:
            return {
                "action": "EMERGENCY_STOP",
                "reason": f"CRITICAL vibration {vib:.1f} mm/s - immediate shutdown required (Fast Loop)",
                "llm_used": False
            }
        
        if critical_temp:
            return {
                "action": "EMERGENCY_STOP",
                "reason": f"CRITICAL temperature {temp:.1f}°C - immediate shutdown required (Fast Loop)",
                "llm_used": False
            }
        
        if critical_lid:
            return {
                "action": "EMERGENCY_STOP",
                "reason": "CRITICAL safety violation - lid open while running (Fast Loop)",
                "llm_used": False
            }
        
        # Check for warning conditions (not critical, might need LLM evaluation)
        vib_warning = vib > 5.0 
        temp_warning = temp > 75.0

        if not (vib_warning or temp_warning):
            return {
                "action": "MONITOR", 
                "reason": "System nominal - all parameters within safe limits (Fast Loop)",
                "llm_used": False
            }

        # SLOW LOOP: Anomaly detected -> AI 
        
        print(f"Anomaly detected! Invoking LLM for decision...")
        
        # Prepare telemetry string
        telemetry_str = json.dumps(telemetry_dict, indent=2)
        
        # Query relevant manual sections
        query = f"safety limits vibration {vib:.1f} mm/s temperature {temp:.1f}°C"
        docs = self.retriever.invoke(query)
        context_text = "\n---\n".join([d.page_content[:500] for d in docs])  # Limit context size

        try:
            # Invoke LLM
            response = self.chain.invoke({
                "telemetry": telemetry_str,
                "context": context_text
            })
            
            # Clean response (remove markdown if present)
            clean_json = response.replace("```json", "").replace("```", "").strip()
            
            # Parse JSON
            decision = json.loads(clean_json)
            decision['llm_used'] = True
            
            print(f"✓ LLM Decision: {decision['action']} - {decision['reason']}")
            return decision
            
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")
            print(f"Raw LLM Response: {response}")
            return {
                "action": "MONITOR", 
                "reason": f"LLM returned invalid JSON - monitoring only",
                "llm_used": True,
                "error": str(e)
            }
        except Exception as e:
            print(f"Agent Error: {e}")
            return {
                "action": "MONITOR", 
                "reason": f"Agent malfunction - defaulting to monitoring ({str(e)})",
                "llm_used": True,
                "error": str(e)
            }
           
if __name__ == "__main__":
    try:
        manager = AutonomousManager()
        
        # Test case 1: Normal operation
        telemetry_normal = {
            "status": "RUNNING",
            "motor_temp_c": 75.0,
            "vibration_mm_s": 4.5,
            "thermal_trip": False,
            "lid_open": False
        }
        
        print("\n--- Test 1: Normal Operation ---")
        result = manager.evaluate_system(telemetry_normal)
        print(f"Decision: {result}")
        
        # Test case 2: High vibration
        telemetry_anomaly = {
            "status": "RUNNING",
            "motor_temp_c": 92.0,
            "vibration_mm_s": 7.5,
            "thermal_trip": False,
            "lid_open": False
        }
        
        print("\n--- Test 2: High Vibration & Temp ---")
        result = manager.evaluate_system(telemetry_anomaly)
        print(f"Decision: {result}")
        
    except Exception as e:
        print(f"Critical error: {e}")