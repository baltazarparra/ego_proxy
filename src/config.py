"""
Central configuration module for the ego_proxy application.

This module manages all configuration settings including:
- Model selection and parameters
- Device and dtype settings
- Generation parameters
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Central configuration for the LLM application."""

    # Model settings
    MODEL_ID: str = os.getenv("MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")

    # Device and compute settings
    USE_GPU: bool = os.getenv("USE_GPU", "true").lower() == "true"
    TORCH_DTYPE: str = os.getenv("TORCH_DTYPE", "auto")  # "auto", "float16", "bfloat16", "float32"
    DEVICE_MAP: str = os.getenv("DEVICE_MAP", "auto")

    # Generation parameters (defaults)
    MAX_NEW_TOKENS: int = int(os.getenv("MAX_NEW_TOKENS", "512"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))
    TOP_P: float = float(os.getenv("TOP_P", "0.9"))
    TOP_K: int = int(os.getenv("TOP_K", "50"))
    DO_SAMPLE: bool = os.getenv("DO_SAMPLE", "true").lower() == "true"

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "WARNING")
    VERBOSE_MODE: bool = False  # Set by command-line flag, shows detailed logs

    @classmethod
    def get_device(cls) -> str:
        """
        Get the appropriate device string for PyTorch.

        Returns:
            "cuda" if GPU is available and enabled, otherwise "cpu"
        """
        if cls.USE_GPU:
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return "cpu"

    @classmethod
    def summary(cls) -> dict:
        """
        Get a summary of current configuration.

        Returns:
            Dictionary with all config values
        """
        return {
            "model_id": cls.MODEL_ID,
            "device": cls.get_device(),
            "torch_dtype": cls.TORCH_DTYPE,
            "max_new_tokens": cls.MAX_NEW_TOKENS,
            "temperature": cls.TEMPERATURE,
            "top_p": cls.TOP_P,
        }


# Singleton instance
config = Config()
