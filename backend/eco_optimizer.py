import math
from models import (
    RecommendationRequest, RecommendationSummary, AdviceOutput, RPMSpeedMapping,
    SpeedRPMCandidate, RecommendationResponse, TrafficState, LeadVehicleStatus,
    LeadVehicleDistance, RecommendedAction, SafetyLevel, GearSpeedRange
)
from vehicle_profile import resolve_vehicle_profile

def model_to_dict(model):
    if model is None:
        return {}
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)

def is_urgent_condition(perception: dict) -> bool:
    """
    Return True when safety overrides fuel economy.
    """
    return (
        perception.get("pedestrian_detected", False)
        or perception.get("hazard_detected", False)
        or perception.get("possible_incident", False)
        or perception.get("lead_vehicle_status") == "stopped"
        or perception.get("traffic_state") == "stopped"
    )

def tire_circumference_m(width_mm: int, aspect_ratio: int, rim_in: int) -> float:
    sidewall_mm = width_mm * (aspect_ratio / 100.0)
    diameter_mm = rim_in * 25.4 + 2 * sidewall_mm
    return math.pi * diameter_mm / 1000.0

def estimate_engine_rpm(speed_mph: float, gear_ratio: float, final_drive_ratio: float, 
                        tire_width: int, aspect_ratio: int, rim_in: int) -> float:
    if speed_mph <= 0:
        return 0.0
    speed_mps = speed_mph * 0.44704
    circ_m = tire_circumference_m(tire_width, aspect_ratio, rim_in)
    wheel_rps = speed_mps / circ_m
    wheel_rpm = wheel_rps * 60.0
    engine_rpm = wheel_rpm * gear_ratio * final_drive_ratio
    return engine_rpm

def speed_from_rpm(rpm: float, gear_ratio: float, final_drive_ratio: float, 
                   tire_width: int, aspect_ratio: int, rim_in: int) -> float:
    wheel_rpm = rpm / (gear_ratio * final_drive_ratio)
    circ_m = tire_circumference_m(tire_width, aspect_ratio, rim_in)
    speed_mps = (wheel_rpm * circ_m) / 60.0
    speed_mph = speed_mps / 0.44704
    return speed_mph

def get_speed_range_for_rpm_band(rpm_low: float, rpm_high: float, vehicle_profile: dict) -> list:
    results = []
    gear_ratios = vehicle_profile.get("gear_ratios", {})
    fd = vehicle_profile.get("final_drive_ratio", 3.7)
    tw = vehicle_profile.get("tire_width", 225)
    ar = vehicle_profile.get("aspect_ratio", 50)
    rim = vehicle_profile.get("rim_in", 17)
    
    for gear_str, ratio in gear_ratios.items():
        try:
            gear = int(gear_str)
        except ValueError:
            continue
        
        speed_low = int(speed_from_rpm(rpm_low, ratio, fd, tw, ar, rim))
        speed_high = int(speed_from_rpm(rpm_high, ratio, fd, tw, ar, rim))
        
        results.append({
            "gear": gear,
            "speed_range_mph": f"{speed_low}-{speed_high}",
            "rpm_band": f"{int(rpm_low)}-{int(rpm_high)}"
        })
    return results

