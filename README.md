# Ego Proxy

Run powerful AI language models on your computer completely offline. No cloud dependencies, no data shared externally. Perfect for chatting with AI while keeping everything private.

## What You Can Do

This project gives you four ways to work with AI models. Chat interactively with a beautiful terminal interface, run quick text generation without opening a chat session, use a simple command-line interface, or start an HTTP server so other programs can access the model.

## What You Need

Python 3.10 or newer. A GPU helps but isn't required. Models download automatically from Hugging Face (default is about 1.5GB). That's it.

## Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Using It

**Interactive Chat:**
```bash
./chat-rich.sh
```

**Quick Text Generation:**
```bash
./run.sh scripts/run_once.py --prompt "What is machine learning?"
```

**API Server:**
```bash
./api.sh
```
Then access it at `http://localhost:8000/docs`

## Configuration

Create a `.env` file to customize settings:
```
MODEL_ID=Qwen/Qwen2.5-1.5B-Instruct
USE_GPU=true
MAX_NEW_TOKENS=512
TEMPERATURE=0.7
```

## Troubleshooting

**Out of memory?** Lower `MAX_NEW_TOKENS` or try `USE_GPU=false`

**Very slow?** You're probably on CPU. GPU is much faster.

**Scripts won't run?** Make them executable: `chmod +x chat.sh run.sh api.sh`

## That's It

Your data stays local. No tracking. No cloud calls. Just you and your AI model running on your machine.

Want more details? Check out `PLAN.md` for the development roadmap.
