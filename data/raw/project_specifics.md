# INTERNAL PROTOCOLS: RBM-500 OPERATION

## 1. Operational Limits (Simulated Digital Twin Specs)
These parameters override the general manufacturer manual for the specific Digital Twin instance.

### 1.1 Vibration Thresholds
- **Normal Range:** 0.0 - 4.0 mm/s.
- **Warning Range:** 4.0 - 6.0 mm/s (Schedule Maintenance).
- **CRITICAL FAILURE:** > 6.0 mm/s.
  - **Action:** STOP IMMEDIATELY. This indicates bearing damage.
  - **Reference:** Digital Twin Sensor ID: `vibration_mm_s`.

### 1.2 Thermal Protection System
- **Trip Point:** 95.0°C.
- **Reset Requirement:** The motor must cool down below **70.0°C** before the thermal relay can be reset.
- **Cooling Physics:** The motor cools passively based on ambient temperature. In hot environments (>35°C), cooling will be slower.

### 1.3 Loading
- **Maximum Load:** 140 kg.
- **Overload Consequence:** Exceeding 140kg increases amperage exponentially and causes rapid overheating.