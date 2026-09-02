# Phase 11 — Advanced Document Intelligence & Enterprise Document Management

## 1. Executive Summary

Milestone 11 delivers a unified, enterprise-grade Document Intelligence and Document Management System (DMS) for **IntelliFlow AI**. It transforms raw uploaded files into governed, immutable, AI-synthesized organizational knowledge assets with strict multi-tenant authorization, version control, granular access sharing, lifecycle policies, and grounded conversational intelligence.

---

## 2. Core Architecture & System Invariants

```
                            ┌─────────────────────────────────────────────────────────┐
                            │                 Next.js 16 Frontend UI                  │
                            │  /documents  •  /documents/[id]  •  Modals & AI Panels  │
                            └────────────────────────────┬────────────────────────────┘
                                                         │ HTTPS / JSON & Multipart
                                                         ▼
                            ┌─────────────────────────────────────────────────────────┐
                            │                 FastAPI API Router                      │
                            │              /api/v1/documents (31 Routes)              │
                            └──────┬─────────────────────┬─────────────────────┬──────┘
                                   │                     │                     │
                                   ▼                     ▼                     ▼
┌─────────────────────────────────────────┐ ┌─────────────────────────┐ ┌───────────────────────────────┐
│          DocumentAccessService          │ │     DocumentService     │ │       DocumentAIService       │
│ • Centralized Synchronous Permission    │ │ • Version Revisions     │ │ • Grounded Executive Summary  │
│ • Single-Query SQL Auth Filter Builder  │ │ • Lifecycle Transitions │ │ • Document-Scoped AI Chat     │
│ • Eager-loaded O(1) in-memory eval      │ │ • Granular User Shares  │ │ • Prompt-Injection Defenses   │
│ • Timezone-safe grant expiration        │ │ • Bulk Batch Operations │ │ • Passage Citation Inspector  │
└─────────────────────────────────────────┘ └────────────┬────────────┘ └───────────────┬───────────────┘
                                                         │                              │
                                   ┌─────────────────────┴──────────────────────────────┴─────┐
                                   │                                                          │
                                   ▼                                                          ▼
               ┌──────────────────────────────────────┐                   ┌──────────────────────────────────────┐
               │         PostgreSQL Database          │                   │            Celery Worker             │
               │  • documents (Enterprise Columns)    │                   │  • tasks.process_document_ocr        │
               │  • document_versions (Immutable)     │                   │  • tasks.check_document_expirations  │
               │  • document_shares (Access Grants)   │                   └──────────────────────────────────────┘
               │  • document_chunks (Version-aware)   │
               │  • audit_logs (Complete Audit Trail) │
               └──────────────────────────────────────┘
```

### System Invariants
1. **Immutable Non-Destructive Versioning**: Every file modification or upload creates a new revision record in `document_versions`. Old files remain unchanged on disk and can be restored or downloaded at any time.
2. **Centralized Authorization (`DocumentAccessService`)**:
   - Zero bypass: No document metadata, preview stream, version download, chunk search result, or AI prompt may execute without passing centralized authorization.
   - Evaluation hierarchy:
     1. System Administrators (`admin` role) have unconditional `MANAGE` access.
     2. Document Owner (`owner_id == actor.id`) has `MANAGE` access.
     3. Direct Active Access Grants (`document_shares` active row) grant `view`, `download`, `edit`, or `manage`.
     4. Department Members (`department_id == actor.department_id`): `view` for `public`, `internal`, and `confidential` documents.
     5. Public documents: `view` access for all active users.
     6. Default: `None` (Access Denied / 403 Forbidden / filtered out of queries).
3. **Grounded AI Synthesis & Security**:
   - Document-level AI summaries and chat are strictly constrained to chunks of the target document.
   - Text chunks are placed inside `<DOCUMENT_CONTEXT>` tags and treated as untrusted data.
   - Full citation tracking links every generated answer to chunk numbers and text excerpts.
4. **Soft Deletion with Historical Integrity**: Soft-deleting a document sets `deleted_at` timestamp while preserving all version history, chunks, and audit logs.

---

## 3. Database Schema & Alembic Migration

### `005_document_intelligence.py`

#### Table: `documents`
- `title` (VARCHAR 255) — Human-readable document title
- `description` (TEXT) — Abstract or summary description
- `category` (VARCHAR 100) — Business category (e.g. "Legal", "Finance")
- `document_type` (VARCHAR 50) — Document classification (e.g. "Contract", "Invoice", "Policy")
- `tags` (JSONB / JSON) — Tag array for categorization and filtering
- `confidentiality` (VARCHAR 30) — `public`, `internal`, `confidential`, `restricted`
- `lifecycle_status` (VARCHAR 30) — `draft`, `active`, `archived`, `expired`, `deleted`
- `retention_period_days` (INTEGER) — Retention policy in days
- `activated_at` (TIMESTAMPTZ) — Timestamp of transition to active
- `archived_at` (TIMESTAMPTZ) — Timestamp of transition to archived
- `expires_at` (TIMESTAMPTZ) — Document expiration timestamp
- Relationships: `versions` (One-to-Many to `DocumentVersion`), `shares` (One-to-Many to `DocumentShare`).

#### Table: `document_versions`
- `id` (UUID, Primary Key)
- `document_id` (UUID, Foreign Key to `documents.id` ON DELETE CASCADE)
- `version_number` (INTEGER, Not Null)
- `file_name` (VARCHAR 255, Not Null)
- `storage_path` (VARCHAR 1024, Not Null)
- `file_type` (VARCHAR 100)
- `file_size` (BIGINT)
- `checksum` (VARCHAR 64) — SHA-256 hash
- `created_by` (UUID, Foreign Key to `users.id`)
- `is_current` (BOOLEAN, Default True)
- `change_summary` (TEXT)
- `created_at` (TIMESTAMPTZ)
- Constraint: `uq_document_versions_doc_ver` (`document_id`, `version_number`)

