# CopyMint Wallet Custody and Recovery Notice

> Status: owner approved on 2026-08-05. Legal review remains required before production funding.

CopyMint creates an Ethereum execution wallet for you and holds its encrypted signing key in a
separate private signer service. Your Telegram account controls access to CopyMint, but Telegram
never receives or stores the private key or seed phrase.

During the invite-only paper release:

- CopyMint cannot sign or broadcast transactions;
- creating a wallet does not move funds or mint an NFT;
- wallet addresses and balance snapshots are visible only inside your approved personal workspace;
- other invited users cannot view your wallets;
- loss of Telegram access does not automatically prove ownership or trigger recovery; and
- future account recovery and encrypted wallet export require identity verification outside
  Telegram and are not enabled during the paper release.

Do not fund a CopyMint wallet until the owner announces that funding and recovery procedures have
been reviewed and enabled. Blockchain transfers are irreversible. CopyMint cannot reverse a
transfer made to the wrong address or guarantee recovery from a lost or compromised Telegram
account.

CopyMint's approved product direction includes out-of-band account recovery and encrypted wallet
export. Neither private keys nor export files will be delivered through Telegram. These options
remain unavailable until the controls in `docs/wallet-recovery-and-export-policy.md` pass a
dedicated security review.

Selecting **Create wallet** confirms only that you understand this custody model and want CopyMint
to create an unfunded Ethereum address for paper-mode use.
