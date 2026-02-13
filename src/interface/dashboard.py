import streamlit as st
import pandas as pd
import time
import sys
import os

# Adjust path to import simulation
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.simulation.mixer_sim import RBM_500

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="RBM-500 HMI", layout="wide")
st.title("RBM-500 | Industrial Twin Interface")

# --- STATE MANAGEMENT ---
if 'mixer' not in st.session_state:
    st.session_state['mixer'] = RBM_500()
    st.session_state['history'] = []
    st.session_state['last_manual_rerun'] = 0

mixer = st.session_state['mixer']

# --- SIDEBAR: CONTROL PANEL ---
with st.sidebar:
    st.header("Operator Control Panel")
    
    # 1. Actuators (Visualmente desactivados si hay trip)
    st.subheader("Actuators")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        # Si hay thermal trip, mostramos el toggle apagado
        main_val = False if mixer.thermal_trip else None 
        main_power = st.toggle("MAIN DRIVE", value=main_val, key="toggle_main")
        
    with col_s2:
        disch_val = False if mixer.thermal_trip else None
        discharge_power = st.toggle("DISCHARGE", value=disch_val, key="toggle_disch")
        
    target_speed = st.slider("Set Point (RPM)", 0, 24, 20)
    
    st.divider()
    
    # 2. Environment (NUEVO)
    st.subheader("Environment (External)")
    amb_temp = st.slider("Ambient Temp (°C)", 10, 50, 25, help="Simulate Factory Temp")
    mixer.ambient_temp_c = amb_temp
    
    # 3. Fault Injection
    st.subheader("Fault Injection")
    if not discharge_power:
        mixer.fill_level_kg = st.slider("Load (kg)", 0, 140, 70)
    
    mixer._bearing_wear = st.slider("Bearing Wear", 0.0, 1.0, 0.0)
    mixer._clogged_outlet = st.checkbox("Discharge Blockage")
    mixer.lid_open = st.checkbox("Open Safety Interlock")

    # APLICAR CONTROL
    # No mostramos errores en sidebar para evitar parpadeos
    mixer.set_controls(main_power, discharge_power, target_speed)

# --- PHYSICS CYCLE ---
data = mixer.update_physics()

# Total Power Calculation
total_power = data['main_motor_amps'] + data['discharge_amps']
data['total_amps'] = total_power

# Histórico
st.session_state['history'].append(data)
if len(st.session_state['history']) > 60:
    st.session_state['history'].pop(0)
df = pd.DataFrame(st.session_state['history'])

# --- ALARMS & INTERVENTION ---
st.divider()
c_alert1, c_alert2 = st.columns([3, 1])

with c_alert1:
    if data['thermal_trip']:
        st.error(f"🚨 CRITICAL ALARM: THERMAL TRIP ACTIVE | Temp: {data['motor_temp_c']:.1f}°C")
        st.caption("Safety Relay engaged. Wait for cooldown (<70°C).")
    
    elif data['lid_open']:
        if main_power:
            st.error("⛔ SAFETY LOCK: Cannot start Main Drive while Lid is Open.")
        else:
            st.warning("⚠️ SAFETY WARNING: Lid Open.")
            
    elif data['vibration_mm_s'] > 6.0:
        st.warning(f"⚠️ VIBRATION ALERT: High Level ({data['vibration_mm_s']:.1f} mm/s)")
        
    else:
        st.success("✅ SYSTEM STATUS: NOMINAL")

with c_alert2:
    # LÓGICA DE BOTÓN SIN CALLBACK (Directa y Atómica)
    if data['thermal_trip']:
        can_reset = data['motor_temp_c'] < 70.0
        label = "🔘 RESET RELAY" if can_reset else f"⏳ COOLING ({data['motor_temp_c']:.1f}°C)..."
        
        # Al pulsar, ejecutamos reset y REINICIAMOS INMEDIATAMENTE
        if st.button(label, type="primary", disabled=not can_reset):
            mixer.reset_thermal_trip()
            st.session_state['last_manual_rerun'] = time.time()
            st.rerun()

# --- KPI DASHBOARD ---
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

kpi1.metric("Total Load", f"{total_power:.1f} A", delta_color="inverse" if total_power > 20 else "normal")
kpi2.metric("Speed", f"{data['rpm_shaft']:.1f} RPM")
kpi3.metric("Temp", f"{data['motor_temp_c']:.1f} °C", delta=f"Amb: {data['ambient_temp_c']}°C", delta_color="off")
kpi4.metric("Vibration", f"{data['vibration_mm_s']:.1f} mm/s", delta_color="inverse")
kpi5.metric("Level", f"{data['fill_level_kg']:.1f} kg")

# --- GRÁFICAS ---
st.subheader("Telemetry Analysis")
tab1, tab2, tab3 = st.tabs(["⚡ Power Network", "🌡️ Thermal", "⚙️ Vibration"])

with tab1:
    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown("**Main Drive**")
        if not df.empty: st.line_chart(df[['timestamp', 'main_motor_amps']].set_index('timestamp'), height=200)
    with g2:
        st.markdown("**Discharge**")
        if not df.empty: st.line_chart(df[['timestamp', 'discharge_amps']].set_index('timestamp'), height=200)
    with g3:
        st.markdown("**Total Plant**")
        if not df.empty: st.area_chart(df[['timestamp', 'total_amps']].set_index('timestamp'), height=200, color="#ff4b4b")

with tab2:
    if not df.empty: 
        st.line_chart(df[['timestamp', 'motor_temp_c', 'ambient_temp_c']].set_index('timestamp'))

with tab3:
    if not df.empty: st.line_chart(df[['timestamp', 'vibration_mm_s']].set_index('timestamp'))

# --- AUTO-REFRESH ---
# Solo refrescamos si es necesario.
# Evitamos auto-refresh justo después de un reset manual
time_since_manual = time.time() - st.session_state['last_manual_rerun']

active_system = (
    main_power or 
    discharge_power or 
    data['thermal_trip'] or 
    data['motor_temp_c'] > (data['ambient_temp_c'] + 1)
)

# Solo auto-refresh si han pasado >0.5s desde el último rerun manual
if active_system and time_since_manual > 0.5:
    time.sleep(1)
    st.rerun()