def choose_best_gear_and_rpm(speed_mph: float, vehicle_profile: dict, grade_percent: float) -> dict:
    gear_ratios = vehicle_profile.get("gear_ratios", {})
    fd = vehicle_profile.get("final_drive_ratio", 3.7)
    tw = vehicle_profile.get("tire_width", 225)
    ar = vehicle_profile.get("aspect_ratio", 50)
    rim = vehicle_profile.get("rim_in", 17)
    
    best_gear = None
    best_rpm = None
    min_cost = float('inf')
    
    target_low = 1500
    target_high = 2300
    if grade_percent > 3.0:
        target_low = 1800
        target_high = 2800
        
    for gear_str, ratio in gear_ratios.items():
        try:
            gear = int(gear_str)
        except ValueError:
            continue
        
        rpm = estimate_engine_rpm(speed_mph, ratio, fd, tw, ar, rim)
        
        cost = 0
        if rpm < 1100:
            cost += (1100 - rpm) * 0.1
        if rpm > 3000:
            cost += (rpm - 3000) * 0.05
            
        if rpm < target_low:
            cost += (target_low - rpm) * 0.01
        elif rpm > target_high:
            cost += (rpm - target_high) * 0.01
            
        if speed_mph > 12 and gear == 1:
            cost += 80
        if speed_mph > 25 and gear <= 2:
            cost += 40
            
        # Tiebreaker: prefer highest gear
        cost -= gear * 0.001
            
        if cost < min_cost:
            min_cost = cost
            best_gear = gear
            best_rpm = rpm
            
    if best_gear is None:
        best_gear = 3
        best_rpm = 1800
        
    return {
        "recommended_gear": best_gear,
        "estimated_rpm": int(best_rpm),
        "target_rpm_range": f"{target_low}-{target_high}",
        "gear_confidence": 0.7
    }

def estimate_current_rpm_range(current_speed_mph: float, vehicle_profile: dict, grade_percent: float) -> dict:
    gear_ratios = vehicle_profile.get("gear_ratios", {})
    fd = vehicle_profile.get("final_drive_ratio", 3.7)
    tw = vehicle_profile.get("tire_width", 225)
    ar = vehicle_profile.get("aspect_ratio", 50)
    rim = vehicle_profile.get("rim_in", 17)
    
    valid_rpms = []
    
    for gear_str, ratio in gear_ratios.items():
        try:
            gear = int(gear_str)
        except ValueError:
            continue
        rpm = estimate_engine_rpm(current_speed_mph, ratio, fd, tw, ar, rim)
        
        if grade_percent > 3.0 and rpm < 1600:
            continue
            
        if 1100 <= rpm <= 3000:
            valid_rpms.append(rpm)
            
    best = choose_best_gear_and_rpm(current_speed_mph, vehicle_profile, grade_percent)
    best_gear = best["recommended_gear"]
    
    if valid_rpms:
        low_bound = int(min(valid_rpms))
        high_bound = int(max(valid_rpms))
    else:
        est_rpm = best["estimated_rpm"]
        low_bound = max(1000, int(est_rpm - 300))
        high_bound = int(est_rpm + 500)
    
    return {
        "estimated_current_rpm_range": f"{low_bound}-{high_bound}",
        "likely_current_gear": best_gear,
        "gear_confidence": best["gear_confidence"]
    }

def perception_speed_cap(perception: dict, speed_limit_mph: float, traffic_speed_mph: float) -> float:
    cap = speed_limit_mph
    
    # Defaults if missing
    p_ped = perception.get("pedestrian_detected", False)
    p_cyc = perception.get("cyclist_detected", False)
    p_haz = perception.get("hazard_detected", False)
    p_stop = perception.get("stopped_vehicle_detected", False)
    p_inc = perception.get("possible_incident", False)
    p_lead_s = perception.get("lead_vehicle_status", "none")
    p_lead_d = perception.get("lead_vehicle_distance", "far")
    p_traf = perception.get("traffic_state", "clear")
    
    if p_ped:
        cap = min(cap, 10.0)
    elif p_cyc and p_lead_d in ["close", "medium"]:
        cap = min(cap, 15.0)
    elif p_haz:
        cap = min(cap, 20.0)
    elif p_stop:
        cap = min(cap, 15.0)
    elif p_inc:
        cap = min(cap, 20.0)
    elif p_lead_s == "stopped":
        cap = min(cap, 10.0)
    elif p_lead_s == "braking" and p_lead_d == "close":
        if traffic_speed_mph:
            cap = min(cap, traffic_speed_mph)
    elif p_traf == "stopped":
        cap = min(cap, 10.0)
    elif p_traf == "slowing":
        if traffic_speed_mph:
            cap = min(cap, traffic_speed_mph + 5.0)
            
    return cap

