from __future__ import annotations

import os
import re
from typing import Literal, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

IntentType = Literal["greeting", "help", "detail", "search"]


def classify_intent(message: str, conversation_context: str = "") -> Tuple[IntentType, Optional[str]]:
    """Classify user message into intent type using LLM, with regex fallback.
    
    Args:
        message: User's message
        conversation_context: Current conversation context (e.g., "discussing_listing")
    
    Returns: (intent, context)
        - greeting: "hey", "hello", "hi"
        - help: "what can you do", "help", "how does this work"
        - detail: "tell me more about X", "details on the second listing", OR follow-up questions about current listing
        - search: default for apartment search queries
    """
    # Try LLM classification first
    try:
        result = _classify_with_llm(message, conversation_context)
        if result:
            return result
    except Exception:
        pass  # Fall back to regex
    
    # Fallback: regex-based classification
    return _classify_with_regex(message, conversation_context)


def _classify_with_llm(message: str, conversation_context: str = "") -> Optional[Tuple[IntentType, Optional[str]]]:
    """Use Gemini to classify intent."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    if not api_key:
        return None
    
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        context_hint = ""
        if conversation_context == "discussing_listing":
            context_hint = (
                "\n\nIMPORTANT: The user is currently discussing a specific apartment listing. "
                "If their message is a follow-up question about that listing (e.g., asking about features, "
                "utilities, amenities, details) OR if they want to see that listing again (e.g., 'show me again', "
                "'tell me about that one', 'display it'), classify it as 'detail' intent with context='current', NOT 'search'."
            )
        
        prompt = (
            "You are an intent classifier for an apartment search chatbot. "
            "Classify the user message into ONE of these intents:\n\n"
            "1. greeting - User is saying hello, hi, hey, good morning, etc.\n"
            "2. help - User wants to know what you can do, asking for help, capabilities, how to use\n"
            "3. detail - User wants more information about a specific listing OR is asking a follow-up question about the current listing they're discussing\n"
            "4. search - User is searching for apartments (city, budget, rooms, areas, etc.)\n"
            f"{context_hint}\n"
            f"User message: \"{message}\"\n\n"
            "Return ONLY a JSON object: {\"intent\": \"greeting|help|detail|search\", \"context\": \"optional context for detail requests\"}\n"
            "If intent is 'detail', extract the listing reference in context (e.g., 'second', 'Studentstaden 22', '2', or 'current' for follow-up questions)."
        )
        
        resp = model.generate_content(prompt)
        text = resp.text if hasattr(resp, "text") else (resp.candidates[0].content.parts[0].text if resp.candidates else "")
        
        # Parse JSON response
        import json
        text = text.strip()
        # Extract JSON if wrapped in markdown
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        
        data = json.loads(text)
        intent = data.get("intent")
        context = data.get("context")
        
        if intent in ["greeting", "help", "detail", "search"]:
            return (intent, context)  # type: ignore
        
        return None
    
    except Exception:
        return None


def _classify_with_regex(message: str, conversation_context: str = "") -> Tuple[IntentType, Optional[str]]:
    """Regex-based fallback classification."""
    msg_lower = message.lower().strip()
    
    # If we're discussing a listing and the message is a short question, it's likely a follow-up
    if conversation_context == "discussing_listing":
        # Questions about features/utilities or requests to see listing again
        follow_up_patterns = [
            r"\b(does it have|is there|are there|what about|how about)\b",
            r"\b(internet|water|electricity|heating|utilities|included|extra)\b",
            r"\b(balcony|parking|elevator|laundry|pets|furnished)\b",
            r"^(so|and|also|what|when|where|how|why)\s+",
            r"\b(show|tell|describe|display)\s+(me|it|that|this)\s+(again|once more)\b",
            r"\b(that|this|the)\s+(listing|apartment|one|place)\b",
        ]
        for pat in follow_up_patterns:
            if re.search(pat, msg_lower):
                return ("detail", "current")
    
    # Greeting
    greeting_patterns = [
        r"^(hi|hey|hello|good\s+(morning|afternoon|evening))[\s\.,!]*$",
        r"^(hej|hejsan|tjena)[\s\.,!]*$",  # Swedish
    ]
    for pat in greeting_patterns:
        if re.match(pat, msg_lower):
            return ("greeting", None)
    
    # Help / capabilities
    help_patterns = [
        r"what (can|should|do) (i|you)",
        r"what all",
        r"what are you",
        r"who are you",
        r"how (does this|do you|do i) (work|use)",
        r"^\s*help\s*$",
        r"what (is|are) your (feature|capabilit)",
        r"can you help",
        r"tell me (what|how|about)",
        r"explain",
        r"guide me",
        r"vad kan du",  # Swedish "what can you"
        r"how to use",
        r"what to tell",
        r"what information",
    ]
    for pat in help_patterns:
        if re.search(pat, msg_lower):
            return ("help", None)
    
    # Detail request: "tell me more about X", "details on the second", "what about listing 3"
    detail_patterns = [
        r"(tell me more|more info|details|describe|explain).*(about|on|for)\s+(.+)",
        r"what about (the\s+)?(first|second|third|1st|2nd|3rd|\d+)(th)?\s*(listing|one|apartment)?",
        r"(the\s+)?(first|second|third|1st|2nd|3rd|\d+)(th)?\s*(listing|one|apartment)",
    ]
    for pat in detail_patterns:
        m = re.search(pat, msg_lower)
        if m:
            # Extract context: could be listing title, address, or position
            # For simplicity, return the matched group or whole message
            context = m.group(3) if len(m.groups()) >= 3 and m.group(3) else message
            return ("detail", context.strip())
    
    # Default: search
    return ("search", None)
