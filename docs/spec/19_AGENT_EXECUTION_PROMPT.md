# 19 --- Initial Prompt for Codex / Claude Code / Copilot

You are implementing the Agentic Knowledge & Assessment Harness.

Read these files before changing code: - 00_MASTER_SPEC.md -
01_ARCHITECTURE.md - 02_DATABASE_SCHEMA.md - 03_API_CONTRACTS.md -
17_REPO_AND_ENGINEERING.md - 18_IMPLEMENTATION_BACKLOG.md

## Execution protocol

1.  Inspect the repository.
2.  Determine the next incomplete task in
    `18_IMPLEMENTATION_BACKLOG.md`.
3.  Read only the specifications relevant to that task.
4.  Implement the smallest vertical slice.
5.  Add unit/integration tests.
6.  Run formatting, linting, type checks and tests.
7.  Fix failures.
8.  Update documentation/configuration if behavior changed.
9.  Report:
    -   files changed;
    -   tests added;
    -   commands executed;
    -   acceptance criteria satisfied;
    -   known limitations.

## Hard constraints

-   Python 3.12+.
-   Do not hard-code LLM providers/models.
-   Do not put provider SDK calls in domain code.
-   Do not store source binaries in PostgreSQL.
-   Do not discard duplicate source artifacts.
-   Do not generate knowledge without provenance.
-   Do not fabricate citations.
-   Do not require paid APIs for tests.
-   Do not implement microservices unless explicitly requested.
-   Do not change architecture decisions silently.

## First task

If the repository is empty, implement TASK-001 and TASK-002 only.

Stop after those tasks and report results. Do not jump ahead.
