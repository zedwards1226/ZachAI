"""Claude API wrapper with Opus/Haiku routing for cost efficiency."""
import os
from anthropic import Anthropic

_client = None

OPUS = "claude-opus-4-7"
HAIKU = "claude-haiku-4-5-20251001"

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
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def pick_model(question: str) -> str:
    """Route simple lookups to Haiku, reasoning to Opus."""
    q = question.lower()
    simple_triggers = ("show", "pull up", "open", "find", "list", "where is")
    if any(q.startswith(t) for t in simple_triggers) and len(q) < 80:
        return HAIKU
    return OPUS


def ask(question: str, context: str = "", machine: str = "", history: list | None = None) -> dict:
    """Ask Jarvis a question with optional PDF context and conversation history."""
    model = pick_model(question)
    messages = []
    if history:
        for turn in history[-6:]:  # last 3 exchanges
            messages.append({"role": turn["role"], "content": turn["content"]})

    user_content = question
    if machine:
        user_content = f"[Machine: {machine}]\n{user_content}"
    if context:
        user_content = f"{user_content}\n\n--- REFERENCE DOCUMENT ---\n{context}"

    messages.append({"role": "user", "content": user_content})

    resp = client().messages.create(
        model=model,
        max_tokens=1024,
        system=JARVIS_SYSTEM,
        messages=messages,
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return {
        "text": text,
        "model": model,
        "usage": {
            "input": resp.usage.input_tokens,
            "output": resp.usage.output_tokens,
        },
    }


def greeting() -> str:
    """One-shot witty greeting on app open."""
    resp = client().messages.create(
        model=HAIKU,
        max_tokens=120,
        system=JARVIS_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                "Zach just opened the field-tech app. Give him a one-sentence "
                "greeting — dry wit, Jarvis energy, ask what we're troubleshooting. "
                "No 'sir'. Keep under 20 words."
            ),
        }],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
