"""
Smart HITL Intervention Algorithm.

Replaces timer-based "ask every N cycles" with a decision function that
considers:
  - agent confidence (0-100) on the current step
  - human_effort   (1-10): how much the user WANTS to be involved
  - human_expertise (1-10): how well the user knows the domain
  - step context:  type of decision, fatigue, recency, confidence trend

Core idea:  intervention_score > dynamic_threshold  →  ask the human.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

# ── Step types that the planner can label ────────────────────────────────────
StepType = Literal[
    "direction",       # choosing what to research / investigate next
    "contradiction",   # conflicting sources — expert can resolve
    "fact_check",      # verifying a specific claim
    "prioritize",      # ranking importance of findings
    "tool_choice",     # which tool or query to use
    "analysis",        # interpreting results
    "synthesis",       # combining information
    "unknown",         # fallback
]

# How much a human adds value for each step type (multiplicative)
STEP_TYPE_WEIGHTS: dict[str, float] = {
    "direction":     1.40,   # user steers the ship
    "contradiction": 1.50,   # expert resolves conflicts
    "fact_check":    1.15,   # expert validates claims
    "prioritize":    1.25,   # user knows what matters to them
    "tool_choice":   0.60,   # agent usually knows best
    "analysis":      1.00,   # neutral
    "synthesis":     0.85,   # agent job
    "unknown":       1.00,
}


# ── Tracker keeps rolling state across steps ─────────────────────────────────

@dataclass
class InterventionTracker:
    """Accumulates state across agent steps within a session."""

    human_effort: int = 5          # 1-10
    human_expertise: int = 5       # 1-10

    interventions_fired: int = 0
    steps_since_last_intervention: int = 0
    total_steps: int = 0

    # Rolling window of last N confidences (for trend detection)
    _confidence_window: list[int] = field(default_factory=list)
    _window_size: int = 6

    # History log for debugging / test harness
    history: list[dict] = field(default_factory=list)

    def record_step(self, confidence: int, step_type: StepType = "unknown") -> dict:
        """
        Record a step and decide whether to intervene.

        Returns a decision dict:
          {
            "should_intervene": bool,
            "score": float,
            "threshold": float,
            "reason": str,       # human-readable explanation
            "step_type": str,
            "confidence": int,
          }
        """
        self.total_steps += 1
        self.steps_since_last_intervention += 1

        # Push into rolling window
        self._confidence_window.append(confidence)
        if len(self._confidence_window) > self._window_size:
            self._confidence_window = self._confidence_window[-self._window_size:]

        decision = compute_intervention(
            confidence=confidence,
            human_effort=self.human_effort,
            human_expertise=self.human_expertise,
            step_type=step_type,
            interventions_so_far=self.interventions_fired,
            steps_since_last=self.steps_since_last_intervention,
            recent_confidences=list(self._confidence_window),
        )

        if decision["should_intervene"]:
            self.interventions_fired += 1
            self.steps_since_last_intervention = 0

        # Log for debugging
        decision["step_number"] = self.total_steps
        self.history.append(decision)
        return decision

    def reset(self):
        """Reset for a new session."""
        self.interventions_fired = 0
        self.steps_since_last_intervention = 0
        self.total_steps = 0
        self._confidence_window.clear()
        self.history.clear()

    def to_dict(self) -> dict:
        return {
            "human_effort": self.human_effort,
            "human_expertise": self.human_expertise,
            "interventions_fired": self.interventions_fired,
            "steps_since_last_intervention": self.steps_since_last_intervention,
            "total_steps": self.total_steps,
            "recent_confidences": list(self._confidence_window),
        }


# ── Core algorithm ───────────────────────────────────────────────────────────

def compute_intervention(
    confidence: int,
    human_effort: int,
    human_expertise: int,
    step_type: StepType = "unknown",
    interventions_so_far: int = 0,
    steps_since_last: int = 0,
    recent_confidences: list[int] | None = None,
) -> dict:
    """
    Pure function.  Decides whether to ask the human right now.

    Returns:
      {
        "should_intervene": bool,
        "score": float,        # 0-1+  (higher = more reason to ask)
        "threshold": float,    # dynamic bar the score must clear
        "reason": str,
      }
    """
    # ── Normalize inputs ────────────────────────────────────────────
    confidence  = max(0, min(100, confidence))
    effort      = max(1, min(10, human_effort))
    expertise   = max(1, min(10, human_expertise))
    uncertainty = (100 - confidence) / 100.0          # 0→1

    effort_norm    = effort / 10.0                    # 0.1→1
    expertise_norm = expertise / 10.0                 # 0.1→1

    # ── How much value would human input add? ───────────────────────
    #   Expertise matters more (user CAN help) vs effort (user WANTS to help)
    #   But even a willing non-expert is useful for direction calls
    input_value = expertise_norm * 0.55 + effort_norm * 0.45

    # ── Base score: uncertainty × input_value ───────────────────────
    score = uncertainty * input_value

    # ── Step type weight ────────────────────────────────────────────
    type_weight = STEP_TYPE_WEIGHTS.get(step_type, 1.0)
    score *= type_weight

    # ── Confidence trend: sustained low confidence boosts urgency ───
    trend_boost = 0.0
    if recent_confidences and len(recent_confidences) >= 3:
        avg_recent = sum(recent_confidences[-3:]) / 3.0
        if avg_recent < 45:
            trend_boost = 0.15        # 3+ steps all below 45 → something is off
        elif avg_recent < 60:
            trend_boost = 0.07
    score += trend_boost

    # ── Dynamic threshold ───────────────────────────────────────────
    base_threshold = 0.35

    # Fatigue: raise bar as we ask more (user gets annoyed)
    fatigue = min(0.25, interventions_so_far * 0.045)

    # Staleness: lower bar if we haven't checked in for a while
    staleness_bonus = min(0.15, steps_since_last * 0.025)

    threshold = base_threshold + fatigue - staleness_bonus

    # ── Hard overrides ──────────────────────────────────────────────
    reason_parts = []

    # 1) Autopilot override: effort ≤ 2 and not critically uncertain
    if effort <= 2 and confidence > 35:
        return {
            "should_intervene": False,
            "score": round(score, 3),
            "threshold": round(threshold, 3),
            "reason": "Autopilot mode (effort≤2, confidence OK)",
            "step_type": step_type,
            "confidence": confidence,
        }

    # 2) Critical uncertainty + expert user → definitely ask
    if confidence < 20 and expertise >= 6:
        score = max(score, 0.85)
        reason_parts.append("critical uncertainty + expert user")

    # 3) Surgical mode: user wants tight control → lower bar
    if effort >= 9:
        threshold = max(0.12, threshold - 0.18)
        reason_parts.append("surgical mode (effort≥9)")

    # 4) Contradiction step with moderate+ expertise → boost
    if step_type == "contradiction" and expertise >= 5:
        score = max(score, score * 1.2)
        reason_parts.append("contradiction needs expert resolution")

    # ── Final decision ──────────────────────────────────────────────
    should = score > threshold

    if should:
        reason = _build_reason(score, threshold, confidence, step_type, reason_parts)
    else:
        reason = f"score {score:.2f} ≤ threshold {threshold:.2f}"

    return {
        "should_intervene": should,
        "score": round(score, 3),
        "threshold": round(threshold, 3),
        "reason": reason,
        "step_type": step_type,
        "confidence": confidence,
    }


def _build_reason(score, threshold, confidence, step_type, extra_parts):
    parts = [f"score {score:.2f} > threshold {threshold:.2f}"]
    if confidence < 40:
        parts.append(f"low confidence ({confidence})")
    if step_type in ("direction", "contradiction", "prioritize"):
        parts.append(f"high-value step type ({step_type})")
    parts.extend(extra_parts)
    return "; ".join(parts)


# ── Convenience: generate the question the agent should ask ──────────────────

def suggest_question_type(step_type: StepType, confidence: int) -> str:
    """Return a hint about what kind of question to ask the user."""
    if step_type == "direction":
        return "Ask which direction to investigate next"
    if step_type == "contradiction":
        return "Present conflicting findings and ask which to trust"
    if step_type == "prioritize":
        return "List options and ask what matters most"
    if step_type == "fact_check":
        return "Present a claim and ask if it matches user's knowledge"
    if confidence < 25:
        return "Explain uncertainty and ask for guidance"
    return "Ask a focused question about the current step"
