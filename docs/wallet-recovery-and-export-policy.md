# Wallet Recovery and Export Policy

> Status: product direction approved on 2026-08-05. Operational implementation remains disabled
> until its dedicated security review and drill pass.

CopyMint will support two out-of-band options for an execution wallet:

1. **Account recovery** — after identity re-verification, restore access to the existing private
   workspace and its wallet references without changing or exposing the wallet key.
2. **Wallet export** — after stronger identity verification and a fresh confirmation, provide an
   industry-standard encrypted Ethereum keystore file protected by a user-selected password.

Neither option is delivered through Telegram. Telegram may only start a recovery request and show
its opaque status. Private keys, seed phrases, keystore files, passwords, KMS payloads, and download
links must never be placed in a Telegram message, bot callback, application log, or support ticket.

## Required controls before enabling either option

- A recovery request is bound to the workspace and wallet by server-side state.
- Identity is re-verified through an owner-approved channel outside Telegram.
- Two-person administrative approval is required for an export.
- The signer performs the operation; the bot API never receives plaintext key material.
- Export artifacts are encrypted before leaving the signer boundary, expire quickly, are
  single-download, and are deleted after retrieval or expiry.
- The password is supplied by the user through a separate protected channel and is never stored.
- Every request, approval, denial, generation, retrieval, expiry, and cancellation is audited
  without sensitive payloads.
- Recovery/export is paused globally during a security incident.

Until these controls and a dedicated security review are complete, `/recovery` may provide policy
information or accept a non-sensitive request, but it must not recover or export any key.
