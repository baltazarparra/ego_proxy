"""
Text generation wrapper module.

This module provides a clean interface for text generation with:
- Configurable sampling parameters
- Chat template support
- Streaming capability
"""

import logging
import signal
from contextlib import contextmanager
from threading import Thread
from typing import Iterator

import torch
from transformers import TextIteratorStreamer

from .config import config

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Exception raised when generation times out."""

    pass


class TextGenerator:
    """Wrapper around model.generate() with sane defaults."""

    def __init__(self, model, tokenizer, generation_timeout: int = 300):
        """
        Initialize the text generator.

        Args:
            model: The loaded language model
            tokenizer: The loaded tokenizer
            generation_timeout: Maximum time in seconds for generation (default: 300s/5min)
        """
        self.model = model
        self.tokenizer = tokenizer
        self.device = model.device
        self.generation_timeout = generation_timeout

    @contextmanager
    def _generation_timeout(self, timeout: int | None = None):
        """Context manager for generation timeout."""
        timeout = timeout or self.generation_timeout

        def timeout_handler(signum, frame):
            raise TimeoutException(f"Generation timed out after {timeout} seconds")

        # Set alarm (only works on Unix-like systems AND main thread)
        try:
            import threading

            if threading.current_thread() is not threading.main_thread():
                # Can't use signals in background threads, just proceed without timeout
                logger.debug("Skipping timeout (not in main thread)")
                yield
                return

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except (AttributeError, ValueError) as e:
            # Windows doesn't have SIGALRM or signal error, just proceed without timeout
            logger.debug(f"Timeout not available: {e}")
            yield

    def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        do_sample: bool | None = None,
        return_full_text: bool = False,
    ) -> str:
        """
        Generate text completion for a given prompt.

        Args:
            prompt: The user prompt/question
            system_prompt: Optional system instruction
            max_new_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (higher = more random)
            top_p: Nucleus sampling probability
            top_k: Top-k sampling parameter
            do_sample: Whether to use sampling (vs greedy)
            return_full_text: If True, return prompt + completion; if False, only completion

        Returns:
            Generated text string
        """
        # Use config defaults for any unspecified parameters
        max_new_tokens = max_new_tokens or config.MAX_NEW_TOKENS
        temperature = temperature if temperature is not None else config.TEMPERATURE
        top_p = top_p if top_p is not None else config.TOP_P
        top_k = top_k if top_k is not None else config.TOP_K
        do_sample = do_sample if do_sample is not None else config.DO_SAMPLE

        # Build the conversation in chat format
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Apply chat template
        try:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception as e:
            logger.warning(f"Chat template failed, using raw prompt: {e}")
            text = prompt

        # Tokenize
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        input_length = inputs.input_ids.shape[1]

        logger.debug(f"Input length: {input_length} tokens")
        logger.debug(f"Generating up to {max_new_tokens} new tokens")

        # Generate with timeout protection
        try:
            with self._generation_timeout():
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        top_k=top_k,
                        do_sample=do_sample,
                        pad_token_id=self.tokenizer.eos_token_id,
                    )
        except TimeoutException as e:
            logger.error(f"Generation timed out: {e}")
            return "[Generation timed out - please try a shorter prompt or reduce max_tokens]"

        # Decode
        full_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        if return_full_text:
            return full_text
        else:
            # Return only the generated portion
            # Try to extract just the assistant's response
            try:
                # For chat models, try to find the assistant response
                if "assistant" in full_text.lower():
                    parts = full_text.split("assistant")
                    if len(parts) > 1:
                        return parts[-1].strip()

                # Fallback: decode only the new tokens
                new_tokens = outputs[0][input_length:]
                return self.tokenizer.decode(new_tokens, skip_special_tokens=True)
            except Exception as e:
                logger.warning(f"Could not extract assistant response: {e}")
                return full_text

    def generate_chat(
        self,
        messages: list[dict],
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        do_sample: bool | None = None,
        **kwargs,
    ) -> str:
        """
        Generate a response for a multi-turn conversation.

        Args:
            messages: List of message dicts with 'role' and 'content'
                     e.g., [{"role": "user", "content": "Hello"}]
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling probability
            do_sample: Whether to use sampling (vs greedy)
            **kwargs: Additional generation parameters

        Returns:
            Generated assistant response
        """
        # Use config defaults
        max_new_tokens = max_new_tokens or config.MAX_NEW_TOKENS
        temperature = temperature if temperature is not None else config.TEMPERATURE
        top_p = top_p if top_p is not None else config.TOP_P
        do_sample = do_sample if do_sample is not None else config.DO_SAMPLE

        # Apply chat template
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Tokenize
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        input_length = inputs.input_ids.shape[1]

        # Generate with timeout protection
        try:
            with self._generation_timeout():
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        do_sample=do_sample,
                        pad_token_id=self.tokenizer.eos_token_id,
                        **kwargs,
                    )
        except TimeoutException as e:
            logger.error(f"Generation timed out: {e}")
            return "[Generation timed out - please try a shorter prompt or reduce max_tokens]"

        # Decode only the new tokens
        new_tokens = outputs[0][input_length:]
        response = self.tokenizer.decode(new_tokens, skip_special_tokens=True)

        return response.strip()

    def generate_chat_stream(
        self,
        messages: list[dict],
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        do_sample: bool | None = None,
        **kwargs,
    ) -> Iterator[str]:
        """
        Generate a streaming response for a multi-turn conversation.

        Yields tokens as they are generated in real-time.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling probability
            do_sample: Whether to use sampling (vs greedy)
            **kwargs: Additional generation parameters

        Yields:
            Generated text chunks (tokens or token groups)

        Example:
            >>> for chunk in generator.generate_chat_stream(messages):
            ...     print(chunk, end='', flush=True)
        """
        # Use config defaults
        max_new_tokens = max_new_tokens or config.MAX_NEW_TOKENS
        temperature = temperature if temperature is not None else config.TEMPERATURE
        top_p = top_p if top_p is not None else config.TOP_P
        do_sample = do_sample if do_sample is not None else config.DO_SAMPLE

        # Apply chat template
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Tokenize
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)

        # Create streamer
        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        # Prepare generation kwargs
        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=do_sample,
            pad_token_id=self.tokenizer.eos_token_id,
            **kwargs,
        )

        # Start generation in background thread
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        # Yield tokens as they're generated
        for new_text in streamer:
            yield new_text

        # Wait for generation to complete
        thread.join()