def required_power_kw(speed_mph: float, grade_percent: float, mass_kg: float, 
                      cd: float = 0.29, frontal_area_m2: float = 2.2, crr: float = 0.012) -> float:
    v = speed_mph * 0.44704
    rho = 1.225
    g = 9.81
    
    drag_force = 0.5 * rho * cd * frontal_area_m2 * v**2
    rolling_force = crr * mass_kg * g
    grade_force = mass_kg * g * (grade_percent / 100.0)
    
    total_force = drag_force + rolling_force + grade_force
    power_kw = max(total_force * v / 1000.0, 0.0)
    return power_kw

def score_speed_gear_candidate(candidate_speed: float, candidate_gear: int, 
                               context: dict, perception: dict, vehicle_profile: dict) -> float:
    limit = context.get("speed_limit_mph", 60)
    traffic_speed = context.get("traffic_speed_mph")
    grade = context.get("road_grade_percent", 0.0)
    stop_dist = context.get("upcoming_stop_distance_m")
    
    cap = perception_speed_cap(perception, limit, traffic_speed or limit)
    urgent = is_urgent_condition(perception)
    
    score = 0.0
    
    # Penalize speed over limit
    if candidate_speed > limit:
        score += (candidate_speed - limit) * 5.0
        
    # Penalize speed over cap
    if candidate_speed > cap:
        score += (candidate_speed - cap) * 10.0
        
    if traffic_speed and not urgent:
        if candidate_speed < traffic_speed - 7:
            score += (traffic_speed - candidate_speed) * 3.0
            
    if not urgent and perception.get("traffic_state") != "stopped":
        if candidate_speed < 15:
            score += (15 - candidate_speed) * 5.0
            
    # Penalize speed much higher than traffic
    if traffic_speed and candidate_speed > traffic_speed + 5:
        score += (candidate_speed - traffic_speed) * 2.0
        
    # Penalize driving too slow if road is clear
    if candidate_speed < limit - 5 and cap >= limit and (not traffic_speed or traffic_speed >= limit):
        score += (limit - candidate_speed) * 0.5
        
    # Penalize upcoming stop
    if stop_dist and stop_dist < 300 and candidate_speed > 25:
        score += (candidate_speed - 25) * (300 - stop_dist) / 100.0
        
    # RPM and power penalties
    gear_ratios = vehicle_profile.get("gear_ratios", {})
    fd = vehicle_profile.get("final_drive_ratio", 3.7)
    tw = vehicle_profile.get("tire_width", 225)
    ar = vehicle_profile.get("aspect_ratio", 50)
    rim = vehicle_profile.get("rim_in", 17)
    mass = vehicle_profile.get("mass_kg", 1500)
    
    ratio = gear_ratios.get(str(candidate_gear), 1.0)
    rpm = estimate_engine_rpm(candidate_speed, ratio, fd, tw, ar, rim)
    
    if rpm < 1100:
        score += (1100 - rpm) * 0.2
    if rpm > 3000:
        score += (rpm - 3000) * 0.1
        
    # Uphill with low RPM penalty
    if grade > 3.0 and rpm < 1800:
        score += (1800 - rpm) * 0.1
        
    # Downhill too fast
    if grade < -3.0 and candidate_speed > limit - 5:
        score += (candidate_speed - (limit - 5)) * 1.0
        
    # Power required
    power = required_power_kw(candidate_speed, grade, mass)
    score += power * 0.1
    
    # Low-gear penalties
    if candidate_speed > 12 and candidate_gear == 1:
        score += 80
    if candidate_speed > 25 and candidate_gear <= 2:
        score += 40
    if candidate_speed > 35 and candidate_gear <= 3:
        score += 20
        
    # Tiebreaker for highest gear
    score -= candidate_gear * 0.001
    
    return score

