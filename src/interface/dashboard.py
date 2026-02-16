import streamlit as st
import pandas as pd
import time
import sys
import os

# Adjust path to import simulation and agents
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import simulator
from src.simulation.mixer_sim import RBM_500

# Try to import agents - gracefully handle if not available
try:
    from src.agent.rag_agent import Assistant
    ASSISTANT_AVAILABLE = True
except Exception as e:
    ASSISTANT_AVAILABLE = False
    print(f"Assistant not available: {e}")

try:
    from src.agent.autonomous_agent import AutonomousManager
    from src.agent.tools import MachineTools
    AUTONOMOUS_AVAILABLE = True
except Exception as e:
    AUTONOMOUS_AVAILABLE = False
    print(f"Autonomous Manager not available: {e}")

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBM-500 HMI", layout="wide")
st.title("RBM-500 | Twin Interface")

# --- STATE MANAGEMENT (INITIALIZATION) ---
if 'mixer' not in st.session_state:
    st.session_state['mixer'] = RBM_500()
    st.session_state['history'] = []
    st.session_state['chat_messages'] = []
    st.session_state['agent_mode'] = 'Assistant'
    st.session_state['autonomous_actions'] = []
    st.session_state['maintenance_tickets'] = []
    st.session_state['monitoring_logs'] = []
    st.session_state['last_autonomous_decision'] = None
    st.session_state['last_action_time'] = 0.0

if 'assistant' not in st.session_state: st.session_state['assistant'] = None
if 'autonomous_manager' not in st.session_state: st.session_state['autonomous_manager'] = None

if 'toggle_main' not in st.session_state: st.session_state['toggle_main'] = False
if 'toggle_disch' not in st.session_state: st.session_state['toggle_disch'] = False
if 'slider_speed' not in st.session_state: st.session_state['slider_speed'] = 20

mixer = st.session_state['mixer']

# --- HELPER: Format telemetry ---
def format_telemetry(data):
    status = "CRITICAL" if data['thermal_trip'] else ("WARNING" if data['vibration_mm_s'] > 6.0 else "NOMINAL")
    return f"""STATUS: {status}
    - Motor Temperature: {data['motor_temp_c']:.1f}°C (Ambient: {data['ambient_temp_c']:.1f}°C)
    - Vibration: {data['vibration_mm_s']:.2f} mm/s
    - Shaft Speed: {data['rpm_shaft']:.1f} RPM
    - Main Drive Current: {data['main_motor_amps']:.2f} A
    - Discharge Current: {data['discharge_amps']:.2f} A
    - Fill Level: {data['fill_level_kg']:.1f} kg
    - Lid Status: {'OPEN' if data['lid_open'] else 'CLOSED'}
    - Thermal Trip: {'ACTIVE' if data['thermal_trip'] else 'INACTIVE'}
    - Overall Status: {data['status']}"""

# =========================================================================
# 1. COGNITIVE CONTROL LOOP (EJECUCIÓN DEL AGENTE ANTES DE DIBUJAR LA UI)
# =========================================================================
# Leemos el estado del ciclo anterior para tomar decisiones
last_data = st.session_state['history'][-1] if st.session_state['history'] else mixer.get_telemetry()
current_time = time.time()

if st.session_state['agent_mode'] == 'Autonomous' and st.session_state['autonomous_manager'] is not None:
    time_since_last_action = current_time - st.session_state['last_action_time']
    
    # Cooldown de 2 segundos para no hacer spam de decisiones
    if time_since_last_action > 2.0:
        decision = st.session_state['autonomous_manager'].evaluate_system(last_data)
        st.session_state['last_autonomous_decision'] = decision
        
        if decision['action'] != "MONITOR":
            # Ejecutamos la acción en el backend
            result = MachineTools.execute_action(decision['action'], decision['reason'])
            
            st.session_state['chat_messages'].append({
                "role": "system",
                "content": f"**AUTONOMOUS ACTION**\n\n{result}\n\n*Reason: {decision['reason']}*"
            })
            st.session_state['last_action_time'] = current_time
            
            # --- EL ARREGLO ESTRELLA ---
            # Modificamos los widgets AHORA, antes de que el Sidebar los renderice.
            # Esto evita el StreamlitAPIException por completo.
            if decision['action'] == "EMERGENCY_STOP":
                st.session_state['toggle_main'] = False
                st.session_state['toggle_disch'] = False

