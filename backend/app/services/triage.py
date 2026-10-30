"""Deterministic backend triage: relevance, follow-ups, rule-based diagnosis.

No AI calls here. This layer decides whether Groq is needed at all.
"""
import re
from typing import Optional

CAR_KEYWORDS = [
    "car", "vehicle", "auto", "mechanic", "engine", "brake", "tyre", "tire",
    "battery", "alternator", "starter", "radiator", "coolant", "overheat",
    "oil", "gear", "clutch", "transmission", "steering", "suspension",
    "shock", "ac", "air conditioner", "heater", "fuel", "petrol", "diesel",
    "cng", "ev", "electric", "headlight", "taillight", "indicator", "horn",
    "wiper", "mirror", "door", "lock", "key", "remote", "dashboard",
    "warning", "light", "noise", "sound", "vibration", "smoke", "smell",
    "leak", "mileage", "pickup", "start", "crank", "stall", "misfire",
    "knock", "squeal", "grind", "rattle", "puncture", "flat", "tow",
    "jumpstart", "jump start", "breakdown", "rsa", "service", "repair",
    "inspection", "dent", "paint", "bumper", "windshield", "glass",
    "alloy", "wheel", "alignment", "balancing", "exhaust", "catalytic",
    "airbag", "srs",
    "spark", "plug", "timing", "belt", "chain", "pump", "filter",
    "maruti", "hyundai", "tata", "honda", "toyota", "kia", "mahindra",
    "skoda", "volkswagen", "vw", "ford", "chevrolet", "nissan", "renault",
    "mg", "jeep", "swift", "baleno", "creta", "i10", "i20", "nexon",
    "harrier", "safari", "thar", "scorpio", "xuv", "innova", "fortuner",
    "city", "civic", "corolla", "alto", "wagon", "dzire", "venue", "seltos",
    "sonet", "punch", "tiago", "altroz", "verna", "slavia", "virtus",
    "gaadi", "gadi",
]

GREETING_PATTERN = re.compile(
    r"^(hi|hello|hey|namaste|good\s?(morning|afternoon|evening)|yo|hii+)\b",
    re.IGNORECASE,
)
SHORT_GENERIC = re.compile(r"^(ok|thanks|thank you|bye|yes|no|hmm+)\s*$", re.IGNORECASE)

