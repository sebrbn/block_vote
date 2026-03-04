import requests
import time

TOKEN = "test-secret"
NODES = ["http://127.0.0.1:5000", "http://127.0.0.1:5001", "http://127.0.0.1:5002"]

def test_system():
    print("\n--- 1. Testing Auto-Discovery (Wait 15s) ---")
    time.sleep(15) 
    
    # RSA Login for each node to set session
    sessions = []
    for node in NODES:
        s = requests.Session()
        # 1. Get challenge
        login_page = s.get(f"{node}/admin/login").text
        import re
        challenge = re.search(r'class="challenge">(.*?)</div>', login_page).group(1)
        
        # 2. Sign challenge (Simplified RSA)
        # Key Setup match rsa_signature.py
        p, q = 61, 53
        n = p * q
        phi = (p - 1) * (q - 1)
        e = 17
        d = pow(e, -1, phi)
        import hashlib
        m_hash = int(hashlib.sha256(challenge.encode()).hexdigest(), 16) % n
        signature = pow(m_hash, d, n)
        
        # 3. Submit Login
        s.post(f"{node}/admin/login", data={'signature': signature})
        sessions.append(s)
        print(f"[*] Logged into {node} using RSA Signature.")

    print("\n--- 2. Testing Candidate Sync ---")
    new_candidate = "Charlie_Candidate"
    try:
        print(f"[*] Adding {new_candidate} to Node 5000...")
        sessions[0].post(f"{NODES[0]}/admin/add_candidate", data={'name': new_candidate})
        time.sleep(2)
        print("[*] Candidate addition broadcasted.")
    except Exception as e:
        print(f"[!] Candidate test failed: {e}")

    print("\n--- 3. Testing Shamir Threshold Activation (3 Nodes) ---")
    shares = ["1,123456790", "2,246913580", "3,370370370"]
    for i, node in enumerate(NODES):
        print(f"[*] Submitting Share {i+1} to {node}...")
        sessions[i].post(f"{node}/admin/submit_share", data={'share': shares[i]})
        time.sleep(1)

    print("\n--- 4. Verifying Election Activation ---")
    time.sleep(2)
    active_status = sessions[0].get(f"{NODES[0]}/explorer/data").json()['is_active']
    print(f"[*] Election Active: {active_status}")

    print("\n--- 5. Testing Auto-Mining (3 Votes) ---")
    import blind_signature
    for i in range(3):
        token = f"TOKEN_{i}"
        vote_choice = "Alice"
        
        # 1. Blind the TOKEN
        blinded, r = blind_signature.blind_message(token)
        # 2. Admin signs it (Authority)
        signed_blinded = blind_signature.sign_blinded_message(blinded)
        # 3. Unblind it to get the valid signature
        signature = blind_signature.unblind_signature(signed_blinded, r)
        
        print(f"[*] Casting Vote {i+1} with valid token signature...")
        payload = {
            'token': token,
            'candidate': vote_choice,
            'signature': signature
        }
        sessions[0].post(f"{NODES[0]}/cast_vote", data=payload)
    
    print("[*] Waiting for auto-miner (15s)...")
    time.sleep(15)
    
    node_data = sessions[2].get(f"{NODES[2]}/explorer/data").json()
    chain_len = len(node_data['chain'])
    print(f"[*] Node 5002 Chain Length: {chain_len} (Expected: 2)")
    if chain_len > 1:
        print("SUCCESS: Blockchain consensus reached and blocks mined!")
    else:
        print("FAILURE: Blockchain did not reach consensus.")

if __name__ == "__main__":
    test_system()
