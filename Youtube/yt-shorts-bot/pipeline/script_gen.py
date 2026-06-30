"""
Phase 1 — Script generation.

Generates a viral-style YouTube Shorts script using Gemini (preferred)
or Groq (fallback) and saves it as a JSON file.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "scripts"
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

SYSTEM_PROMPT = """\
You are an expert YouTube Shorts scriptwriter specialising in viral short-form content.
You always respond with ONLY valid JSON — no markdown fences, no commentary.
"""

SCRIPT_PROMPT = """\
Write a viral YouTube Shorts script about: "{topic}"

CRITICAL word count rule: The "script" field MUST be between 80 and 130 words.
Count every word carefully before responding. A 45-second Short needs ~100 words spoken aloud.

Other rules:
- The hook MUST grab attention in the first 3 seconds (one punchy sentence, max 15 words).
- The script should cover 3-5 distinct tips/points to fill the time — not just 1-2 sentences.
- Write conversational, direct language — no filler phrases like "In today's video..."
- End with a clear call-to-action (e.g. "Follow for more", "Try this today").
- Flag any factual claims that need human verification with [VERIFY].
- visual_keywords: 4-6 short search terms (2-3 words each) describing matching footage.

Respond with ONLY this JSON (no markdown, no explanation):
{{
  "hook": "<one punchy opening sentence, max 15 words>",
  "script": "<full voiceover text including hook, MUST BE 80-130 words — count carefully>",
  "title": "<YouTube Shorts title, max 60 chars, ends with #Shorts>",
  "description": "<2-3 sentence description with #Shorts and relevant hashtags>",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]
}}
"""

STORY_PROMPT = """\
Write a 60-second Hindi short story (kahani) for YouTube Shorts about: "{topic}"

CRITICAL word count rule: The "script" field MUST be between 140 and 170 words.
Hindi speech pace is ~2.3 words/second, so 150 words = ~65 seconds.
Count every word carefully before responding.

Story structure rules:
- hook: Ek aisa pehla sentence jo sunne wale ko rok de — emotional ya suspenseful (max 15 words).
- script: Poori kahani — shuruat (setup), beech (conflict/tension), aur ant (resolution/lesson).
  - Pure Hindi mein likho (Devanagari nahi, Roman Hindi theek hai).
  - Seedhi, simple bhasha use karo — jaise koi dost baat kar raha ho.
  - Ek clear life lesson ya twist ending hona chahiye.
  - MUST BE 140-170 words — count carefully.
- title: Hindi mein YouTube title, max 60 chars, ends with #Shorts
- description: 2-3 sentences Hindi mein, #Shorts aur relevant hashtags ke saath.
- visual_keywords: 4-6 English search terms for matching stock footage (scenes from the story).

Respond with ONLY this JSON (no markdown, no explanation):
{{
  "hook": "<pehla punchy sentence Hindi mein, max 15 words>",
  "script": "<poori kahani Hindi mein, MUST BE 140-170 words>",
  "title": "<Hindi YouTube title, max 60 chars, ends with #Shorts>",
  "description": "<2-3 sentence Hindi description with #Shorts and hashtags>",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "visual_keywords": ["english keyword1", "english keyword2", "english keyword3", "english keyword4"]
}}
"""

FACTS_PROMPT = """\
You are one of the world's best YouTube Shorts scriptwriters with expertise in viral educational content.
Generate a 50–60 second script for a YouTube Shorts video about: "{topic}"

The generated script must be optimized for maximum audience retention, curiosity, and engagement.

Requirements:
Language:
- Natural Roman Hindi (Hinglish)
- Very easy words
- Conversational tone
- No difficult vocabulary
- Sounds like a real human, not AI

Content Rules:
- Every fact must be 100% verified.
- Never invent facts.
- Never repeat common facts.
- Every fact should surprise the viewer.
- Use only interesting and little-known facts.
- No fake statistics.
- No clickbait that cannot be justified.

