import streamlit as st
import pandas as pd
import time
import sys
import os

# Adjust path to import simulation and assistant
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import simulator (REQUIRED - must be in src/simulation/mixer_sim.py)
from src.simulation.mixer_sim import RBM_500

# Try to import Assistant - gracefully handle if not available
try:
    from src.agent.rag_agent import Assistant
    ASSISTANT_AVAILABLE = True
except Exception as e:
    ASSISTANT_AVAILABLE = False
    print(f"Assistant not available: {e}")

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBM-500 HMI", layout="wide")
st.title("RBM-500 | Industrial Twin Interface")

# --- STATE MANAGEMENT ---
if 'mixer' not in st.session_state:
    st.session_state['mixer'] = RBM_500()
    st.session_state['history'] = []
    st.session_state['chat_messages'] = []
    st.session_state['assistant'] = None
    st.session_state['assistant_error'] = None
    st.session_state['refresh_counter'] = 0

# Initialize assistant (only once)
if ASSISTANT_AVAILABLE and st.session_state['assistant'] is None:
    try:
        with st.spinner("Initializing Technical Assistant..."):
            st.session_state['assistant'] = Assistant()
    except Exception as e:
        st.session_state['assistant_error'] = str(e)
        print(f"Failed to initialize Assistant: {e}")

mixer = st.session_state['mixer']
assistant = st.session_state['assistant']

# --- HELPER: Format telemetry for agent ---
def format_telemetry(data):
    """Creates a concise telemetry string for the agent"""
    status = "CRITICAL" if data['thermal_trip'] else ("WARNING" if data['vibration_mm_s'] > 6.0 else "NOMINAL")
    
    return f"""STATUS: {status}
    - Motor Temperature: {data['motor_temp_c']:.1f}°C (Ambient: {data['ambient_temp_c']:.1f}°C)
    - Vibration: {data['vibration_mm_s']:.2f} mm/s
    - Shaft Speed: {data['rpm_shaft']:.1f} RPM (Target: {data['speed_setpoint']} RPM)
    - Main Drive Current: {data['main_motor_amps']:.2f} A
    - Discharge Current: {data['discharge_amps']:.2f} A
    - Fill Level: {data['fill_level_kg']:.1f} kg
    - Lid Status: {'OPEN' if data['lid_open'] else 'CLOSED'}
    - Thermal Trip: {'ACTIVE' if data['thermal_trip'] else 'INACTIVE'}
    - Overall Status: {data['status']}"""

# --- SIDEBAR: CONTROL PANEL ---
with st.sidebar:
    st.header("Operator Control Panel")
    
    # 1. Actuators (Visually disabled if thermal trip)
    st.subheader("Actuators")
    col_s1, col_s2 = st.columns(2)
    
    with col_s1:
        # If thermal trip active, force toggle to off
        if mixer.thermal_trip:
            main_power = st.toggle("MAIN DRIVE", value=False, disabled=True, key="toggle_main")
        else:
            main_power = st.toggle("MAIN DRIVE", value=mixer.target_rpm > 0, key="toggle_main")
        
    with col_s2:
        if mixer.thermal_trip:
            discharge_power = st.toggle("DISCHARGE", value=False, disabled=True, key="toggle_disch")
        else:
            discharge_power = st.toggle("DISCHARGE", value=mixer.discharge_motor_on, key="toggle_disch")
    
    # Speed setpoint slider
    target_speed = st.slider("Set Point (RPM)", 0, 24, int(mixer.target_rpm) if not mixer.thermal_trip else 0)
    
    st.divider()
    
    # 2. Environment Control
    st.subheader("Environment (External)")
    amb_temp = st.slider("Ambient Temp (°C)", 10, 50, int(mixer.ambient_temp_c), 
                         help="Simulate factory temperature conditions")
    mixer.ambient_temp_c = float(amb_temp)
    
    st.divider()
    
    # 3. Fault Injection
    st.subheader("Fault Injection")
    
    # Only allow load changes when discharge is off
    if not discharge_power:
        new_load = st.slider("Fill Level (kg)", 0, 140, int(mixer.fill_level_kg), 
                            help="Material load in mixer")
        mixer.fill_level_kg = float(new_load)
    else:
        st.metric("Fill Level (kg)", f"{mixer.fill_level_kg:.1f}", help="Cannot adjust while discharging")
    
    # Bearing wear simulation
    new_wear = st.slider("Bearing Wear", 0.0, 1.0, mixer._bearing_wear, 0.1,
                        help="0.0 = new, 1.0 = failed")
    mixer._bearing_wear = new_wear
    
    # Belt slip simulation
    new_slip = st.slider("Belt Slip Factor", 0.0, 1.0, mixer._belt_slip_factor, 0.1,
                        help="0.0 = no slip, 1.0 = broken belt")
    mixer._belt_slip_factor = new_slip
    
    # Blockage toggle
    clogged = st.checkbox("Discharge Blockage", value=mixer._clogged_outlet,
                         help="Simulates material jam in discharge")
    mixer._clogged_outlet = clogged
    
    # Safety interlock
    lid_open = st.checkbox("Open Safety Interlock", value=mixer.lid_open,
                          help="Prevents main drive from starting")
    mixer.lid_open = lid_open

    # APPLY CONTROLS TO SIMULATOR
    control_result = mixer.set_controls(main_power, discharge_power, target_speed)
    
    # Show control errors in sidebar (small notification)
    if control_result != "OK":
        st.caption(f"⚠️ {control_result}")
    
    st.divider()
    
    # 4. Technical Assistant Status
    if ASSISTANT_AVAILABLE:
        if assistant is not None:
            st.success("AI Assistant: Online")
        elif st.session_state['assistant_error']:
            st.error(f"AI Assistant: Offline")
            with st.expander("Error Details"):
                st.code(st.session_state['assistant_error'])
    else:
        st.info("AI Assistant: Not installed")

