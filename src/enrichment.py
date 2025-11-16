"""
Entity extraction and metadata enrichment using LLM.

Uses the loaded language model to extract structured metadata
from conversation messages, including people, topics, sentiment, etc.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from .generator import TextGenerator
from .prompts import EXTRACTION_SYSTEM_PROMPT, create_extraction_prompt

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extract structured metadata from conversation messages using LLM."""

    def __init__(self, generator: TextGenerator):
        """
        Initialize the metadata extractor.

        Args:
            generator: TextGenerator instance for LLM inference
        """
        self.generator = generator

    def extract_metadata(self, message: str, role: str = "user") -> Dict:
        """
        Extract metadata from a conversation message.

        Args:
            message: The message content to analyze
            role: The role of the message sender ('user' or 'assistant')

        Returns:
            Dictionary with extracted metadata
        """
        # Only extract metadata from user messages (assistant messages are responses)
        # But we can still extract some info from assistant messages if needed
        if not message or len(message.strip()) < 5:
            return self._empty_metadata()

        try:
            # Create the extraction prompt
            extraction_request = create_extraction_prompt(message)
            
            # Prepare messages for the LLM
            messages = [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": extraction_request}
            ]
            
            # Generate response with lower temperature for more consistent extraction
            response = self.generator.generate_chat(
                messages,
                max_new_tokens=256,
                temperature=0.1,  # Low temperature for deterministic output
                do_sample=True
            )
            
            # Parse the JSON response
            metadata = self._parse_json_response(response)
            
            # Validate and clean the metadata
            metadata = self._validate_metadata(metadata)
            
            logger.debug(f"Extracted metadata: {metadata}")
            return metadata
            
        except Exception as e:
            logger.warning(f"Could not extract metadata: {e}")
            return self._empty_metadata()

    def _parse_json_response(self, response: str) -> Dict:
        """
        Parse JSON from LLM response, handling common formatting issues.

        Args:
            response: LLM response text

        Returns:
            Parsed JSON dictionary
        """
        # Try to find JSON in the response
        # Sometimes LLMs add explanatory text before/after JSON
        
        # Look for JSON between curly braces
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Try parsing the entire response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse JSON from response: {response[:100]}")
            return self._empty_metadata()

    def _validate_metadata(self, metadata: Dict) -> Dict:
        """
        Validate and clean extracted metadata.

        Args:
            metadata: Raw metadata dictionary

        Returns:
            Cleaned and validated metadata
        """
        validated = {}
        
        # People: ensure it's a list of strings
        people = metadata.get('people', [])
        if isinstance(people, list):
            validated['people'] = [str(p).strip() for p in people if p]
        else:
            validated['people'] = []
        
        # Topics: ensure it's a list of strings
        topics = metadata.get('topics', [])
        if isinstance(topics, list):
            validated['topics'] = [str(t).strip().lower() for t in topics if t]
        else:
            validated['topics'] = []
        
        # Dates mentioned: convert to string
        dates = metadata.get('dates_mentioned', '')
        if dates:
            validated['dates_mentioned'] = str(dates).strip()
        else:
            validated['dates_mentioned'] = None
        
        # Sentiment: ensure it's a string
        sentiment = metadata.get('sentiment', 'neutral')
        if sentiment:
            validated['sentiment'] = str(sentiment).strip().lower()
        else:
            validated['sentiment'] = 'neutral'
        
        # Category: ensure it's a string
        category = metadata.get('category', 'general')
        if category:
            validated['category'] = str(category).strip().lower()
        else:
            validated['category'] = 'general'
        
        return validated

    def _empty_metadata(self) -> Dict:
        """
        Return empty metadata structure.

        Returns:
            Dictionary with empty metadata fields
        """
        return {
            'people': [],
            'topics': [],
            'dates_mentioned': None,
            'sentiment': 'neutral',
            'category': 'general'
        }

    def extract_metadata_simple(self, message: str) -> Dict:
        """
        Extract metadata using simple heuristics without LLM.
        Fallback method if LLM extraction fails or is too slow.

        Args:
            message: Message to analyze

        Returns:
            Dictionary with extracted metadata
        """
        metadata = {
            'people': [],
            'topics': [],
            'dates_mentioned': None,
            'sentiment': 'neutral',
            'category': 'general'
        }
        
        # Simple name detection (capitalized words)
        # This is a naive approach but works for common first names
        name_pattern = r'\b[A-Z][a-z]+\b'
        potential_names = re.findall(name_pattern, message)
        
        # Filter out common words that aren't names
        common_words = {'I', 'The', 'A', 'An', 'This', 'That', 'There', 'Here', 
                       'Today', 'Tomorrow', 'Yesterday', 'Next', 'Last'}
        names = [name for name in potential_names if name not in common_words]
        metadata['people'] = list(set(names))[:5]  # Limit to 5 unique names
        
        # Simple topic detection (common work-related keywords)
        topic_keywords = {
            'meeting': 'meeting',
            'pair': 'pair programming',
            'programming': 'programming',
            'code': 'coding',
            'review': 'code review',
            'bug': 'bug fixing',
            'feature': 'feature development',
            'task': 'task',
            'project': 'project',
            'deadline': 'deadline',
            'presentation': 'presentation',
            'call': 'call',
            'email': 'email'
        }
        
        message_lower = message.lower()
        for keyword, topic in topic_keywords.items():
            if keyword in message_lower:
                metadata['topics'].append(topic)
        
        # Date/time detection
        time_keywords = ['today', 'tomorrow', 'yesterday', 'last week', 'next week',
                        'last time', 'next time', 'this morning', 'this afternoon',
                        'tonight', 'last session', 'next session']
        
        found_dates = [kw for kw in time_keywords if kw in message_lower]
        if found_dates:
            metadata['dates_mentioned'] = ', '.join(found_dates)
        
        # Simple sentiment detection
        positive_words = ['happy', 'good', 'great', 'excellent', 'excited', 'glad']
        negative_words = ['sad', 'bad', 'angry', 'frustrated', 'upset', 'worried', 'concerned']
        
        has_positive = any(word in message_lower for word in positive_words)
        has_negative = any(word in message_lower for word in negative_words)
        
        if has_negative:
            metadata['sentiment'] = 'negative'
        elif has_positive:
            metadata['sentiment'] = 'positive'
        
        # Category detection
        if any(word in message_lower for word in ['meeting', 'call', 'presentation']):
            metadata['category'] = 'meeting'
        elif any(word in message_lower for word in ['code', 'programming', 'bug', 'feature']):
            metadata['category'] = 'technical'
        elif any(word in message_lower for word in ['task', 'deadline', 'project']):
            metadata['category'] = 'task'
        
        return metadata


def extract_metadata_batch(
    generator: TextGenerator,
    messages: List[str]
) -> List[Dict]:
    """
    Extract metadata from multiple messages.

    Args:
        generator: TextGenerator instance
        messages: List of messages to process

    Returns:
        List of metadata dictionaries
    """
    extractor = MetadataExtractor(generator)
    results = []
    
    for message in messages:
        metadata = extractor.extract_metadata(message)
        results.append(metadata)
    
    return results

