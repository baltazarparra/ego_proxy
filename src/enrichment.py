"""
Entity extraction and metadata enrichment using LLM.

Uses the loaded language model to extract structured metadata
from conversation messages, including people, topics, sentiment, etc.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import dateutil.tz
from dateutil import parser as dateparser

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
                {"role": "user", "content": extraction_request},
            ]

            # Generate response with lower temperature for more consistent extraction
            response = self.generator.generate_chat(
                messages,
                max_new_tokens=256,
                temperature=0.1,  # Low temperature for deterministic output
                do_sample=True,
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
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)

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
        people = metadata.get("people", [])
        if isinstance(people, list):
            validated["people"] = [str(p).strip() for p in people if p]
        else:
            validated["people"] = []

        # Topics: ensure it's a list of strings
        topics = metadata.get("topics", [])
        if isinstance(topics, list):
            validated["topics"] = [str(t).strip().lower() for t in topics if t]
        else:
            validated["topics"] = []

        # Dates mentioned: convert to string
        dates = metadata.get("dates_mentioned", "")
        if dates:
            validated["dates_mentioned"] = str(dates).strip()
        else:
            validated["dates_mentioned"] = None

        # Sentiment: ensure it's a string
        sentiment = metadata.get("sentiment", "neutral")
        if sentiment:
            validated["sentiment"] = str(sentiment).strip().lower()
        else:
            validated["sentiment"] = "neutral"

        # Category: ensure it's a string
        category = metadata.get("category", "general")
        if category:
            validated["category"] = str(category).strip().lower()
        else:
            validated["category"] = "general"

        return validated

    def _empty_metadata(self) -> Dict:
        """
        Return empty metadata structure.

        Returns:
            Dictionary with empty metadata fields
        """
        return {
            "people": [],
            "topics": [],
            "dates_mentioned": None,
            "sentiment": "neutral",
            "category": "general",
        }

    def detect_calendar_intent(self, message: str) -> Optional[Dict]:
        """
        Detect if message contains a calendar-related request.

        Args:
            message: User message to analyze

        Returns:
            Dictionary with calendar event details if detected, None otherwise
            Format: {
                'intent': 'create_event',
                'summary': str,
                'datetime': datetime,
                'duration_hours': float,
                'description': Optional[str]
            }
        """
        message_lower = message.lower().strip()

        # Calendar intent trigger phrases
        calendar_triggers = [
            "add to my calendar",
            "add on my calendar",
            "add to my agenda",
            "add on my agenda",
            "add to calendar",
            "add on agenda",
            "schedule",
            "create event",
            "add event",
            "add a new event",
            "add an event",
            "new event",
            "put on my calendar",
            "put on calendar",
            "calendar event",
            "set up a meeting",
            "set up meeting",
            "book a meeting",
            "book meeting",
            "add appointment",
            "add a new appointment",
            "add an appointment",
            "create appointment",
            "new appointment",
        ]

        # Check if message contains calendar intent
        has_calendar_intent = any(
            trigger in message_lower for trigger in calendar_triggers
        )

        if not has_calendar_intent:
            logger.debug(f"No calendar intent detected in message: {message[:50]}...")
            return None

        logger.info(f"Calendar intent detected in message: {message[:100]}...")

        try:
            # Extract event details using LLM
            calendar_prompt = f"""Extract calendar event details from this message:
"{message}"

Respond with JSON containing:
- summary: Brief event title (required)
- datetime_description: When the event should happen (e.g., "tomorrow at 3pm", "next Monday at 10am")
- duration_hours: Event duration in hours (default 1.0)
- description: Optional additional details

Example response:
{{"summary": "Meeting with John", "datetime_description": "tomorrow at 3pm", "duration_hours": 1.0, "description": null}}

