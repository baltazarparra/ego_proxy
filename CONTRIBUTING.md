# Contributing to ego_proxy

First off, thank you for considering contributing to ego_proxy! It's people like you that make this project better for everyone.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Pull Request Process](#pull-request-process)

---

## 📜 Code of Conduct

This project and everyone participating in it is governed by common sense and mutual respect. By participating, you are expected to uphold this standard. Please be kind, considerate, and constructive.

### Our Standards

- **Be Respectful**: Treat others as you'd like to be treated
- **Be Constructive**: Provide helpful feedback and suggestions
- **Be Patient**: Remember that contributors have varying experience levels
- **Be Open**: Welcome newcomers and help them get started

---

## 🤝 How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates.

**Good Bug Report Includes:**
- Clear, descriptive title
- Steps to reproduce
- Expected vs actual behavior
- System information (OS, Python version, GPU)
- Relevant logs or error messages
- Code samples (if applicable)

**Example:**
```markdown
**Bug**: Model loading fails on Windows with CUDA

**Steps to Reproduce:**
1. Install on Windows 11 with NVIDIA RTX 3060
2. Set USE_GPU=true in .env
3. Run `./chat.sh`

**Expected**: Model loads on GPU
**Actual**: Error: "CUDA initialization failed"

**System**:
- OS: Windows 11
- Python: 3.10.5
- PyTorch: 2.0.1+cu118
- GPU: NVIDIA RTX 3060 (12GB)

**Logs**:
```
[paste error logs here]
```
```

### Suggesting Enhancements

Enhancement suggestions are welcome! Please provide:
- Clear description of the enhancement
- Use case / why it's needed
- Example of how it would work
- Any implementation ideas (optional)

### Code Contributions

We're actively looking for contributions in these areas:

**High Priority:**
- Writing tests (pytest) - See PLAN.md Phase 5
- API streaming endpoints (Server-Sent Events)
- Docker setup
- Documentation improvements

**Medium Priority:**
- Model quantization support
- Batch processing
- Response caching
- Additional endpoints

**Low Priority:**
- RAG implementation
- Web UI
- Fine-tuning support

---

## 🛠️ Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- (Optional) NVIDIA GPU with CUDA support
- (Optional) direnv for auto-activation

### Setup Steps

```bash
# 1. Fork and clone
git clone https://github.com/YOUR-USERNAME/ego_proxy.git
cd ego_proxy

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install development dependencies
pip install black isort autoflake pytest pytest-cov mypy

# 5. Configure environment
cp .env.example .env
nano .env  # Edit as needed

# 6. Verify setup
python3 -c "from src.config import config; print('Setup OK!')"
```

### Development Tools

```bash
# Format code
black src/ scripts/
isort src/ scripts/

# Remove unused imports
autoflake --remove-all-unused-imports --in-place src/*.py scripts/*.py

# Type checking (when implemented)
mypy src/ scripts/

# Run tests (when available)
pytest
pytest --cov=src --cov-report=html
```

---

## 📏 Coding Standards

### Python Style

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with some modifications:

- **Line Length**: 100 characters (not 79)
- **Formatter**: Black (primary), isort (imports)
- **Type Hints**: Required for function parameters, encouraged for returns
- **Docstrings**: Required for all public functions/classes

### Code Style Example

```python
from typing import Optional, List

from src.config import config

def generate_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_new_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Generate text completion for a given prompt.

    Args:
        prompt: The user prompt/question
        system_prompt: Optional system instruction
        max_new_tokens: Maximum number of tokens to generate
        temperature: Sampling temperature (higher = more random)

    Returns:
        Generated text string

    Example:
        >>> text = generate_text("What is Python?", max_new_tokens=100)
        >>> print(text)
        "Python is a high-level programming language..."
    """
    # Use config defaults for unspecified parameters
    max_new_tokens = max_new_tokens or config.MAX_NEW_TOKENS
    temperature = temperature if temperature is not None else config.TEMPERATURE
    
    # Implementation here
    return generated_text
```

### File Organization

```python
# 1. Docstring (module-level)
"""
Module description.

This module provides...
"""

# 2. Standard library imports
import logging
import time
from typing import Optional, List, Dict

# 3. Third-party imports
import torch
from transformers import AutoModel

# 4. Local imports
from .config import config
from .model_loader import load_model

# 5. Constants
DEFAULT_MAX_TOKENS = 512
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0

# 6. Functions and classes
logger = logging.getLogger(__name__)

def my_function():
    pass

class MyClass:
    pass
```

### Naming Conventions

- **Variables/Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: `_leading_underscore`
- **Very Private**: `__double_leading_underscore`

### Documentation

**Docstring Format** (Google Style):

```python
def function(param1: str, param2: int) -> bool:
    """
    Short one-line description.

    Longer description if needed. Explain what the function does,
    any important details, edge cases, etc.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When param1 is empty
        RuntimeError: When something fails

    Example:
        >>> result = function("hello", 42)
        >>> print(result)
        True
    """
    pass
```

---

## 🧪 Testing Guidelines

### Writing Tests

We use pytest. Tests should be:
- **Focused**: One concept per test
- **Independent**: No dependencies between tests
- **Fast**: Avoid slow operations when possible
- **Clear**: Descriptive test names

### Test Structure

