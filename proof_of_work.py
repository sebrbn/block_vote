import hashlib
import time

def mine(block_data, difficulty=4):
    """
    Mines a block by finding a nonce that satisfies the difficulty target.
    """
    prefix = "0" * difficulty
    nonce = 0
    print(f"⛏️  Mining block with difficulty {difficulty}...")
    
    start_time = time.time()
    
    while True:
        text = f"{block_data}{nonce}".encode()
        hash_value = hashlib.sha256(text).hexdigest()

        if hash_value.startswith(prefix):
            end_time = time.time()
            print(f"✅ Found Nonce: {nonce} ({round(end_time - start_time, 2)}s)")
            return nonce
        
        nonce += 1

if __name__ == "__main__":
    mine("test_block_data", 4)