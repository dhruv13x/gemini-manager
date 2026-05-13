# Gemini Manager Mandates

## Core Principles
- **Machine-Time Authoritative**: All timestamps and schedules MUST be calculated and displayed in the user's local system timezone.
- **Identity Isolation**: Never leak session tokens or account emails in logs or crash reports.
- **Atomic Operations**: All file manipulations (backups, restores, config updates) MUST be atomic and safe against concurrent execution using lockfiles.

## Backup Naming Convention
Backups MUST follow this naming pattern for automatic discovery:
`YYYY-MM-DD_HHMMSS-<email>.gemini-manager.tar.gz[.gpg]`

- The timestamp SHOULD represent the `next_available_at` (reset time) for the account.
- Metadata MUST be stored in a sidecar file named:
  `YYYY-MM-DD_HHMMSS-<email>.gemini-manager.metadata.json`

## Cloud Storage (B2/S3)
- Cloud storage is the source of truth for account health in multi-machine environments.
- Every `gm status` or `gm backup` SHOULD sync metadata to the cloud if configured.
- `gm cooldown` SHOULD prioritize cloud-synced metadata.
