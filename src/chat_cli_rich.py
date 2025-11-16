"""
Enhanced Interactive CLI chat interface with Rich UI.

Provides a beautiful REPL for multi-turn conversations with:
- Markdown rendering with syntax highlighting
- Streaming responses with live updates
- Multiline input support
- Persistent history with search (Ctrl+R)
- Auto-suggestions from previous prompts
- Rich panels and formatting
"""

import argparse
import logging
import sys
from typing import Dict, List

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from .config import config
from .generator import TextGenerator
from .model_loader import get_model_info, load_tokenizer_and_model

logger = logging.getLogger(__name__)


class RichChatCLI:
    """Enhanced interactive chat REPL with Rich UI."""

    def __init__(
        self,
        generator: TextGenerator,
        system_prompt: str = None,
        max_history: int = 50,
        history_file: str = ".llm_chat_history",
    ):
        """
        Initialize the enhanced chat CLI.

        Args:
            generator: TextGenerator instance
            system_prompt: Optional system instruction for the conversation
            max_history: Maximum number of messages to keep in history
            history_file: Path to file for persistent history
        """
        self.generator = generator
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.history: List[Dict[str, str]] = []

        # Rich console for beautiful output
        self.console = Console()

        # Prompt Toolkit session with history and auto-suggestions
        # Key bindings for Meta+Enter to submit
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

        # Add system prompt to history if provided
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def add_message(self, role: str, content: str):
        """Add a message to the conversation history."""
        self.history.append({"role": role, "content": content})

        # Trim history if too long (keep system prompt if it exists)
        if len(self.history) > self.max_history:
            if self.history[0].get("role") == "system":
                self.history = [self.history[0]] + self.history[
                    -(self.max_history - 1) :
                ]
            else:
                self.history = self.history[-self.max_history :]

    def reset_history(self):
        """Clear conversation history (keep system prompt if exists)."""
        if self.system_prompt:
            self.history = [{"role": "system", "content": self.system_prompt}]
        else:
            self.history = []

    def print_welcome(self):
        """Display welcome message with Rich formatting."""
        welcome_text = f"""
# 🤖 Ego Proxy Chat Interface

**Model**: {config.MODEL_ID}
**Device**: {config.get_device()}

## How to Use

- Type your message (supports **multiple lines**)
- Press **Meta+Enter** (ESC then Enter) or **Alt+Enter** to submit
- Press **Ctrl+R** to search history
- Type `/help` for available commands

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
        """Display help with Rich formatting."""
        help_text = """
# 📖 Available Commands

| Command | Description |
|---------|-------------|
| `/help`, `/h` | Show this help message |
| `/reset`, `/clear` | Clear conversation history |
| `/history` | Show conversation history |
| `/export [file]` | Export conversation to markdown file |
| `/exit`, `/quit`, `/q` | Exit the chat |

# ⌨️ Keyboard Shortcuts

- **Meta+Enter** (ESC+Enter) or **Alt+Enter** - Submit message
- **Ctrl+R** - Search command history
- **Ctrl+C** - Cancel current input
- **Arrow Up/Down** - Navigate history

# 💡 Tips

