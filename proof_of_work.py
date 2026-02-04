import hashlib
import time

difficulty = 4
prefix = "0" * difficulty
nonce = 0

start_time = time.time()

while True:
    block_data = f"previous_hash|votes|{nonce}".encode()
    hash_value = hashlib.sha256(block_data).hexdigest()

    if hash_value.startswith(prefix):
        break
    nonce += 1

end_time = time.time()

print("Nonce Found:", nonce)
print("Block Hash:", hash_value)
print("Time Taken:", round(end_time - start_time, 2), "seconds")
print("✅ Block mined successfully")
