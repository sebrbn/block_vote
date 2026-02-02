import hashlib

def sha256_hash(data):
    return int(hashlib.sha256(str(data).encode()).hexdigest(), 16)