- Start code blocks with triple backticks for syntax highlighting
- Responses render with beautiful markdown formatting
- History is saved across sessions
        """
        help_panel = Panel(
            Markdown(help_text),
            title="[bold green]Help[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        self.console.print(help_panel)
        self.console.print()

    def print_history(self):
        """Print conversation history with Rich formatting."""
        if not self.history:
            self.console.print("[yellow]No conversation history yet.[/yellow]\n")
            return

        history_text = "# 📜 Conversation History\n\n"

        for i, msg in enumerate(self.history, 1):
            role = msg["role"].upper()
            content = msg["content"]

            # Truncate long messages
            if len(content) > 100:
                content = content[:97] + "..."

            history_text += f"{i}. **[{role}]** {content}\n\n"

        history_panel = Panel(
            Markdown(history_text),
            title="[bold cyan]History[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print(history_panel)
        self.console.print()

    def export_conversation(self, filename: str = "conversation.md"):
        """Export conversation to markdown file."""
        try:
            with open(filename, "w") as f:
                f.write(f"# Chat Conversation\n\n")
                f.write(f"**Model**: {config.MODEL_ID}\n\n")
                f.write("---\n\n")

                for msg in self.history:
                    role = msg["role"].title()
                    content = msg["content"]
                    f.write(f"## {role}\n\n{content}\n\n")

            self.console.print(
                f"[green]✓ Conversation exported to {filename}[/green]\n"
            )
        except Exception as e:
            self.console.print(f"[red]✗ Error exporting: {e}[/red]\n")

    def handle_command(self, command: str) -> bool:
        """
        Handle special commands.

        Args:
            command: The command string (including /)

        Returns:
            True if should exit, False otherwise
        """
        parts = command.lower().strip().split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else None

        if cmd in ["/exit", "/quit", "/q"]:
            self.console.print("\n[yellow]👋 Goodbye![/yellow]\n")
            return True

        elif cmd in ["/reset", "/clear"]:
            self.reset_history()
            self.console.print("[green]✓ Conversation history cleared[/green]\n")
            return False

        elif cmd in ["/help", "/h"]:
            self.print_help()
            return False

        elif cmd == "/history":
            self.print_history()
            return False

        elif cmd == "/export":
            filename = args if args else "conversation.md"
            self.export_conversation(filename)
            return False

        else:
            self.console.print(f"[red]✗ Unknown command: {cmd}[/red]")
            self.console.print("Type [green]/help[/green] for available commands\n")
            return False

    def stream_response(self, messages: List[dict]) -> str:
        """
        Generate streaming response with live Rich display.

        Args:
            messages: Conversation history

        Returns:
            Complete generated response
        """
        accumulated = ""

        try:
            # Use Rich Live display for smooth streaming
            with Live(refresh_per_second=10, console=self.console) as live:
                for chunk in self.generator.generate_chat_stream(messages):
                    accumulated += chunk

                    # Render accumulated text as markdown
                    md = Markdown(accumulated, code_theme="monokai")
                    panel = Panel(
                        md,
                        title="[bold green]🤖 Assistant[/bold green]",
                        border_style="green",
                        padding=(1, 2),
                    )
                    live.update(panel)

            return accumulated

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self.console.print(f"[red]✗ Error during generation: {e}[/red]")
            return ""

    def run(self):
        """Start the interactive chat loop."""
        self.print_welcome()

        while True:
            try:
                # Get user input with Prompt Toolkit
                user_input = self.session.prompt(
                    "You> ",
                    multiline=True,
                ).strip()

                # Skip empty input
                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    should_exit = self.handle_command(user_input)
                    if should_exit:
                        break
                    continue

                # Add user message to history
                self.add_message("user", user_input)

                # Generate streaming response
                self.console.print()  # Blank line before response
                response = self.stream_response(self.history)

                if response:  # Only add if generation succeeded
                    # Add assistant response to history
                    self.add_message("assistant", response)

                self.console.print()  # Blank line after response

            except KeyboardInterrupt:
                self.console.print(
                    "\n[yellow]⚠ Interrupted. Type /exit to quit or continue chatting.[/yellow]\n"
                )
                continue

            except EOFError:
                self.console.print("\n[yellow]👋 Goodbye![/yellow]\n")
                break


def main():
    """Main entry point for the enhanced chat CLI."""
    parser = argparse.ArgumentParser(
        description="Enhanced interactive chat with ego_proxy (Rich UI)"
    )
    parser.add_argument(
        "--model", type=str, default=None, help=f"Model ID (default: {config.MODEL_ID})"
    )
    parser.add_argument(
        "--system-prompt",
        type=str,
        default=None,
        help="System prompt for the conversation",
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
        "--no-history",
        action="store_true",
        help="Disable conversation history (stateless mode)",
    )
    parser.add_argument(
        "--history-file",
        type=str,
        default=".llm_chat_history",
        help="File to store command history (default: .llm_chat_history)",
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
        console.print("[cyan]Loading model... (this may take a minute)[/cyan]")
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

        # Create and run enhanced chat CLI
        max_history = 1 if args.no_history else 50
        chat = RichChatCLI(
            generator=generator,
            system_prompt=args.system_prompt,
            max_history=max_history,
            history_file=args.history_file,
        )
        chat.run()

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Interrupted during startup. Exiting...[/yellow]")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Failed to start chat: {e}")
        console.print(f"\n[red]✗ Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