def optimize_speed_and_rpm_jointly(context: dict, perception: dict, vehicle_profile: dict, current_speed_mph: float) -> dict:
    limit = context.get("speed_limit_mph", 60)
    traffic_speed = context.get("traffic_speed_mph")
    gear_ratios = vehicle_profile.get("gear_ratios", {})
    cap = perception_speed_cap(perception, limit, traffic_speed or limit)
    urgent = is_urgent_condition(perception)
    
    # Generate candidate speeds
    candidates_set = set()
    for s in range(5, int(limit) + 6, 5):
        candidates_set.add(float(s))
        
    candidates_set.add(float(current_speed_mph))
    candidates_set.add(float(current_speed_mph - 5))
    candidates_set.add(float(current_speed_mph - 10))
    if traffic_speed is not None:
        candidates_set.add(float(traffic_speed))
        candidates_set.add(float(traffic_speed + 5))
        candidates_set.add(float(traffic_speed - 5))
    candidates_set.add(float(cap))
    candidates_set.add(float(limit))
    
    # Clip candidates
    valid_speeds = []
    max_speed = limit
    if not urgent:
        max_speed = min(max_speed, cap)
    else:
        max_speed = cap
        
    for s in candidates_set:
        clipped = max(0.0, min(s, max_speed))
        valid_speeds.append(round(clipped, 1))
        
    valid_speeds = sorted(list(set(valid_speeds)))
    
    best_speed = None
    best_gear = None
    min_score = float('inf')
    best_rpm = None
    
    candidates_output = []
    
    for speed in valid_speeds:
        best_gear_for_speed = None
        best_rpm_for_speed = None
        min_cost_for_speed = float('inf')
        
        for gear_str in gear_ratios.keys():
            try:
                gear = int(gear_str)
            except ValueError:
                continue
                
            score = score_speed_gear_candidate(speed, gear, context, perception, vehicle_profile)
            
            # calculate rpm
            fd = vehicle_profile.get("final_drive_ratio", 3.7)
            tw = vehicle_profile.get("tire_width", 225)
            ar = vehicle_profile.get("aspect_ratio", 50)
            rim = vehicle_profile.get("rim_in", 17)
            ratio = gear_ratios[gear_str]
            rpm = estimate_engine_rpm(speed, ratio, fd, tw, ar, rim)
            
            if score < min_cost_for_speed:
                min_cost_for_speed = score
                best_gear_for_speed = gear
                best_rpm_for_speed = rpm
                
        if best_gear_for_speed is not None:
            candidates_output.append({
                "speed_mph": speed,
                "best_gear": best_gear_for_speed,
                "estimated_rpm": int(best_rpm_for_speed),
                "cost": round(min_cost_for_speed, 1)
            })
            
            if min_cost_for_speed < min_score:
                min_score = min_cost_for_speed
                best_speed = speed
                best_gear = best_gear_for_speed
                best_rpm = int(best_rpm_for_speed)
                
    if best_speed is None:
        best_speed = 25.0
        best_gear = 3
        best_rpm = 1800
        min_score = 0.0
        
    candidates_output.sort(key=lambda x: x["cost"])
    top_candidates = candidates_output[:5]
    
    band_low = max(5, int(best_speed - 3))
    band_high = int(best_speed + 3)
    
    target_low = 1500
    target_high = 2300
    if context.get("road_grade_percent", 0.0) > 3.0:
        target_low = 1800
        target_high = 2800

    return {
        "optimal_speed_now_mph": best_speed,
        "recommended_speed_band_mph": f"{band_low}-{band_high}",
        "recommended_gear": best_gear,
        "estimated_rpm_at_optimal_speed": best_rpm,
        "target_rpm_range_at_optimal_speed": f"{target_low}-{target_high}",
        "selected_cost": round(min_score, 1),
        "speed_rpm_candidates": top_candidates
    }

