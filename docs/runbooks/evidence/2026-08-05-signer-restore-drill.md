# Signer Restore Drill Evidence — 2026-08-05

- Environment: non-production `development`
- Signer release: working tree based on commit `9ea2ff3`
- KMS: real non-production AWS KMS symmetric encryption key; ARN intentionally omitted
- Source database: isolated local Docker PostgreSQL signer service
- Restored database: temporary isolated `copymint_signer_restore_drill`
- Backup method: PostgreSQL custom-format `pg_dump` and `pg_restore`
- Signer key ID: `019fd423-2123-74c4-92ea-3feac0abb763`
- Workspace ID: `019fd423-20e8-79d7-baee-a2c7f99fe36f`
- Expected address: `0xbaa8Ee53CF6D37d46395263164e589541FeBdC00`
- Derived address: `0xbaa8Ee53CF6D37d46395263164e589541FeBdC00`
- KMS health: passed
- Creation idempotency: passed
- Restore from copied database: passed
- Wrong-workspace restore rejection: passed
- Application-credential signer-database isolation: passed
- Schema review: encrypted envelope fields only; no plaintext private-key column
- Output review: successful drill output contained only sanitized result metadata
- Operator: Codex under CopyMint owner authorization
- Reviewer: Wale, CopyMint owner
- Cleanup: temporary restored database, backup artifact, and source drill envelope removed

No private key, decrypted data key, ciphertext, nonce, authentication secret, AWS credential, AWS
account identifier, or KMS key ARN is recorded in this evidence.
