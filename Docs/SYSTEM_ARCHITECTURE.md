SYSTEM_ARCHITECTURE.md

Project: IntelliFlow AI

Version: 1.0

Document Type: Technical Architecture Specification

Owner: Solution Architect

Table of Contents
Introduction
Architecture Goals
High-Level Architecture
Technology Stack
Frontend Architecture
Backend Architecture
Database Architecture
AI Architecture
Authentication Architecture
Workflow Engine
Notification System
Logging & Monitoring
Deployment Architecture
Security Architecture
Scalability
Error Handling
Future Architecture
1. Introduction

This document defines the complete technical architecture of IntelliFlow AI.

Its purpose is to ensure that every developer, AI coding agent, and future contributor follows the same architectural principles.

The architecture is designed to be:

Modular
Scalable
Secure
Cloud Ready
Easy to Maintain
Easy to Test
Production Grade
2. Architecture Goals

The system must provide:

Separation of concerns
Modular services
Independent feature development
High performance
Security by default
Easy deployment
Easy testing
Cloud compatibility
Maintainability
3. High-Level Architecture
                   Internet
                       │
                 Cloudflare CDN
                       │
                    HTTPS
                       │
                     Nginx
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
  Next.js Frontend             FastAPI Backend
                                     │
       ┌─────────────────────────────┼──────────────────────────┐
       ▼                             ▼                          ▼
 PostgreSQL                     Redis Cache                Celery Workers
       │                             │                          │
       └──────────────┬──────────────┴──────────────┬───────────┘
                      ▼                             ▼
               AI Services                    Object Storage
         (LLM + OCR + RAG)             (Local / S3 / Supabase)
4. Technology Stack
Frontend
Next.js 15
React
TypeScript
Tailwind CSS
Shadcn UI
React Query
Zustand
React Hook Form
Zod
Backend
FastAPI
Python 3.12
SQLAlchemy
Alembic
Pydantic
Celery
Database
PostgreSQL
Cache
Redis
AI
Ollama
Llama 3.1
Sentence Transformers
FAISS
LangChain
Tesseract OCR
DevOps
Docker
Docker Compose
GitHub Actions
Nginx
Cloudflare
5. Frontend Architecture

The frontend follows a feature-based architecture.

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

public/
Responsibilities
App Router

Handles routing.

Components

Reusable UI components.

Example

Button

Modal

Table

Card

Sidebar

Navbar

Features

Each business module lives inside features.

Example

features/

auth/

dashboard/

documents/

analytics/

workflow/

chat/
Services

Responsible for API calls.

Frontend never directly calls the backend inside components.

Instead:

Component

↓

Service

↓

API

Store

Global state.

Uses Zustand.

Stores:

Current User

Theme

Notifications

Language

6. Backend Architecture

Backend follows Clean Architecture principles.

backend/

app/

api/

core/

models/

schemas/

repositories/

services/

workers/

middleware/

utils/

tests/
Responsibilities
API Layer

Only receives requests.

Returns responses.

No business logic.

Service Layer

Contains business logic.

Example

Upload document

↓

Validate

↓

Store

↓

Trigger OCR

↓

Return response

Repository Layer

Responsible for database queries.

Only repositories communicate with PostgreSQL.

Models

SQLAlchemy models.

Schemas

Pydantic validation.

Core

Configuration

Security

Settings

Dependencies

Logging

Request Flow
Browser

↓

API Route

↓

Validation

↓

Service

↓

Repository

↓

Database

↓

Repository

↓

Service

↓

Response

↓

Browser
7. Database Architecture

Database engine:

PostgreSQL

Migration tool:

Alembic

ORM:

SQLAlchemy

Naming convention:

snake_case

Primary key:

UUID

Relationships:

Foreign Keys

Indexes:

Frequently searched columns

Soft Delete:

Supported

Audit Fields:

created_at

updated_at

deleted_at

8. AI Architecture
User

↓

Upload PDF

↓

OCR

↓

Extract Text

↓

Chunk Text

↓

Embeddings

↓

FAISS

↓

User asks question

↓

Similarity Search

↓

LLM

↓

Answer
Components

OCR

Extracts text.

Chunking

Splits documents.

Embedding

Converts text into vectors.

Vector Database

Stores embeddings.

LLM

Generates final response.

9. Authentication Architecture

Authentication uses JWT.

User

↓

Login

↓

JWT Token

↓

Browser

↓

Authorization Header

↓

Backend

↓

Validate Token

↓

Access Granted

Access Token

15 minutes

Refresh Token

7 days

Passwords

Argon2 hashing

10. Workflow Engine
Trigger

↓

Conditions

↓

Actions

↓

Notifications

↓

Database Update

↓

Complete

Triggers

Document Uploaded

Employee Created

Invoice Approved

Report Generated

11. Notification System

Channels

Email

In-App

Future

SMS

Push

WhatsApp

Notification flow

Event

↓

Queue

↓

Worker

↓

Send

↓

Log

12. Logging & Monitoring

Logging Library

Python logging

Log Levels

DEBUG

INFO

WARNING

ERROR

CRITICAL

Log Format

Timestamp

User

Request ID

Route

Status

Execution Time

Monitoring

Health Endpoint

GET /health

Returns

{
 "status":"ok"
}

Future

Prometheus

Grafana

13. Deployment Architecture
Internet

↓

Cloudflare

↓

Nginx

↓

Next.js

↓

FastAPI

↓

Redis

↓

PostgreSQL

↓

Workers

↓

Object Storage

Everything runs inside Docker containers.

Docker Containers
frontend

backend

postgres

redis

worker

nginx
14. Security Architecture

Security layers

HTTPS

↓

Cloudflare

↓

Nginx

↓

JWT

↓

RBAC

↓

Validation

↓

SQLAlchemy ORM

↓

Database

Protection

Rate Limiting

XSS

SQL Injection

CSRF (where applicable)

Secure Headers

File Validation

Audit Logging

15. Scalability

Horizontal Scaling

Multiple backend instances

↓

Shared Redis

↓

Shared PostgreSQL

↓

Load Balancer

Frontend

Stateless

Backend

Stateless

Database

Master + Read Replicas (future)

16. Error Handling

Standard Response

{
  "success": false,
  "message": "Validation failed",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}

HTTP Status Codes

200

201

400

401

403

404

409

422

500

17. Development Principles
Feature-first architecture
Keep business logic out of API routes
Repository pattern for database access
Dependency injection for shared services
Configuration via environment variables
Stateless backend services
Background tasks for long-running jobs
Strong typing with TypeScript and Python type hints
Modular, testable code
18. Future Architecture

The system should be designed so it can evolve without major rewrites:

Kubernetes deployment
Microservices (if needed)
Multi-tenant SaaS
Event-driven architecture with Kafka
Distributed caching
Separate AI service
Dedicated analytics service
Multi-region deployment
Real-time collaboration
Mobile applications
Architecture Decision Records (ADR)

Document key architectural choices for future contributors:

Decision	Reason
FastAPI	High performance, async support, Python ecosystem
Next.js	SSR, routing, modern React features
PostgreSQL	Mature relational database with JSON support
Redis	Fast caching and task queue support
Docker	Consistent development and deployment environments
Ollama	Local AI models with no API cost during development
FAISS	Efficient vector similarity search for RAG
Notes for the AI Coding Agent
This document is the technical source of truth.
Follow the defined layers and responsibilities.
Do not bypass the service or repository layers.
Do not introduce architectural changes without updating this document.
Build features incrementally according to the Development Roadmap.
Favor maintainability and clarity over premature optimization.