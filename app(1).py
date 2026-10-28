import json
import os
import sys
from pathlib import Path
from uuid import uuid4
import re
import time
import statistics
import httpx
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="backslashreplace")

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="AI Diet Assistant - Dual-Screen Live Architecture System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 连接你在 Apollo gpu5 上部署的 Gemma 4 31B (通过本地 11434 SSH 隧道)
client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
    api_key="ollama",
    timeout=httpx.Timeout(float(os.getenv("MODEL_TIMEOUT", "120")), connect=5.0),
    max_retries=0,
)
MODEL_ID = os.getenv("MODEL_ID", "gemma4:31b")

MAX_PARALLEL_LLM_CALLS = 1
BATCH_SIZE = 25

with open(BASE_DIR / "dishes_50.json", "r", encoding="utf-8") as f:
    ALL_DISHES = json.load(f)

# Bind supplied artwork by both dish ID and name to prevent accidental swaps.
with open(BASE_DIR / "FoodCompass-Web" / "assets" / "dishes" / "manifest.json", encoding="utf-8") as f:
    image_manifest = json.load(f)
DISH_IMAGES = {entry["id"]: entry for entry in image_manifest}
if len(DISH_IMAGES) != len(image_manifest) or set(DISH_IMAGES) != {d["id"] for d in ALL_DISHES}:
    raise ValueError("Dish image manifest IDs do not match the dataset")
for dish in ALL_DISHES:
    entry = DISH_IMAGES[dish["id"]]
    if entry["name"] != dish["name"]:
        raise ValueError(f"Dish image name mismatch for ID {dish['id']}")
    if not (BASE_DIR / "FoodCompass-Web" / "assets" / entry["image"]).is_file():
        raise ValueError(f"Missing image for dish {dish['id']}")
    dish["image"] = entry["image"]
    dish["image_url"] = "/assets/" + entry["image"]
    dish["image_kind"] = "dish_illustration"
    dish["image_note"] = "Supplied artwork for " + dish["name"]

SESSION_STORE: Dict[str, Any] = {}

# =====================================================================
# 实时架构态势看板全局状态机 (供网页 2 /monitor 实时轮询渲染动画与字幕)
# =====================================================================
def get_initial_monitor_state() -> Dict[str, Any]:
    return {
        "run_id": str(uuid4()),
        "updated_at": time.time(),
        "current_page": 1,
        "subtitle_stream": [
            "Waiting for preferences..."
        ],
        "left_track": {
            "node_l1_restrictions": {"status": "pending", "items": []},
            "node_l2_cuisines": {"status": "pending", "items": []},
            "node_l3_goals": {"status": "pending", "items": []},
            "base_profile_ready": False
        },
        "right_track": {
            "node_r1_prompt1": {
                "status": "pending",
                "pool_a_count": 0,
                "pool_b_count": 0,
                "probes": []
            },
            "node_r2_swipes": {
                "status": "pending",
                "swipes": []  # [{name, category, liked}]
            },
            "node_r3_prompt2": {
                "status": "pending",
                "verdicts": {}
            },
            "dynamic_profile_ready": False
        },
        "fusion_node": {
            "status": "pending",  # pending -> merging -> merged
            "summary": ""
        },
        "dispatch_animation": False,  # 控制合并后的图标向3个专家发射粒子的动画
        "experts_node": {
            "nutrition_expert": {"status": "pending", "batch_1": "pending", "batch_2": "pending", "sample_scores": []},
            "culinary_explorer": {"status": "pending", "batch_1": "pending", "batch_2": "pending", "sample_scores": []},
            "caring_assistant": {"status": "pending", "batch_1": "pending", "batch_2": "pending", "sample_scores": []}
        },
        "consensus_node": {
            "status": "pending",
            "top_dishes": [],
            "price_filter": {"min": 0, "max": 30, "visible_count": 50}
        }
    }

MONITOR_STATE: Dict[str, Any] = get_initial_monitor_state()

def push_subtitle(text: str):
    """向实时字幕流推送最新进度标签"""
    MONITOR_STATE["subtitle_stream"].append(text)
    if len(MONITOR_STATE["subtitle_stream"]) > 12:
        MONITOR_STATE["subtitle_stream"] = MONITOR_STATE["subtitle_stream"][-12:]
    MONITOR_STATE["updated_at"] = time.time()

RESTRICTION_KEYWORDS = {
    "no beef": ["beef"],
    "no eggs": ["egg", "eggs"],
    "no cheese": ["cheese", "cheddar", "mozzarella", "parmesan", "pecorino", "mascarpone", "paneer"],
    "no spicy": ["chili", "gochujang", "spicy"],
    "no pork": ["pork", "bacon", "sausage"],
    "no seafood": ["fish", "cod", "sea bass", "salmon", "shrimp", "clams", "seafood"],
    "no nuts": ["peanuts", "nuts", "almond"],
    "no dairy": ["milk", "cream", "butter", "yogurt", "cheese", "dairy", "paneer", "mozzarella", "cheddar", "parmesan"]
}

