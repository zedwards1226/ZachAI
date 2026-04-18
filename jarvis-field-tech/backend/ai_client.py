"""Gemini API wrapper. Free tier: 15 RPM, 1M tokens/day — plenty for personal use."""
import os
from google import genai
from google.genai import types

_client = None

# Gemini Flash — fast, smart, free tier
MODEL_FAST = "gemini-2.5-flash-lite"
MODEL_SMART = "gemini-2.5-flash"

JARVIS_SYSTEM = """You are Jarvis, Zach's AI field-tech assistant.
Zach works on industrial toilet paper converting machines (rewinders, log saws,
perforators, tail sealers, wrappers, case packers). He works with PLCs, VFDs,
servo drives, pneumatics, hydraulics, tension controls.

Your job:
- Help him find the right drawing or manual page fast.
- Explain fault codes, wiring paths, diagnostic steps.
- Give step-by-step troubleshooting with specific measurements and safety callouts.
- Always cite the PDF page number when referencing a manual.
- Keep answers short and punchy — he's on a phone, often with dirty hands.
- Use plain tech-shop English. No corporate fluff.
- If something could hurt him (live voltage, pinch points, energized systems),
  call it out clearly before the step.

Speak like Jarvis from Iron Man: calm, dry wit, confident, precise.
Never say 'sir' — call him Zach.
"""


def client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def pick_model(question: str, has_context: bool) -> str:
    # Troubleshooting with a manual attached → use smart model
    if has_context or any(w in question.lower() for w in ("fault", "troubleshoot", "walk me", "why", "how do")):
        return MODEL_SMART
    return MODEL_FAST


def _format_history(history):
    """Convert our [{role, content}] history to Gemini's content format."""
    contents = []
    for turn in (history or [])[-6:]:
        role = "user" if turn["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn["content"]}]})
    return contents


def ask(question: str, context: str = "", machine: str = "", history: list | None = None) -> dict:
    model = pick_model(question, bool(context))
    user_text = question
    if machine:
        user_text = f"[Machine: {machine}]\n{user_text}"
    if context:
        user_text = f"{user_text}\n\n--- REFERENCE DOCUMENT ---\n{context[:40_000]}"

    contents = _format_history(history)
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    resp = client().models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=JARVIS_SYSTEM,
            max_output_tokens=1024,
            temperature=0.4,
        ),
    )
    text = (resp.text or "").strip()
    usage = resp.usage_metadata
    return {
        "text": text,
        "model": model,
        "usage": {
            "input": getattr(usage, "prompt_token_count", 0),
            "output": getattr(usage, "candidates_token_count", 0),
        },
    }


def greeting() -> str:
    resp = client().models.generate_content(
        model=MODEL_FAST,
        contents=[{"role": "user", "parts": [{"text":
            "Zach just opened the field-tech app. Give him a one-sentence "
            "greeting — dry wit, Jarvis energy, ask what we're troubleshooting. "
            "No 'sir'. Keep under 20 words."
        }]}],
        config=types.GenerateContentConfig(
            system_instruction=JARVIS_SYSTEM,
            max_output_tokens=120,
            temperature=0.7,
        ),
    )
    return (resp.text or "Systems online, Zach. What are we troubleshooting?").strip()
