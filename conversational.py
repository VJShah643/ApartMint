from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()


def summarize_listing_with_llm(listing: Dict[str, Any], user_question: str = "", previous_conversation: str = "") -> str:
    """Use Gemini to generate a natural conversational summary of a listing.
    
    Args:
        listing: normalized listing dict
        user_question: optional user query like "tell me more about this one" or "does it have internet?"
        previous_conversation: previous messages about this listing for context
    
    Returns:
        A 2-4 sentence natural summary highlighting key details, or specific answer to follow-up question.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    if not api_key:
        return _fallback_summary(listing, user_question)
    
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        # Build a concise prompt with key listing fields
        title = listing.get("title") or "This listing"
        city = listing.get("city") or ""
        area = listing.get("area") or ""
        rent = listing.get("rent") or ""
        rooms = listing.get("rooms") or ""
        size = listing.get("size") or ""
        move_in = listing.get("moveIn") or ""
        landlord = listing.get("landlord") or ""
        images_count = len(listing.get("images") or [])
        
        # Description and facilities (may be Swedish or English)
        # Send FULL description, no truncation
        description = listing.get("description") or listing.get("description_en") or ""
        facilities = listing.get("facilities") or listing.get("facilities_en") or []
        
        # Detect if this is a follow-up question (asking specific details, not requesting initial summary)
        is_follow_up = bool(user_question and any(word in user_question.lower() for word in 
            ["does it", "is there", "are there", "what about", "how about", "included", "have",
             "contact", "reach", "get in touch", "landlord", "email", "phone", "call",
             "internet", "water", "electricity", "utilities", "wifi", "parking", 
             "balcony", "elevator", "laundry", "pets", "furnished"]))
        
        if is_follow_up:
            # This is a follow-up question about the listing
            # For follow-ups, we DON'T repeat the summary - just answer the specific question
            prompt = (
                f"You are a helpful apartment search assistant. The user already knows about this listing and is asking a specific follow-up question.\n\n"
                f"CONTEXT (for reference only - do NOT repeat this in your answer):\n"
                f"Listing: {title}\n"
                f"Location: {city}, {area}\n"
                f"Rent: {rent}\n"
                f"Rooms: {rooms}\n"
                f"Size: {size}\n"
                f"Move-in: {move_in}\n"
                f"Landlord: {landlord}\n"
                f"Description: {description}\n"
                f"Facilities: {', '.join(facilities[:20]) if facilities else 'N/A'}\n\n"
                f"User's specific question: '{user_question}'\n\n"
                f"IMPORTANT INSTRUCTIONS:\n"
                f"- Answer ONLY their specific question - do NOT repeat the listing description or summary\n"
                f"- Be direct and concise (1-2 sentences max)\n"
                f"- If they ask HOW to contact the landlord, say 'You can contact {landlord} directly - their contact details should be in the full listing or on the rental platform.'\n"
                f"- If the answer isn't in the listing details above, say \"That's not mentioned in the listing - you'd need to contact {landlord} to find out.\"\n"
                f"- If they ask about specific amenities/features, check the description and facilities list\n"
                f"- Be friendly but brief"
            )
        else:
            # Initial summary request
            prompt = (
                f"You are a friendly apartment search assistant. Summarize this listing in 3-5 sentences for a user. "
                f"Be conversational and highlight important details. Include key points from the description.\n\n"
                f"Listing: {title}\n"
                f"Location: {city}, {area}\n"
                f"Rent: {rent}\n"
                f"Rooms: {rooms}\n"
                f"Size: {size}\n"
                f"Move-in: {move_in}\n"
                f"Landlord: {landlord}\n"
                f"Images: {images_count}\n"
                f"Description: {description}\n"
                f"Facilities: {', '.join(facilities[:20]) if facilities else 'N/A'}\n\n"
            )
            
            if user_question:
                prompt += f"User asked: '{user_question}'\n"
            
            prompt += "Provide a friendly, natural summary."
        
        resp = model.generate_content(prompt)
        text = resp.text if hasattr(resp, "text") else (resp.candidates[0].content.parts[0].text if resp.candidates else "")
        return text.strip() or _fallback_summary(listing, user_question)
    
    except Exception:
        return _fallback_summary(listing, user_question)


def _fallback_summary(listing: Dict[str, Any], user_question: str = "") -> str:
    """Template-based summary if LLM unavailable."""
    title = listing.get("title") or "This apartment"
    city = listing.get("city") or "the area"
    rent = listing.get("rent") or "rent not specified"
    rooms = listing.get("rooms") or "rooms not specified"
    size = listing.get("size") or ""
    move_in = listing.get("moveIn") or "move-in date not specified"
    
    parts = [f"{title} is located in {city}."]
    parts.append(f"It has {rooms}" + (f" and {size}" if size else "") + f", with rent at {rent}.")
    parts.append(f"Available from {move_in}.")
    
    # Include description snippet if available
    description = listing.get("description") or listing.get("description_en") or ""
    if description:
        snippet = description[:400].strip()  # increased from 200 to 400
        if len(description) > 400:
            snippet += "..."
        parts.append(snippet)
    
    facilities = listing.get("facilities") or listing.get("facilities_en") or []
    if facilities:
        parts.append(f"Amenities include: {', '.join(facilities[:8])}.")
    
    return " ".join(parts)


def summarize_results_with_llm(results: list, prefs: Dict[str, Any]) -> str:
    """Generate a 1-2 sentence natural intro summarizing the result set.
    
    Args:
        results: list of normalized listings
        prefs: user preferences dict (city, rooms, budget, etc.)
    
    Returns:
        A friendly summary like 'I found 6 apartments in Uppsala with 2 rooms under 9,000 kr. Most are available in December.'
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    if not api_key or not results:
        return _fallback_result_summary(results, prefs)
    
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        # Build a short summary of the result set
        count = len(results)
        cities = list({r.get("city") for r in results if r.get("city")})
        rents = [r.get("rentNumeric") for r in results if r.get("rentNumeric")]
        avg_rent = int(sum(rents) / len(rents)) if rents else None
        
        # Highlights from top 2
        highlights = []
        for r in results[:2]:
            title = r.get("title") or "A listing"
            move_in = r.get("moveIn") or ""
            highlights.append(f"{title}" + (f" (available {move_in})" if move_in else ""))
        
        prompt = (
            f"You are a friendly apartment search assistant. Write a 1-2 sentence intro summarizing these search results. "
            f"Be warm and conversational.\n\n"
            f"Found {count} apartments.\n"
            f"Cities: {', '.join(cities) if cities else 'various'}\n"
            f"Average rent: {avg_rent} kr/month\n" if avg_rent else ""
            f"User preferences: {prefs}\n"
            f"Top listings: {'; '.join(highlights)}\n\n"
            f"Write a short, friendly intro."
        )
        
        resp = model.generate_content(prompt)
        text = resp.text if hasattr(resp, "text") else (resp.candidates[0].content.parts[0].text if resp.candidates else "")
        return text.strip() or _fallback_result_summary(results, prefs)
    
    except Exception:
        return _fallback_result_summary(results, prefs)