# Frontend labels mapped to ingredient keywords in the sample dataset.
RESTRICTION_KEYWORDS.update({
    "nuts": ["peanut", "almond", "cashew", "walnut", "nuts"],
    "peanuts": ["peanut"], "tree nuts": ["almond", "cashew", "walnut", "nuts"],
    "milk": RESTRICTION_KEYWORDS["no dairy"], "eggs": ["egg"],
    "fish": ["fish", "salmon", "cod", "sea bass", "tuna"],
    "shellfish": ["shrimp", "clam", "prawn", "crab", "lobster", "mussel"],
    "wheat": ["wheat", "noodle", "pasta", "bread", "flour", "spaghetti"],
    "soy": ["soy", "tofu", "edamame", "miso"],
    "no meat": ["pork", "beef", "chicken", "duck", "lamb", "bacon", "sausage", "fish", "salmon", "cod", "shrimp", "clam", "sea bass", "tuna"],
    "no spicy food": ["chili", "chilli", "gochujang", "spicy"],
    "no alcohol": ["wine", "beer", "sake", "alcohol"],
    "no coriander": ["coriander", "cilantro"],
})
RESTRICTION_KEYWORDS["vegan"] = RESTRICTION_KEYWORDS["no meat"] + RESTRICTION_KEYWORDS["no dairy"] + ["egg", "honey"]

EXPERT_PROFILES = {
    "nutrition_expert": {
        "id": "agent_1_nutrition",
        "name": "Dr. Nutri (Diet & Health Nutrition Expert)",
        "badge": "🥗 Health & Nutrition Specialist",
        "persona": (
            "You are a rigorous Diet and Health Nutrition Expert (饮食健康营养专家). "
            "You evaluate all 50 dishes primarily through clinical nutrition, metabolic health, "
            "protein-to-calorie ratio, dietary fiber, vegetable/fruit content, and clean cooking methods "
            "(strongly favoring steaming, boiling, grilling, and raw/chilled over deep-frying or heavy cream). "
            "You also check if a dish violates the user's health/dietary restrictions."
        )
    },
    "culinary_explorer": {
        "id": "agent_2_explorer",
        "name": "Chef Nova (Culinary Creativity & Flavor Explorer)",
        "badge": "🌶️ Creative Flavor Explorer",
        "persona": (
            "You are a passionate Culinary Creativity & Exploration Connoisseur (饮食创意探索达人). "
            "You evaluate all 50 dishes based on flavor complexity, cross-cultural excitement, ingredient synergy, "
            "cooking craftsmanship, and dining rating. If the user showed any openness to exploring new flavors or "
            "trying boundary-testing ingredients, you boldly reward exciting and high-rated culinary creations."
        )
    },
    "caring_assistant": {
        "id": "agent_3_assistant",
        "name": "CareBot (Empathetic & High-Obedience Diet Assistant)",
        "badge": "🤝 Caring & Obedient Assistant",
        "persona": (
            "You are a warm, attentive, and strictly obedient Dietary Recommendation Assistant (贴心的服从性高的饮食推荐助手). "
            "Your absolute top priority is 100% faithfulness to the user's merged profile: their exact budget ceiling, "
            "their stated favorite cuisines, and their confirmed attitude toward restricted ingredients (if their restriction "
            "is strict, you heavily penalize dishes containing restricted items; if flexible, you gently allow them)."
        )
    }
}

class InitialProfileRequest(BaseModel):
    language: str = "English"
    restrictions: List[str]
    cuisines: List[str]
    goals: List[str]

class DishChoice(BaseModel):
    dish_id: int
    liked: bool

class FeedbackRequest(BaseModel):
    session_id: Optional[str] = None
    choices: List[DishChoice]

class LiveSyncEvent(BaseModel):
    event_type: str  # "reset" | "page_step" | "single_swipe" | "price_slider"
    page: Optional[int] = None
    restrictions: Optional[List[str]] = None
    cuisines: Optional[List[str]] = None
    goals: Optional[List[str]] = None
    swipe_item: Optional[Dict[str, Any]] = None
    price_filter: Optional[Dict[str, Any]] = None
    swipes: Optional[List[Dict[str, Any]]] = None

def check_dish_restrictions(dish: dict, restrictions: List[str]) -> List[str]:
    violated = []
    ing_str = " ".join(dish["ingredients"]).lower() + " " + dish["name"].lower()
    for r in restrictions:
        r_lower = r.lower().strip()
        keywords = RESTRICTION_KEYWORDS.get(r_lower, [r_lower.replace("no ", "").strip()])
        if any(k in ing_str for k in keywords if k):
            violated.append(r)
    return violated

def extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No valid JSON found in LLM response")

