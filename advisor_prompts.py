"""
Advisor mode prompts and response generation.
Uses RAG-retrieved context to provide grounded, educational responses.
"""

# System prompt for advisor mode
ADVISOR_SYSTEM_PROMPT = """You are an expert housing advisor for Sweden, with specialized knowledge of Uppsala and Stockholm. Your role is to provide educational, consultative guidance about finding and securing rental housing.

## Your Expertise
You have deep knowledge about:
- Bostadsförmedling queue systems (Bostad Uppsala, Stockholms Bostadsförmedling, etc.)
- Heimstaden and other private landlords across Sweden
- Student housing options (Studentstaden, AF Bostäder, nations, etc.)
- Queue day strategies and optimization
- Budget planning for renters
- Neighborhood comparisons in Uppsala and Stockholm
- Application strategies and tips
- Swedish rental regulations

## Your Approach
1. **Educational**: Explain concepts thoroughly so users understand the "why" behind advice
2. **Practical**: Provide actionable steps, templates, and specific recommendations
3. **Realistic**: Set honest expectations about timelines, costs, and competition
4. **Empathetic**: Understand that housing search is stressful, be encouraging
5. **Comprehensive**: Cover multiple aspects (budget, location, timeline, strategy)

## Critical Rules
- **ONLY use information from the provided context** (knowledge base sections and any listings mentioned)
- **DO NOT hallucinate or make up information** not in the context
- **If the context doesn't contain relevant information**, say: "I don't have specific information about that in my knowledge base, but I recommend..."
- **Cite sources** when appropriate (e.g., "According to the Bostad process guide...")
- **Be conversational** but professional - you're a friendly expert, not a robot

## Response Structure
1. **Direct answer first**: Address the user's specific question immediately
2. **Context and explanation**: Provide the "why" and background
3. **Practical steps**: Give actionable advice (bullet points, numbered steps)
4. **Additional considerations**: Related tips or warnings
5. **Encouragement**: End with supportive message if appropriate

## Context Awareness
- You are in "Advisor Mode" - primarily consultative and educational
- If user asks to search/filter apartments, remind them to switch to "Broker Mode"
- You CAN reference and analyze apartments from previous search results if provided in context
- Focus on guidance, education, and strategy

Remember: Your goal is to empower users with knowledge so they can make informed decisions about their housing search in Sweden!
"""


def build_advisor_prompt(user_question: str, retrieved_context: str, conversation_history: list = None) -> str:
    """
    Build the full prompt for advisor mode response generation.
    
    Args:
        user_question: The user's question
        retrieved_context: Context retrieved from RAG system
        conversation_history: Optional list of previous messages
        
    Returns:
        Full prompt for the LLM
    """
    prompt = ADVISOR_SYSTEM_PROMPT + "\n\n"
    
    # Add conversation history if available
    if conversation_history and len(conversation_history) > 0:
        prompt += "## Conversation History\n\n"
        for msg in conversation_history[-6:]:  # Last 3 exchanges (6 messages)
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            prompt += f"**{role.capitalize()}**: {content}\n\n"
        prompt += "---\n\n"
    
    # Add retrieved context
    prompt += "## Knowledge Base Context\n\n"
    prompt += retrieved_context
    prompt += "\n\n---\n\n"
    
    # Add current question
    prompt += f"## User's Question\n\n{user_question}\n\n"
    
    # Add instruction
    prompt += """## Your Task

Based on the knowledge base context provided above, answer the user's question thoroughly and helpfully. 

Remember:
- Use ONLY information from the provided context
- Be specific and practical
- Provide actionable advice
- Be encouraging and supportive
- If context doesn't have the answer, acknowledge that clearly

Now, provide your response:"""
    
    return prompt