Retention Rules:
- The first 2 seconds must create instant curiosity.
- Never introduce yourself.
- Never say "Hello Friends".
- Start immediately with suspense.

Example style:
"Tum yakeen nahi karoge..."
"Sirf 1% log ye jaante hain..."
"Ye fact akhir tak dekhna..."

The script must feel like a story instead of reading facts.
Each fact should naturally connect to the next.
Use transition phrases like:
- "Lekin asli surprise abhi baaki hai..."
- "Par ye to kuch bhi nahi..."
- "Aur ab aata hai sabse dangerous fact..."
- "Ab jo sunoge uspar yakeen karna mushkil hai..."

The last fact must be the strongest.

Fact Order:
Fact 7 → Good
Fact 6 → Better
Fact 5 → More shocking
Fact 4 → Even stronger
Fact 3 → Incredible
Fact 2 → Mind blowing
Fact 1 → Impossible to forget

Writing Style:
- Short sentences.
- High energy.
- Curiosity in every line.
- No unnecessary explanations.
- Maximum 2 sentences per fact.
- Every sentence should make viewers want the next one.

End with:
Ask a question that encourages comments.
Example:
"Inme se kaunsa fact tumhe sabse zyada shocking laga?"

Also include:
- Viral Title
- Thumbnail Text
- SEO Description
- 20 SEO Keywords
- 20 Trending Hashtags
- Reliable Sources for every fact.

Output Format (ONLY valid JSON, no markdown formatting fences, no explanations):
{{
  "title": "<Viral Title>",
  "thumbnail": "<Thumbnail Text>",
  "description": "<SEO Description>",
  "script": "<The generated 50-60 second voice-over script, conversational Roman Hindi, 7 facts ordered from 7 to 1, with story-like transitions and ending question>",
  "keywords": ["keyword1", "keyword2", ..., "keyword20"],
  "hashtags": ["hashtag1", "hashtag2", ..., "hashtag20"],
  "sources": ["source for fact 7", "source for fact 6", ..., "source for fact 1"]
}}
"""


def _load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _call_gemini(prompt: str, config: dict) -> str:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set in .env")

    client = genai.Client(api_key=api_key)
    model_name = config.get("llm", {}).get("gemini_model", "gemini-2.0-flash")
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.8,
        ),
    )
    return response.text


def _call_groq(prompt: str, config: dict, messages: list | None = None) -> str:
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set in .env")

    client = Groq(api_key=api_key)
    model_name = config.get("llm", {}).get("groq_model", "llama-3.3-70b-versatile")
    msgs = messages or [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    response = client.chat.completions.create(
        model=model_name,
        messages=msgs,
        temperature=0.8,
    )
    return response.choices[0].message.content


def _extract_json(raw: str) -> dict:
    """Strip markdown fences if the model ignored instructions, then parse."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON output.\n\nRaw response:\n{raw}\n\nError: {exc}"
        ) from exc


