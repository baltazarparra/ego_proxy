"""
Interactive CLI chat interface.

Provides a REPL for multi-turn conversations with the local LLM.
Supports commands like /reset, /exit, and maintains conversation history.
"""

import logging
import sys
import argparse
from typing import List, Dict

from .config import config
from .model_loader import load_tokenizer_and_model, get_model_info
from .generator import TextGenerator

logger = logging.getLogger(__name__)


class ChatCLI:
    """Interactive chat REPL."""

    def __init__(
        self,
        generator: TextGenerator,
        system_prompt: str = None,
        max_history: int = 50
    ):
        """
        Initialize the chat CLI.

        Args:
            generator: TextGenerator instance
            system_prompt: Optional system instruction for the conversation
            max_history: Maximum number of messages to keep in history
        """
        self.generator = generator
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.history: List[Dict[str, str]] = []

        # Add system prompt to history if provided
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def add_message(self, role: str, content: str):
        """Add a message to the conversation history."""
        self.history.append({"role": role, "content": content})

        # Trim history if too long (keep system prompt if it exists)
        if len(self.history) > self.max_history:
            if self.history[0].get("role") == "system":
                self.history = [self.history[0]] + self.history[-(self.max_history-1):]
            else:
                self.history = self.history[-self.max_history:]

    def reset_history(self):
        """Clear conversation history (keep system prompt if exists)."""
        if self.system_prompt:
            self.history = [{"role": "system", "content": self.system_prompt}]
        else:
            self.history = []

    def handle_command(self, command: str) -> bool:
        """
        Handle special commands.

        Args:
            command: The command string (including /)

        Returns:
            True if should exit, False otherwise
        """
        command = command.lower().strip()

        if command in ["/exit", "/quit", "/q"]:
            print("\nGoodbye!")
            return True

        elif command in ["/reset", "/clear"]:
            self.reset_history()
            print("\n[Conversation history cleared]\n")
            return False

        elif command in ["/help", "/h"]:
            self.print_help()
            return False

        elif command == "/history":
            self.print_history()
            return False

        else:
            print(f"\nUnknown command: {command}")
            print("Type /help for available commands\n")
            return False

    def print_help(self):
        """Print available commands."""
        print("\nAvailable commands:")
        print("  /help, /h      - Show this help message")
        print("  /reset, /clear - Clear conversation history")
        print("  /history       - Show conversation history")
        print("  /exit, /quit   - Exit the chat")
        print()

    def print_history(self):
        """Print conversation history."""
        print("\n=== Conversation History ===")
        for i, msg in enumerate(self.history):
            role = msg['role'].upper()
            content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            print(f"{i+1}. [{role}] {content}")
        print("============================\n")

    def run(self):
        """Start the interactive chat loop."""
        print("=" * 60)
        print("Ego Proxy Chat Interface")
        print("=" * 60)
        print(f"Model: {config.MODEL_ID}")
        print(f"Device: {config.get_device()}")
        print("\nType your message and press Enter to chat.")
        print("Type /help for available commands.")
        print("Type /exit to quit.\n")
        print("=" * 60)
        print()

        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()

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

                # Generate response
                print("Assistant: ", end="", flush=True)

                try:
                    response = self.generator.generate_chat(self.history)
                    print(response)

                    # Add assistant response to history
                    self.add_message("assistant", response)

                except Exception as e:
                    print(f"\n[Error generating response: {e}]")
                    logger.error(f"Generation error: {e}", exc_info=True)

                print()  # Blank line for readability

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type /exit to quit or continue chatting.\n")
                continue

            except EOFError:
                print("\n\nGoodbye!")
                break


def main():
    """Main entry point for the chat CLI."""
    parser = argparse.ArgumentParser(description="Interactive chat with ego_proxy")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Model ID (default: {config.MODEL_ID})"
    )
    parser.add_argument(
        "--system-prompt",
        type=str,
        default=None,
        help="System prompt for the conversation"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help=f"Maximum tokens to generate (default: {config.MAX_NEW_TOKENS})"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Sampling temperature (default: {config.TEMPERATURE})"
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Disable conversation history (stateless mode)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Override config if specified
    if args.max_tokens:
        config.MAX_NEW_TOKENS = args.max_tokens
    if args.temperature is not None:
        config.TEMPERATURE = args.temperature

    try:
        # Load model and tokenizer
        print("Loading model... (this may take a minute)")
        tokenizer, model = load_tokenizer_and_model(model_id=args.model)

        # Print model info
        model_info = get_model_info(model)
        if model_info:
            print(f"\nModel loaded: {model_info.get('num_parameters_millions', '?')}M parameters")
            print(f"Device: {model_info.get('device', '?')}")
            print(f"Dtype: {model_info.get('dtype', '?')}\n")

        # Create generator
        generator = TextGenerator(model, tokenizer)

        # Create and run chat CLI
        max_history = 1 if args.no_history else 50
        chat = ChatCLI(
            generator=generator,
            system_prompt=args.system_prompt,
            max_history=max_history
        )
        chat.run()

    except KeyboardInterrupt:
        print("\n\nInterrupted during startup. Exiting...")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Failed to start chat: {e}", exc_info=True)
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
