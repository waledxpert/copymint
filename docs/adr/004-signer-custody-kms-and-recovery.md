# ADR-004: Signer custody, AWS KMS and recovery

- Status: Accepted
- Date: 2026-08-05
- Owners: Product owner, security, signer engineering

## Context

CopyMint creates Ethereum execution wallets for unrelated users. Users must not see one another's wallets, and private keys must never pass through Telegram, the bot/API process, normal application tables, logs, or error reporting. Render services have ephemeral filesystems by default, so local files cannot be key storage.

Release 1 needs wallet addresses for eligibility and paper simulation but must not sign or broadcast. Later signing must not require redesigning custody.

## Decision

Run a dedicated signer as a Render private service. It is the only process permitted to create or decrypt Ethereum private key material. The bot/API stores only public address, status, and an opaque `signer_key_id`.

Use AWS KMS with a symmetric customer-managed key for envelope encryption:

1. The signer requests an AES-256 data key with `GenerateDataKey`.
2. The signer generates a valid secp256k1 private key using the operating system CSPRNG.
3. The signer encrypts the private key with AES-256-GCM using the plaintext data key.
4. Additional authenticated data binds the envelope version, signer key ID, workspace ID, chain ID, and public address.
5. The signer stores the encrypted private key, encrypted data key, nonce, tag, KMS key ARN/version, public address, and metadata in signer-owned durable storage.
6. Plaintext private/data-key buffers are released/overwritten on a best-effort basis immediately after use.
7. Only the public address and opaque signer key ID return to the application.

The AWS KMS encryption context includes `environment`, `workspace_id`, `chain_id`, `signer_key_id`, and `purpose`. Decrypt calls must provide the exact same context. IAM limits the signer role to the one environment-specific KMS key and required operations.

Python cannot guarantee complete memory zeroization. Isolation, short plaintext lifetime, least-privilege KMS access, process hardening, limited wallet funds, and later signer policy caps address this residual risk. This limitation is documented rather than hidden.

## Release 1 signer surface

Allowed:

- health/readiness;
- idempotent wallet creation;
- public address verification;
- controlled non-production restore verification.

Unavailable:

- arbitrary decrypt;
- private-key export;
- signing;
- raw transaction return;
- broadcast;
- seed phrase creation or display.

Signing routes return a release-lock error and have a regression test proving they cannot be enabled with an environment variable.

## Authentication and isolation

- The signer has no public URL.
- Calls use private networking plus an authenticated, timestamped request envelope.
- The envelope contains action, caller, workspace, chain, idempotency key, correlation ID, body hash, and expiry.
- Replays and expired requests fail.
- A signer key ID is permanently bound to one workspace, environment, chain, and public address.
- Cross-workspace key references fail as not found and emit a security event.
- Signer logs are allowlist-based; arbitrary request bodies are never logged.

## Storage and recovery

Signer ciphertext lives in dedicated signer-owned PostgreSQL tables/credentials, not local disk. Backups require both the encrypted database material and authorized access to the environment-specific KMS key.

Before production wallet creation:

- enable KMS key rotation where compatible with the recovery design;
- protect against accidental KMS key deletion with owner-controlled process and waiting period;
- create encrypted PostgreSQL backups and verify restoration;
- restore a non-production wallet and verify its derived address;
- document staff access, incident response, and user custody terms;
- decide the out-of-band user recovery/export policy.

Release 1 does not export private keys. Users are warned not to fund wallets until custody and recovery notices are accepted. Revoking Telegram access does not delete a wallet or its recovery evidence.

## Consequences

- A database leak alone does not reveal private keys.
- A bot token or application compromise alone cannot retrieve key plaintext.
- AWS KMS becomes a critical external dependency and recovery component.
- The signer remains custodial; operational and legal responsibilities require explicit notices.
- Real signing still requires an independent typed-plan policy introduced in Release 2.

## Rejected alternatives

- Plaintext keys or seed phrases in PostgreSQL: prohibited.
- Render environment variables containing user private keys: prohibited.
- Persistent local disk as the key vault: rejected for isolation, backup, and scaling concerns.
- Sending keys through Telegram: prohibited.
- One global deterministic mnemonic: rejected because one secret compromises every user.
- Enabling arbitrary-hash signing: rejected because the signer must eventually validate structured plans.

## Verification

- Database, log, Telegram, and error snapshots contain no plaintext keys.
- Repeated wallet-creation idempotency keys return one wallet.
- Wrong environment/workspace/chain encryption contexts fail decryption.
- Restored ciphertext derives the stored public address.
- The application database credential cannot read signer ciphertext tables.
- Release 1 signing and broadcast contract tests always fail closed.

## References

- https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html
- https://docs.aws.amazon.com/kms/latest/developerguide/kms-cryptography.html
- https://render.com/docs/private-services
- https://render.com/docs/deploys