```python
# tests/test_generator.py
import pytest
from src.generator import TextGenerator
from src.model_loader import load_tokenizer_and_model

@pytest.fixture
def generator():
    """Fixture providing a TextGenerator instance."""
    tokenizer, model = load_tokenizer_and_model()
    return TextGenerator(model, tokenizer)

def test_generate_text_returns_string(generator):
    """Test that generate_text returns a string."""
    result = generator.generate_text(prompt="Hello", max_new_tokens=10)
    assert isinstance(result, str)
    assert len(result) > 0

def test_generate_text_respects_max_tokens(generator):
    """Test that max_new_tokens limit is respected."""
    result = generator.generate_text(prompt="Count to 100", max_new_tokens=5)
    tokens = generator.tokenizer.encode(result)
    assert len(tokens) <= 5 + 10  # Some buffer for variation

def test_generate_text_with_system_prompt(generator):
    """Test generation with system prompt."""
    result = generator.generate_text(
        prompt="Say hello",
        system_prompt="You are a pirate",
        max_new_tokens=20
    )
    assert isinstance(result, str)
    # Could check for pirate-like language if deterministic
```

### Test Locations

```
tests/
├── __init__.py
├── conftest.py           # Shared fixtures
├── test_config.py        # Config tests
├── test_model_loader.py  # Model loading tests
├── test_generator.py     # Generation tests
├── test_chat_cli.py      # CLI tests
├── test_api_server.py    # API tests
└── test_integration.py   # End-to-end tests
```

### Running Tests

```bash
# All tests
pytest

# Specific file
pytest tests/test_generator.py

# Specific test
pytest tests/test_generator.py::test_generate_text_returns_string

# With coverage
pytest --cov=src --cov-report=html

# Verbose
pytest -v

# Show print statements
pytest -s
```

---

## 📝 Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, etc.)
- **refactor**: Code refactoring
- **test**: Adding/updating tests
- **chore**: Maintenance tasks

### Examples

**Good:**
```
feat(api): add streaming endpoint for chat completion

Implement Server-Sent Events streaming for /chat endpoint.
Allows clients to receive tokens in real-time as they're generated.

Closes #42
```

```
fix(generator): handle empty prompts gracefully

Previously would crash with ValueError when prompt was empty string.
Now returns helpful error message.

Fixes #38
```

```
docs(readme): add Docker deployment section

Add comprehensive Docker setup instructions with examples
for both CPU and GPU configurations.
```

**Bad:**
```
fixed stuff
```

```
Update README
```

```
WIP
```

### Tips

- Use imperative mood ("add" not "added")
- Don't capitalize first letter
- No period at the end
- Reference issues/PRs when relevant
- Keep subject under 50 characters
- Wrap body at 72 characters

---

## 🔄 Pull Request Process

### Before Submitting

**Checklist:**
- [ ] Code follows style guidelines
- [ ] All tests pass (`pytest`)
- [ ] Code is formatted (`black`, `isort`)
- [ ] No unused imports (`autoflake --check`)
- [ ] Documentation updated (if needed)
- [ ] CHANGELOG.md updated (if appropriate)
- [ ] Commit messages follow guidelines

### Submitting

1. **Fork the repository**
2. **Create a branch**: `git checkout -b feat/my-new-feature`
3. **Make your changes**
4. **Test thoroughly**
5. **Commit**: Follow commit message guidelines
6. **Push**: `git push origin feat/my-new-feature`
7. **Open Pull Request**: Use the PR template

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?
Describe testing done

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] No new warnings
```

### Review Process

1. **Automated Checks**: CI/CD runs (when implemented)
2. **Code Review**: Maintainer reviews code
3. **Feedback**: Address any comments/suggestions
4. **Approval**: Once approved, maintainer merges

### After Merge

- **Delete branch**: Keep repo clean
- **Close related issues**: Reference in commit/PR
- **Update local**: `git pull origin main`

---

## 🎯 Priority Areas

Looking for where to start? These areas need help:

### High Priority
1. **Testing** (Phase 5)
   - Write unit tests for all modules
   - Integration tests for API
   - Achieve 80%+ coverage

2. **CI/CD Pipeline**
   - GitHub Actions workflow
   - Automated testing
   - Code quality checks

3. **Documentation**
   - API documentation website
   - Video tutorials
   - More code examples

### Medium Priority
4. **API Streaming** (Phase 6)
   - Server-Sent Events implementation
   - Streaming endpoints

5. **Docker** (Phase 7)
   - Dockerfile for CPU
   - Dockerfile for GPU
   - docker-compose.yml

6. **Performance**
   - Benchmarking suite
   - Optimization opportunities
   - Memory profiling

---

## 💡 Development Tips

### Local Testing

```bash
# Test all interfaces quickly
./run.sh scripts/run_once.py --prompt "Test" --max-tokens 5
./chat-rich.sh  # Type /exit to quit quickly
./api.sh &  # Run in background
curl http://localhost:8000/health
pkill -f api_server
```

### Debugging

```bash
# Verbose logging
export LOG_LEVEL=DEBUG
./chat.sh

# Python debugger
python3 -m pdb scripts/run_once.py --prompt "Test"

# Profile performance
python3 -m cProfile -o profile.stats scripts/run_once.py --prompt "Test"
```

### Quick Iteration

```bash
# Watch for changes and auto-reload (API)
uvicorn src.api_server:app --reload

# Use direnv for auto-activation
echo 'source .venv/bin/activate' > .envrc
direnv allow .
```

---

## 📧 Questions?

- **Issues**: [GitHub Issues](https://github.com/yourusername/ego_proxy/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/ego_proxy/discussions)

---

## 🙏 Thank You!

Every contribution, no matter how small, is valuable. Whether it's:
- Reporting a bug
- Suggesting a feature
- Writing code
- Improving documentation
- Helping others

You're making ego_proxy better for everyone. Thank you! 🎉

---

**Happy Coding!**  
The ego_proxy Team