# =========================================================================
# 2. SIDEBAR & USER INTERFACE
# =========================================================================
with st.sidebar:
    st.header("Operator Control Panel")
    
    st.subheader("AI Agent Mode")
    agent_options = []
    if ASSISTANT_AVAILABLE: agent_options.append("Assistant (Consultive)")
    if AUTONOMOUS_AVAILABLE: agent_options.append("Autonomous Manager")
    
    if len(agent_options) > 0:
        selected_mode = st.radio("Select Agent Type:", agent_options)
        
        if "Assistant" in selected_mode:
            st.session_state['agent_mode'] = 'Assistant'
            if st.session_state['assistant'] is None:
                with st.spinner("Initializing Technical Assistant..."):
                    st.session_state['assistant'] = Assistant()
                    
        elif "Autonomous" in selected_mode:
            st.session_state['agent_mode'] = 'Autonomous'
            if st.session_state['autonomous_manager'] is None:
                with st.spinner("Initializing Autonomous Manager..."):
                    st.session_state['autonomous_manager'] = AutonomousManager()
    
    st.divider()
    
    # Actuadores (Leerán el False que puso el Agente si hubo emergencia)
    st.subheader("Actuators")
    col_s1, col_s2 = st.columns(2)
    
    with col_s1:
        st.toggle("MAIN DRIVE", key="toggle_main", disabled=mixer.thermal_trip)
    with col_s2:
        st.toggle("DISCHARGE", key="toggle_disch", disabled=mixer.thermal_trip)
    
    st.slider("Set Point (RPM)", 0, 24, key="slider_speed", disabled=mixer.thermal_trip)
    
    # Aplicar la intención del usuario (o la del agente sobreescrita) al motor
    control_result = mixer.set_controls(
        st.session_state['toggle_main'], 
        st.session_state['toggle_disch'], 
        st.session_state['slider_speed']
    )
    if control_result != "OK":
        st.caption(f"⚠️ {control_result}")
    
    st.divider()
    
    st.subheader("Environment (External)")
    amb_temp = st.slider("Ambient Temp (°C)", 10, 50, int(mixer.ambient_temp_c))
    mixer.ambient_temp_c = float(amb_temp)
    
    st.divider()
    
    st.subheader("Fault Injection")
    if not st.session_state['toggle_disch']:
        new_load = st.slider("Fill Level (kg)", 0, 140, int(mixer.fill_level_kg))
        mixer.fill_level_kg = float(new_load)
    else:
        st.metric("Fill Level (kg)", f"{mixer.fill_level_kg:.1f}")
    
    mixer._bearing_wear = st.slider("Bearing Wear", 0.0, 1.0, mixer._bearing_wear, 0.1)
    mixer._belt_slip_factor = st.slider("Belt Slip Factor", 0.0, 1.0, mixer._belt_slip_factor, 0.1)
    mixer._clogged_outlet = st.checkbox("Discharge Blockage", value=mixer._clogged_outlet)
    mixer.lid_open = st.checkbox("Open Safety Interlock", value=mixer.lid_open)

# =========================================================================
# 3. PHYSICS UPDATE
# =========================================================================
data = mixer.update_physics()
data['speed_setpoint'] = mixer.target_rpm
total_power = data['main_motor_amps'] + data['discharge_amps']
data['total_amps'] = total_power

st.session_state['history'].append(data)
if len(st.session_state['history']) > 60:
    st.session_state['history'].pop(0)
df = pd.DataFrame(st.session_state['history'])

# =========================================================================
# 4. DASHBOARD RENDER
# =========================================================================
st.divider()
c_alert1, c_alert2 = st.columns([3, 1])

with c_alert1:
    if data['thermal_trip']:
        st.error(f"🚨 CRITICAL ALARM: THERMAL TRIP ACTIVE | Temp: {data['motor_temp_c']:.1f}°C")
    elif data['lid_open']:
        if st.session_state['toggle_main']:
            st.error("⛔ SAFETY LOCK: Cannot start Main Drive while Lid is Open.")
        else:
            st.warning("⚠️ SAFETY WARNING: Lid Open - Close before operation.")
    elif data['vibration_mm_s'] > 6.0:
        st.warning(f"⚠️ VIBRATION ALERT: High Level ({data['vibration_mm_s']:.2f} mm/s)")
    elif mixer._clogged_outlet and st.session_state['toggle_disch']:
        st.warning("⚠️ DISCHARGE WARNING: Blockage detected - High motor current.")
    else:
        st.success("✅ SYSTEM STATUS: NOMINAL - All parameters within limits")

with c_alert2:
    if data['thermal_trip']:
        can_reset = data['motor_temp_c'] < 70.0
        label = "RESET RELAY" if can_reset else f"COOLING ({data['motor_temp_c']:.1f}°C)..."
        if st.button(label, type="primary" if can_reset else "secondary", disabled=not can_reset, use_container_width=True):
            mixer.reset_thermal_trip()
            st.rerun()

st.divider()
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("Total Load", f"{total_power:.1f} A", delta_color="inverse" if total_power > 20 else "normal")
kpi2.metric("Shaft Speed", f"{data['rpm_shaft']:.1f} RPM")
kpi3.metric("Motor Temp", f"{data['motor_temp_c']:.1f} °C", delta_color="inverse" if data['motor_temp_c'] > 80 else "off")
kpi4.metric("Vibration", f"{data['vibration_mm_s']:.2f} mm/s", delta_color="inverse")
kpi5.metric("Fill Level", f"{data['fill_level_kg']:.1f} kg")

st.divider()

