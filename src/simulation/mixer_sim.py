import time
import random
from typing import Dict, Union

class RBM_500:
    """
    RBM-500 Digital twin.

    This class simulates the physical, electrical and thermal behaviour of an
    industrial mixer. It is designed to be controllede by an AI agent or PLC logic.

    Specifications:
    - Mixing cabinet capacity: 500L
    - Approximate capacity: 140Kg
    - Stirring paddel diameter: 700mm
    - Stirring revolutions per min: 24
    - Motor power: 7.5kW
    - Dimensions: 2280x700x1150mm
    - Weight: 1500kg
    - Discharge motor power: 1.5kW
    """
    def __init__(self):
        # Physical state
        self.connected = True
        self.lid_open = False               # Safety grid sensor
        self.discharge_valve_open = False
        self.discharge_motor_on = False

        # Process variables
        self.target_rpm = 0              
        self.motor_rpm = 0          # Internal motor speed
        self.shaft_rpm = 0          # Ribbon speed
        self.fill_level_kg = 0.0    # Max 140

        # Ambient variables
        self.ambient_temp_c = 25.0

        # Sensors (Telemetry)
        self.main_motor_amps = 0.0  # Main 7.5kW motor current
        self.disch_motor_amps = 0.0 # Discharge 1.5kW motor current
        self.motor_temp_c = 22.0    # Winding temperature
        self.vibration_level = 0.0  # mm/s
        self.sound_db = 0.0

        # Hidden fault states (simulation only)
        self._belt_slip_factor = 0.0    # 0.0 (new) to 1.0 (broken)
        self._bearing_wear = 0.0        # 0.0 (new) to 1.0 (broken)
        self._clogged_outlet = False    # Simulates blockage in discharge
        self.thermal_trip = False

    def set_controls(self, run_main_motor: bool, run_discharge: bool, target_rpm: int = 24) -> str:
        """
        Actuates the mixer motors. The agent uses this to operate the machine.

        Args:
            run_main_motor: Set True to turn on the mixing ribbons.
            run_discharge: Set True to open valve and run dischage auger.
            target_rpm: Desired speed in RPM. Hard limited to 24 RPM.

        Returns:
            str: "OK" if successful, or an error message
        """
        # Safety interlock: main motor can't run if lid is open
        if self.lid_open and run_main_motor:
            self.target_rpm = 0
            return "ERROR: Safety lid open"
        
        if self.thermal_trip:
            self.target_rpm = 0
            self.discharge_motor_on = False
            return "ERROR: Thermal trip active (reset required)"
        
        # Main motor control
        if run_main_motor:
            # Cap RMP at specific hardware limit
            self.target_rpm = min(target_rpm, 24)
        else:
            self.target_rpm = 0
        
        # Discharge motor control
        self.discharge_motor_on = run_discharge

        return "OK"
    
    def update_physics(self) -> Dict[str, Union[float, str, bool]]:
        """
        Steps the physics simulation forward by 1 second.
        Calculates inertia, thermodynamics, and electrical loads.
        """
        # 1. Main motor dinamics
        if self.target_rpm > self.motor_rpm:
            self.motor_rpm += 1.0 #Slow acceleration
        elif self.target_rpm < self.motor_rpm:
            self.motor_rpm -= 2.0 # Friction deceleration

        self.motor_rpm = max(0, self.motor_rpm)

        # 2. Transmision logic (Belt)
        # If belt slips, shaft turns slower than motor
        efficiency = 1.0 - self._belt_slip_factor
        self.shaft_rpm = self.motor_rpm * efficiency

        # 3. Electric load calculation
        idle_amps = 4.0

        # Load factor: mixin 140 kg is harder than mixing 20kg
        load_factor = (self.fill_level_kg / 140.0)
        # Friction factor
        friction_drag = self._bearing_wear * 5.0
        # Total amps calculation
        if self.motor_rpm > 1:
            current_target = idle_amps + (10.0 * load_factor) + friction_drag
            # Add noise + startup spike simulation
            self.main_motor_amps = max(0, current_target + random.uniform(-0.3, 0.3))
        else:
            self.main_motor_amps = 0.0

        # 4. Discharge motor logic
        if self.discharge_motor_on:
            base_disch_amp = 2.5
            if self._clogged_outlet:
                base_disch_amp += 5.0 # Spike indicating stall
            self.disch_motor_amps = base_disch_amp + random.uniform(-0.1, 0.1)

            # Empties the tank if valve is open
            if self.fill_level_kg > 0 and not self._clogged_outlet:
                self.fill_level_kg = max(0, self.fill_level_kg - 1.5)
        else:
            self.disch_motor_amps = 0.0

        # 5. Motor heat
        # heat is proportional to current squared
        heat_generation = (self.main_motor_amps **2) * 0.006
        delta_temp = self.motor_temp_c - self.ambient_temp_c
        passive_cooling = delta_temp * 0.03
        self.motor_temp_c += heat_generation - passive_cooling

        if self.motor_temp_c > 95.0:
            self.thermal_trip = True
            self.target_rpm = 0
            self.discharge_motor_on = False

        # 6. Vibration
        # Base vibration increases with RPM
        base_vib = (self.shaft_rpm / 24.0) * 0.8
        # Fault vibration increases with bearing wear
        fault_vib = self._bearing_wear * 7.0 * (self.shaft_rpm / 24.0)
        self.vibration_level = base_vib + fault_vib + random.uniform(0, 0.05)

        return self.get_telemetry()
    
    def get_telemetry(self) -> Dict[str, Union[float, str, bool]]:
        """Returns the current state dictionary for sensor."""
        return {
            "timestamp": time.time(),
            "status": "RUNNING" if self.motor_rpm > 0 else "STOPPED",
            "rpm_shaft": round(self.shaft_rpm, 1),
            "main_motor_amps": round(self.main_motor_amps,2),
            "discharge_amps": round(self.disch_motor_amps, 2),
            "motor_temp_c": round(self.motor_temp_c, 1),
            "ambient_temp_c": round(self.ambient_temp_c, 1),
            "vibration_mm_s": round(self.vibration_level, 2),
            "fill_level_kg": round(self.fill_level_kg, 1),
            "lid_open": self.lid_open,
            "thermal_trip": self.thermal_trip
        }

    def reset_thermal_trip(self):
        """
        Attempts to manually reset the thermal overload relay.
        Only works if the motor has cooled down below 70°C.
        """
        if self.motor_temp_c < 70:
            self.thermal_trip = False
            return "OK: Thremal relay reset successful."
        else:
            return f"ERROR: Motor too hot ({self.motor_temp_c:.1f}°C). Wait for cooling."
