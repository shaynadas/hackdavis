from mock_data import get_demo_recommendation_payload
from eco_optimizer import get_recommendation
import json

def run_smoke_test():
    payload = get_demo_recommendation_payload()
    result = get_recommendation(payload)
    
    summary = result.get("summary", {})
    advice = result.get("advice", {})
    debug = result.get("debug", {})
    
    current_speed = summary.get("current_speed_mph")
    optimal_speed = summary.get("optimal_speed_now_mph")
    action = summary.get("recommended_action")
    est_rpm = summary.get("estimated_rpm_at_optimal_speed")
    safety = summary.get("safety_level")
    
    print("SMOKE TEST RESULTS")
    print("------------------")
    print(f"Current Speed: {current_speed} mph")
    print(f"Optimal Speed: {optimal_speed} mph")
    print(f"Action:        {action}")
    print(f"Est. RPM:      {est_rpm}")
    print(f"Safety Level:  {safety}")
    print(f"Advice:        {advice.get('voice_line')}")
    print(f"Reason:        {advice.get('reason')}")
    print(f"RPM Estimated: {debug.get('rpm_is_estimated')}")
    
    # Assertions
    assert 18 <= optimal_speed <= 30, f"Optimal speed {optimal_speed} is out of realistic range (18-30)"
    assert safety == "caution", f"Expected caution, got {safety}"
    assert action in ["coast", "slow_down"], f"Expected coast or slow_down, got {action}"
    assert debug.get("rpm_is_estimated") is True, "rpm_is_estimated must be true"
    
    print("\n✅ All assertions passed!")

if __name__ == "__main__":
    run_smoke_test()
