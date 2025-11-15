#!/usr/bin/env python3
"""
One-off text generation script.

Usage:
    python scripts/run_once.py --prompt "Your question here"
    python scripts/run_once.py --prompt "Explain quantum computing" --max-tokens 256
    echo "What is Python?" | python scripts/run_once.py
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.generator import TextGenerator
from src.model_loader import get_model_info, load_tokenizer_and_model


def main():
    """Main entry point for one-off text generation."""
    parser = argparse.ArgumentParser(
        description="Generate text completion using ego_proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_once.py --prompt "What is the meaning of life?"
  python scripts/run_once.py --prompt "Explain AI" --max-tokens 128
  python scripts/run_once.py --prompt "Hello" --system-prompt "You are a pirate"
  echo "What is Python?" | python scripts/run_once.py
        """,
    )

    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="The prompt to generate from (if not provided, reads from stdin)",
    )
    parser.add_argument(
        "--system-prompt", type=str, default=None, help="Optional system instruction"
    )
    parser.add_argument(
        "--model", type=str, default=None, help=f"Model ID (default: {config.MODEL_ID})"
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
        "--top-p",
        type=float,
        default=None,
        help=f"Nucleus sampling probability (default: {config.TOP_P})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Show the full formatted prompt before generation",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    # Get prompt from args or stdin
    if args.prompt:
        prompt = args.prompt
    else:
        if sys.stdin.isatty():
            parser.error("No prompt provided. Use --prompt or pipe input via stdin")
        prompt = sys.stdin.read().strip()
        if not prompt:
            parser.error("Empty prompt provided")

    logger.info(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

    # Override config if specified
    if args.max_tokens:
        config.MAX_NEW_TOKENS = args.max_tokens
    if args.temperature is not None:
        config.TEMPERATURE = args.temperature
    if args.top_p is not None:
        config.TOP_P = args.top_p

    try:
        # Load model
        print("Loading model... (this may take a minute on first run)", file=sys.stderr)
        logger.info(f"Loading model: {args.model or config.MODEL_ID}")

        tokenizer, model = load_tokenizer_and_model(model_id=args.model)

        # Show model info
        model_info = get_model_info(model)
        if model_info:
            logger.info(
                f"Model: {model_info.get('num_parameters_millions', '?')}M parameters"
            )
            logger.info(f"Device: {model_info.get('device', '?')}")
            logger.info(f"Dtype: {model_info.get('dtype', '?')}")

        print("Model loaded successfully!", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

        # Show formatted prompt if requested
        if args.show_prompt:
            messages = []
            if args.system_prompt:
                messages.append({"role": "system", "content": args.system_prompt})
            messages.append({"role": "user", "content": prompt})

            try:
                formatted = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                print("\n[Formatted Prompt]", file=sys.stderr)
                print(formatted, file=sys.stderr)
                print("-" * 60, file=sys.stderr)
            except Exception as e:
                logger.warning(f"Could not format prompt: {e}")

        # Create generator
        generator = TextGenerator(model, tokenizer)

        # Generate
        print("\n[Generating...]", file=sys.stderr)
        output = generator.generate_text(
            prompt=prompt,
            system_prompt=args.system_prompt,
            max_new_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            return_full_text=False,
        )

        print("-" * 60, file=sys.stderr)
        print("\n[Output]\n", file=sys.stderr)

        # Print output to stdout (clean, no prefix)
        print(output)

        logger.info("Generation completed successfully")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(130)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