def _validate_script(data: dict, style: str = "tips") -> None:
    required = {"hook", "script", "title", "description", "tags", "visual_keywords"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Script JSON is missing required fields: {missing}")

    word_count = len(data["script"].split())
    if style == "story":
        ok = (140 <= word_count <= 180)
        target = "140-180"
    elif style == "facts":
        ok = (100 <= word_count <= 180)
        target = "100-180"
    else:
        ok = (80 <= word_count <= 130)
        target = "80-130"

    if not ok:
        print(
            f"  Warning: script word count is {word_count} "
            f"(target {target}). Check before continuing.",
            file=sys.stderr,
        )


def _expand_prompt(min_words: int, style: str) -> str:
    if style == "story":
        return (
            f"The script you returned is too short (under {min_words} words). "
            f"A 60-second Hindi story needs {min_words}-170 words. "
            f"Please rewrite ONLY the 'script' field — expand the story with more detail, "
            f"dialogue, or emotion. Keep all other fields the same. "
            f"Return the complete updated JSON — nothing else."
        )
    return (
        f"The script you returned is too short (under {min_words} words). "
        f"Please rewrite ONLY the 'script' field so it contains at least {min_words} words "
        f"by adding more tips, examples, or detail. Keep all other fields the same. "
        f"Return the complete updated JSON — nothing else."
    )


def _call_llm(prompt: str, config: dict, provider: str, messages: list | None = None) -> str:
    if provider == "gemini":
        return _call_gemini(prompt, config)
    return _call_groq(prompt, config, messages=messages)


def generate_script(topic: str, style: str = "tips") -> Path:
    """
    Generate a script for *topic* and save to output/scripts/.

    style: "tips"  — viral tips/hacks format, 80-130 words (~45 sec)
           "story" — Hindi narrative story format, 140-170 words (~60 sec)
    """
    config = _load_config()
    effective_topic = topic or config.get("niche", "general tips")

    preferred = config.get("llm", {}).get("preferred", "gemini")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    groq_key = os.environ.get("GROQ_API_KEY", "")

    if preferred == "gemini" and gemini_key:
        provider_used = "gemini"
        model_label = config.get("llm", {}).get("gemini_model", "gemini-2.0-flash")
    elif groq_key:
        provider_used = "groq"
        model_label = config.get("llm", {}).get("groq_model", "llama-3.3-70b-versatile")
    elif gemini_key:
        provider_used = "gemini"
        model_label = config.get("llm", {}).get("gemini_model", "gemini-2.0-flash")
        print("  Preferred provider is Groq but GROQ_API_KEY missing - falling back to Gemini...")
    else:
        raise EnvironmentError(
            "No LLM API key found.\n"
            "Set GEMINI_API_KEY or GROQ_API_KEY in your .env file.\n"
            "Copy .env.example -> .env and fill in at least one key."
        )

    print(f"  Using {provider_used.title()} ({model_label})...")
    print(f"  Style: {style}")

    if style == "story":
        template, min_words = STORY_PROMPT, 140
    elif style == "facts":
        template, min_words = FACTS_PROMPT, 100
    else:
        template, min_words = SCRIPT_PROMPT, 80

    prompt = template.format(topic=effective_topic)
    raw = _call_llm(prompt, config, provider_used)
    data = _extract_json(raw)

    if style == "facts":
        if "tags" not in data:
            data["tags"] = data.get("keywords", []) + data.get("hashtags", [])
        if "visual_keywords" not in data:
            data["visual_keywords"] = data.get("keywords", [])[:8]
        if "hook" not in data:
            script_text = data.get("script", "")
            sentences = re.split(r'[.!?।]\s*', script_text)
            data["hook"] = sentences[0] if sentences else ""

    word_count = len(data.get("script", "").split())
    if word_count < min_words:
        print(f"  Script too short ({word_count} words) - requesting expansion...")
        expand_msg = _expand_prompt(min_words, style)
        expand_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": raw},
            {"role": "user", "content": expand_msg},
        ]
        if provider_used == "groq":
            raw = _call_groq(prompt, config, messages=expand_messages)
        else:
            raw = _call_gemini(expand_msg + "\n\nPrevious JSON:\n" + raw, config)
        data = _extract_json(raw)

        if style == "facts":
            if "tags" not in data:
                data["tags"] = data.get("keywords", []) + data.get("hashtags", [])
            if "visual_keywords" not in data:
                data["visual_keywords"] = data.get("keywords", [])[:8]
            if "hook" not in data:
                script_text = data.get("script", "")
                sentences = re.split(r'[.!?।]\s*', script_text)
                data["hook"] = sentences[0] if sentences else ""

    _validate_script(data, style)

    data["_meta"] = {
        "topic": effective_topic,
        "style": style,
        "provider": provider_used,
        "generated_at": datetime.now().isoformat(),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"{timestamp}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return out_path
