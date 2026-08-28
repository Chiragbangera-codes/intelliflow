CODING_STANDARDS.md

# IntelliFlow AI

Version: 1.0

Document Type: Engineering Coding Standards

---

# Table of Contents

1. Purpose
2. General Principles
3. Project Structure
4. Naming Conventions
5. Python Standards
6. TypeScript Standards
7. React Standards
8. FastAPI Standards
9. Database Standards
10. API Standards
11. Error Handling
12. Logging Standards
13. Configuration Management
14. Security Standards
15. Testing Standards
16. Documentation Standards
17. Git Standards
18. Performance Standards
19. Code Review Checklist
20. AI Coding Rules

---

# 1. Purpose

This document defines the coding standards that every contributor and AI coding agent must follow.

Goals:

- Maintain consistency
- Improve readability
- Reduce bugs
- Improve maintainability
- Make onboarding easier
- Ensure production-quality code

---

# 2. General Principles

Always write code that is:

- Readable
- Maintainable
- Testable
- Modular
- Reusable
- Secure
- Well documented

Avoid:

- Duplicate code
- Deep nesting
- Magic numbers
- Hardcoded secrets
- Global mutable state

---

# 3. Project Structure

Frontend

frontend/

app/

components/

features/

hooks/

services/

store/

types/

utils/

styles/

Backend

backend/

app/

api/

core/

models/

schemas/

repositories/

services/

middleware/

workers/

utils/

tests/

---

# 4. Naming Conventions

Folders

snake_case

Example

document_service

workflow_engine

Files

snake_case

Example

user_service.py

document_repository.py

Classes

PascalCase

Example

UserService

DocumentRepository

Variables

snake_case (Python)

camelCase (TypeScript)

Constants

UPPER_SNAKE_CASE

Example

MAX_UPLOAD_SIZE

JWT_SECRET

Functions

Python

get_user()

create_document()

TypeScript

getUser()

createDocument()

Booleans

Always begin with

is

has

can

should

Example

isAdmin

hasPermission

canUpload

---

# 5. Python Standards

Python Version

3.12+

Style Guide

PEP8

Formatting

Black

Import Sorting

isort

Linting

Ruff

Type Checking

mypy

Every function must have:

Type hints

Docstrings

Example

def create_user(
    user: UserCreate
) -> User:
    """Create a new user."""
    ...

Maximum function length

50 lines

Maximum file length

400 lines

---

# 6. TypeScript Standards

Strict Mode

Enabled

Avoid

any

Prefer

unknown

Use Interfaces

For API responses

Use Types

For unions

Components

Functional only

Never use class components.

---

# 7. React Standards

Use

Server Components

Whenever possible.

Client Components

Only when necessary.

Use

React Query

For server state.

Use

Zustand

For global state.

Never call APIs directly inside UI components.

Always use service layer.

---

# 8. FastAPI Standards

Routes

Only handle

Request

↓

Validation

↓

Service Call

↓

Response

Business logic

Never inside routes.

Dependency Injection

Required

Response Models

Required

Validation

Required

---

# 9. Database Standards

ORM

SQLAlchemy

Never write raw SQL unless absolutely necessary.

Use

UUID

For primary keys.

Every table must include

created_at

updated_at

deleted_at

Use transactions

For multi-step operations.

---

# 10. API Standards

Every endpoint

Must have

Summary

Description

Request Model

Response Model

Status Codes

Authentication

Example

GET /users

POST /documents

PUT /workflow/{id}

DELETE /notifications/{id}

---

# 11. Error Handling

Never expose

Stack traces

SQL errors

Secrets

Always return

Consistent JSON

Example

{
  "success": false,
  "message": "Validation failed."
}

Use

Custom exceptions

Global exception handler

---

# 12. Logging Standards

Every request

Log

Timestamp

Method

Path

User

Response Time

Status

Errors

Include stack trace internally.

Never expose to users.

---

# 13. Configuration

Never hardcode

Passwords

Keys

URLs

Secrets

Always use

.env

Access configuration through

Settings class

Never call os.getenv()

Directly throughout the codebase.

---

# 14. Security Standards

Passwords

Argon2

JWT

Access + Refresh

Validate

Every request

Use HTTPS

In production

Validate uploads

Validate MIME types

Validate file size

Rate limiting

Required

---

# 15. Testing Standards

Backend

pytest

Frontend

Vitest

E2E

Playwright

Coverage

90%+

Every bug fix

Requires a regression test.

---

# 16. Documentation Standards

Every public function

Must have docstring.

Complex logic

Requires comments.

README

Must remain updated.

Swagger

Must remain updated.

---

# 17. Git Standards

Branch

feature/document-upload

Commit

feat(document): add upload service

Never commit

.env

Secrets

node_modules

__pycache__

Generated files

---

# 18. Performance Standards

Avoid

N+1 queries

Lazy loading

Where appropriate

Pagination

Required

Caching

Redis

Background jobs

Celery

Optimize

Large queries

Large uploads

AI requests

---

# 19. Code Review Checklist

Readable

Typed

Documented

Tested

Secure

Performant

No duplication

No hardcoded values

No dead code

No unnecessary dependencies

Architecture respected

---

# 20. AI Coding Rules

Claude Sonnet must:

- Read every document before generating code.
- Never invent architecture.
- Never skip validation.
- Never skip typing.
- Never bypass the service layer.
- Never access the database directly from API routes.
- Never implement features outside the current milestone.
- Prefer clarity over cleverness.
- Explain major architectural choices in comments where useful.
- Keep commits small and focused.
- Refactor instead of duplicating logic.
- Ask for clarification if requirements are ambiguous.

---

# Code Quality Targets

Cyclomatic Complexity

< 10 per function

Function Length

< 50 lines

Class Length

< 300 lines

File Length

< 400 lines

API Response Time

< 300 ms

Test Coverage

≥ 90%

Lint Errors

0

Type Errors

0

---

# Required Development Tools

Python

- Black
- Ruff
- isort
- mypy
- pytest

TypeScript

- ESLint
- Prettier
- TypeScript Strict Mode
- Vitest

Git Hooks

- pre-commit
- lint-staged

---

# Final Rule

If there is a conflict between generated code and these coding standards, the coding standards always take precedence.