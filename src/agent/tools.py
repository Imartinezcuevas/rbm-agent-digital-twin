import streamlit as st
from typing import Dict

class MachineTools:
    """
    Executable actions that the autonomous agent can trigger.
    These are the ONLY actions the agent can perform on the physical system.
    """

    @staticmethod
    def emergency_stop(reason: str) -> str:
        """
        Triggers an immediate halt of all motors.
        
        Args:
            reason: Explanation for the emergency stop
            
        Returns:
            Confirmation message or error
        """
        if 'mixer' in st.session_state:
            mixer = st.session_state['mixer']
            mixer.set_controls(run_main_motor=False, run_discharge=False, target_rpm=0)
            
            # Log the action
            if 'autonomous_actions' not in st.session_state:
                st.session_state['autonomous_actions'] = []
            
            st.session_state['autonomous_actions'].append({
                "action": "EMERGENCY_STOP",
                "reason": reason,
                "timestamp": mixer.get_telemetry()['timestamp']
            })
            
            return f"ACTION EXECUTED: Emergency stop triggered. Reason: {reason}"
        return "ERROR: Mixer not found in session."
    
    @staticmethod
    def reset_thermal_relay() -> str:
        """
        Attempts to reset the thermal relay if conditions allow.
        
        Returns:
            Success or failure message with details
        """
        if 'mixer' in st.session_state:
            mixer = st.session_state['mixer']
            result = mixer.reset_thermal_trip()
            
            # Log the action
            if 'autonomous_actions' not in st.session_state:
                st.session_state['autonomous_actions'] = []
            
            st.session_state['autonomous_actions'].append({
                "action": "RESET_THERMAL_RELAY",
                "result": result,
                "timestamp": mixer.get_telemetry()['timestamp']
            })
            
            return f"ACTION EXECUTED: Reset thermal relay. Result: {result}"
        return "ERROR: Mixer not found in session."
    
    @staticmethod
    def log_maintenance_ticket(issue: str) -> str:
        """
        Logs a virtual maintenance ticket for operator review.
        
        Args:
            issue: Description of the maintenance issue
            
        Returns:
            Confirmation of ticket creation
        """
        # Store tickets in session state
        if 'maintenance_tickets' not in st.session_state:
            st.session_state['maintenance_tickets'] = []
        
        ticket = {
            "id": len(st.session_state['maintenance_tickets']) + 1,
            "issue": issue,
            "status": "OPEN",
            "created_at": st.session_state['mixer'].get_telemetry()['timestamp'] if 'mixer' in st.session_state else None
        }
        
        st.session_state['maintenance_tickets'].append(ticket)
        
        return f"TICKET CREATED: Maintenance notified about '{issue}' (Ticket #{ticket['id']})"
    
    @staticmethod
    def monitor_only(reason: str) -> str:
        """
        Logs a monitoring observation without taking action.
        
        Args:
            reason: Observation or note
            
        Returns:
            Confirmation of monitoring log
        """
        if 'monitoring_logs' not in st.session_state:
            st.session_state['monitoring_logs'] = []
        
        st.session_state['monitoring_logs'].append({
            "reason": reason,
            "timestamp": st.session_state['mixer'].get_telemetry()['timestamp'] if 'mixer' in st.session_state else None
        })
        
        return f"MONITORING: {reason}"
    
    @staticmethod
    def execute_action(action_type: str, reason: str) -> str:
        """
        Dispatcher that executes the appropriate action based on agent decision.
        
        Args:
            action_type: One of ["EMERGENCY_STOP", "RESET_RELAY", "LOG_TICKET", "MONITOR"]
            reason: Explanation for the action
            
        Returns:
            Result of the action
        """
        action_map = {
            "EMERGENCY_STOP": lambda: MachineTools.emergency_stop(reason),
            "RESET_RELAY": lambda: MachineTools.reset_thermal_relay(),
            "LOG_TICKET": lambda: MachineTools.log_maintenance_ticket(reason),
            "MONITOR": lambda: MachineTools.monitor_only(reason)
        }
        
        if action_type in action_map:
            return action_map[action_type]()
        else:
            return f"ERROR: Unknown action type '{action_type}'"