# =====================================================================
# 实时事件同步端点 (让网页 1 的每次点击/滑动实时反映在网页 2 上)
# =====================================================================
@app.post("/api/live-sync")
def handle_live_sync(ev: LiveSyncEvent):
    global MONITOR_STATE
    if ev.event_type == "reset":
        MONITOR_STATE = get_initial_monitor_state()
        return {"status": "reset"}

    if ev.event_type == "probe_reset":
        left_track = MONITOR_STATE["left_track"]
        MONITOR_STATE = get_initial_monitor_state()
        MONITOR_STATE["left_track"] = left_track

    if ev.page is not None:
        MONITOR_STATE["current_page"] = ev.page

    if ev.event_type == "page_step":
        if ev.restrictions is not None:
            MONITOR_STATE["left_track"]["node_l1_restrictions"] = {"status": "done", "items": ev.restrictions}
            push_subtitle(f"🛡️ [Preferences] Dietary restrictions recorded: {', '.join(ev.restrictions) or 'None'}")
        if ev.cuisines is not None:
            MONITOR_STATE["left_track"]["node_l2_cuisines"] = {"status": "done", "items": ev.cuisines}
            push_subtitle(f"🍜 [Preferences] Cuisines recorded: {', '.join(ev.cuisines)}")
        if ev.goals is not None:
            MONITOR_STATE["left_track"]["node_l3_goals"] = {"status": "done", "items": ev.goals}
            MONITOR_STATE["left_track"]["base_profile_ready"] = True
            push_subtitle(f"🎯 [Preferences] Meal goals recorded: {', '.join(ev.goals)} ➔ 🧑‍🌾 Declared preference profile ready.")

    elif ev.event_type == "swipe_snapshot" and ev.swipes is not None:
        swipes = ev.swipes[:5]
        MONITOR_STATE["right_track"]["node_r2_swipes"] = {
            "status": "done" if len(swipes) == 5 else "running" if swipes else "pending",
            "swipes": swipes,
        }
        push_subtitle(f"[Swipe Update] {len(swipes)}/5 probe choices recorded (including any Undo changes).")

    elif ev.event_type == "single_swipe" and ev.swipe_item:
        MONITOR_STATE["right_track"]["node_r2_swipes"]["status"] = "running"
        MONITOR_STATE["right_track"]["node_r2_swipes"]["swipes"].append(ev.swipe_item)
        tag = "🟢 LIKE" if ev.swipe_item.get("liked") else "🔴 DISLIKE"
        push_subtitle(
            f"👆 [Swipe Signal {len(MONITOR_STATE['right_track']['node_r2_swipes']['swipes'])}/5] "
            f"{tag} on '{ev.swipe_item.get('name')}' [{ev.swipe_item.get('category')}]"
        )
        if len(MONITOR_STATE["right_track"]["node_r2_swipes"]["swipes"]) >= 5:
            MONITOR_STATE["right_track"]["node_r2_swipes"]["status"] = "done"

    elif ev.event_type == "price_slider" and ev.price_filter:
        MONITOR_STATE["consensus_node"]["price_filter"] = ev.price_filter
        push_subtitle(
            f"💷 [Active Filters] Budget range £{ev.price_filter['min']} - £{ev.price_filter['max']} "
            f"({ev.price_filter['visible_count']} dishes match current filters)"
        )

    MONITOR_STATE["updated_at"] = time.time()
    return {"status": "synced"}

@app.get("/api/monitor-state")
def get_monitor_state():
    return MONITOR_STATE

# =====================================================================
# Prompt 构建函数
# =====================================================================
def build_prompt_1(profile: dict, safe_dishes: list, boundary_dishes: list) -> str:
    return f"""You are an expert AI Dietary Recommendation Strategist.

### 1. User's Initial Profile
- Dietary Restrictions (Do Not Eat): {json.dumps(profile['restrictions'])}
- Preferred Cuisines: {json.dumps(profile['cuisines'])}
- Dietary Goals: {json.dumps(profile['goals'])}

### 2. Candidate Dish Pools
- **Pool A (Strictly Safe Dishes - All restrictions removed)**:
{json.dumps(safe_dishes, indent=2)}

- **Pool B (Boundary-Testing Dishes - Contains a restricted item to test if the user is willing to make an exception today)**:
{json.dumps(boundary_dishes, indent=2)}

### 3. Your Task (Prompt 1)
Select **EXACTLY 5 dishes** across a strategic diagnostic spectrum to probe the user's exact cravings today:
- **Dish 1 & Dish 2 (Core Budget Anchor)**: From Pool A, matching preferred cuisines & goals at an affordable price (£3.5 - £10.5).
- **Dish 3 (High-Price Quality Probe)**: From Pool A, a higher-priced dish (£13.0 - £28.0) testing high-price acceptance.
- **Dish 4 (Novelty Flavor Probe)**: From Pool A, a dish from a cuisine outside their top preferences, testing willingness to explore new flavors.
- **Dish 5 (Restriction Boundary Probe)**: If Pool B is non-empty, pick 1 dish from Pool B to test if their restriction is flexible today. Otherwise pick from Pool A.

Write all human-readable response values in English. Return ONLY valid JSON:
{{
  "initial_reasoning": "2-3 sentences analyzing the user's cuisines and goals.",
  "selected_dishes": [
    {{
      "dish_id": <int>,
      "probe_category": "<Budget Anchor | High-Price Probe | Novelty Probe | Boundary Probe>",
      "probe_hypothesis": "What we learn if the user swipes RIGHT (Like) vs LEFT (Dislike)."
    }}
  ]
}}"""

def build_prompt_2(profile: dict, prompt1_context: dict, detailed_swipe_results: list) -> str:
    return f"""You are an expert AI Dietary Profiler.

### 1. Context from Step 1 (Initial Profile & Prompt 1 Reasoning)
- Initial Dietary Restrictions: {json.dumps(profile['restrictions'])}
- Initial Preferred Cuisines: {json.dumps(profile['cuisines'])}
- Initial Dietary Goals: {json.dumps(profile['goals'])}
- Prompt 1 Initial Reasoning: {json.dumps(prompt1_context.get('initial_reasoning', ''))}

### 2. User's Explicit Swipe Choices on the 5 Probe Dishes
{json.dumps(detailed_swipe_results, indent=2)}

### 3. Your Task (Prompt 2)
Synthesize the initial profile and the 5 swipe decisions to output the user's inferred current preference analysis.
Write all human-readable response values in English. Return ONLY valid JSON:
{{
  "accepts_high_price_dishes": {{
    "verdict": "<Yes / Moderate / No - Budget Focused>",
    "max_comfortable_price_gbp": <float>,
    "evidence": "Explanation based on price of liked vs disliked dishes."
  }},
  "prioritizes_health_and_wellness": {{
    "verdict": "<High / Balanced / Low - Taste First>",
    "preferred_nutrition_focus": "<e.g., High Protein & Low Calorie / Balanced Macros / Comfort & Satiety>",
    "evidence": "Explanation based on nutritional attributes of liked dishes."
  }},
  "wants_to_explore_new_flavors": {{
    "verdict": "<Adventurous / Selective Explorer / Prefers Familiar Cuisines>",
    "evidence": "Explanation based on novelty probe response."
  }},
  "restriction_flexibility": {{
    "verdict": "<Strictly Enforced / Flexible - Willing to Try Restricted Items Today>",
    "confirmed_hard_restrictions": ["list of items the user still strictly refuses"],
    "softened_restrictions_today": ["list of initially restricted items the user liked or showed openness to today"],
    "evidence": "Explanation based on the boundary probe dish."
  }},
  "refined_today_persona_summary": "A concise 2-3 sentence summary of the user's exact dining mood today."
}}"""