#### Table: `document_shares`
- `id` (UUID, Primary Key)
- `document_id` (UUID, Foreign Key to `documents.id` ON DELETE CASCADE)
- `user_id` (UUID, Foreign Key to `users.id` ON DELETE CASCADE)
- `granted_by` (UUID, Foreign Key to `users.id`)
- `permission` (VARCHAR 20, Not Null) — `view`, `download`, `edit`, `manage`
- `expires_at` (TIMESTAMPTZ, Nullable)
- `created_at` (TIMESTAMPTZ)
- `revoked_at` (TIMESTAMPTZ, Nullable)
- Constraint: `uq_document_shares_doc_user` (`document_id`, `user_id`)

#### Table: `document_chunks`
- `version_id` (UUID, Foreign Key to `document_versions.id` ON DELETE SET NULL)
- `version_number` (INTEGER, Default 1)

---

## 4. API Endpoints Reference

### Document Operations
| Method | Endpoint | Description | Required Perm |
|---|---|---|---|
| `POST` | `/api/v1/documents/upload` | Multipart file upload & initial version creation | Authenticated |
| `GET` | `/api/v1/documents` | List authorized documents with multi-filter query | View (filtered) |
| `GET` | `/api/v1/documents/{id}` | Retrieve document metadata | View |
| `PATCH` | `/api/v1/documents/{id}` | Update document metadata | Edit |
| `DELETE` | `/api/v1/documents/{id}` | Soft-delete document | Manage |
| `GET` | `/api/v1/documents/{id}/download` | Secure streaming binary download | Download |
| `GET` | `/api/v1/documents/{id}/preview` | Secure in-browser content preview | View |

### Versioning
| Method | Endpoint | Description | Required Perm |
|---|---|---|---|
| `POST` | `/api/v1/documents/{id}/versions` | Upload replacement version file | Edit |
| `GET` | `/api/v1/documents/{id}/versions` | List all revisions ordered newest first | View |
| `GET` | `/api/v1/documents/{id}/versions/{v_id}` | Get single version metadata | View |
| `POST` | `/api/v1/documents/{id}/versions/{v_id}/restore` | Restore historical version as new current revision | Edit |
| `GET` | `/api/v1/documents/{id}/versions/{v_id}/download` | Download specific historical version file | Download |

### Access Grants & Sharing
| Method | Endpoint | Description | Required Perm |
|---|---|---|---|
| `POST` | `/api/v1/documents/{id}/shares` | Grant user access permission | Manage |
| `GET` | `/api/v1/documents/{id}/shares` | List active user access grants | Manage / Self |
| `PATCH` | `/api/v1/documents/{id}/shares/{s_id}` | Update share permission or expiration | Manage |
| `DELETE` | `/api/v1/documents/{id}/shares/{s_id}` | Revoke access grant | Manage |

### Lifecycle Management
| Method | Endpoint | Description | Required Perm |
|---|---|---|---|
| `POST` | `/api/v1/documents/{id}/activate` | Activate draft or restored document | Manage |
| `POST` | `/api/v1/documents/{id}/archive` | Archive active document | Manage |
| `POST` | `/api/v1/documents/{id}/restore` | Restore archived/expired document | Manage |
| `POST` | `/api/v1/documents/{id}/expire` | Manually mark document as expired | Manage |

### Bulk Operations
| Method | Endpoint | Description | Required Perm |
|---|---|---|---|
| `POST` | `/api/v1/documents/bulk/archive` | Batch archive documents | Manage (per item) |
| `POST` | `/api/v1/documents/bulk/restore` | Batch restore documents | Manage (per item) |
| `POST` | `/api/v1/documents/bulk/delete` | Batch soft-delete documents | Manage (per item) |
| `POST` | `/api/v1/documents/bulk/tag` | Batch append/replace tags | Edit (per item) |
| `POST` | `/api/v1/documents/bulk/share` | Batch grant user access | Manage (per item) |

### AI Intelligence & Activity
| Method | Endpoint | Description | Required Perm |
|---|---|---|---|
| `POST` | `/api/v1/documents/{id}/ai/summary` | Executive summary with cited chunk sources | View |
| `POST` | `/api/v1/documents/{id}/ai/chat` | Grounded document-scoped conversational Q&A | View |
| `GET` | `/api/v1/documents/{id}/activity` | Sanitized audit activity timeline | View |

---

## 5. Background Tasks

### Expiration Task (`tasks.check_document_expirations`)
- Periodic Celery beat task running every hour.
- Identifies active documents where `expires_at <= datetime.now(UTC)`.
- Updates `lifecycle_status = 'expired'`.
- Records `document.expired` audit event.
- Dispatches `Document Expired` in-app notification to the document owner.

---

## 6. Frontend Workspace

- **`/documents`**: Multi-dimensional search & filtering (search query, lifecycle filter, confidentiality filter, shared-with-me toggle, sort options), selection checkboxes, floating batch action toolbar, quick modals for AI summary, AI chat, sharing, and version history.
- **`/documents/[id]`**: Enterprise workspace featuring 6 rich tabs:
  1. *Overview & Properties* (properties table, compliance metadata, tags, lifecycle actions).
  2. *Preview & Extracted Text* (inline PDF/image/text viewer with raw OCR chunks inspector).
  3. *Version History* (complete revision tree with restore and download actions).
  4. *Document AI Intelligence* (one-click executive summary and interactive grounded chat).
  5. *Access Grants & Sharing* (user-level permissions and expiration windows).
  6. *Activity Audit Timeline* (chronological audit history).