# Symptom patterns -> (key, follow_up_question, diagnosis_template)
SYMPTOM_RULES = [
    {
        "key": "battery_no_start",
        "patterns": ["no start", "not start", "won't start", "wont start", "crank",
                     "clicking", "click sound", "dead battery", "battery"],
        "needs": ["crank_sound", "lights"],
        "follow_up": "When you turn the key (or press start), do you hear a rapid clicking sound, a single click, or complete silence? Do the dashboard lights come on?",
        "diagnosis": {
            "summary": "Battery or starting-system issue is the most likely cause of the no-start condition.",
            "possible_causes": ["Discharged or ageing 12V battery", "Loose/corroded battery terminals", "Failing starter motor or ignition switch"],
            "supporting_symptoms": [],
            "recommended_service": "battery_jumpstart",
            "next_steps": ["Try a jumpstart with proper cable order and 2-minute idle charge", "If it starts, drive 20+ minutes or get the battery load-tested", "If clicking persists, request on-spot battery replacement check"],
            "urgency": "medium",
            "drive_guidance": "Do not keep cranking for more than 10 seconds at a time. If jumpstart fails, do not attempt to push-start an automatic.",
            "safety_warning": "Keep hands away from the fan belt area. Do not smoke near the battery.",
            "inspection_recommended": True,
        },
    },
    {
        "key": "overheating",
        "patterns": ["overheat", "temperature high", "temp gauge", "coolant", "steam", "radiator"],
        "needs": ["steam", "gauge"],
        "follow_up": "Is steam or coolant smell coming from the bonnet, and is the temperature gauge in the red zone? Did the AC stop cooling before this happened?",
        "diagnosis": {
            "summary": "Engine overheating — likely cooling-system fault. Treat as potentially unsafe to drive.",
            "possible_causes": ["Low coolant due to leak", "Stuck thermostat or failed water pump", "Blocked radiator or failed cooling fan"],
            "supporting_symptoms": [],
            "recommended_service": "towing",
            "next_steps": ["Stop in a safe location, switch off the engine and wait 30+ minutes", "Do NOT open the radiator cap while hot", "Request towing/inspection rather than driving further"],
            "urgency": "critical",
            "drive_guidance": "DO NOT DRIVE. Overheating can seize the engine within minutes.",
            "safety_warning": "Hot coolant can cause severe burns. Keep bonnet closed until the engine cools.",
            "inspection_recommended": True,
        },
    },
    {
        "key": "airbag_warning",
        "patterns": ["airbag", "srs", "supplemental restraint"],
        "needs": ["light_state"],
        "follow_up": "Is the SRS/airbag warning light staying on while driving? Have there been any recent impacts, seat removal, or electrical work?",
        "diagnosis": {
            "summary": "SRS/airbag system warning — the safety restraint system needs prompt inspection.",
            "possible_causes": ["Faulty seatbelt pretensioner or airbag sensor", "Loose connector under a seat", "Clock-spring or crash-sensor fault"],
            "supporting_symptoms": [],
            "recommended_service": "general_repair",
            "next_steps": ["Do not ignore a red SRS/airbag light", "Avoid highway driving until the system is checked", "Book an SRS/airbag diagnostic scan"],
            "urgency": "high",
            "drive_guidance": "Airbags may not deploy in a crash. Drive only to a safe place and get the SRS system inspected.",
            "safety_warning": "Do not attempt to repair airbag wiring or remove airbag components yourself.",
            "inspection_recommended": True,
        },
    },
    {
        "key": "flat_tyre",
        "patterns": ["flat tyre", "flat tire", "puncture", "tyre pressure", "tire pressure", "low pressure tyre"],
        "needs": ["spare"],
        "follow_up": "Is the tyre completely flat on the ground, or slowly losing air? Do you have a spare tyre and jack in the car, and where are you parked (safe shoulder or roadside)?",
        "diagnosis": {
            "summary": "Flat tyre / puncture requiring tyre change or puncture repair.",
            "possible_causes": ["Nail/screw puncture", "Sidewall cut or valve leak", "Under-inflation leading to pinch damage"],
            "supporting_symptoms": [],
            "recommended_service": "flat_tyre",
            "next_steps": ["Park on flat ground with hazard lights on", "If a spare and tools are available a mechanic can swap it on-spot", "Otherwise request roadside tyre assistance"],
            "urgency": "high",
            "drive_guidance": "Do not drive on a fully flat tyre — it destroys the rim and is unsafe.",
            "safety_warning": "Never work under a car supported only by a jack. Stay away from traffic side.",
            "inspection_recommended": True,
        },
    },
    {
        "key": "brakes",
        "patterns": ["brake", "braking", "squeal when braking", "grinding brake", "brake pedal", "abs light"],
        "needs": ["noise_type"],
        "follow_up": "Is the braking issue a squealing/grinding noise, a soft/spongy pedal, vibration, or a dashboard brake/ABS warning light?",
        "diagnosis": {
            "summary": "Brake system fault — needs prompt in-person inspection.",
            "possible_causes": ["Worn brake pads", "Low brake fluid or air in lines", "Warped rotor or faulty ABS sensor"],
            "supporting_symptoms": [],
            "recommended_service": "general_repair",
            "next_steps": ["Check brake fluid level only if you know how", "Drive slowly to the nearest safe stop using engine braking", "Request mechanic inspection before highway driving"],
            "urgency": "critical",
            "drive_guidance": "DO NOT DRIVE at speed. Brakes are safety-critical — tow if the pedal sinks to the floor.",
            "safety_warning": "If braking feels unsafe, stop immediately in a safe place and call roadside assistance.",
            "inspection_recommended": True,
        },
    },
    {
        "key": "fuel_empty",
        "patterns": ["fuel", "petrol finished", "diesel finished", "out of fuel", "empty tank", "reserve"],
        "needs": ["location"],
        "follow_up": "Are you fully out of fuel and stranded, or just on low reserve? Please share your safe parking location so fuel delivery can reach you.",
        "diagnosis": {
            "summary": "Vehicle out of fuel — fuel delivery required.",
            "possible_causes": ["Empty fuel tank", "Faulty fuel gauge reading"],
            "supporting_symptoms": [],
            "recommended_service": "fuel_delivery",
            "next_steps": ["Switch off engine, turn on hazards", "Share live location for fuel delivery", "After refuel, crank in short bursts"],
            "urgency": "medium",
            "drive_guidance": "Do not attempt to drive on an empty tank — it can damage the fuel pump.",
            "safety_warning": "Do not carry loose fuel in unsafe containers.",
            "inspection_recommended": False,
        },
    },
    {
        "key": "key_lockout",
        "patterns": ["locked out", "lockout", "keys inside", "key locked", "lost key", "key not working"],
        "needs": ["spare_key"],
        "follow_up": "Are the keys visibly locked inside the car, lost, or is the remote/battery not working? Is there a spare key someone can bring?",
        "diagnosis": {
            "summary": "Vehicle access issue — key lockout or key failure.",
            "possible_causes": ["Keys locked inside", "Dead key-fob battery", "Faulty door lock actuator"],
            "supporting_symptoms": [],
            "recommended_service": "key_lockout",
            "next_steps": ["Confirm ownership documents are available", "Request key-lockout assistance — do not force the door", "Replace fob battery if remote is weak"],
            "urgency": "medium",
            "drive_guidance": "No driving guidance — vehicle is inaccessible.",
            "safety_warning": "Do not break glass unless there is an emergency (child/pet inside in heat).",
            "inspection_recommended": False,
        },
    },
    {
        "key": "engine_noise",
        "patterns": ["knocking", "rattling", "squealing", "grinding noise", "vibration", "engine noise", "belt noise"],
        "needs": ["when"],
        "follow_up": "When does the noise happen — at idle, acceleration, braking, or turning? Is any warning light on, and has engine oil been checked recently?",
        "diagnosis": {
            "summary": "Abnormal engine/chassis noise needing diagnosis. Avoid high-speed driving until inspected.",
            "possible_causes": ["Worn drive belt or pulley", "Low engine oil causing tapping", "Loose heat shield or suspension component"],
            "supporting_symptoms": [],
            "recommended_service": "general_repair",
            "next_steps": ["Note when the noise occurs (idle/accel/turn)", "Check engine oil level on flat ground when cool", "Book an inspection; record a short audio/video clip if safe"],
            "urgency": "high",
            "drive_guidance": "Drive gently to a safe location only. Stop if the noise worsens or a red warning light appears.",
            "safety_warning": "Do not open moving engine covers or touch hot parts.",
            "inspection_recommended": True,
        },
    },
]

