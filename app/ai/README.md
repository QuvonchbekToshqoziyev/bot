# AI boundary

`AIOrchestrator` uses the OpenAI Responses API when the optional `ai` extra is installed. It first exposes only enabled skill metadata, asks the model to select matching skills, then exposes only tools from those selected skills. Every execution goes through `SkillRegistry.execute`, including permission and enablement checks.

If no enabled skill matches, it returns a structured `not_found` result. `OPENAI_API_KEY` is optional; the bot remains usable without AI configured.