# --- PHYSICS CYCLE ---
data = mixer.update_physics()

# Add speed setpoint to telemetry (for assistant context)
data['speed_setpoint'] = mixer.target_rpm

# Total Power Calculation
total_power = data['main_motor_amps'] + data['discharge_amps']
data['total_amps'] = total_power

# Add to history
st.session_state['history'].append(data)
if len(st.session_state['history']) > 60:
    st.session_state['history'].pop(0)

# Create DataFrame for charts
df = pd.DataFrame(st.session_state['history'])

# --- ALARMS & INTERVENTION ---
st.divider()
c_alert1, c_alert2 = st.columns([3, 1])

with c_alert1:
    if data['thermal_trip']:
        st.error(f"CRITICAL ALARM: THERMAL TRIP ACTIVE | Temp: {data['motor_temp_c']:.1f}°C")
        st.caption("Safety relay engaged. Wait for cooldown (<70°C) before reset.")
    
    elif data['lid_open']:
        if main_power:
            st.error("SAFETY LOCK: Cannot start Main Drive while Lid is Open.")
        else:
            st.warning("SAFETY WARNING: Lid Open - Close before operation.")
            
    elif data['vibration_mm_s'] > 6.0:
        st.warning(f"VIBRATION ALERT: High Level ({data['vibration_mm_s']:.2f} mm/s)")
        st.caption("Check for bearing wear, load imbalance, or mechanical issues.")
    
    elif mixer._clogged_outlet and discharge_power:
        st.warning("DISCHARGE WARNING: Blockage detected - High motor current.")
        st.caption("Stop discharge and inspect outlet for material jam.")
        
    else:
        st.success("SYSTEM STATUS: NOMINAL - All parameters within limits")

with c_alert2:
    # THERMAL RELAY RESET BUTTON
    if data['thermal_trip']:
        can_reset = data['motor_temp_c'] < 70.0
        
        if can_reset:
            label = "RESET RELAY"
            button_type = "primary"
        else:
            label = f"COOLING ({data['motor_temp_c']:.1f}°C)..."
            button_type = "secondary"
        
        if st.button(label, type=button_type, disabled=not can_reset, use_container_width=True):
            mixer.reset_thermal_trip()
            # Don't rerun - let natural cycle handle it

# --- KPI DASHBOARD ---
st.divider()
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

kpi1.metric(
    "Total Load", 
    f"{total_power:.1f} A",
    delta=f"{total_power - 4.0:.1f} A" if total_power > 4.0 else None,
    delta_color="inverse" if total_power > 20 else "normal"
)

