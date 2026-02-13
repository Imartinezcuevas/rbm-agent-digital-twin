import streamlit as st

class MachineTools:
    """
    Executable actions that the autonomous agent can trigger.
    """

    @staticmethod
    def emergency_stop(reason:str) -> str:
        """
        Triggers an immediate halt of all motors.
        """
        if 'mixer' in st.session_state:
            mixer = st.session_state['mixer']
            mixer.set_controls(run_main_motor=False, run_discharge=False, target_rpm=0)
            return f"AACTION EXECUTED: Emergency stop triggered. Reason {reason}"
        return "ERROR: Mixer not found in session."
    
    @staticmethod
    def reset_thermal_relay() -> str:
        """
        Attempts to reset the thermal relay if conditions allow.
        """
        if 'mixer' in st.session_state:
            mixer = st.session_state['mixer']
            result = mixer.reset_thermal_trip()
            return f"ACTION EXECUTED: Reset thermal relay. Result: {result}"
        return "ERROR: Mixer not found in session."
    
    @staticmethod
    def log_maintenance_ticket(issue: str) -> str:
        """
        Logs a virtual maintenance ticket.
        """
        return f"TICKED CREATED: Maintenance notified about '{issue}'."