JSON response:"""

            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts calendar event information. Always respond with valid JSON only.",
                },
                {"role": "user", "content": calendar_prompt},
            ]

            response = self.generator.generate_chat(
                messages, max_new_tokens=150, temperature=0.1, do_sample=True
            )

            # Parse the JSON response
            event_data = self._parse_json_response(response)
            logger.debug(f"Extracted event data: {event_data}")

            if not event_data or "summary" not in event_data:
                logger.warning(
                    f"Could not extract event summary from message. Raw response: {response[:200]}"
                )
                return None

            # Parse datetime from natural language
            datetime_desc = event_data.get("datetime_description", "")
            logger.debug(f"Attempting to parse datetime: {datetime_desc}")
            parsed_datetime = self._parse_natural_datetime(datetime_desc)

            if not parsed_datetime:
                logger.warning(f"Could not parse datetime: {datetime_desc}")
                return None

            logger.info(
                f"Successfully extracted calendar event: {event_data['summary']} at {parsed_datetime}"
            )
            return {
                "intent": "create_event",
                "summary": event_data["summary"],
                "datetime": parsed_datetime,
                "duration_hours": float(event_data.get("duration_hours", 1.0)),
                "description": event_data.get("description"),
            }

        except Exception as e:
            logger.error(f"Error detecting calendar intent: {e}", exc_info=True)
            return None

    def _parse_natural_datetime(self, datetime_str: str) -> Optional[datetime]:
        """
        Parse natural language datetime string to datetime object.

        Args:
            datetime_str: Natural language datetime (e.g., "tomorrow at 3pm")

        Returns:
            datetime object or None if parsing fails
        """
        if not datetime_str:
            return None

        datetime_str = datetime_str.lower().strip()
        now = datetime.now(dateutil.tz.tzlocal())

        try:
            # Handle common relative dates
            if "tomorrow" in datetime_str:
                base_date = now + timedelta(days=1)
                # Extract time if present
                time_part = datetime_str.replace("tomorrow", "").strip()
                if time_part:
                    time_part = time_part.replace("at", "").strip()
                    parsed_time = dateparser.parse(time_part, fuzzy=True)
                    if parsed_time:
                        base_date = base_date.replace(
                            hour=parsed_time.hour,
                            minute=parsed_time.minute,
                            second=0,
                            microsecond=0,
                        )
                else:
                    base_date = base_date.replace(
                        hour=9, minute=0, second=0, microsecond=0
                    )
                return base_date

            elif "today" in datetime_str:
                base_date = now
                time_part = datetime_str.replace("today", "").strip()
                if time_part:
                    time_part = time_part.replace("at", "").strip()
                    parsed_time = dateparser.parse(time_part, fuzzy=True)
                    if parsed_time:
                        base_date = base_date.replace(
                            hour=parsed_time.hour,
                            minute=parsed_time.minute,
                            second=0,
                            microsecond=0,
                        )
                return base_date

            elif "next week" in datetime_str:
                base_date = now + timedelta(days=7)
                base_date = base_date.replace(hour=9, minute=0, second=0, microsecond=0)
                return base_date

            elif (
                "next monday" in datetime_str
                or "next tuesday" in datetime_str
                or "next wednesday" in datetime_str
                or "next thursday" in datetime_str
                or "next friday" in datetime_str
                or "next saturday" in datetime_str
                or "next sunday" in datetime_str
            ):
                # Find next occurrence of the day
                days = [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                ]
                for i, day in enumerate(days):
                    if f"next {day}" in datetime_str:
                        days_ahead = i - now.weekday()
                        if days_ahead <= 0:
                            days_ahead += 7
                        base_date = now + timedelta(days=days_ahead)
                        # Extract time if present
                        time_part = datetime_str.replace(f"next {day}", "").strip()
                        if time_part:
                            time_part = time_part.replace("at", "").strip()
                            parsed_time = dateparser.parse(time_part, fuzzy=True)
                            if parsed_time:
                                base_date = base_date.replace(
                                    hour=parsed_time.hour,
                                    minute=parsed_time.minute,
                                    second=0,
                                    microsecond=0,
                                )
                        else:
                            base_date = base_date.replace(
                                hour=9, minute=0, second=0, microsecond=0
                            )
                        return base_date

            # Try using dateutil parser for other formats
            parsed = dateparser.parse(datetime_str, fuzzy=True)
            if parsed:
                # If no time specified, default to 9 AM
                if (
                    parsed.hour == 0
                    and parsed.minute == 0
                    and "am" not in datetime_str
                    and "pm" not in datetime_str
                    and ":" not in datetime_str
                ):
                    parsed = parsed.replace(hour=9)
                return parsed.replace(tzinfo=dateutil.tz.tzlocal())

            return None

        except Exception as e:
            logger.error(f"Error parsing datetime '{datetime_str}': {e}")
            return None

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
            "people": [],
            "topics": [],
            "dates_mentioned": None,
            "sentiment": "neutral",
            "category": "general",
        }

        # Simple name detection (capitalized words)
        # This is a naive approach but works for common first names
        name_pattern = r"\b[A-Z][a-z]+\b"
        potential_names = re.findall(name_pattern, message)

        # Filter out common words that aren't names
        common_words = {
            "I",
            "The",
            "A",
            "An",
            "This",
            "That",
            "There",
            "Here",
            "Today",
            "Tomorrow",
            "Yesterday",
            "Next",
            "Last",
        }
        names = [name for name in potential_names if name not in common_words]
        metadata["people"] = list(set(names))[:5]  # Limit to 5 unique names

        # Simple topic detection (common work-related keywords)
        topic_keywords = {
            "meeting": "meeting",
            "pair": "pair programming",
            "programming": "programming",
            "code": "coding",
            "review": "code review",
            "bug": "bug fixing",
            "feature": "feature development",
            "task": "task",
            "project": "project",
            "deadline": "deadline",
            "presentation": "presentation",
            "call": "call",
            "email": "email",
        }

        message_lower = message.lower()
        for keyword, topic in topic_keywords.items():
            if keyword in message_lower:
                metadata["topics"].append(topic)

        # Date/time detection
        time_keywords = [
            "today",
            "tomorrow",
            "yesterday",
            "last week",
            "next week",
            "last time",
            "next time",
            "this morning",
            "this afternoon",
            "tonight",
            "last session",
            "next session",
        ]

        found_dates = [kw for kw in time_keywords if kw in message_lower]
        if found_dates:
            metadata["dates_mentioned"] = ", ".join(found_dates)

        # Simple sentiment detection
        positive_words = ["happy", "good", "great", "excellent", "excited", "glad"]
        negative_words = [
            "sad",
            "bad",
            "angry",
            "frustrated",
            "upset",
            "worried",
            "concerned",
        ]

        has_positive = any(word in message_lower for word in positive_words)
        has_negative = any(word in message_lower for word in negative_words)

        if has_negative:
            metadata["sentiment"] = "negative"
        elif has_positive:
            metadata["sentiment"] = "positive"

        # Category detection
        if any(word in message_lower for word in ["meeting", "call", "presentation"]):
            metadata["category"] = "meeting"
        elif any(
            word in message_lower for word in ["code", "programming", "bug", "feature"]
        ):
            metadata["category"] = "technical"
        elif any(word in message_lower for word in ["task", "deadline", "project"]):
            metadata["category"] = "task"

        return metadata


def extract_metadata_batch(generator: TextGenerator, messages: List[str]) -> List[Dict]:
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
