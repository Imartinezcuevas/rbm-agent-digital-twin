import pytest
import sys
import os

# Hack to import sibling modules without configuration issues
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.simulation.mixer_sim import RBM_500

class TestRBMSafety:
    """
    Test Suite to validate RBM-500 safety systems and physics logic.
    """

    def test_lid_interlock_prevention(self):
        """1. Motor must NOT start if the lid is open."""
        mixer = RBM_500()
        mixer.lid_open = True
        
        # Attempt start
        status = mixer.set_controls(run_main_motor=True, run_discharge=False)
        
        # Validations
        assert "ERROR" in status, "Controller should return error"
        assert mixer.target_rpm == 0, "target_rpm must be forced to 0"
        
        # Advance physics
        mixer.update_physics()
        assert mixer.shaft_rpm == 0, "Physical shaft should not move"

    def test_lid_interlock_cutoff(self):
        """2. If the lid opens during operation, the system must stop."""
        mixer = RBM_500()
        
        # Normal start
        mixer.set_controls(run_main_motor=True, run_discharge=False)
        mixer.motor_rpm = 24.0 # Force current speed
        
        # Event: Someone opens the lid
        mixer.lid_open = True
        
        # Next control cycle
        status = mixer.set_controls(run_main_motor=True, run_discharge=False)
        
        assert "ERROR" in status
        assert mixer.target_rpm == 0

    def test_thermal_trip_activation(self):
        """3. System must trip the relay if T > 95°C."""
        mixer = RBM_500()
        
        # Edge case / Boundary condition
        mixer.motor_temp_c = 94.0
        mixer.set_controls(run_main_motor=True, run_discharge=False)
        
        # Artificially force temperature rise (override physics for test)
        mixer.motor_temp_c = 100.0 
        
        # Execute physics tick
        mixer.update_physics()
        
        assert mixer.thermal_trip is True, "thermal_trip flag must activate"
        assert mixer.target_rpm == 0, "Motor must receive stop command"
        assert mixer.discharge_motor_on is False, "Discharge must also cut off"

    def test_thermal_reset_logic(self):
        """4. Cannot reset if still hot (>70°C)."""
        mixer = RBM_500()
        mixer.thermal_trip = True
        
        # Case A: Too hot
        mixer.motor_temp_c = 85.0
        res = mixer.reset_thermal_trip()
        assert "ERROR" in res, "Should not allow reset at 85°C"
        assert mixer.thermal_trip is True
        
        # Case B: Cooled down
        mixer.motor_temp_c = 60.0
        res = mixer.reset_thermal_trip()
        assert "OK" in res, "Should allow reset at 60°C"
        assert mixer.thermal_trip is False

    def test_ambient_temperature_physics(self):
        """5. Motor must tend towards ambient temperature (Newton's Law)."""
        mixer = RBM_500()
        
        # Scenario: Motor off but cold (10°C), Hot Room (40°C)
        # The motor should passively HEAT UP to match the room.
        mixer.ambient_temp_c = 40.0
        mixer.motor_temp_c = 10.0
        mixer.main_motor_amps = 0.0 # Motor off
        
        # Advance 10 ticks (seconds)
        temp_inicial = mixer.motor_temp_c
        for _ in range(10):
            mixer.update_physics()
            
        assert mixer.motor_temp_c > temp_inicial, \
            f"Motor should passively warm up towards {mixer.ambient_temp_c}°C"

    def test_load_calculation(self):
        """6. Higher physical load must result in higher amperage."""
        mixer_empty = RBM_500()
        mixer_full = RBM_500()
        
        # Identical configuration
        mixer_empty.target_rpm = 24
        mixer_full.target_rpm = 24
        
        # Load difference
        mixer_empty.fill_level_kg = 0
        mixer_full.fill_level_kg = 140
        
        # Stabilize (let motor spin up)
        for _ in range(10):
            mixer_empty.update_physics()
            mixer_full.update_physics()
            
        # Loaded consumption must be higher than empty
        assert mixer_full.main_motor_amps > mixer_empty.main_motor_amps + 5.0, \
            "Full machine must consume significantly more power"

if __name__ == "__main__":
    pytest.main()