# Golden fixtures

`manifest.json` is the inventory and review state for historical Ethereum fixtures. Raw provider payloads will be stored under a directory named for the fixture ID only after their source block is finalized and their expected outcome is reviewed.

Fixture files must not contain RPC URLs, API credentials, private keys, Telegram data, or user-private CopyMint records.

Each completed fixture will contain:

- `source.json` — chain, block, transaction hash, collection and provenance;
- the raw evidence files named in the manifest;
- `expected.json` — decoded events, identities, confidence/reasons, route and classification;
- adapter-specific expected eligibility/quote/build/simulation results when applicable.