def format_advisor_response_with_sources(response: str, sources: list) -> dict:
    """
    Format advisor response with source citations.
    
    Args:
        response: The LLM's response text
        sources: List of source dicts from RAG retrieval
        
    Returns:
        Dict with response and sources
    """
    # Extract unique source files
    unique_sources = set()
    for source in sources:
        unique_sources.add(source['source_file'])
    
    # Create source reference
    source_files = {
        'bostad_process.md': 'Bostadsförmedling Queue System Guide',
        'heimstaden_process.md': 'Heimstaden Application Guide',
        'queue_strategies.md': 'Queue Day Optimization Strategies',
        'student_housing.md': 'Student Housing Guide',
        'budget_planning.md': 'Budget Planning for Renters',
        'area_comparisons.md': 'Area & Neighborhood Comparison Guide',
        'application_tips.md': 'Application Tips & Strategies'
    }
    
    sources_text = "\n\n---\n\n**Sources consulted**: "
    source_names = [source_files.get(s, s) for s in unique_sources]
    sources_text += ", ".join(source_names)
    
    return {
        'response': response,
        'sources': list(unique_sources),
        'response_with_sources': response + sources_text
    }


# Sample follow-up questions to suggest to users
SUGGESTED_FOLLOW_UPS = {
    'bostad': [
        "How long does it typically take to get an apartment through Bostadsförmedling?",
        "What are queue days and how do they work?",
        "Can I keep accumulating queue days while living in a Bostadsförmedling apartment?"
    ],
    'heimstaden': [
        "What income do I need to qualify for Heimstaden?",
        "Can CSN count as income for Heimstaden applications?",
        "How long does the Heimstaden application process take?"
    ],
    'student': [
        "What's the difference between student housing organizations and Bostadsförmedling?",
        "Should I register for Bostadsförmedling even as a student?",
        "What are the pros and cons of student corridors?"
    ],
    'budget': [
        "How much should I budget for electricity in Sweden?",
        "What percentage of my income should go to rent?",
        "What are the hidden costs of renting?"
    ],
    'areas': [
        "Which neighborhoods are most affordable in Uppsala?",
        "Which areas in Stockholm are good for students?",
        "What's the difference between central and suburban areas?"
    ],
    'strategy': [
        "How can I increase my chances of getting an apartment?",
        "What's the 'ladder strategy' for housing?",
        "When is the best time to apply for apartments?"
    ],
    'application': [
        "What documents do I need for apartment applications?",
        "How should I write my application message?",
        "How quickly should I respond to listings?"
    ]
}


def get_suggested_questions(user_question: str, sources: list) -> list:
    """
    Suggest relevant follow-up questions based on the user's query and retrieved sources.
    
    Args:
        user_question: The user's original question
        sources: List of source dicts from RAG retrieval
        
    Returns:
        List of suggested follow-up questions (max 3)
    """
    question_lower = user_question.lower()
    
    # Determine topic based on keywords and sources
    suggestions = []
    
    if 'bostad' in question_lower or any('bostad_process' in s['source_file'] for s in sources):
        suggestions.extend(SUGGESTED_FOLLOW_UPS['bostad'])
    
    if 'heimstaden' in question_lower or any('heimstaden_process' in s['source_file'] for s in sources):
        suggestions.extend(SUGGESTED_FOLLOW_UPS['heimstaden'])
    
    if 'student' in question_lower or any('student_housing' in s['source_file'] for s in sources):
        suggestions.extend(SUGGESTED_FOLLOW_UPS['student'])
    
    if 'budget' in question_lower or 'cost' in question_lower or any('budget_planning' in s['source_file'] for s in sources):
        suggestions.extend(SUGGESTED_FOLLOW_UPS['budget'])
    
    if 'area' in question_lower or 'neighborhood' in question_lower or any('area_comparisons' in s['source_file'] for s in sources):
        suggestions.extend(SUGGESTED_FOLLOW_UPS['areas'])
    
    if 'strategy' in question_lower or 'queue' in question_lower or any('queue_strategies' in s['source_file'] for s in sources):
        suggestions.extend(SUGGESTED_FOLLOW_UPS['strategy'])
    
    if 'apply' in question_lower or 'application' in question_lower or any('application_tips' in s['source_file'] for s in sources):
        suggestions.extend(SUGGESTED_FOLLOW_UPS['application'])
    
    # If no specific matches, provide general suggestions
    if not suggestions:
        suggestions = [
            "What are queue days and how do they work?",
            "Which neighborhoods are most affordable?",
            "What documents do I need for apartment applications?"
        ]
    
    # Remove duplicates and return max 3
    unique_suggestions = list(dict.fromkeys(suggestions))
    return unique_suggestions[:3]
