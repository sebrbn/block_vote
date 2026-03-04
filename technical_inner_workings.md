# Secure Voting System: Technical Inner Workings

This document provides a deep-dive into the cryptographic algorithms, network protocols, and security architecture of the decentralized voting system.

---

## 🔐 1. Distributed Consensus (Shamir's Secret Sharing)
The election begins in a `LOCKED` state. It cannot be activated by a single administrator, preventing a "rogue admin" from starting or manipulating the election timeline.

- **Algorithm**: Shamir’s Secret Sharing over a large prime field (GF(P)).
- **The Secret**: A global activation key.
- **Shares**: This secret is split into $N$ shares. Our system requires a **Threshold (K) of 3** shares.
- **Inner Working**: 
    1. A polynomial $f(x)$ of degree $K-1$ (degree 2) is generated where the constant term $f(0)$ is the secret.
    2. Each Admin Node is assigned a point $(x, y)$ on the curve.
    3. When 3 points are submitted across the P2P network, the system performs **Lagrange Interpolation** to reconstruct $f(0)$ and verify the activation key.
- **Security**: Even if 2 nodes are compromised, the election cannot be started.

---

## 👤 2. Voter Anonymity (Blind RSA Signatures)
To ensure "One person, one vote" without compromising secrecy, the system uses the **Chaumian Blind Signature** protocol.

- **The Problem**: If the Admin signs a vote, they know which voter chose which candidate.
- **The Solution (The Envelope Analogy)**: The voter puts their vote in an envelope with a piece of carbon paper. The Admin signs the outside of the envelope. The voter then removes the vote from the envelope; it now has the Admin's physical signature on it even though the Admin never saw it.
- **Mathematical Flow**:
    1. **Token Generation**: Voter generates a unique 256-bit `Token`.
    2. **Blinding**: Voter picks a random factor $r$ and computes $m' = (m \cdot r^e) \mod n$.
    3. **Admin Signing**: Admin signs the blinded message $s' = (m')^d \mod n$.
    4. **Unblinding**: Voter computes $s = s' \cdot r^{-1} \mod n$.
    5. **Verification**: The network verifies that $s^e \equiv m \mod n$.
- **Result**: The blockchain contains a valid signature prove the vote is authorized, but no link exists between the voter's identity and the vote data.

---

## ⛓️ 3. The Blockchain Ledger (Proof of Work)
The ledger is a decentralized, immutable sequence of blocks.

- **Block Structure**: `index`, `timestamp`, `transactions`, `nonce`, `previous_hash`.
- **Proof of Work (PoW)**: Any node wishing to add a block must solve a computationally expensive puzzle.
    - **Target**: Find a `nonce` such that `SHA-256(Block Data + Nonce)` starts with `0000` (Difficulty 4).
- **Auto-Miner Logic**:
    - **Threshold**: Mines immediately if $\ge 3$ transactions are in the mempool.
    - **Interval**: Mines after 60 seconds regardless of count to ensure throughput for low-activity periods.
- **P2P Conflict Resolution**: If two nodes have different versions of the ledger, the **Longest Valid Chain** (the one representing the most cumulative PoW) is accepted as the Truth.

---

## 🛡️ 4. Security & Pentest Analysis

### Scenario A: Double Voting
- **Attack**: A voter uses the same token twice.
- **Mitigation**: The `Blockchain.add_transaction` method checks the unique token against every transaction logged in the entire chain history and the current mempool. Replays are rejected instantly ($O(1)$ lookup via Set).

### Scenario B: Rogue Admin Node
- **Attack**: An admin tries to add a custom "Victory" block.
- **Mitigation**: Every other node validates the PoW hash, the signature on every vote, and the `previous_hash` link. A rogue block will be orphaned by the P2P network as it fails the `is_valid_chain()` check.

### Scenario C: Sybil Attack
- **Attack**: An attacker spins up 100 fake nodes to flood the network.
- **Mitigation**: In this system, only **Admins** (Full Nodes) can mine. The identity of Admins is managed via IP-based manual peering or a pre-shared token mechanism, making Sybil attacks expensive/impossible without physical IP control.

### Scenario D: Data Modification
- **Attack**: Changing a single vote in Block #5.
- **Mitigation**: Changing any data in Block #5 changes its hash. Since Block #6 contains `previous_hash_5`, Block #6 becomes invalid. This cascades to the end of the chain, making the fraud immediately visible to all peers.

---

## 🚀 5. Secured Discovery & Portability

### Zero-Config Security
- **The Protocol**: Nodes use UDP broadcasting on Port 5005.
- **Shared Secret**: Every broadcast packet contains a payload: `BLOCKVOTE_NODE:{PORT}:{ADMIN_TOKEN}`.
- **Defense**: The `discovery_listener_task` explicitly ignores any packet that does not contain the correct `ADMIN_TOKEN`. Even if an attacker knows the "Magic String," they cannot join the network without the shared secret.

### Deployment Ease
- **requirements.txt**: Standardizes the environment (Flask, Requests).
- **start_admin.bat**: A Windows wrapper that handles dependency installation, port selection, and environment variable configuration in a single click.

---

## Part 6: Zero-Trust Security Model

To ensure the highest integrity, the system now enforces a "Zero-Trust" policy between voters, admins, and the blockchain ledger.

### 1. RSA Challenge-Response (Admin)
Static passwords are prone to brute-force attacks. Our system generates a unique `auth-XXXX` challenge per session. The Admin must provide an RSA signature of this challenge. Since the public key is known and the private key never leaves the Admin's device, this prevents unauthorized access even if the "Admin Token" is leaked.

### 2. Blind Signature Enforcement
A vote transition is only valid if:
- The token is 256-bit and unique.
- The token is accompanied by an RSA signature from the Election Authority.
This prevents "padding" the ballot box with fake tokens, as only the authorized Admin can issue a valid signature.

### 3. Threshold Consensus (Shamir)
The master secret required to unlock the election is split using Shamir's $(3, 5)$ scheme. This ensures that no single rogue admin can start or stop the election arbitrarily. It requires the cooperation of a trusted majority.