def build_expert_batch_scoring_prompt(
    expert_key: str,
    merged_user_profile: dict,
    dish_batch: list,
    batch_idx: int,
    total_batches: int,
    initial_restrictions: List[str]
) -> str:
    expert = EXPERT_PROFILES[expert_key]
    compact_lines = [
        "ID | Name | Cuisine | Price(£) | Cal | Prot(g) | Veg(g) | Fruit(g) | Weight(g) | Fiber(g) | Method | Period | Role | Rating | Ingredients | Initial_Restriction_Flag"
    ]
    for d in dish_batch:
        violated = check_dish_restrictions(d, initial_restrictions)
        flag_str = f"Contains:{','.join(violated)}" if violated else "None(Safe)"
        line = (
            f"{d['id']} | {d['name']} | {d['cuisine']} | £{d['price']} | {d['calories']}kcal | "
            f"P:{d['protein_g']}g | V:{d['veg_content_g']}g | Fr:{d['fruit_content_g']}g | W:{d['weight_g']}g | Fib:{d['fiber_g']}g | "
            f"{d['cooking_method']} | {'/'.join(d['meal_period'])} | {d['role']} | ★{d['rating']} | "
            f"{','.join(d['ingredients'])} | {flag_str}"
        )
        compact_lines.append(line)
    dishes_table_str = "\n".join(compact_lines)

    return f"""### Expert Role & Persona
{expert['persona']}

### Task Instruction (Batch {batch_idx} of {total_batches} — Scoring {len(dish_batch)} Dishes)
Acting strictly in your persona as **{expert['name']}**, score EVERY dish in this batch ({len(dish_batch)} dishes) based on the user's **Merged Final Profile** below.

### User's Merged Final Profile (Step 8: Initial Setup + Prompt 2 Inferred Preferences)
{json.dumps(merged_user_profile, indent=2)}

### Unified Multi-Attribute Scoring Rules (1 to 10 Scale)
Score EVERY dish below on the exact same **5 Dish Attribute Dimensions** (1 = worst fit, 10 = best fit):
1. **s1_nutrition** (1-10): Based on `calories`, `protein_g`, `fiber_g`, `veg_content_g`, `fruit_content_g`, and `weight_g`.
2. **s2_cooking** (1-10): Based on `cooking_method` and `ingredients` healthiness & quality.
3. **s3_flavor** (1-10): Based on `cuisine`, `rating`, flavor appeal, and alignment with the user's novelty exploration preference.
4. **s4_price** (1-10): Based on `price` (£) relative to the user's `accepts_high_price_dishes` verdict and budget goals.
5. **s5_goal** (1-10): Based on `role`, `meal_period`, `Initial_Restriction_Flag` (penalize heavily if user is Strictly Enforced, or score generously if user is Flexible today), and overall goal fit.

### Dishes Batch ({len(dish_batch)} Dishes)
{dishes_table_str}

### Output Format
Return ONLY valid JSON containing all {len(dish_batch)} dish IDs in this batch:
{{
  "scores": [
    {{
      "id": <int>,
      "s1_nutrition": <float 1-10>,
      "s2_cooking": <float 1-10>,
      "s3_flavor": <float 1-10>,
      "s4_price": <float 1-10>,
      "s5_goal": <float 1-10>,
      "comment": "<Max 10 words in your persona voice>"
    }}
  ]
}}"""