def _fallback_result_summary(results: list, prefs: Dict[str, Any]) -> str:
    """Template-based result summary if LLM unavailable."""
    count = len(results)
    city = prefs.get("city") or "your search area"
    rooms = prefs.get("rooms")
    max_rooms = prefs.get("maxRooms")
    budget = prefs.get("budget")
    
    parts = [f"I found {count} apartment{'s' if count != 1 else ''}"]
    if city:
        parts.append(f"in {city}")
    if rooms and max_rooms and rooms == max_rooms:
        parts.append(f"with exactly {rooms} room{'s' if rooms > 1 else ''}")
    elif rooms and max_rooms:
        parts.append(f"with {rooms}–{max_rooms} rooms")
    elif rooms:
        parts.append(f"with at least {rooms} room{'s' if rooms > 1 else ''}")
    elif max_rooms:
        parts.append(f"with at most {max_rooms} room{'s' if max_rooms > 1 else ''}")
    if budget:
        parts.append(f"under {budget:,} kr/month")
    
    return " ".join(parts) + "."


def generate_greeting_with_llm(message: str = "") -> str:
    """Generate a personalized greeting using LLM.
    
    Args:
        message: User's greeting message (e.g., "hey", "good morning")
    
    Returns:
        A warm, conversational greeting
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    if not api_key:
        return _fallback_greeting()
    
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        prompt = (
            f"You are ApartMint, a friendly apartment search assistant. "
            f"The user just greeted you with: '{message}'\n\n"
            f"Respond with a warm, brief greeting (2-3 sentences) and tell them you can help find apartments in Sweden. "
            f"Mention that they can search by city, budget, number of rooms, and neighborhoods. "
            f"Be conversational and welcoming."
        )
        
        resp = model.generate_content(prompt)
        text = resp.text if hasattr(resp, "text") else (resp.candidates[0].content.parts[0].text if resp.candidates else "")
        return text.strip() or _fallback_greeting()
    
    except Exception:
        return _fallback_greeting()


def _fallback_greeting() -> str:
    """Template-based greeting if LLM unavailable."""
    return (
        "Hey there! 👋 I'm ApartMint, your apartment search assistant. "
        "I can help you find homes across Sweden based on your preferences. "
        "Just tell me what you're looking for — city, budget, number of rooms, or specific neighborhoods!"
    )


def generate_help_with_llm() -> str:
    """Generate a helpful capabilities explanation using LLM.
    
    Returns:
        A conversational explanation of what the bot can do
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    if not api_key:
        return _fallback_help()
    
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        prompt = (
            "You are ApartMint, a friendly apartment search assistant. "
            "Explain what you can do in a conversational, helpful way (4-5 sentences). "
            "Cover these capabilities:\n"
            "- Search apartments by city (Uppsala, Stockholm, etc.)\n"
            "- Filter by number of rooms (e.g., '2 rooms', 'at least 3 rooms')\n"
            "- Filter by monthly rent budget\n"
            "- Search in specific neighborhoods/areas\n"
            "- Remember preferences across the conversation\n"
            "- Provide detailed summaries of specific listings\n"
            "- Handle queries in English or Swedish\n\n"
            "Make it warm and encouraging. Use bullet points or natural paragraphs."
        )
        
        resp = model.generate_content(prompt)
        text = resp.text if hasattr(resp, "text") else (resp.candidates[0].content.parts[0].text if resp.candidates else "")
        return text.strip() or _fallback_help()
    
    except Exception:
        return _fallback_help()


