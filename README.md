# ✳️ ego_proxy
Run powerful AI language models FREE completely offline. No "Big Brother" with your data, stay 100% local.

## What You Can Do

**Standard Chat:** Chat interactively with AI using a beautiful, feature-rich terminal interface. Ego Proxy provides a modern chat experience with markdown rendering, syntax highlighting, streaming responses, and conversation history.

**Personal Assistant (NEW!):** Transform your chat into an intelligent personal work assistant that remembers everything you tell it and interact with your calendar. Automatically tracks people, topics, dates, and provides context-aware advice based on your conversation history. Perfect for logging daily work activities and getting intelligent reminders.

## What You Need

Python 3.10 or newer. A GPU helps but isn't required. Models download automatically from Hugging Face (default is about 1.5GB). That's it.

## Getting Started

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install
# Run the optimized installation script
./scripts/install.sh

# or
# Install dependencies via pip
pip install --prefer-binary --upgrade-strategy only-if-needed -r requirements.txt
```

## Using It

**Standard Interactive Chat:**
```bash
./chat-rich.sh
```

**Personal Assistant with Memory:**
```bash
./assistant.sh
```

The assistant automatically saves all conversations, extracts metadata (people, topics, sentiment), and retrieves relevant context when you ask questions. See `ASSISTANT.md` for detailed documentation.

## Configuration

Create a `.env` file to customize settings:
```
MODEL_ID=Qwen/Qwen2.5-1.5B-Instruct
USE_GPU=true
MAX_NEW_TOKENS=512
TEMPERATURE=0.7
```

## Troubleshooting

### Installation Issues

**pip install is very slow?**
- Use `uv` instead: `uv pip install -r requirements.txt` (often 10-100x faster)
- Use pip cache: `pip install --cache-dir ~/.cache/pip -r requirements.txt`
- Use `--prefer-binary` flag to avoid building from source
- PyTorch is large (~500MB-2GB). First install takes time, subsequent installs use cache
- For CPU-only systems, use PyTorch CPU build: `pip install torch --index-url https://download.pytorch.org/whl/cpu`

**Network timeouts or slow downloads?**
- Use a pip mirror: `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt` (China)
- Increase pip timeout: `pip install --default-timeout=1000 -r requirements.txt`
- Check your internet connection and firewall settings

**Out of disk space?**
- PyTorch and dependencies need ~3-5GB free space
- Use pip cache cleanup: `pip cache purge` (then reinstall with cache)

**Permission errors?**
- Make sure virtual environment is activated: `source .venv/bin/activate`
- Don't use `sudo` with pip in virtual environments

### Runtime Issues

**Out of memory?** Lower `MAX_NEW_TOKENS` or try `USE_GPU=false`

**Very slow?** You're probably on CPU. GPU is much faster.

**Script won't run?** Make it executable: `chmod +x chat-rich.sh`

## Documentation

- **PLAN.md** - Development roadmap and architecture
- **ASSISTANT.md** - Personal Assistant feature documentation
- **CONTRIBUTING.md** - Contribution guidelines

## That's It

Your data stays local. No tracking. No cloud calls. Just you and your AI model running on your machine.
