Build a production-oriented Telegram bot platform called "Telegram Workspace Manager".

CONTEXT

This is intended to become a general-purpose Telegram management bot. It should eventually support many independent capabilities ("skills") such as:

- channel/group backup
- message/file library management
- search
- moderation
- scheduled posts
- statistics
- duplicate detection
- content organization
- future AI-powered orchestration

The bot will initially run on a single Linux server and should be cheap to operate.

The most important architectural requirement is that features MUST be implemented as independent, enable/disable-able skills. Later, an AI agent will be given access to these skills as tools.

Do NOT implement the AI yet.

PRIMARY GOAL

Build the foundational architecture and a minimal working Telegram bot demonstrating the skill system.

TECHNICAL PREFERENCES

- Python 3.12+
- Async architecture
- Telegram Bot API
- SQLite initially
- SQLAlchemy or another lightweight ORM only if it materially improves maintainability
- Environment variables for secrets
- No unnecessary external services
- Docker is optional but should not be required for local development
- No Redis
- No PostgreSQL initially
- No LLM/API dependency
- Type hints throughout
- Structured logging
- pytest for tests

ARCHITECTURE

Create a clean separation between:

1. Telegram adapter
2. Application/core
3. Skill system
4. Permissions
5. Persistence
6. Configuration
7. Future AI/tool interface

Suggested structure:

app/
    core/
        config.py
        logging.py
        permissions.py
        router.py
        skill_registry.py
        models.py
    telegram/
        bot.py
        handlers.py
        adapter.py
    skills/
        base.py
        library/
        backup/
        moderation/
        scheduler/
        statistics/
    storage/
        database.py
        repositories/
    ai/
        README.md
        tool_interface.py
    tests/

You may change the structure if you have a materially better design, but preserve the architectural boundaries.

SKILL SYSTEM

Create a formal Skill abstraction.

Each skill should define at minimum:

- unique name
- version
- description
- configuration schema
- required permissions
- commands/actions it exposes
- execute/action interface
- lifecycle hooks if needed

Create a SkillRegistry that can:

- register skills
- discover skills
- enable/disable skills
- retrieve a skill by name
- list enabled skills
- expose machine-readable skill metadata

The registry should be the future source of truth for AI tool discovery.

A disabled skill must not be executable.

PERMISSIONS

Create centralized permission handling.

Do NOT allow skills to independently bypass authorization.

Define permissions at a sufficiently granular level, for example:

- read_messages
- send_messages
- copy_messages
- delete_messages
- edit_messages
- pin_messages
- manage_members
- schedule_messages
- manage_backup
- read_library

The exact list can evolve.

The core permission system should determine whether an operation is allowed.

The future AI must use exactly the same permission system as normal commands.

MULTI-TENANCY

Design the data model so that the bot can eventually serve many independent users.

At minimum distinguish:

- User
- Chat
- Skill configuration
- User/chat skill enablement

Do not assume the entire installation belongs to one Telegram user.

However, keep the first implementation simple.

DATABASE

Use SQLite.

Create migrations or a migration-friendly schema.

Store configuration/state in the database rather than scattering JSON configuration files throughout the project.

Do not store Telegram files themselves on the server unless a future skill explicitly requires it.

TELEGRAM

Implement:

/start
/help
/skills

/skill enable <name>
/skill disable <name>

/status

Only authorized administrators should be able to change skill configuration.

Do not hard-code a Telegram user ID.

Use environment variables or database configuration for initial administrator setup.

SECURITY

Treat the Telegram bot token as a secret.

Never log it.

Never expose it through error messages.

Validate all administrative actions.

Do not implement arbitrary shell execution.

Do not give skills unrestricted filesystem access.

Do not give future AI unrestricted Telegram API access.

AI TOOL BOUNDARY

Create a future-proof interface where every skill can expose structured actions/tools.

For example conceptually:

Skill:
    metadata()
    permissions()
    tools()

Tool:
    name
    description
    input_schema
    required_permissions
    execute(context, arguments)

The AI layer should eventually be able to discover:

enabled skills → available tools → schemas → execute through permission system.

But DO NOT connect an LLM yet.

DEMO SKILLS

Implement two minimal skills to prove the architecture.

1. StatisticsSkill

It should expose a harmless command/action that returns basic bot statistics.

2. LibrarySkill

Do not implement a full library yet.

Implement only enough to prove that a skill can:

- register itself
- expose metadata
- require permissions
- be enabled/disabled
- expose a structured tool/action
- access the database through a repository/service rather than directly manipulating unrelated application state

You may use a simple "list indexed messages" demonstration.

Do NOT spend time implementing the complete backup system yet.

TESTING

Write tests for:

- skill registration
- duplicate skill registration
- enabling/disabling
- disabled skill execution rejection
- permission rejection
- permission success
- tool metadata/schema generation
- user/chat skill configuration
- database persistence
- Telegram command routing where practical

DESIGN PRINCIPLES

1. Skills should be replaceable modules.
2. Core should not contain skill-specific business logic.
3. Skills should not depend directly on Telegram handlers.
4. Telegram should be an adapter, not the application architecture.
5. Permissions must be centralized.
6. Database access must be centralized through repositories/services.
7. AI must eventually operate through the same tool interface as normal execution.
8. Disabled skills must be genuinely inaccessible.
9. Avoid premature abstractions.
10. Prefer boring, understandable code over clever frameworks.

DEVELOPMENT PROCESS

Before writing code:

1. Inspect the repository.
2. Identify existing files and conventions.
3. Produce a concise architecture proposal.
4. Identify conflicts with the existing project.
5. Then implement incrementally.

Do not rewrite unrelated existing code.

After implementation:

1. Run tests.
2. Run type checking if configured.
3. Run linting if configured.
4. Run the bot locally or provide the exact command needed.
5. Report what was implemented.
6. Report remaining architectural risks.
7. Report the next 3 highest-value implementation steps.

IMPORTANT

Do not build a giant framework.

The goal is a small, clean foundation that can grow into a serious Telegram platform.

Do not add AI merely because the project mentions AI.

Do not implement all future features now.

The architecture should make future features easy to add without making the current system complicated.