if st.session_state['agent_mode'] == 'Assistant':
    st.subheader("Technical Support Assistant (Consultive)")
    if st.session_state['assistant'] is not None:
        chat_col, info_col = st.columns([2, 1])
        with info_col:
            st.info("**Mode: CONSULTIVE**\n- Answers your questions\n- Does NOT take actions")
            quick_questions = ["What should I do right now?", "How do I reset the thermal relay?", "Why is vibration high?"]
            for i, q in enumerate(quick_questions):
                if st.button(q, key=f"quick_{i}", use_container_width=True):
                    st.session_state['chat_messages'].append({"role": "user", "content": q})
                    with st.spinner("Consulting manual..."):
                        response = st.session_state['assistant'].ask(q, format_telemetry(data))
                    st.session_state['chat_messages'].append({"role": "assistant", "content": response})
                    st.rerun()
        
        with chat_col:
            chat_container = st.container(height=400)
            with chat_container:
                if len(st.session_state['chat_messages']) == 0:
                    st.info("Ask me anything about the RBM-500!")
                for msg in st.session_state['chat_messages']:
                    if msg["role"] == "system": st.warning(msg["content"])
                    else: st.chat_message(msg["role"]).write(msg["content"])
            
            if user_question := st.chat_input("Ask the technical assistant..."):
                st.session_state['chat_messages'].append({"role": "user", "content": user_question})
                with st.spinner("Consulting manual..."):
                    try:
                        response = st.session_state['assistant'].ask(user_question, format_telemetry(data))
                        st.session_state['chat_messages'].append({"role": "assistant", "content": response})
                    except Exception as e:
                        st.session_state['chat_messages'].append({"role": "assistant", "content": f"⚠️ Error: {str(e)}"})
                st.rerun()

elif st.session_state['agent_mode'] == 'Autonomous':
    st.subheader("Autonomous Manager (Active Control)")
    if st.session_state['autonomous_manager'] is not None:
        col_decision, col_actions = st.columns([2, 1])
        with col_decision:
            st.markdown("**Current Decision:**")
            if st.session_state.get('last_autonomous_decision'):
                decision = st.session_state['last_autonomous_decision']
                if decision['action'] == "EMERGENCY_STOP": st.error(f"**{decision['action']}**")
                elif decision['action'] == "RESET_RELAY": st.warning(f"**{decision['action']}**")
                elif decision['action'] == "LOG_TICKET": st.info(f"**{decision['action']}**")
                else: st.success(f"**{decision['action']}**")
                st.caption(f"*{decision['reason']}*")
            else:
                st.info("Waiting for first evaluation...")
        
        with col_actions:
            st.markdown("**Actions Taken:**")
            st.metric("Total Actions", len(st.session_state.get('autonomous_actions', [])))
            st.metric("Open Tickets", len(st.session_state.get('maintenance_tickets', [])))
        
        st.divider()
        st.markdown("**Activity Log:**")
        log_container = st.container(height=300)
        with log_container:
            messages = st.session_state['chat_messages'][-10:]
            if not messages: st.info("System is monitoring...")
            for msg in reversed(messages):
                if msg["role"] == "system": st.warning(msg["content"])
        
        if len(st.session_state.get('maintenance_tickets', [])) > 0:
            st.divider()
            for ticket in st.session_state['maintenance_tickets']:
                if ticket['status'] == 'OPEN':
                    with st.expander(f"Ticket #{ticket['id']}: {ticket['issue'][:50]}..."):
                        st.write(f"**Issue:** {ticket['issue']}")
                        if st.button(f"Close Ticket #{ticket['id']}", key=f"close_{ticket['id']}"):
                            ticket['status'] = 'CLOSED'
                            st.rerun()

# --- TELEMETRY CHARTS ---
st.divider()
st.subheader("Telemetry Analysis")
tab1, tab2, tab3, tab4 = st.tabs(["⚡ Power", "🌡️ Thermal", "⚙️ Vibration", "📊 Process"])

with tab1:
    g1, g2, g3 = st.columns(3)
    if not df.empty:
        g1.line_chart(df[['timestamp', 'main_motor_amps']].set_index('timestamp'), height=200)
        g2.line_chart(df[['timestamp', 'discharge_amps']].set_index('timestamp'), height=200)
        g3.area_chart(df[['timestamp', 'total_amps']].set_index('timestamp'), height=200)

with tab2:
    if not df.empty: st.line_chart(df[['timestamp', 'motor_temp_c', 'ambient_temp_c']].set_index('timestamp'))
with tab3:
    if not df.empty: st.line_chart(df[['timestamp', 'vibration_mm_s']].set_index('timestamp'))
with tab4:
    if not df.empty:
        col1, col2 = st.columns(2)
        col1.line_chart(df[['timestamp', 'rpm_shaft']].set_index('timestamp'))
        col2.line_chart(df[['timestamp', 'fill_level_kg']].set_index('timestamp'))

# --- AUTO-REFRESH ---
active_system = (
    st.session_state['toggle_main'] or 
    st.session_state['toggle_disch'] or 
    data['thermal_trip'] or 
    data['motor_temp_c'] > (data['ambient_temp_c'] + 2)
)

if active_system:
    time.sleep(1)
    st.rerun()