def _fallback_help() -> str:
    """Template-based help if LLM unavailable."""
    return (
        "I can help you find apartments! Here's what I understand:\n\n"
        "🏙️ City: Tell me which city you're interested in (e.g., Uppsala, Stockholm)\n"
        "💰 Budget: Specify your max rent (e.g., 'under 9000 kr')\n"
        "🛏️ Rooms: How many rooms you need (e.g., '2 rooms', 'at least 3 rooms', 'at most 1 room')\n"
        "📍 Areas: Specific neighborhoods (e.g., 'Rosendal', 'Luthagen')\n"
        "🔍 Keywords: Special requirements (e.g., 'balcony', 'student', 'elevator')\n\n"
        "I'll remember your preferences across our conversation, so you can refine your search step by step. "
        "Ask me for 'details on the second listing' to learn more about specific apartments!"
    )


def generate_advisor_response(user_question: str, conversation_history: list = None, broker_listings: list = None) -> Dict[str, Any]:
    """Generate advisor mode response using RAG + LLM.
    
    This is the main advisor mode function that:
    1. Retrieves relevant context from knowledge base
    2. Optionally includes broker mode listings if provided
    3. Builds prompt with context
    4. Generates response with LLM
    5. Returns formatted response with sources
    
    Args:
        user_question: The user's question
        conversation_history: Optional list of previous messages for context
        broker_listings: Optional list of apartment listings from broker mode to reference
    
    Returns:
        Dict with:
            - response: The advisor's response text
            - sources: List of source files consulted
            - suggested_questions: Follow-up questions to suggest
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    
    try:
        # Import RAG system
        from rag_system import get_knowledge_base
        from advisor_prompts import (
            build_advisor_prompt, 
            format_advisor_response_with_sources,
            get_suggested_questions
        )
        
        # Get knowledge base instance
        kb = get_knowledge_base()
        
        # Retrieve relevant context
        retrieved_chunks = kb.retrieve(user_question, n_results=5)
        
        # Format context for LLM
        formatted_context = kb.retrieve_formatted(user_question, n_results=5)
        
        # Add broker listings to context if provided
        if broker_listings and len(broker_listings) > 0:
            listings_context = "\n\n## Available Listings from Recent Search\n\n"
            for idx, listing in enumerate(broker_listings[:10], 1):  # Max 10 listings
                listings_context += f"**Listing {idx}**: {listing.get('title', 'Untitled')}\n"
                listings_context += f"- Location: {listing.get('city', '')}, {listing.get('area', '')}\n"
                listings_context += f"- Rent: {listing.get('rent', 'N/A')}\n"
                listings_context += f"- Rooms: {listing.get('rooms', 'N/A')}\n"
                listings_context += f"- Size: {listing.get('size', 'N/A')}\n"
                listings_context += f"- Move-in: {listing.get('moveIn', 'N/A')}\n"
                listings_context += f"- Landlord: {listing.get('landlord', 'N/A')}\n"
                description = listing.get('description') or listing.get('description_en') or ''
                if description:
                    desc_snippet = description[:200] + '...' if len(description) > 200 else description
                    listings_context += f"- Description: {desc_snippet}\n"
                listings_context += "\n"
            formatted_context += listings_context
        
        # Build full prompt
        full_prompt = build_advisor_prompt(
            user_question=user_question,
            retrieved_context=formatted_context,
            conversation_history=conversation_history
        )
        
        # Generate response with LLM if available
        if api_key:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash-exp")
            
            resp = model.generate_content(full_prompt)
            response_text = resp.text if hasattr(resp, "text") else (
                resp.candidates[0].content.parts[0].text if resp.candidates else ""
            )
        else:
            # Fallback if no API key
            response_text = (
                "I'd love to help with your question, but I need an API key to generate responses. "
                "However, I found relevant information in these sources:\n\n"
            )
            for chunk in retrieved_chunks[:3]:
                response_text += f"**{chunk['section']}** (from {chunk['source_file']})\n\n"
                response_text += chunk['text'][:300] + "...\n\n"
        
        # Format response with sources
        formatted_response = format_advisor_response_with_sources(
            response=response_text.strip(),
            sources=retrieved_chunks
        )
        
        # Get suggested follow-up questions
        suggested = get_suggested_questions(user_question, retrieved_chunks)
        
        return {
            'response': formatted_response['response_with_sources'],
            'sources': formatted_response['sources'],
            'suggested_questions': suggested
        }
    
    except Exception as e:
        # Graceful fallback if RAG system fails
        return {
            'response': (
                f"I apologize, but I encountered an issue accessing my knowledge base. "
                f"Please try switching to Broker Mode to search for apartments, or try your question again. "
                f"(Error: {str(e)})"
            ),
            'sources': [],
            'suggested_questions': [
                "How do I register for Bostadsförmedling?",
                "What are good neighborhoods for students?",
                "What documents do I need for apartment applications?"
            ]
        }
