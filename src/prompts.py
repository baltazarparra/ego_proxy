"""
Specialized prompts for the personal assistant.

Contains prompt templates for the assistant persona, context injection,
and metadata extraction.
"""

from typing import Dict, List


# Assistant system prompt
ASSISTANT_SYSTEM_PROMPT = """You are a highly capable personal work assistant with perfect memory. Your role is to:

1. **Remember Everything**: You have access to all past conversations and can recall specific details about people, events, tasks, and discussions.

2. **Ask Before Answering**: IMPORTANT - Before providing any advice, suggestions, or substantial answers, you MUST FIRST ask the user to confirm they want that information. Use natural phrasing like:
   - "Did you want to know how to [topic]?"
   - "Would you like me to provide advice on [topic]?"
   - "Would you like me to suggest ways to [action]?"

3. **Two-Step Response Pattern**:
   - First message: Acknowledge what the user said and ask if they want advice/help
   - Wait for confirmation from the user
   - Second message: After user confirms (yes/sure/ok), provide the actual advice/answer
   - Exception: For simple acknowledgments (like "yes", "thanks", "ok") or when user is just logging information, respond naturally without asking for confirmation again

4. **Be Proactive**: When relevant context from past conversations exists, naturally reference it in your responses to provide better advice and continuity.

5. **Be Professional**: Communicate in a clear, helpful, and professional manner. You're like a trusted secretary or executive assistant.

6. **Understand Context**: Use past interactions to understand patterns, relationships, and situations better.

7. **Be Concise**: Provide helpful, actionable advice without unnecessary elaboration unless asked.

When responding:
- Reference past conversations naturally (e.g., "Last time you mentioned Matthew was feeling down...")
- ALWAYS ask for confirmation before providing advice or answers
- After receiving confirmation, provide context-aware suggestions based on history
- Be supportive and helpful

Examples of the two-step pattern:

User: "I'm feeling stressed"
You: "I understand you're feeling stressed. Did you want to know how to reduce stress?"
User: "yes"
You: [Provide stress reduction advice based on context]

User: "I have a meeting with Sarah tomorrow"
You: "I've noted that you have a meeting with Sarah tomorrow. Would you like me to suggest discussion topics or help you prepare?"
User: "no thanks, just wanted to log it"
You: "Understood. I've logged your upcoming meeting with Sarah."

User: "I met with John today about the project"
You: "Thank you for letting me know about your meeting with John. Would you like me to provide any follow-up suggestions?"

You have access to conversation history and can search through past interactions to provide informed responses."""


# Metadata extraction prompt
EXTRACTION_SYSTEM_PROMPT = """You are a metadata extraction assistant. Your job is to analyze conversation messages and extract structured information.

Extract the following from each message:
1. **people**: Names of people mentioned (first names or full names)
2. **topics**: Main topics, activities, or subjects discussed (e.g., "meeting", "pair programming", "code review")
3. **dates_mentioned**: Any temporal references (e.g., "last week", "yesterday", "tomorrow", "last session")
4. **sentiment**: Overall emotional tone (positive, negative, neutral, concerned, excited, frustrated, etc.)
5. **category**: General category (work, meeting, technical, personal, task, planning, etc.)

Return ONLY a valid JSON object with these fields. If a field has no relevant data, use null or an empty array.

Example:
Input: "I will have a pair programming session with Matthew today. Last time he was feeling sad about something."

Output:
{
    "people": ["Matthew"],
    "topics": ["pair programming"],
    "dates_mentioned": "today, last time",
    "sentiment": "concerned",
    "category": "work"
}"""


def create_extraction_prompt(message: str) -> str:
    """
    Create a prompt for extracting metadata from a message.

    Args:
        message: The message to extract metadata from

    Returns:
        Formatted extraction prompt
    """
    return f"""Extract metadata from this message:

"{message}"

Return only valid JSON with fields: people, topics, dates_mentioned, sentiment, category."""


def create_context_injection_prompt(retrieved_contexts: List[Dict], current_query: str) -> str:
    """
    Create a prompt that injects retrieved context into the conversation.

    Args:
        retrieved_contexts: List of relevant past conversations
        current_query: The current user query

    Returns:
        Formatted prompt with context
    """
    if not retrieved_contexts:
        return current_query
    
    context_parts = []
    context_parts.append("Based on your conversation history:\n")
    
    for i, ctx in enumerate(retrieved_contexts[:5], 1):  # Limit to top 5
        timestamp = ctx.get('timestamp', 'Unknown time')
        role = ctx.get('role', 'unknown')
        content = ctx.get('content', '')
        people = ctx.get('people', [])
        topics = ctx.get('topics', [])
        sentiment = ctx.get('sentiment', '')
        
        # Format timestamp if it's a datetime string
        if timestamp and timestamp != 'Unknown time':
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass
        
        context_str = f"[{timestamp}] {role}: {content[:200]}"
        if len(content) > 200:
            context_str += "..."
        
        metadata_parts = []
        if people:
            metadata_parts.append(f"People: {', '.join(people)}")
        if topics:
            metadata_parts.append(f"Topics: {', '.join(topics)}")
        if sentiment:
            metadata_parts.append(f"Sentiment: {sentiment}")
        
        if metadata_parts:
            context_str += f"\n  ({'; '.join(metadata_parts)})"
        
        context_parts.append(f"\n{i}. {context_str}")
    
    context_parts.append("\n\n---\n")
    context_parts.append(f"Current question: {current_query}")
    
    return "".join(context_parts)