def deterministic_persona_fallback_score(expert_key: str, dish: dict, merged_profile: dict, violated_items: List[str]) -> dict:
    base_prefs = merged_profile.get("initial_base_preferences", {})
    inferred = merged_profile.get("inferred_current_preferences", {})
    max_price = inferred.get("accepts_high_price_dishes", {}).get("max_comfortable_price_gbp", 13.0)
    pref_cuisines = [c.lower() for c in base_prefs.get("cuisine_preferences", [])]
    flex_verdict = inferred.get("restriction_flexibility", {}).get("verdict", "Strictly Enforced")
    is_flexible = "flexible" in flex_verdict.lower()

    s1 = min(10.0, max(2.0, (dish["protein_g"] / 5.0) + (dish["fiber_g"] / 2.5) + (dish["veg_content_g"] / 80.0) - (max(0, dish["calories"] - 550) / 150.0)))
    healthy_methods = {"steaming": 9.5, "boiling": 9.0, "grilling": 8.5, "chilled/raw": 9.0, "whisking": 8.8, "blending": 8.8, "stir-fry": 7.5, "simmering": 7.2, "baking": 7.0, "roasting": 7.8, "deep-fry": 3.0}
    s2 = healthy_methods.get(dish["cooking_method"].lower(), 6.8)
    is_pref_cuisine = dish["cuisine"].lower() in pref_cuisines
    s3 = (dish["rating"] - 4.0) * 8.0 + (2.0 if not is_pref_cuisine and expert_key == "culinary_explorer" else (2.0 if is_pref_cuisine else 0.5))
    s4 = 9.5 if dish["price"] <= max_price else max(2.0, 9.0 - (dish["price"] - max_price) * 0.6)
    s5 = 8.6 if is_pref_cuisine else 6.8
    if violated_items:
        s5 = 6.5 if is_flexible else 1.5

    if expert_key == "nutrition_expert":
        s1 = min(10.0, s1 * 1.1)
        s2 = s2 if s2 > 5 else s2 * 0.7
        if violated_items and not is_flexible:
            s5 = 2.0
        comment = f"Prot {dish['protein_g']}g, {dish['calories']}kcal ({dish['cooking_method']})."
    elif expert_key == "culinary_explorer":
        s3 = min(10.0, s3 + 1.2)
        if violated_items and is_flexible:
            s3 = min(10.0, s3 + 0.8)
            s5 = 8.2
        comment = f"Bold {dish['cuisine']} creation (★{dish['rating']})."
    else:
        s4 = s4 if dish["price"] <= max_price else s4 * 0.6
        if violated_items:
            s5 = 7.0 if is_flexible else 1.0
        comment = f"Restriction:{','.join(violated_items)}" if violated_items else f"Fits £{dish['price']} & profile."

    return {
        "id": dish["id"],
        "s1_nutrition": round(max(1.0, min(10.0, s1)), 1),
        "s2_cooking": round(max(1.0, min(10.0, s2)), 1),
        "s3_flavor": round(max(1.0, min(10.0, s3)), 1),
        "s4_price": round(max(1.0, min(10.0, s4)), 1),
        "s5_goal": round(max(1.0, min(10.0, s5)), 1),
        "comment": comment.strip()
    }

def score_one_batch_job(job_args: dict) -> dict:
    expert_key = job_args["expert_key"]
    batch_idx = job_args["batch_idx"]
    total_batches = job_args["total_batches"]
    dish_batch = job_args["dish_batch"]
    merged_profile = job_args["merged_profile"]
    initial_restrictions = job_args["initial_restrictions"]

    expert_name = EXPERT_PROFILES[expert_key]["name"].split("(")[0].strip()
    MONITOR_STATE["experts_node"][expert_key]["status"] = "running"
    MONITOR_STATE["experts_node"][expert_key][f"batch_{batch_idx}"] = "running"
    push_subtitle(
        f"🧠 [{expert_name}] Evaluating Batch {batch_idx}/{total_batches} "
        f"(Dishes #{dish_batch[0]['id']}~#{dish_batch[-1]['id']}): [Nutrition balance] [Cooking healthiness] [Flavor fit] [Price fit] [Goal alignment]..."
    )

    prompt = build_expert_batch_scoring_prompt(
        expert_key, merged_profile, dish_batch, batch_idx, total_batches, initial_restrictions
    )
    batch_score_map = {}

    try:
        resp = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        parsed = extract_json(resp.choices[0].message.content)
        for item in parsed.get("scores", []):
            did = item.get("id")
            if did is not None:
                batch_score_map[int(did)] = item
    except Exception as e:
        print(f"⚠️ [LLM Warning] Agent='{expert_key}' Batch {batch_idx} error ({e}), using fallback.")

    MONITOR_STATE["experts_node"][expert_key][f"batch_{batch_idx}"] = "done"
    if batch_idx == total_batches:
        MONITOR_STATE["experts_node"][expert_key]["status"] = "done"
    push_subtitle(f"✅ [{expert_name}] Completed Batch {batch_idx}/{total_batches} (25 Dishes × 5 Attributes Scored)")

    return {
        "expert_key": expert_key,
        "batch_idx": batch_idx,
        "prompt": prompt,
        "batch_score_map": batch_score_map
    }

