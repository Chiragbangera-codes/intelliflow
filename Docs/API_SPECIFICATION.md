API_SPECIFICATION.md

Project: IntelliFlow AI

Version: 1.0

Document Type: REST API Specification

Protocol: HTTPS

Style: RESTful

Format: JSON

Authentication: JWT Bearer Token

Version: /api/v1

Table of Contents
API Overview
Design Principles
Base URL
Authentication
Standard Response Format
HTTP Status Codes
Error Handling
Pagination
Filtering
Sorting
Rate Limiting
Endpoint Specifications
File Upload Standards
AI API Standards
Versioning Strategy
Security Guidelines
1. API Overview

The IntelliFlow AI backend exposes REST APIs that are consumed by:

Web Frontend (Next.js)
Future Mobile App
Internal Services
Third-party Integrations (Future)

All APIs communicate using JSON except file upload endpoints.

2. Design Principles

Every API must:

Be RESTful
Be stateless
Return consistent JSON
Validate all inputs
Use proper HTTP methods
Return meaningful status codes
Never expose internal errors
Be documented using OpenAPI (Swagger)
3. Base URL

Development

http://localhost:8000/api/v1

Production

https://api.intelliflow.ai/api/v1
4. Authentication

Authentication uses JWT Bearer Tokens.

Example Header

Authorization: Bearer <JWT_TOKEN>

Access Token

Lifetime: 15 minutes

Refresh Token

Lifetime: 7 days

Public Endpoints

Login
Register
Forgot Password
Health Check

All other endpoints require authentication.

5. Standard Response Format

Every successful response

{
  "success": true,
  "message": "Request completed successfully.",
  "data": {},
  "meta": {}
}

Every error response

{
  "success": false,
  "message": "Validation failed.",
  "errors": [
    {
      "field": "email",
      "message": "Invalid email address."
    }
  ]
}
6. HTTP Status Codes
Code	Meaning
200	Success
201	Created
204	No Content
400	Bad Request
401	Unauthorized
403	Forbidden
404	Not Found
409	Conflict
422	Validation Error
429	Too Many Requests
500	Internal Server Error
7. Error Handling

Errors must never expose:

SQL queries
Stack traces
Server paths
Secrets
API keys

Instead return user-friendly messages.

8. Pagination

Every list endpoint supports

?page=1
&page_size=20

Response

{
  "success": true,
  "data": [],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total_items": 140,
    "total_pages": 7
  }
}
9. Filtering

Example

GET /documents?status=processed

Multiple filters

GET /documents?status=processed&owner=123
10. Sorting

Ascending

?sort=name

Descending

?sort=-created_at
11. Rate Limiting

Public APIs

60 requests/minute

Authenticated APIs

300 requests/minute

Admin APIs

1000 requests/minute

12. Endpoint Specifications
Health
GET /health

Purpose

Check API availability.

Authentication

No

Response

{
  "status":"ok"
}
Authentication
POST /auth/register

Purpose

Create a new account.

Body

{
  "first_name":"John",
  "last_name":"Doe",
  "email":"john@example.com",
  "password":"StrongPassword123!"
}

Response

{
  "success": true,
  "message":"Account created successfully."
}
POST /auth/login

Request

{
  "email":"john@example.com",
  "password":"password"
}

Response

{
  "success": true,
  "data": {
    "access_token":"...",
    "refresh_token":"...",
    "user": {}
  }
}
POST /auth/logout

Invalidates refresh token.

POST /auth/refresh

Returns a new access token.

Users
GET /users

List all users.

Supports:

Pagination
Filtering
Sorting
GET /users/{id}

Returns one user.

POST /users

Create user.

(Admin only)

PUT /users/{id}

Update user.

DELETE /users/{id}

Soft delete user.

Documents
POST /documents/upload

Multipart request.

Fields

file
category
tags

Response

{
  "document_id":"UUID",
  "status":"uploaded"
}
GET /documents

List uploaded documents.

Supports:

Pagination

Filtering

Sorting

Search

GET /documents/{id}

Returns metadata.

DELETE /documents/{id}

Soft delete.

OCR
POST /documents/{id}/ocr

Starts OCR.

Returns Job ID.

GET /ocr/jobs/{id}

Returns processing status.

AI Chat
POST /chat

Request

{
  "message":"Summarize invoice."
}

Response

{
  "answer":"..."
}
POST /chat/stream

Streaming AI response.

Uses Server-Sent Events (SSE).

Workflow
POST /workflows

Create workflow.

GET /workflows

List workflows.

PUT /workflows/{id}

Update.

DELETE /workflows/{id}

Archive workflow.

POST /workflows/{id}/run

Execute workflow.

Analytics
GET /analytics/dashboard

Returns dashboard KPIs.

GET /analytics/revenue

Revenue chart.

GET /analytics/employees

Employee statistics.

Reports
POST /reports/pdf

Generate PDF.

POST /reports/excel

Generate Excel.

POST /reports/csv

Generate CSV.

Notifications
GET /notifications

User notifications.

PUT /notifications/{id}/read

Mark as read.

DELETE /notifications/{id}

Delete notification.

Audit Logs
GET /audit-logs

Admin only.

Supports:

Pagination

Date filtering

Search

13. File Upload Standards

Allowed Formats

PDF
DOCX
XLSX
PNG
JPG
JPEG

Maximum Size

100 MB

Virus Scan

Future feature

14. AI API Standards

Supported Models

Llama 3.1
Gemma
Mistral

Every AI request stores:

Prompt
Response
Model
Response Time
Token Usage
15. Versioning Strategy

Current

/api/v1

Future

/api/v2

Never modify existing versions in a breaking way. Introduce new versions when necessary.

16. Security Guidelines
JWT authentication
Role-Based Access Control (RBAC)
Input validation using Pydantic
CORS configuration
Rate limiting
Secure headers
File type validation
File size validation
SQL injection prevention via ORM
XSS prevention on frontend
HTTPS only in production
API Naming Rules
Good	Avoid
/users	/getUsers
/documents/{id}	/documentById
/workflows/{id}/run	/executeWorkflow

Use:

Nouns for resources
HTTP methods for actions
Plural resource names
API Lifecycle
Client
   │
   ▼
HTTP Request
   │
   ▼
API Route
   │
   ▼
Authentication
   │
   ▼
Validation
   │
   ▼
Service Layer
   │
   ▼
Repository
   │
   ▼
Database / AI / Storage
   │
   ▼
Response Formatter
   │
   ▼
Client
OpenAPI / Swagger Requirements

The backend must automatically generate OpenAPI documentation.

Requirements:

Every endpoint has a summary.
Every endpoint has a description.
Request schemas are documented.
Response schemas are documented.
Authentication requirements are declared.
Example requests and responses are included.
Testing Requirements

Every endpoint should have:

Unit tests
Integration tests
Authentication tests (where applicable)
Validation tests
Error handling tests

Target API test coverage: ≥90%.

Notes for the AI Coding Agent
Follow REST principles consistently.
Keep route handlers thin; business logic belongs in services.
Validate all incoming data with Pydantic.
Use dependency injection for shared resources.
Return the standard response envelope for all endpoints.
Do not expose stack traces or internal implementation details.
Keep API versioning stable and backward compatible.