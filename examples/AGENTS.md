# Optional project override

The canonical rules live in the bot repository:

https://github.com/nitsan-technologies/t3planet-ai-bot/blob/main/AGENTS.md

You do **not** need to copy that file into every project.

Add a local `AGENTS.md` in a calling repository only when you need
project-specific extras (for example architecture notes unique to that
extension). The bot will follow:

1. Bot `AGENTS.md` (always)
2. Project `AGENTS.md` (optional override / extras)
