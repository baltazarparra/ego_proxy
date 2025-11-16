"""
Personal Assistant Chat Interface with Memory.

Enhanced chat interface that automatically stores conversations,
extracts metadata, and retrieves relevant context for intelligent responses.
"""

import argparse
import logging
import sys
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import config
from .database import AssistantDatabase
from .enrichment import MetadataExtractor
from .generator import TextGenerator
from .google_calendar import GoogleCalendarIntegration
from .model_loader import get_model_info, load_tokenizer_and_model
from .prompts import (
    ASSISTANT_SYSTEM_PROMPT,
    create_context_injection_prompt,
    create_search_results_summary,
    create_stats_summary,
    create_timeline_summary,
)
from .retrieval import ContextRetriever
from .semantic_search import embedding_to_bytes, generate_embedding

logger = logging.getLogger(__name__)


class AssistantChatCLI:
    """Personal assistant chat interface with memory and context retrieval."""

    def __init__(
        self,
        generator: TextGenerator,
        db_path: str = "assistant_memory.db",
        max_history: int = 50,
        history_file: str = ".assistant_chat_history",
        session_id: Optional[str] = None,
    ):
        """
        Initialize the assistant chat interface.

        Args:
            generator: TextGenerator instance
            db_path: Path to SQLite database
            max_history: Maximum messages in working memory
            history_file: Path for prompt history
            session_id: Optional session identifier
        """
        self.generator = generator
        self.max_history = max_history
        self.history: List[Dict[str, str]] = []
        self.session_id = session_id or str(uuid.uuid4())

        # Rich console for beautiful output
        self.console = Console()

        # Database for persistent memory
        self.db = AssistantDatabase(db_path)
        self.console.print(f"[cyan]Memory loaded: {db_path}[/cyan]")

        # Metadata extractor
        self.extractor = MetadataExtractor(generator)

        # Context retriever
        self.retriever = ContextRetriever(self.db)

        # Google Calendar integration
        self.calendar = None
        try:
            self.calendar = GoogleCalendarIntegration(self.db.conn)
            # Try to authenticate (will use cached tokens if available)
            if self.calendar.authenticate():
                self.console.print("[green]📅 Google Calendar connected[/green]")
            else:
                self.console.print(
                    "[yellow]📅 Google Calendar not configured (use GOOGLE_CALENDAR_SETUP.md)[/yellow]"
                )
                self.calendar = None
        except Exception as e:
            logger.debug(f"Calendar integration not available: {e}")
            self.calendar = None

        # Prompt Toolkit session
        kb = KeyBindings()

        @kb.add("escape", "enter")
        def _(event):
            """Submit on Meta+Enter (ESC+Enter)"""
            event.current_buffer.validate_and_handle()

        self.session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
            multiline=True,
            enable_history_search=True,
            key_bindings=kb,
        )

        # Add system prompt to working history
        self.history.append({"role": "system", "content": ASSISTANT_SYSTEM_PROMPT})

    def add_message(self, role: str, content: str):
        """Add a message to working memory."""
        self.history.append({"role": role, "content": content})

        # Trim history if too long (keep system prompt)
        if len(self.history) > self.max_history:
            self.history = [self.history[0]] + self.history[-(self.max_history - 1) :]

    def save_conversation(self, role: str, content: str) -> int:
        """
        Save a conversation message to the database.

        Args:
            role: Message role
            content: Message content

        Returns:
            Conversation ID
        """
        conv_id = self.db.add_conversation(
            role=role, content=content, session_id=self.session_id
        )
        logger.debug(f"Saved conversation {conv_id}")
        return conv_id

    def enrich_conversation(self, conversation_id: int, message: str, role: str):
        """
        Extract and save metadata for a conversation asynchronously.

        Args:
            conversation_id: ID of the conversation
            message: Message content
            role: Message role
        """
        try:
            # Extract metadata using LLM
            metadata = self.extractor.extract_metadata(message, role)

            # Generate embedding
            embedding = generate_embedding(message)
            embedding_bytes = embedding_to_bytes(embedding)

            # Save metadata to database
            self.db.add_metadata(
                conversation_id=conversation_id,
                people=metadata.get("people"),
                topics=metadata.get("topics"),
                dates_mentioned=metadata.get("dates_mentioned"),
                sentiment=metadata.get("sentiment"),
                category=metadata.get("category"),
                embedding=embedding_bytes,
            )

            logger.debug(f"Enriched conversation {conversation_id}")
        except Exception as e:
            logger.warning(f"Could not enrich conversation: {e}")

    def _enrich_messages_background(
        self,
        user_conv_id: int,
        user_message: str,
        assistant_conv_id: int,
        assistant_message: str,
    ):
        """
        Enrich both user and assistant messages in background thread.

        This runs asynchronously to avoid blocking the UI while metadata
        extraction and embedding generation happen.

        Args:
            user_conv_id: User conversation ID
            user_message: User message content
            assistant_conv_id: Assistant conversation ID
            assistant_message: Assistant message content
        """
        try:
            self.enrich_conversation(user_conv_id, user_message, "user")
            self.enrich_conversation(assistant_conv_id, assistant_message, "assistant")
        except Exception as e:
            logger.warning(f"Background enrichment failed: {e}")

    def retrieve_context(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Retrieve relevant context for a query.

        Args:
            query: User query
            top_k: Number of results

        Returns:
            List of relevant conversations
        """
        try:
            contexts = self.retriever.smart_retrieve(query, top_k=top_k)
            logger.debug(f"Retrieved {len(contexts)} relevant contexts")
            return contexts
        except Exception as e:
            logger.warning(f"Could not retrieve context: {e}")
            return []

    def reset_history(self):
        """Clear working memory (keep system prompt)."""
        self.history = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}]

    def print_welcome(self):
        """Display welcome message."""
        stats = self.db.get_stats()

        welcome_text = f"""
# 🧠 Personal Assistant with Memory

**Model**: {config.MODEL_ID}
**Device**: {config.get_device()}
**Memory**: {stats["total_conversations"]} conversations stored

I'm your personal work assistant. I remember everything you tell me and can:
- Recall past conversations and context
- Track people, topics, and events
- Provide advice based on your history
- Search through your past interactions

## How to Use

- Type naturally about your work, meetings, tasks, etc.
- Press **Meta+Enter** (ESC then Enter) or **Alt+Enter** to submit
- Press **Ctrl+R** to search command history
- Type `/help` for available commands

I automatically save everything and retrieve relevant context for you.

---
        """
        welcome_panel = Panel(
            Markdown(welcome_text),
            title="[bold blue]Welcome[/bold blue]",
            border_style="blue",
            padding=(1, 2),
        )
        self.console.print(welcome_panel)
        self.console.print()

    def print_help(self):
        """Display help."""
        help_text = """
# 📖 Assistant Commands

| Command | Description |
|---------|-------------|
| `/help`, `/h` | Show this help message |
| `/reset`, `/clear` | Clear working memory (database preserved) |
| `/search <query>` | Search past conversations |
| `/timeline [person]` | Show chronological history |
| `/people` | List all people mentioned |
| `/topics` | List all topics discussed |
| `/stats` | Show memory statistics |
| `/export [file]` | Export current session to markdown |
| `/exit`, `/quit`, `/q` | Exit the assistant |

# ⌨️ Keyboard Shortcuts

- **Meta+Enter** (ESC+Enter) or **Alt+Enter** - Submit message
- **Ctrl+R** - Search command history
- **Ctrl+C** - Cancel current input

# 💡 Tips

- Speak naturally: "I have a meeting with Sarah tomorrow"
- I automatically remember people, topics, dates, and sentiment
- Ask for advice: "What should I discuss with Sarah?"
- Search history: "/search sarah meeting"
        """
        help_panel = Panel(
            Markdown(help_text),
            title="[bold green]Help[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        self.console.print(help_panel)
        self.console.print()

    def handle_command(self, command: str) -> bool:
        """
        Handle special commands.

        Args:
            command: Command string

        Returns:
            True if should exit
        """
        parts = command.lower().strip().split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else None

        if cmd in ["/exit", "/quit", "/q"]:
            self.console.print(
                "\n[yellow]👋 Goodbye! Your memory has been saved.[/yellow]\n"
            )
            return True

        elif cmd in ["/reset", "/clear"]:
            self.reset_history()
            self.console.print(
                "[green]✓ Working memory cleared (database preserved)[/green]\n"
            )
            return False

        elif cmd in ["/help", "/h"]:
            self.print_help()
            return False

        elif cmd == "/search":
            if not args:
                self.console.print("[red]Usage: /search <query>[/red]\n")
            else:
                self._handle_search(args)
            return False

        elif cmd == "/timeline":
            self._handle_timeline(args)
            return False

        elif cmd == "/people":
            self._handle_people()
            return False

        elif cmd == "/topics":
            self._handle_topics()
            return False

        elif cmd == "/stats":
            self._handle_stats()
            return False

        elif cmd == "/export":
            filename = args if args else "assistant_session.md"
            self._export_session(filename)
            return False

        else:
            self.console.print(f"[red]✗ Unknown command: {cmd}[/red]")
            self.console.print("Type [green]/help[/green] for available commands\n")
            return False

    def _handle_search(self, query: str):
        """Handle search command."""
        self.console.print(f"[cyan]Searching for: {query}[/cyan]\n")

        results = self.retrieve_context(query, top_k=10)

        if results:
            summary = create_search_results_summary(results, query)
            panel = Panel(
                Markdown(summary),
                title="[bold cyan]Search Results[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
            self.console.print(panel)
        else:
            self.console.print("[yellow]No results found.[/yellow]")

        self.console.print()

    def _handle_timeline(self, person: Optional[str]):
        """Handle timeline command."""
        if person:
            self.console.print(f"[cyan]Timeline for: {person}[/cyan]\n")
            conversations = self.retriever.retrieve_timeline(person=person, limit=30)
        else:
            self.console.print("[cyan]Recent timeline[/cyan]\n")
            conversations = self.retriever.retrieve_timeline(limit=30)

        if conversations:
            summary = create_timeline_summary(conversations, person)
            panel = Panel(
                Markdown(summary),
                title="[bold cyan]Timeline[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
            self.console.print(panel)
        else:
            self.console.print("[yellow]No conversations found.[/yellow]")

        self.console.print()

    def _handle_people(self):
        """Handle people command."""
        people = self.db.get_all_people()

        if people:
            table = Table(
                title="People Mentioned", show_header=True, header_style="bold magenta"
            )
            table.add_column("Name", style="cyan")

            for person in people:
                table.add_row(person)

            self.console.print(table)
        else:
            self.console.print("[yellow]No people mentioned yet.[/yellow]")

        self.console.print()

    def _handle_topics(self):
        """Handle topics command."""
        topics = self.db.get_all_topics()

        if topics:
            table = Table(
                title="Topics Discussed", show_header=True, header_style="bold magenta"
            )
            table.add_column("Topic", style="cyan")

            for topic in topics:
                table.add_row(topic)

            self.console.print(table)
        else:
            self.console.print("[yellow]No topics tracked yet.[/yellow]")

        self.console.print()

    def _handle_stats(self):
        """Handle stats command."""
        stats = self.db.get_stats()
        summary = create_stats_summary(stats)

        panel = Panel(
            Markdown(summary),
            title="[bold cyan]Memory Statistics[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print(panel)
        self.console.print()

    def _export_session(self, filename: str):
        """Export current session to markdown."""
        try:
            with open(filename, "w") as f:
                f.write(f"# Assistant Session\n\n")
                f.write(f"**Session ID**: {self.session_id}\n")
                f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
                f.write("---\n\n")

                for msg in self.history:
                    if msg["role"] == "system":
                        continue
                    role = msg["role"].title()
                    content = msg["content"]
                    f.write(f"## {role}\n\n{content}\n\n")

            self.console.print(f"[green]✓ Session exported to {filename}[/green]\n")
        except Exception as e:
            self.console.print(f"[red]✗ Error exporting: {e}[/red]\n")

    def stream_response_with_context(self, user_message: str) -> str:
        """
        Generate response with context retrieval.

        Args:
            user_message: User's message

        Returns:
            Generated response
        """
        # Keep spinner active through entire thinking process
        accumulated = ""
        with self.console.status("[dim]Thinking...", spinner="dots"):
            # Retrieve relevant context
            relevant_contexts = self.retrieve_context(user_message, top_k=5)

            # Prepare messages with context injection
            messages_for_llm = [self.history[0]]  # System prompt

            # If we have relevant context, inject it
            if relevant_contexts:
                context_message = create_context_injection_prompt(
                    relevant_contexts, user_message
                )
                messages_for_llm.append({"role": "user", "content": context_message})
            else:
                # No context, use original message
                messages_for_llm.append({"role": "user", "content": user_message})

            # Add recent conversation history (excluding system prompt)
            for msg in self.history[1:]:
                if msg not in messages_for_llm:
                    messages_for_llm.append(msg)

            # Start streaming and get first chunk before spinner ends
            stream_iterator = self.generator.generate_chat_stream(messages_for_llm)
            try:
                first_chunk = next(stream_iterator)
                accumulated = first_chunk
            except StopIteration:
                return ""

        # Spinner ends here - show context count if relevant
        if relevant_contexts:
            self.console.print(
                f"[dim]Found {len(relevant_contexts)} relevant past conversation(s)[/dim]\n"
            )

        # Now start Live() display with first chunk already visible
        try:
            with Live(refresh_per_second=10, console=self.console) as live:
                # Show first chunk immediately
                md = Markdown(accumulated, code_theme="monokai")
                panel = Panel(
                    md,
                    title="[bold green]🧠 Assistant[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
                live.update(panel)

                # Continue with remaining chunks
                for chunk in stream_iterator:
                    accumulated += chunk

                    # Render as markdown
                    md = Markdown(accumulated, code_theme="monokai")
                    panel = Panel(
                        md,
                        title="[bold green]🧠 Assistant[/bold green]",
                        border_style="green",
                        padding=(1, 2),
                    )
                    live.update(panel)

            # Add newline after Live() context for clean console state
            self.console.print()
            return accumulated

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self.console.print(f"[red]✗ Error during generation: {e}[/red]")
            return ""

    def print_ready_indicator(self):
        """Display ready indicator showing assistant is waiting for input."""
        from rich.rule import Rule

        # Ensure clean separation from previous output
        self.console.print()
        self.console.print(
            Rule("[dim green]Ready[/dim green]", style="dim green", characters="·")
        )
        self.console.print(
            "[dim]Type your message and press Meta+Enter (ESC+Enter) or Alt+Enter to send[/dim]"
        )
        self.console.print()

    def run(self):
        """Start the interactive assistant chat loop."""
        self.print_welcome()

        while True:
            try:
                # Get user input with styled prompt
                from prompt_toolkit.formatted_text import HTML

                prompt_text = HTML(
                    "<ansiblue><b>You</b></ansiblue> <ansicyan>➜</ansicyan> "
                )
                user_input = self.session.prompt(prompt_text, multiline=True).strip()

                # Skip empty input
                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    should_exit = self.handle_command(user_input)
                    if should_exit:
                        break
                    continue

                # Check for calendar intent before processing
                calendar_event = None
                if self.calendar:
                    calendar_event = self.extractor.detect_calendar_intent(user_input)
                    if calendar_event:
                        # Create calendar event
                        created_event = self.calendar.create_event(
                            summary=calendar_event["summary"],
                            start_time=calendar_event["datetime"],
                            end_time=calendar_event["datetime"]
                            + timedelta(hours=calendar_event["duration_hours"]),
                            description=calendar_event.get("description"),
                        )

                        if created_event:
                            # Show confirmation
                            confirmation = self.calendar.format_event_confirmation(
                                created_event
                            )
                            self.console.print(
                                Panel(
                                    confirmation,
                                    title="[bold green]Calendar Event Created[/bold green]",
                                    border_style="green",
                                )
                            )
                            self.console.print()

                # Save user message to database
                user_conv_id = self.save_conversation("user", user_input)

                # Add to working memory
                self.add_message("user", user_input)

                # Generate response with context
                self.console.print()
                response = self.stream_response_with_context(user_input)

                if response:
                    # Save assistant response
                    assistant_conv_id = self.save_conversation("assistant", response)

                    # Add to working memory
                    self.add_message("assistant", response)

                    # Show ready indicator FIRST (immediate feedback)
                    self.print_ready_indicator()

                    # Enrich both messages in background thread (non-blocking)
                    enrichment_thread = threading.Thread(
                        target=self._enrich_messages_background,
                        args=(user_conv_id, user_input, assistant_conv_id, response),
                        daemon=True,
                    )
                    enrichment_thread.start()
                else:
                    # No response, still show ready indicator
                    self.print_ready_indicator()

            except KeyboardInterrupt:
                self.console.print(
                    "\n[yellow]⚠ Interrupted. Type /exit to quit or continue chatting.[/yellow]\n"
                )
                continue

            except EOFError:
                self.console.print(
                    "\n[yellow]👋 Goodbye! Your memory has been saved.[/yellow]\n"
                )
                break


def main():
    """Main entry point for the assistant chat."""
    parser = argparse.ArgumentParser(
        description="Personal Assistant with Memory - ego_proxy"
    )
    parser.add_argument(
        "--model", type=str, default=None, help=f"Model ID (default: {config.MODEL_ID})"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="assistant_memory.db",
        help="Database path (default: assistant_memory.db)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help=f"Maximum tokens to generate (default: {config.MAX_NEW_TOKENS})",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Sampling temperature (default: {config.TEMPERATURE})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed technical logs for debugging",
    )

    args = parser.parse_args()

    # Set verbose mode in config
    config.VERBOSE_MODE = args.verbose

    # Configure logging with Rich handler
    from rich.logging import RichHandler

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_time=False, show_path=False)],
    )

    # Override config if specified
    if args.max_tokens:
        config.MAX_NEW_TOKENS = args.max_tokens
    if args.temperature is not None:
        config.TEMPERATURE = args.temperature

    console = Console()

    try:
        # Load model and tokenizer
        with console.status(
            "[cyan]Loading model...", spinner="dots", spinner_style="cyan"
        ):
            tokenizer, model = load_tokenizer_and_model(model_id=args.model)

        # Print model info
        model_info = get_model_info(model)
        if model_info:
            info_text = f"""
**Model loaded**: {model_info.get("num_parameters_millions", "?")}M parameters
**Device**: {model_info.get("device", "?")}
**Dtype**: {model_info.get("dtype", "?")}
            """
            console.print(Panel(Markdown(info_text), border_style="cyan"))
            console.print()

        # Create generator
        generator = TextGenerator(model, tokenizer)

        # Create and run assistant
        assistant = AssistantChatCLI(generator=generator, db_path=args.db)
        assistant.run()

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Interrupted during startup. Exiting...[/yellow]")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Failed to start assistant: {e}")
        console.print(f"\n[red]✗ Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
