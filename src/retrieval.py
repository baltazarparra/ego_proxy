"""
Intelligent context retrieval engine.

Combines semantic search, entity-based filtering, and temporal ranking
to retrieve the most relevant past conversations.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .database import AssistantDatabase
from .semantic_search import generate_embedding, embedding_to_bytes, search_conversations

logger = logging.getLogger(__name__)


class ContextRetriever:
    """Retrieve relevant context from conversation history."""

    def __init__(self, database: AssistantDatabase):
        """
        Initialize the context retriever.

        Args:
            database: AssistantDatabase instance
        """
        self.db = database

    def retrieve_relevant_context(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.3,
        time_decay: bool = True,
        time_window_days: Optional[int] = None,
        person_filter: Optional[str] = None,
        topic_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve relevant context for a query using multiple strategies.

        Args:
            query: The user's query or message
            top_k: Number of results to return
            min_similarity: Minimum semantic similarity threshold
            time_decay: Whether to apply time-based decay to scores
            time_window_days: Only consider conversations within this many days
            person_filter: Only include conversations mentioning this person
            topic_filter: Only include conversations about this topic

        Returns:
            List of relevant conversation dictionaries with metadata
        """
        # Get all embeddings from database
        stored_embeddings = self.db.get_embeddings_for_search()
        
        if not stored_embeddings:
            logger.info("No stored embeddings found")
            return []
        
        # Perform semantic search
        semantic_results = search_conversations(
            query,
            stored_embeddings,
            top_k=top_k * 3,  # Get more candidates for filtering/ranking
            min_similarity=min_similarity
        )
        
        if not semantic_results:
            logger.info("No semantically similar conversations found")
            return []
        
        # Retrieve full conversation details with metadata
        conversations = []
        for conv_id, similarity in semantic_results:
            conv = self.db.get_conversation_with_metadata(conv_id)
            if conv:
                conv['similarity'] = similarity
                conversations.append(conv)
        
        # Apply filters
        conversations = self._apply_filters(
            conversations,
            person_filter=person_filter,
            topic_filter=topic_filter,
            time_window_days=time_window_days
        )
        
        # Re-rank with combined scoring
        conversations = self._rerank_results(
            conversations,
            apply_time_decay=time_decay
        )
        
        # Return top k results
        return conversations[:top_k]

    def retrieve_by_person(self, person: str, limit: int = 10) -> List[Dict]:
        """
        Retrieve all conversations mentioning a specific person.

        Args:
            person: Person name to search for
            limit: Maximum number of results

        Returns:
            List of conversation dictionaries
        """
        results = self.db.search_by_people(person, limit=limit)
        logger.debug(f"Found {len(results)} conversations mentioning {person}")
        return results

    def retrieve_by_topic(self, topic: str, limit: int = 10) -> List[Dict]:
        """
        Retrieve conversations about a specific topic.

        Args:
            topic: Topic to search for
            limit: Maximum number of results

        Returns:
            List of conversation dictionaries
        """
        results = self.db.search_by_topic(topic, limit=limit)
        logger.debug(f"Found {len(results)} conversations about {topic}")
        return results

    def retrieve_recent(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """
        Retrieve recent conversations within a time window.

        Args:
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of conversation dictionaries
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        conversations = self.db.get_conversations(
            limit=limit,
            start_date=start_date,
            end_date=end_date
        )
        
        logger.debug(f"Found {len(conversations)} conversations in last {days} days")
        return conversations

    def retrieve_timeline(
        self,
        person: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Retrieve chronological timeline of conversations.

        Args:
            person: Optional person filter
            limit: Maximum number of conversations

        Returns:
            List of conversations in chronological order
        """
        if person:
            conversations = self.retrieve_by_person(person, limit=limit)
        else:
            conversations = self.db.get_conversations(limit=limit)
        
        # Sort by timestamp (oldest first for timeline)
        conversations.sort(key=lambda x: x.get('timestamp', ''))
        
        return conversations

    def _apply_filters(
        self,
        conversations: List[Dict],
        person_filter: Optional[str] = None,
        topic_filter: Optional[str] = None,
        time_window_days: Optional[int] = None
    ) -> List[Dict]:
        """
        Apply filters to conversation results.

        Args:
            conversations: List of conversations to filter
            person_filter: Filter by person
            topic_filter: Filter by topic
            time_window_days: Filter by time window

        Returns:
            Filtered list of conversations
        """
        filtered = conversations
        
        # Person filter
        if person_filter:
            person_lower = person_filter.lower()
            filtered = [
                conv for conv in filtered
                if any(person_lower in p.lower() for p in (conv.get('people') or []))
            ]

        # Topic filter
        if topic_filter:
            topic_lower = topic_filter.lower()
            filtered = [
                conv for conv in filtered
                if any(topic_lower in t.lower() for t in (conv.get('topics') or []))
            ]
        
        # Time window filter
        if time_window_days:
            cutoff_date = datetime.now() - timedelta(days=time_window_days)
            filtered = [
                conv for conv in filtered
                if self._parse_timestamp(conv.get('timestamp')) >= cutoff_date
            ]
        
        logger.debug(f"Filtered from {len(conversations)} to {len(filtered)} conversations")
        return filtered

    def _rerank_results(
        self,
        conversations: List[Dict],
        apply_time_decay: bool = True
    ) -> List[Dict]:
        """
        Re-rank results using combined scoring.

        Args:
            conversations: List of conversations with similarity scores
            apply_time_decay: Whether to apply time-based decay

        Returns:
            Re-ranked list of conversations
        """
        for conv in conversations:
            # Base score from semantic similarity
            base_score = conv.get('similarity', 0.5)
            
            # Time decay: recent conversations get higher scores
            time_score = 1.0
            if apply_time_decay:
                timestamp = self._parse_timestamp(conv.get('timestamp'))
                if timestamp:
                    days_ago = (datetime.now() - timestamp).days
                    # Exponential decay: score halves every 30 days
                    time_score = 0.5 ** (days_ago / 30.0)
            
            # Role boost: user messages often more informative
            role_score = 1.1 if conv.get('role') == 'user' else 1.0
            
            # Sentiment boost: emotional content often important
            sentiment = conv.get('sentiment', 'neutral')
            sentiment_score = 1.2 if sentiment in ['negative', 'positive'] else 1.0
            
            # Combined score
            final_score = base_score * time_score * role_score * sentiment_score
            conv['final_score'] = final_score
        
        # Sort by final score
        conversations.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        
        return conversations

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """
        Parse timestamp string to datetime object.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Datetime object or None if parsing fails
        """
        if not timestamp_str:
            return None
        
        try:
            # Try parsing ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            try:
                # Try parsing SQLite format
                return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            except:
                logger.warning(f"Could not parse timestamp: {timestamp_str}")
                return None

    def parse_natural_time_filter(self, query: str) -> Optional[int]:
        """
        Parse natural language time references into days.

        Args:
            query: Query text potentially containing time references

        Returns:
            Number of days or None
        """
        query_lower = query.lower()
        
        # Define time patterns
        time_patterns = {
            'today': 1,
            'yesterday': 2,
            'this week': 7,
            'last week': 14,
            'past week': 7,
            'this month': 30,
            'last month': 60,
            'past month': 30,
            'recent': 7,
            'recently': 7
        }
        
        for pattern, days in time_patterns.items():
            if pattern in query_lower:
                return days
        
        # Check for "last N days/weeks"
        import re
        
        days_match = re.search(r'last (\d+) days?', query_lower)
        if days_match:
            return int(days_match.group(1))
        
        weeks_match = re.search(r'last (\d+) weeks?', query_lower)
        if weeks_match:
            return int(weeks_match.group(1)) * 7
        
        return None

    def smart_retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Intelligently retrieve context with automatic filter detection.

        Args:
            query: User query
            top_k: Number of results to return

        Returns:
            List of relevant conversations
        """
        # Detect time filters from query
        time_window = self.parse_natural_time_filter(query)
        
        # Detect person mentions (capitalized words)
        import re
        potential_people = re.findall(r'\b[A-Z][a-z]+\b', query)
        person_filter = potential_people[0] if potential_people else None
        
        # Retrieve with detected filters
        return self.retrieve_relevant_context(
            query=query,
            top_k=top_k,
            time_window_days=time_window,
            person_filter=person_filter
        )