def create_timeline_summary(conversations: List[Dict], person: str = None) -> str:
    """
    Create a human-readable timeline summary of conversations.

    Args:
        conversations: List of conversation dictionaries
        person: Optional person to filter by

    Returns:
        Formatted timeline text
    """
    if not conversations:
        return "No conversations found."
    
    title = f"Timeline for {person}" if person else "Conversation Timeline"
    lines = [f"# {title}\n"]
    
    for conv in conversations:
        timestamp = conv.get('timestamp', 'Unknown')
        role = conv.get('role', 'unknown')
        content = conv.get('content', '')
        people = conv.get('people', [])
        topics = conv.get('topics', [])
        
        # Format timestamp
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            timestamp = dt.strftime('%Y-%m-%d %H:%M')
        except:
            pass
        
        lines.append(f"\n## [{timestamp}] {role.title()}")
        lines.append(f"\n{content}\n")
        
        if people or topics:
            metadata = []
            if people:
                metadata.append(f"**People**: {', '.join(people)}")
            if topics:
                metadata.append(f"**Topics**: {', '.join(topics)}")
            lines.append("  " + " | ".join(metadata) + "\n")
        
        lines.append("---")
    
    return "\n".join(lines)


def create_search_results_summary(results: List[Dict], query: str) -> str:
    """
    Create a formatted summary of search results.

    Args:
        results: List of search result dictionaries
        query: The search query

    Returns:
        Formatted search results text
    """
    if not results:
        return f"No results found for: {query}"
    
    lines = [f"# Search Results for: {query}\n"]
    lines.append(f"Found {len(results)} result(s)\n")
    
    for i, result in enumerate(results, 1):
        timestamp = result.get('timestamp', 'Unknown')
        content = result.get('content', '')
        people = result.get('people', [])
        topics = result.get('topics', [])
        similarity = result.get('similarity', 0)
        
        # Format timestamp
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            timestamp = dt.strftime('%Y-%m-%d %H:%M')
        except:
            pass
        
        lines.append(f"\n## {i}. [{timestamp}]")
        if similarity > 0:
            lines.append(f" (Similarity: {similarity:.2%})")
        lines.append("\n")
        
        # Show first 300 chars of content
        display_content = content[:300]
        if len(content) > 300:
            display_content += "..."
        lines.append(f"{display_content}\n")
        
        if people or topics:
            metadata = []
            if people:
                metadata.append(f"**People**: {', '.join(people)}")
            if topics:
                metadata.append(f"**Topics**: {', '.join(topics)}")
            lines.append("  " + " | ".join(metadata) + "\n")
    
    return "\n".join(lines)


def create_stats_summary(stats: Dict) -> str:
    """
    Create a formatted summary of database statistics.

    Args:
        stats: Statistics dictionary from database

    Returns:
        Formatted statistics text
    """
    lines = ["# Personal Assistant Memory Statistics\n"]
    
    lines.append(f"**Total Conversations**: {stats.get('total_conversations', 0)}")
    lines.append(f"**Your Messages**: {stats.get('user_messages', 0)}")
    lines.append(f"**Assistant Responses**: {stats.get('assistant_messages', 0)}")
    lines.append(f"**Stored Embeddings**: {stats.get('embeddings_count', 0)}")
    lines.append(f"**Unique People Mentioned**: {stats.get('unique_people', 0)}")
    lines.append(f"**Unique Topics Discussed**: {stats.get('unique_topics', 0)}\n")
    
    first = stats.get('first_conversation')
    last = stats.get('last_conversation')
    
    if first:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(first.replace('Z', '+00:00'))
            first = dt.strftime('%Y-%m-%d %H:%M')
        except:
            pass
        lines.append(f"**First Conversation**: {first}")
    
    if last:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
            last = dt.strftime('%Y-%m-%d %H:%M')
        except:
            pass
        lines.append(f"**Last Conversation**: {last}")
    
    return "\n".join(lines)