kpi2.metric(
    "Shaft Speed", 
    f"{data['rpm_shaft']:.1f} RPM",
    delta=f"Target: {data['speed_setpoint']}" if data['rpm_shaft'] != data['speed_setpoint'] else None
)

kpi3.metric(
    "Motor Temp", 
    f"{data['motor_temp_c']:.1f} °C",
    delta=f"+{data['motor_temp_c'] - data['ambient_temp_c']:.1f}°C vs ambient",
    delta_color="inverse" if data['motor_temp_c'] > 80 else "off"
)

kpi4.metric(
    "Vibration", 
    f"{data['vibration_mm_s']:.2f} mm/s",
    delta="HIGH" if data['vibration_mm_s'] > 6.0 else None,
    delta_color="inverse"
)

kpi5.metric(
    "Fill Level", 
    f"{data['fill_level_kg']:.1f} kg",
    delta=f"{(data['fill_level_kg'] / 140.0) * 100:.0f}% capacity"
)

# --- TECHNICAL ASSISTANT CHAT ---
st.divider()
st.subheader("Technical Support Assistant")

if ASSISTANT_AVAILABLE and assistant is not None:
    # Chat interface
    chat_col, info_col = st.columns([2, 1])
    
    with info_col:
        st.info("""
        **Assistant Capabilities:**
        - Troubleshooting guidance
        - Manual reference lookup
        - Procedure recommendations
        - Real-time diagnostics
        
        **Quick Questions:**
        """)
        
        quick_questions = [
            "What should I do right now?",
            "How do I reset the thermal relay?",
            "Why is vibration high?",
            "Explain the discharge procedure"
        ]
        
        for i, q in enumerate(quick_questions):
            if st.button(q, key=f"quick_{i}", use_container_width=True):
                st.session_state['chat_messages'].append({"role": "user", "content": q})
                telemetry_str = format_telemetry(data)
                
                with st.spinner("Analyzing telemetry and consulting manual..."):
                    response = assistant.ask(q, telemetry_str)
                
                st.session_state['chat_messages'].append({"role": "assistant", "content": response})
    
    with chat_col:
        # Display chat history
        chat_container = st.container(height=400)
        with chat_container:
            if len(st.session_state['chat_messages']) == 0:
                st.info("Ask me anything about the RBM-500! I have access to the complete manual and can see the current machine state.")
            
            for msg in st.session_state['chat_messages']:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])
        
        # Chat input
        if user_question := st.chat_input("Ask the technical assistant..."):
            # Add user message
            st.session_state['chat_messages'].append({"role": "user", "content": user_question})
            
            # Get telemetry snapshot
            telemetry_str = format_telemetry(data)
            
            # Get assistant response
            with st.spinner("Consulting manual and analyzing telemetry..."):
                try:
                    response = assistant.ask(user_question, telemetry_str)
                    st.session_state['chat_messages'].append({"role": "assistant", "content": response})
                except Exception as e:
                    error_msg = f"Error consulting assistant: {str(e)}"
                    st.session_state['chat_messages'].append({"role": "assistant", "content": error_msg})
        
        # Clear chat button - usando form para evitar conflictos
        col1, col2 = st.columns([1, 1])
        
        with col1:
            with st.form(key='clear_chat_form', clear_on_submit=True):
                clear_clicked = st.form_submit_button("Clear Chat History", use_container_width=True, type="secondary")
                
                # Process clear action
                if clear_clicked:
                    st.session_state['chat_messages'] = []
        
        with col2:
            # Export chat button - FUERA del form
            if len(st.session_state['chat_messages']) > 0:
                chat_export = "\n\n".join([
                    f"{'USER' if msg['role'] == 'user' else 'ASSISTANT'}: {msg['content']}"
                    for msg in st.session_state['chat_messages']
                ])
                st.download_button(
                    "Download Chat Log",
                    chat_export,
                    file_name=f"rbm500_chat_{int(time.time())}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

elif st.session_state['assistant_error']:
    st.error(f"**Assistant initialization failed:** {st.session_state['assistant_error']}")
    st.info("Please check that the vector database exists at `data/vector_db_local` and Ollama is running.")
else:
    st.info("**AI Assistant not available.** Install dependencies and run vector DB ingestion first.")

# --- TELEMETRY CHARTS ---
st.divider()
st.subheader("Telemetry Analysis")

tab1, tab2, tab3, tab4 = st.tabs(["⚡ Power Network", "🌡️ Thermal Profile", "⚙️ Vibration", "📊 Process"])

with tab1:
    st.markdown("**Electrical Load Monitoring**")
    g1, g2, g3 = st.columns(3)
    
    with g1:
        st.caption("Main Drive (7.5kW)")
        if not df.empty: 
            st.line_chart(df[['timestamp', 'main_motor_amps']].set_index('timestamp'), height=200)
        else:
            st.info("No data yet")
    
    with g2:
        st.caption("Discharge Motor (1.5kW)")
        if not df.empty: 
            st.line_chart(df[['timestamp', 'discharge_amps']].set_index('timestamp'), height=200)
        else:
            st.info("No data yet")
    
    with g3:
        st.caption("Total Plant Load")
        if not df.empty: 
            st.area_chart(df[['timestamp', 'total_amps']].set_index('timestamp'), height=200, color="#ff4b4b")
        else:
            st.info("No data yet")

with tab2:
    st.markdown("**Thermal Management**")
    if not df.empty:
        st.line_chart(df[['timestamp', 'motor_temp_c', 'ambient_temp_c']].set_index('timestamp'))
        
        # Thermal analysis
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("Current Temp", f"{data['motor_temp_c']:.1f}°C")
        col_t2.metric("ΔT (vs ambient)", f"{data['motor_temp_c'] - data['ambient_temp_c']:.1f}°C")
        col_t3.metric("Trip Threshold", "95°C", delta=f"{95 - data['motor_temp_c']:.1f}°C margin")
    else:
        st.info("No thermal data yet")

with tab3:
    st.markdown("**Vibration Analysis**")
    if not df.empty:
        st.line_chart(df[['timestamp', 'vibration_mm_s']].set_index('timestamp'))
        
        # Vibration analysis
        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("Current Level", f"{data['vibration_mm_s']:.2f} mm/s")
        col_v2.metric("Warning Threshold", "6.0 mm/s", 
                     delta=f"{data['vibration_mm_s'] - 6.0:.2f}" if data['vibration_mm_s'] > 6.0 else None,
                     delta_color="inverse")
        
        # Bearing wear indicator
        if mixer._bearing_wear > 0.5:
            col_v3.metric("Bearing Condition", "⚠️ WORN", f"{mixer._bearing_wear * 100:.0f}%")
        else:
            col_v3.metric("Bearing Condition", "✅ GOOD", f"{mixer._bearing_wear * 100:.0f}%")
    else:
        st.info("No vibration data yet")

with tab4:
    st.markdown("**Process Variables**")
    if not df.empty:
        # Dual axis chart: Speed and Fill Level
        col_p1, col_p2 = st.columns(2)
        
        with col_p1:
            st.caption("Shaft Speed")
            st.line_chart(df[['timestamp', 'rpm_shaft']].set_index('timestamp'), height=250)
        
        with col_p2:
            st.caption("Fill Level")
            st.line_chart(df[['timestamp', 'fill_level_kg']].set_index('timestamp'), height=250)
        
        # Process efficiency
        if data['rpm_shaft'] > 0 and mixer.target_rpm > 0:
            efficiency = (data['rpm_shaft'] / mixer.target_rpm) * 100
            st.metric("Transmission Efficiency", f"{efficiency:.1f}%",
                     delta=f"Belt slip: {mixer._belt_slip_factor * 100:.0f}%" if mixer._belt_slip_factor > 0 else None,
                     delta_color="inverse" if mixer._belt_slip_factor > 0.1 else "normal")
    else:
        st.info("No process data yet")

# --- AUTO-REFRESH LOGIC ---
# Determine if system needs monitoring
active_system = (
    main_power or 
    discharge_power or 
    data['thermal_trip'] or 
    data['motor_temp_c'] > (data['ambient_temp_c'] + 2)
)

# Auto-refresh only if system is active
if active_system:
    time.sleep(1)
    st.rerun()