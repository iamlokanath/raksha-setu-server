OPEN_ALERT = {"detected", "acknowledged", "action_planned", "action_in_progress"}
CLEARABLE = {"detected", "acknowledged", "action_planned"}
RANK = {"attention": 1, "urgent": 2}


def shortage_severity(quantity: float, rule: dict) -> str | None:
    if quantity < rule["urgent_below"]:
        return "urgent"
    if quantity < rule["attention_below"]:
        return "attention"
    return None


def capacity_severity(population: int, capacity: int, rule: dict) -> str | None:
    if capacity <= 0:
        return None
    ratio = population / capacity
    if ratio >= rule["urgent_at_ratio"]:
        return "urgent"
    if ratio >= rule["attention_at_ratio"]:
        return "attention"
    return None


def occupancy_band(population: int | None, capacity: int, rule: dict | None) -> str:
    if population is None or rule is None:
        return "unknown"
    severity = capacity_severity(population, capacity, rule)
    if severity is None:
        return "below_attention"
    return severity


def priority_score(factors: dict, config: dict | None) -> float | None:
    if not config:
        return None
    scores = config["severity_scores"]
    weights = config["weights"]
    shortage = scores[factors["shortage_urgency"]]
    vulnerable = min(factors["vulnerable_population"] / config["vulnerable_cap"], 1)
    occupancy = factors["occupancy_pressure"]
    occupancy_norm = 0 if occupancy is None else min(occupancy, 1)
    age_hours = factors["issue_age_seconds"] / 3600
    age_norm = min(age_hours / config["age_cap_hours"], 1)
    return (
        weights["shortage_urgency"] * shortage
        + weights["vulnerable_population"] * vulnerable
        + weights["occupancy_pressure"] * occupancy_norm
        + weights["issue_age"] * age_norm
    )


def priority_band(score: float | None, config: dict | None) -> str:
    if score is None or not config:
        return "unscored"
    if score >= config["bands"]["high"]:
        return "high"
    if score >= config["bands"]["medium"]:
        return "medium"
    return "low"