@app.post("/api/step1-probe")
def create_initial_profile_and_probe(req: InitialProfileRequest):
    profile = req.model_dump()

    # 同步更新左轨 3 个节点与原始偏好卡通图标
    MONITOR_STATE["current_page"] = 5
    MONITOR_STATE["left_track"]["node_l1_restrictions"] = {"status": "done", "items": req.restrictions}
    MONITOR_STATE["left_track"]["node_l2_cuisines"] = {"status": "done", "items": req.cuisines}
    MONITOR_STATE["left_track"]["node_l3_goals"] = {"status": "done", "items": req.goals}
    MONITOR_STATE["left_track"]["base_profile_ready"] = True

    safe_dishes = []
    boundary_dishes = []
    for d in ALL_DISHES:
        violated = check_dish_restrictions(d, req.restrictions)
        compact_dish = {
            "id": d["id"], "name": d["name"], "cuisine": d["cuisine"],
            "price": d["price"], "calories": d["calories"], "protein_g": d["protein_g"],
            "fiber_g": d["fiber_g"], "cooking_method": d["cooking_method"],
            "role": d["role"], "ingredients": d["ingredients"]
        }
        if len(violated) == 0:
            safe_dishes.append(compact_dish)
        elif len(violated) == 1:
            compact_dish["violated_restriction"] = violated[0]
            boundary_dishes.append(compact_dish)

    MONITOR_STATE["right_track"]["node_r1_prompt1"] = {
        "status": "running",
        "pool_a_count": len(safe_dishes),
        "pool_b_count": len(boundary_dishes),
        "probes": []
    }
    MONITOR_STATE["right_track"]["node_r2_swipes"] = {"status": "pending", "swipes": []}
    push_subtitle(
        f"🔍 [Probe Selection] Gemma 4 31B scanning {len(safe_dishes)} Safe Dishes + "
        f"{len(boundary_dishes)} Boundary Dishes... Generating [Budget Anchor] [High-Price Probe] [Novelty Probe] [Boundary Probe]..."
    )

    prompt_1 = build_prompt_1(profile, safe_dishes, boundary_dishes[:8])

    try:
        resp = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt_1}],
            temperature=0.3,
        )
        llm_output = extract_json(resp.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ Prompt 1 异常 ({e})，启用启发式探针选择...")
        fallback_picks = (safe_dishes[:4] + (boundary_dishes[:1] if boundary_dishes else safe_dishes[4:5]))[:5]
        default_tags = ["Budget Anchor", "Budget Anchor", "High-Price Probe", "Novelty Probe", "Boundary Probe"]
        llm_output = {
            "initial_reasoning": f"Selected diagnostic probes for cuisines {req.cuisines} and goals {req.goals}.",
            "selected_dishes": [
                {"dish_id": d["id"], "probe_category": default_tags[idx], "probe_hypothesis": "Testing price, health, and flavor boundary."}
                for idx, d in enumerate(fallback_picks)
            ]
        }

    dish_map = {d["id"]: d for d in ALL_DISHES}
    five_dishes = []
    seen_ids = set()
    for item in llm_output.get("selected_dishes", []):
        did = item.get("dish_id")
        if did in dish_map and did not in seen_ids:
            seen_ids.add(did)
            full_dish = dish_map[did].copy()
            full_dish["probe_category"] = item.get("probe_category", "Diagnostic Probe Probe")
            full_dish["probe_hypothesis"] = item.get("probe_hypothesis", "")
            five_dishes.append(full_dish)

    for d in safe_dishes:
        if len(five_dishes) >= 5:
            break
        if d["id"] not in seen_ids:
            seen_ids.add(d["id"])
            full_dish = dish_map[d["id"]].copy()
            full_dish["probe_category"] = "Supplementary Probe"
            full_dish["probe_hypothesis"] = "Testing general preference."
            five_dishes.append(full_dish)

    five_dishes = five_dishes[:5]
    MONITOR_STATE["right_track"]["node_r1_prompt1"]["status"] = "done"
    MONITOR_STATE["right_track"]["node_r1_prompt1"]["probes"] = [
        {"name": d["name"], "price": d["price"], "tag": d["probe_category"]}
        for d in five_dishes
    ]
    tags_str = " | ".join([f"[{d['probe_category']}: {d['name']} £{d['price']}]" for d in five_dishes])
    push_subtitle(f"✅ [Probe Selection] Five probe dishes ready: {tags_str}")

    session_id = str(uuid4())
    SESSION_STORE[session_id] = {
        "initial_profile": profile,
        "prompt_1_output": llm_output,
        "five_dishes": five_dishes
    }

    SESSION_STORE["current"] = SESSION_STORE[session_id]
    return {
        "status": "ok",
        "session_id": session_id,
        "initial_profile": profile,
        "five_dishes": five_dishes
    }

@app.post("/api/step2-finalize-and-rank")
def finalize_profile_and_multi_agent_rank(req: FeedbackRequest):
    session = SESSION_STORE.get(req.session_id or "current")
    if not session:
        raise HTTPException(status_code=400, detail="No active session. Complete steps 1-4 first.")

    expected_ids = {d["id"] for d in session["five_dishes"]}
    if len(req.choices) != len(expected_ids) or {c.dish_id for c in req.choices} != expected_ids:
        raise HTTPException(status_code=422, detail="Submit exactly one choice for every probe dish.")
    initial_restrictions = session["initial_profile"]["restrictions"]
    dish_lookup = {d["id"]: d for d in session["five_dishes"]}
    detailed_choices = []
    liked_restricted_items = []

    for c in req.choices:
        d = dish_lookup.get(c.dish_id)
        if d:
            violated = check_dish_restrictions(d, initial_restrictions)
            if c.liked and violated:
                liked_restricted_items.extend(violated)
            detailed_choices.append({
                "dish_id": d["id"],
                "name": d["name"],
                "cuisine": d["cuisine"],
                "price_gbp": d["price"],
                "calories": d["calories"],
                "protein_g": d["protein_g"],
                "cooking_method": d["cooking_method"],
                "ingredients": d["ingredients"],
                "violated_initial_restrictions": violated,
                "probe_category": d.get("probe_category"),
                "user_decision": "LIKE (Wants to eat)" if c.liked else "DISLIKE (Does not want to eat)"
            })

    # 1. 启动右轨 Node R3 (Prompt 2 潜意识偏好推断)
    MONITOR_STATE["right_track"]["node_r2_swipes"]["status"] = "done"
    MONITOR_STATE["right_track"]["node_r3_prompt2"]["status"] = "running"
    push_subtitle(
        "🔮 [Preference Inference] Analyzing five swipe choices: [Price tolerance] [Health focus] [Flavor curiosity] [Restriction flexibility]..."
    )

    prompt_2 = build_prompt_2(session["initial_profile"], session["prompt_1_output"], detailed_choices)
    try:
        resp = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt_2}],
            temperature=0.2,
        )
        inferred_preferences = extract_json(resp.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ Prompt 2 异常 ({e})，使用结构化推断...")
        liked_dishes = [x for x in detailed_choices if x["user_decision"].startswith("LIKE")]
        max_price = max([x["price_gbp"] for x in liked_dishes], default=12.0)
        is_flex = len(liked_restricted_items) > 0
        inferred_preferences = {
            "accepts_high_price_dishes": {
                "verdict": "Yes" if max_price >= 14.0 else "Moderate",
                "max_comfortable_price_gbp": max_price,
                "evidence": f"Based on swipe choices (max liked price £{max_price})."
            },
            "prioritizes_health_and_wellness": {
                "verdict": "High",
                "preferred_nutrition_focus": "High Protein & Balanced Fiber",
                "evidence": "Aligned with initial health goals and swipe pattern."
            },
            "wants_to_explore_new_flavors": {
                "verdict": "Adventurous" if is_flex else "Selective Explorer",
                "evidence": "Open to high-rated dishes across cuisines."
            },
            "restriction_flexibility": {
                "verdict": "Flexible - Willing to Try Restricted Items Today" if is_flex else "Strictly Enforced",
                "confirmed_hard_restrictions": [r for r in initial_restrictions if r not in liked_restricted_items],
                "softened_restrictions_today": list(set(liked_restricted_items)),
                "evidence": "User swiped LIKE on the boundary-testing dish!" if is_flex else "User rejected restricted items."
            },
            "refined_today_persona_summary": "Seeking a tailored meal across all 50 candidate dishes evaluated by 3 expert agents."
        }

    # 更新右轨完成状态，点亮动态偏好图标 🕵️‍♂️
    MONITOR_STATE["right_track"]["node_r3_prompt2"] = {
        "status": "done",
        "verdicts": {
            "high_price": inferred_preferences.get("accepts_high_price_dishes", {}).get("verdict", "Moderate"),
            "max_price": inferred_preferences.get("accepts_high_price_dishes", {}).get("max_comfortable_price_gbp", 12.0),
            "health_focus": inferred_preferences.get("prioritizes_health_and_wellness", {}).get("verdict", "High"),
            "novelty": inferred_preferences.get("wants_to_explore_new_flavors", {}).get("verdict", "Selective"),
            "restriction_flex": inferred_preferences.get("restriction_flexibility", {}).get("verdict", "Strict")
        }
    }
    MONITOR_STATE["right_track"]["dynamic_profile_ready"] = True
    push_subtitle("🕵️‍♂️ [Preference Inference] Inferred preference profile ready.")

    # =====================================================================
    # 第 8 步：触发双图标碰撞融合动画 (🧑‍🌾 + 🕵️‍♂️ -> 🧬) 并向 3 位专家发射粒子
    # =====================================================================
    merged_final_user_profile = {
        "initial_base_preferences": {
            "dietary_restrictions": initial_restrictions,
            "cuisine_preferences": session["initial_profile"]["cuisines"],
            "dietary_goals": session["initial_profile"]["goals"]
        },
        "inferred_current_preferences": inferred_preferences
    }

    MONITOR_STATE["fusion_node"] = {
        "status": "merged",
        "summary": inferred_preferences.get("refined_today_persona_summary", "Merged Base & Dynamic Preferences.")
    }
    MONITOR_STATE["dispatch_animation"] = True
    push_subtitle("🧬 [Profile Fusion] Declared and inferred preferences combined for specialist review.")

    # =====================================================================
    # 第 10 步：保留全部 50 道菜，分 2 批（每批 25 道）交给 3 个专家 Agent 打分
    # =====================================================================
    dish_batches = [
        ALL_DISHES[i:i + BATCH_SIZE]
        for i in range(0, len(ALL_DISHES), BATCH_SIZE)
    ]
    total_batches = len(dish_batches)

    expert_keys = ["nutrition_expert", "culinary_explorer", "caring_assistant"]
    all_jobs = []
    for ek in expert_keys:
        for b_idx, batch in enumerate(dish_batches, start=1):
            all_jobs.append({
                "expert_key": ek,
                "batch_idx": b_idx,
                "total_batches": total_batches,
                "dish_batch": batch,
                "merged_profile": merged_final_user_profile,
                "initial_restrictions": initial_restrictions
            })

    raw_agent_scores: Dict[str, Dict[int, dict]] = {ek: {} for ek in expert_keys}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_LLM_CALLS) as executor:
        results = list(executor.map(score_one_batch_job, all_jobs))

    for res in results:
        ek = res["expert_key"]
        raw_agent_scores[ek].update(res["batch_score_map"])

    expert_results: Dict[str, Dict[int, Any]] = {ek: {} for ek in expert_keys}
    for ek in expert_keys:
        for d in ALL_DISHES:
            did = d["id"]
            violated = check_dish_restrictions(d, initial_restrictions)
            raw = raw_agent_scores[ek].get(did)
            if not raw or not all(k in raw for k in ("s1_nutrition", "s2_cooking", "s3_flavor", "s4_price", "s5_goal")):
                raw = deterministic_persona_fallback_score(ek, d, merged_final_user_profile, violated)

            attrs = [
                float(raw["s1_nutrition"]),
                float(raw["s2_cooking"]),
                float(raw["s3_flavor"]),
                float(raw["s4_price"]),
                float(raw["s5_goal"]),
            ]
            agent_dish_mean = round(sum(attrs) / 5.0, 2)
            expert_results[ek][did] = {
                "attributes": {
                    "nutrition_balance": round(attrs[0], 1),
                    "cooking_healthiness": round(attrs[1], 1),
                    "flavor_novelty_match": round(attrs[2], 1),
                    "price_value_fit": round(attrs[3], 1),
                    "goal_role_alignment": round(attrs[4], 1),
                },
                "agent_mean_score": agent_dish_mean,
                "comment": raw.get("comment", "Evaluated across all 5 attributes.")
            }

        # 提取每个专家的前 2 个高分样本展示在监控面板上
        top_samples = sorted(
            [{"name": d["name"], "score": expert_results[ek][d["id"]]["agent_mean_score"]} for d in ALL_DISHES],
            key=lambda x: x["score"],
            reverse=True
        )[:2]
        MONITOR_STATE["experts_node"][ek]["sample_scores"] = top_samples

    # =====================================================================
    # 第 11 步：均值-方差风险共识排序 (Score = μ - 0.25 * σ²)
    # =====================================================================
    LAMBDA_PENALTY = 0.25
    ranked_dishes = []

    for d in ALL_DISHES:
        did = d["id"]
        violated = check_dish_restrictions(d, initial_restrictions)
        s_nutri = expert_results["nutrition_expert"][did]
        s_explo = expert_results["culinary_explorer"][did]
        s_assis = expert_results["caring_assistant"][did]

        three_scores = [
            s_nutri["agent_mean_score"],
            s_explo["agent_mean_score"],
            s_assis["agent_mean_score"]
        ]

        mean_score = round(sum(three_scores) / 3.0, 2)
        variance_score = round(statistics.pvariance(three_scores), 3)
        std_dev = round(statistics.pstdev(three_scores), 2)
        consensus_ranking_score = round(mean_score - (LAMBDA_PENALTY * variance_score), 3)

        dish_entry = d.copy()
        dish_entry["violated_restrictions"] = violated
        dish_entry["distance_km"] = round(0.4 + ((did * 7) % 42) * 0.1, 1)
        dish_entry["evaluation"] = {
            "mean_score": mean_score,
            "variance": variance_score,
            "std_dev": std_dev,
            "consensus_ranking_score": consensus_ranking_score,
            "ranking_formula": "Score = Mean - 0.25 * Variance",
            "experts": {
                "nutrition_expert": s_nutri,
                "culinary_explorer": s_explo,
                "caring_assistant": s_assis
            }
        }
        ranked_dishes.append(dish_entry)

    ranked_dishes.sort(
        key=lambda x: (
            x["evaluation"]["consensus_ranking_score"],
            x["evaluation"]["mean_score"],
            -x["evaluation"]["variance"]
        ),
        reverse=True
    )

    all_prices = [d["price"] for d in ranked_dishes]
    MONITOR_STATE["current_page"] = 6
    MONITOR_STATE["consensus_node"] = {
        "status": "done",
        "top_dishes": [
            {
                "rank": idx + 1,
                "name": d["name"],
                "cuisine": d["cuisine"],
                "price": d["price"],
                "consensus": d["evaluation"]["consensus_ranking_score"],
                "mean": d["evaluation"]["mean_score"],
                "variance": d["evaluation"]["variance"]
            }
            for idx, d in enumerate(ranked_dishes[:5])
        ],
        "price_filter": {"min": min(all_prices), "max": max(all_prices), "visible_count": len(ranked_dishes)}
    }
    push_subtitle(
        f"🏆 [Consensus Ranking Ready] Top 1: {ranked_dishes[0]['name']} "
        f"(Score {ranked_dishes[0]['evaluation']['consensus_ranking_score']}, μ={ranked_dishes[0]['evaluation']['mean_score']}, σ²={ranked_dishes[0]['evaluation']['variance']})"
    )

    return {
        "status": "ok",
        "total_dishes_scored": len(ranked_dishes),
        "merged_final_user_profile": merged_final_user_profile,
        "expert_profiles": EXPERT_PROFILES,
        "ranking_rule_explanation": (
            "All 50 dishes are scored on 5 attributes (1-10) in 2 batches of 25 dishes per agent. "
            "We average the 5 attributes per agent, then compute the 3-agent Mean (μ) and Variance (σ²), "
            "ranking all 50 dishes by Consensus Score = μ - 0.25 × σ²."
        ),
        "price_bounds": {"min": min(all_prices), "max": max(all_prices)},
        "ranked_dishes": ranked_dishes
    }

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    with open(BASE_DIR / "FoodCompass-Web" / "index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/monitor.html", response_class=HTMLResponse)
@app.get("/monitor", response_class=HTMLResponse)
def serve_monitor():
    with open(BASE_DIR / "monitor(1).html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/Original.png", include_in_schema=False)
def serve_original_portrait():
    return FileResponse(BASE_DIR / "Original.png", media_type="image/png")

@app.get("/Dynamic.png", include_in_schema=False)
def serve_dynamic_portrait():
    return FileResponse(BASE_DIR / "Dynamic.png", media_type="image/png")

@app.get("/api/dishes")
def get_dishes():
    return {"dishes": ALL_DISHES}

@app.get("/legacy", response_class=HTMLResponse)
def serve_legacy():
    return (BASE_DIR / "index(1).html").read_text(encoding="utf-8")

app.mount("/", StaticFiles(directory=BASE_DIR / "FoodCompass-Web"), name="frontend")