def determine_recommended_action(current_speed_mph: float, optimal_speed_now_mph: float, perception: dict) -> RecommendedAction:
    if is_urgent_condition(perception):
        return RecommendedAction.urgent_slow_down
        
    diff = current_speed_mph - optimal_speed_now_mph
    
    if diff > 5.0:
        return RecommendedAction.coast # or slow_down, coast is more eco
    elif diff < -5.0:
        return RecommendedAction.accelerate_gently
    else:
        return RecommendedAction.maintain

def compute_eco_score(context: dict, perception: dict, recommendation: dict, current_speed_mph: float) -> int:
    score = 100
    
    optimal = recommendation.get("optimal_speed_now_mph", 30)
    diff = abs(current_speed_mph - optimal)
    if diff > 5:
        score -= int(diff * 1.5)
        
    limit = context.get("speed_limit_mph", 60)
    if current_speed_mph > limit:
        score -= int((current_speed_mph - limit) * 2)
        
    p_lead = perception.get("lead_vehicle_status")
    p_dist = perception.get("lead_vehicle_distance")
    if p_lead == "braking" and p_dist == "close":
        score -= 10
        
    if context.get("congestion_level") == "heavy":
        score -= 5
        
    if context.get("road_grade_percent", 0.0) > 5.0:
        score -= 5
        
    if context.get("upcoming_stop_distance_m", 1000) < 200:
        score -= 5
        
    return max(0, min(100, score))

def determine_safety_level(perception: dict, context: dict) -> SafetyLevel:
    p_ped = perception.get("pedestrian_detected", False)
    p_haz = perception.get("hazard_detected", False)
    p_inc = perception.get("possible_incident", False)
    p_lead_s = perception.get("lead_vehicle_status", "none")
    p_lead_d = perception.get("lead_vehicle_distance", "far")
    p_stop = perception.get("stopped_vehicle_detected", False)
    p_traf = perception.get("traffic_state", "clear")
    inc_ahead = context.get("incident_ahead", False)
    
    if p_ped or p_haz or p_inc or (p_lead_s == "stopped" and p_lead_d == "close"):
        return SafetyLevel.urgent
        
    if p_traf == "slowing" or p_lead_s == "braking" or p_lead_d == "close" or p_stop or inc_ahead:
        return SafetyLevel.caution
        
    return SafetyLevel.safe

def generate_advice(context: dict, perception: dict, recommendation: dict, action: RecommendedAction, vehicle_profile: dict) -> AdviceOutput:
    optimal = recommendation.get("optimal_speed_now_mph", 30)
    target_rpm = recommendation.get("target_rpm_range_at_optimal_speed", "1500-2300")
    
    is_auto = vehicle_profile.get("transmission_type", "automatic") != "manual"
    
    voice = ""
    reason = ""
    
    if action == RecommendedAction.urgent_slow_down:
        voice = "Slow down now. A possible hazard is detected ahead."
        reason = "Hazard, pedestrian, or stopped vehicle detected."
    elif action == RecommendedAction.coast:
        voice = f"Ease off the gas and coast toward {optimal} mph. "
        if perception.get("traffic_state") == "slowing":
            voice += "Traffic is slowing ahead, so coasting now saves fuel and avoids hard braking."
            reason = "Slowing traffic ahead makes coasting efficient."
        elif context.get("upcoming_stop_distance_m", 1000) < 300:
            voice += "A stop is coming up soon, and early coasting avoids wasted braking."
            reason = "Upcoming stop distance is short."
        else:
            voice += f"Targeting {optimal} mph near {target_rpm} RPM is more efficient here."
            reason = "Current speed is above optimal efficiency point."
    elif action == RecommendedAction.accelerate_gently:
        if context.get("road_grade_percent", 0.0) > 3.0:
            voice = "Hold momentum gently uphill, but avoid hard acceleration."
            reason = "Uphill grade requires more power; gentle acceleration minimizes fuel waste."
        else:
            voice = f"Gently accelerate to {optimal} mph."
            reason = "Road is clear and current speed is below optimal flow."
    else: # maintain
        voice = f"Maintain a steady {optimal} mph. "
        if context.get("road_grade_percent", 0.0) > 3.0:
             voice += "Hold momentum gently uphill."
        else:
             voice += "The road ahead is clear, so smooth cruising is most efficient."
        reason = "Current speed matches optimal speed for conditions."

    if action in [RecommendedAction.coast, RecommendedAction.maintain, RecommendedAction.accelerate_gently]:
        if is_auto:
             voice += f" Use light throttle to stay around {target_rpm} estimated RPM and let the transmission settle."
        else:
             voice += f" Target {target_rpm} estimated RPM. Use an appropriate gear if safe and comfortable."
             
    return AdviceOutput(voice_line=voice, reason=reason)

