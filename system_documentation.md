# Secure Voting System: Physical P2P Network Documentation

This document provides a comprehensive guide to setting up, testing, and understanding the decentralized Secure Voting System.

---

## Part 1: Operational Guide (Testing Phases)

### Phase 1: The Network Setup
1.  **Find the IPs**: On Admin **Laptop A** and Admin **Laptop B**, open Command Prompt and type `ipconfig`. Note down their IPv4 addresses (e.g., `192.168.1.5` and `192.168.1.12`).
2.  **Start the Nodes**:
    -   **On Laptop A**: Run `python app.py -p 5000`. (Allow through Windows Firewall if prompted).
    -   **On Laptop B**: Run `python app.py -p 5000`. (Since they are different devices, they can use the same port).
### Phase 1: The Network Setup (Node A, B, C)
1.  **Launch**: Each Admin runs `python app.py -p 5000` on their own device.
2.  **The Handshake**: 
    -   Admin A goes to their dashboard and registers Admin B and C.
    -   Admin B registers Admin A and C.
    -   (Only one node needs to "know" another to begin, but full peering ensures best redundancy).
3.  **Registration Format**: Enter the IPv4 address and port, e.g., `192.168.1.15:5000`.

### Phase 2: Testing Distributed Shamir's
1.  Check that the election is **LOCKED** on both laptops.
2.  **Enter Share #1** on Laptop A.
3.  **Enter Share #2** on Laptop B.
4.  **Enter Share #1** on Laptop A (using a different node's identity if available, or just a 3rd unique share).
5.  **Observe**: Both nodes will automatically sync and flip to **ACTIVE**. This demonstrates decentralized state management using threshold cryptography.

### Phase 3: Testing the Thin Client (Voter Phone)
1.  **Connect**: Open a browser on a smartphone connected to the same Wi-Fi. Type `http://192.168.1.5:5000`.
2.  **Vote**: Log in, generate a token, and cast a vote.
3.  **Verify**: Check Laptop B's terminal or Block Explorer. The vote cast on Laptop A will appear in Laptop B's mempool via the `/transactions/receive` broadcast.

### Phase 4: Testing Consensus (Longest Chain)
1.  **Auto-Mining**: The system will automatically mine once 3 votes are polled or 60 seconds have passed.
2.  **Propagation**: The miner node creates the block and broadcasts it to all peers.
3.  **Consensus**: Refresh the Explorer on Laptop B. It will display the block mined by the network, proving full ledger consensus.

---

## Part 2: Role-Based User Experience

### 👥 The Voter (Thin Client)
Voters are end-users who interact with the system via a standard web browser on any device.

**What they see:**
- A simple, mobile-friendly login page.
- A dashboard indicating if the election is `LOCKED` or `ACTIVE`.
- A success screen confirming their vote is "being mined" by the network.

**What they can do:**
- Log in via User ID and Mock OTP.
- Cast a single, cryptographically blinded vote.
- View the Public Blockchain Explorer to verify their vote status.

---

### 🛠️ The Admin (Full Node)
Admins run the Python software and manage the network infrastructure.

**What they can do:**
- **Network Bridges**: Register neighboring node IPs.
- **Election Authority**: Submit Shamir shares to reach the 3-node threshold.
- **Maintainer**: Monitor the auto-miner or trigger manual mining if needed.
- **Sync**: Force manual chain resolution with peers.

---

## Part 3: Architecture Technicalities
- **Genesis Block**: All nodes share a hardcoded Genesis timestamp to ensure hash consistency across the network.
- **Auto-Miner**: A background daemon thread manages the mempool based on transaction count and time.
- **P2P Sync**: Nodes use the "Longest Valid Chain" rule to resolve conflicts during synchronization.
- **Candidate Propagation**: The global candidate list is synced across all nodes via `/p2p/sync_candidates`.

---

## Part 4: Security & Attack Mitigation

### 1. Unauthorized Admin Access
- **Risk**: Attackers accessing `/admin` to add fake candidates or mine blocks.
- **Mitigation**: 
    - Administrative routes are protected by a required `ADMIN_TOKEN`.
    - Sensitive operations (like starting the election) require a **3-node threshold consensus** via Shamir's Secret Sharing. Single-node compromise is insufficient.

### 2. Double Voting (Sybil/Replay Attacks)
- **Risk**: A voter trying to submit multiple votes.
- **Mitigation**: 
    - The `Blockchain` logic rejects any transaction where the unique `token` is already present in the block ledger OR the current mempool.
    - Each vote is cryptographically verified against the authority's signature.

### 3. Peer Spoofing & Network Integrity
- **Risk**: An attacker spinning up a rogue node to broadcast fake blocks.
- **Mitigation**: 
    - **Proof of Work (PoW)**: Every block must solve a difficult math problem (hash prefix `0000`). Forging a block requires immense computational power.
    - **Longest Chain Rule**: Distributed consensus ensures the network follows the chain with the most cumulative work.

### 4. Candidate Integrity
- **Risk**: Voters voting for non-existent candidates.
- **Mitigation**:
    - The server-side `/cast_vote` logic explicitly validates the `vote_choice` against the official `candidates` list synced across all nodes.