UNSAFE_PATTERNS = ["smoke", "fire", "burning smell", "fuel leak", "brake fail", "steering stuck", "steering locked"]


def is_greeting(text: str) -> bool:
    return bool(GREETING_PATTERN.search(text.strip()))


def looks_car_related(text: str) -> bool:
    t = text.lower()
    if is_greeting(text) or SHORT_GENERIC.match(text.strip()):
        return True  # allow conversational openers; handled separately
    return any(k in t for k in CAR_KEYWORDS)


def find_rule(text: str) -> Optional[dict]:
    t = text.lower()
    for rule in SYMPTOM_RULES:
        if any(p in t for p in rule["patterns"]):
            return rule
    return None


def is_unsafe(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in UNSAFE_PATTERNS)


def extract_vehicle_details(text: str) -> dict:
    """Best-effort deterministic extraction of make/model/year mentions."""
    out: dict = {}
    t = text.lower()
    makes = ["maruti", "hyundai", "tata", "honda", "toyota", "kia", "mahindra",
             "skoda", "volkswagen", "vw", "ford", "nissan", "renault", "mg", "jeep"]
    for m in makes:
        if m in t:
            out["vehicle_make"] = m.title() if m != "vw" else "Volkswagen"
            break
    m = re.search(r"\b(19|20)\d{2}\b", text)
    if m:
        out["vehicle_year"] = m.group(0)
    for fuel in ["petrol", "diesel", "cng", "electric", "hybrid"]:
        if fuel in t:
            out["vehicle_fuel"] = fuel
            break
    return out


def missing_vehicle_info(session) -> list:
    missing = []
    if not session.vehicle_make and not session.vehicle_model:
        missing.append("vehicle")
    return missing


def build_follow_up(session, user_text: str, history_count: int) -> dict:
    """Decide next assistant action deterministically.

    Returns dict with keys: action (follow_up|ready|greet|reject), reply, needs_info.
    """
    text = user_text.strip()
    if not text:
        return {"action": "follow_up", "reply": "Please describe your car problem in a few words (e.g. 'car won't start, clicking sound').", "needs_info": ["symptom"]}
    if SHORT_GENERIC.match(text) or is_greeting(text):
        return {
            "action": "greet",
            "reply": "Namaste! I'm IM Buddy, your car assistant. Tell me your car model and what's wrong (sound, light, smell, or situation) and I'll guide you. For emergencies call +91 6392077642.",
            "needs_info": ["vehicle", "symptom"],
        }
    if not looks_car_related(text):
        return {
            "action": "reject",
            "reply": "I can only help with car/mechanical questions (breakdown, noise, warning lights, battery, tyre, towing, fuel, keys). Please describe your car issue, or call +91 6392077642 for roadside help.",
            "needs_info": [],
        }
    rule = find_rule(text)
    if rule:
        return {"action": "follow_up", "reply": rule["follow_up"], "needs_info": rule["needs"], "rule": rule["key"]}
    # Generic car-related but vague: ask for specifics deterministically.
    if len(text.split()) < 5 or history_count < 2:
        q = "Thanks — to help, please share: (1) car make/model/year, (2) what happens and when (sound/light/smell), (3) where you are parked (safe?)."
        if not session.vehicle_make and not session.vehicle_model:
            return {"action": "follow_up", "reply": q, "needs_info": ["vehicle", "symptom_detail", "location"]}
        return {"action": "follow_up", "reply": "Can you add a bit more detail — when does it happen (starting, driving, braking, idle), and is any warning light on?", "needs_info": ["symptom_detail"]}
    return {"action": "ready", "reply": "Thanks, I have enough to prepare a preliminary diagnosis. You can tap 'Get diagnosis' or add more detail.", "needs_info": []}