def get_recommendation(payload: RecommendationRequest) -> dict:
    req_dict = model_to_dict(payload)
    
    loc = req_dict.get("location", {})
    ctx = req_dict.get("road_context", {})
    perc = req_dict.get("perception", {})
    vp_input = payload.vehicle_profile
    
    current_speed = round(loc.get("speed_mph", 30.0), 1)
    grade = round(ctx.get("road_grade_percent", 0.0), 2)
    
    profile = resolve_vehicle_profile(vp_input)
    
    opt_res = optimize_speed_and_rpm_jointly(ctx, perc, profile, current_speed)
    optimal_speed = round(opt_res["optimal_speed_now_mph"], 1)
    
    est_rpm_range = estimate_current_rpm_range(current_speed, profile, grade)
    
    action = determine_recommended_action(current_speed, optimal_speed, perc)
    eco_score = compute_eco_score(ctx, perc, opt_res, current_speed)
    safety = determine_safety_level(perc, ctx)
    
    advice = generate_advice(ctx, perc, opt_res, action, profile)
    
    target_rpm = opt_res["target_rpm_range_at_optimal_speed"]
    bounds = [int(x) for x in target_rpm.split('-')]
    rpm_band_ranges = get_speed_range_for_rpm_band(bounds[0], bounds[1], profile)
    
    summary = RecommendationSummary(
        current_speed_mph=current_speed,
        optimal_speed_now_mph=optimal_speed,
        recommended_speed_delta_mph=round(optimal_speed - current_speed, 1),
        recommended_action=action,
        recommended_speed_band_mph=opt_res["recommended_speed_band_mph"],
        recommended_gear=opt_res["recommended_gear"],
        estimated_rpm_at_optimal_speed=opt_res["estimated_rpm_at_optimal_speed"],
        target_rpm_range_at_optimal_speed=target_rpm,
        estimated_current_rpm_range=est_rpm_range["estimated_current_rpm_range"],
        likely_current_gear=est_rpm_range["likely_current_gear"],
        gear_confidence=round(est_rpm_range["gear_confidence"], 2),
        eco_score=eco_score,
        safety_level=safety
    )
    
    mapping = RPMSpeedMapping(
        target_rpm_band=target_rpm,
        speed_ranges_by_gear=[GearSpeedRange(**g) for g in rpm_band_ranges]
    )
    
    cands = [SpeedRPMCandidate(**c) for c in opt_res["speed_rpm_candidates"]]
    
    return {
        "summary": model_to_dict(summary),
        "advice": model_to_dict(advice),
        "rpm_speed_mapping": model_to_dict(mapping),
        "speed_rpm_candidates": [model_to_dict(c) for c in cands],
        "context_used": ctx,
        "vehicle_used": {
            "year": profile.get("year"),
            "make": profile.get("make"),
            "model": profile.get("model"),
            "trim": profile.get("trim"),
            "source": profile.get("source", "unknown")
        },
        "debug": {
            "gear_known": False,
            "rpm_is_estimated": True,
            "selected_cost": opt_res["selected_cost"]
        }
    }
