"""
Model and tokenizer loading utilities.

This module handles:
- Loading tokenizer from Hugging Face
- Loading model with appropriate device and dtype
- Device detection and optimization
"""

import logging
from typing import Optional, Tuple

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .config import config

logger = logging.getLogger(__name__)


def get_torch_dtype(dtype_str: str = "auto"):
    """
    Convert dtype string to torch dtype.

    Args:
        dtype_str: String representation of dtype ("auto", "float16", "bfloat16", "float32")

    Returns:
        torch.dtype or "auto"
    """
    if dtype_str == "auto":
        return "auto"

    dtype_map = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }

    return dtype_map.get(dtype_str.lower(), torch.float16)


def load_tokenizer_and_model(
    model_id: Optional[str] = None,
    device_map: Optional[str] = None,
    torch_dtype: Optional[str] = None,
) -> Tuple[AutoTokenizer, AutoModelForCausalLM]:
    """
    Load tokenizer and model from Hugging Face.

    Args:
        model_id: Hugging Face model ID (e.g., "Qwen/Qwen2.5-1.5B-Instruct")
        device_map: Device mapping strategy ("auto", "cpu", "cuda", etc.)
        torch_dtype: Data type for model weights

    Returns:
        Tuple of (tokenizer, model)

    Raises:
        ValueError: If model loading fails
    """
    # Use config defaults if not specified
    model_id = model_id or config.MODEL_ID
    device_map = device_map or config.DEVICE_MAP
    torch_dtype = torch_dtype or config.TORCH_DTYPE

    logger.debug(f"Loading model: {model_id}")
    logger.debug(f"Device map: {device_map}")
    logger.debug(f"Torch dtype: {torch_dtype}")

    # Check CUDA availability
    if torch.cuda.is_available():
        logger.debug(f"GPU detected: {torch.cuda.get_device_name(0)}")
        logger.debug(f"CUDA version: {torch.version.cuda}")
    else:
        logger.debug("No GPU detected, using CPU")

    try:
        # Load tokenizer
        logger.debug("Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

        # Load model
        logger.debug("Loading model...")
        dtype = get_torch_dtype(torch_dtype)

        model = AutoModelForCausalLM.from_pretrained(
            model_id, device_map=device_map, dtype=dtype, trust_remote_code=True
        )

        logger.debug("Model loaded successfully!")
        logger.debug(f"Model device: {model.device}")
        logger.debug(f"Model dtype: {model.dtype}")

        return tokenizer, model

    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise ValueError(f"Model loading failed: {e}")


def get_model_info(model) -> dict:
    """
    Get information about the loaded model.

    Args:
        model: The loaded model

    Returns:
        Dictionary with model information
    """
    try:
        num_params = sum(p.numel() for p in model.parameters())
        num_params_trainable = sum(
            p.numel() for p in model.parameters() if p.requires_grad
        )

        return {
            "device": str(model.device),
            "dtype": str(model.dtype),
            "num_parameters": num_params,
            "num_trainable_parameters": num_params_trainable,
            "num_parameters_millions": round(num_params / 1_000_000, 2),
        }
    except Exception as e:
        logger.warning(f"Could not get model info: {e}")
        return {}
