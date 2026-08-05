# Signer Backup and Restore Runbook

> Status: operational draft. A staging drill with the production-equivalent AWS KMS and
> PostgreSQL configuration is required before launch.

## What must be backed up

The signer database is the authoritative store for encrypted wallet envelopes. Back up the
entire signer PostgreSQL database using encrypted managed backups and point-in-time recovery.
The application database is not a substitute: it contains only wallet addresses and opaque
`signer_key_id` references.

AWS KMS key material is not exported. Protect the configured KMS key against deletion, retain
its key policy and aliases as infrastructure configuration, and enable the provider's audit
trail. The encryption context is integrity metadata, not a secret.

## Preconditions

- Stop wallet creation for the target environment.
- Confirm the target is non-production for drills.
- Record the signer database backup identifier, KMS key ARN, application environment, chain ID,
  and change-ticket/correlation ID. Never record plaintext keys or decrypted data keys.
- Ensure the operator can restore PostgreSQL and call only `kms:GenerateDataKey`, `kms:Decrypt`,
  `kms:DescribeKey`, and the minimum database operations required for the drill.

An identity policy for the drill should scope these actions to the single non-production key:

```json
{
  "Effect": "Allow",
  "Action": ["kms:DescribeKey", "kms:GenerateDataKey", "kms:Decrypt"],
  "Resource": "<non-production-kms-key-arn>"
}
```

The KMS key policy must also allow the drill identity. Do not use `Resource: "*"` or grant
administrative KMS permissions merely to make the drill pass.

## Restore procedure

1. Restore the signer database backup into a new isolated database.
2. Deploy the same or a compatible signer release with a new internal authentication secret.
3. Configure the restored database URL, original KMS key ARN, AWS region, and least-privilege AWS
   credentials. Do not expose the service publicly.
4. Run `alembic -c signer_alembic.ini upgrade head` against the restored database.
5. Select a pre-approved test `signer_key_id`, workspace ID, expected address, environment, and
   chain ID from the application database.
6. Call the signer's non-production `/v1/restore/verify` endpoint through the private network with
   its authenticated request envelope. The endpoint must return the expected address.
7. Repeat with a wrong workspace ID. The request must return a generic not-found response.
8. Confirm logs, traces, database query logs, and error output contain no private key, decrypted
   data key, ciphertext, nonce, authentication secret, or full request body.
9. Destroy the isolated restored database after retaining only the drill result and audit evidence.
10. Restore normal wallet creation only after the signer readiness check succeeds.

## Failure handling

- Address mismatch: stop immediately, quarantine the restored database, and open a security
  incident. Do not retry signing or rotate application references.
- KMS access denied: validate region, key state, key policy, credentials, and the exact encryption
  context. Do not weaken the key policy to make the drill pass.
- Missing envelope: compare backup time with wallet creation time and application audit history.
- Suspected exposure: disable wallet creation, rotate service authentication and AWS credentials,
  preserve audit evidence, and follow the secret-exposure incident process.

## Drill evidence

Record date, environment, backup identifier, signer release, opaque signer key ID, expected and
derived address, negative isolation-test result, log-review result, operator, and reviewer. Record
no secret or encrypted payload values.
