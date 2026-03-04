import requests
import time

NODE1 = "http://127.0.0.1:5000"
NODE2 = "http://127.0.0.1:5001"

def test():
    print("--- 1. Registering Peers ---")
    try:
        r1 = requests.post(f"{NODE1}/nodes/register", json={"nodes": ["127.0.0.1:5001"]})
        print(f"Node 1 Register Node 2: {r1.status_code}")
        r2 = requests.post(f"{NODE2}/nodes/register", json={"nodes": ["127.0.0.1:5000"]})
        print(f"Node 2 Register Node 1: {r2.status_code}")
    except Exception as e:
        print(f"Error registering nodes: {e}")

    print("\n--- 2. Submitting Shares (Distributed Shamir) ---")
    # Using the /p2p/sync_shares endpoint for direct sync simulation
    s1 = requests.post(f"{NODE1}/p2p/sync_shares", json={"share": [1, 123456790]})
    print(f"Share 1 Submitted: {s1.status_code}")
    s2 = requests.post(f"{NODE1}/p2p/sync_shares", json={"share": [2, 123456791]})
    print(f"Share 2 Submitted: {s2.status_code}")
    s3 = requests.post(f"{NODE1}/p2p/sync_shares", json={"share": [3, 123456792]})
    print(f"Share 3 Submitted: {s3.status_code}")

    print("\n--- 3. Checking Election Status ---")
    time.sleep(2)
    chain1 = requests.get(f"{NODE1}/chain").json()
    # This check is indirect, but if it's active we can cast a vote
    print("Nodes should be active now.")

    print("\n--- 4. Casting a Vote on Node 1 ---")
    # We simulate a vote cast
    # Note: session-based token isn't easy via requests without session management,
    # but we can hit /cast_vote if we have a session.
    # Alternatively, we broadcast a new_transaction directly to the P2P endpoint.
    vote_data = {
        "token": "TEST-TOKEN-999",
        "vote": {"candidate": "Candidate A", "signature": "MOCK-SIG"}
    }
    v = requests.post(f"{NODE1}/transactions/receive", json=vote_data)
    print(f"Vote Broadcasted: {v.status_code}")

    print("\n--- 5. Waiting for Auto-Miner (Threshold=1 after 60s, or Manual Trigger) ---")
    print("Wait 15 seconds to see if it mines (Threshold check).")
    # Actually, threshold is 3. Let's send 2 more votes to trigger the 3-tx threshold mining immediately.
    requests.post(f"{NODE1}/transactions/receive", json={"token": "TEST-TOKEN-998", "vote": {"candidate": "B", "signature": "S"}})
    requests.post(f"{NODE1}/transactions/receive", json={"token": "TEST-TOKEN-997", "vote": {"candidate": "C", "signature": "S"}})
    print("Sent 3 votes total. Miner should trigger in ~10 seconds.")
    
    time.sleep(15)

    print("\n--- 6. Verifying Blockchain Sync ---")
    chain1 = requests.get(f"{NODE1}/chain").json()
    chain2 = requests.get(f"{NODE2}/chain").json()
    
    print(f"Node 1 Chain Length: {len(chain1['chain'])}")
    print(f"Node 2 Chain Length: {len(chain2['chain'])}")
    
    if len(chain1['chain']) > 1 and len(chain1['chain']) == len(chain2['chain']):
        print("SUCCESS: Auto-miner triggered and broadcasted the block to Node 2!")
    else:
        print("FAIL: Chain not updated or out of sync.")

if __name__ == "__main__":
    test()
