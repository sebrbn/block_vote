import hashlib

# Key Setup
p, q = 61, 53
n = p * q
phi = (p - 1) * (q - 1)
e = 17
d = pow(e, -1, phi)

def sign(message):
    """Signs a message using the private key."""
    message_hash = int(hashlib.sha256(message.encode()).hexdigest(), 16) % n
    signature = pow(message_hash, d, n)
    return signature

def verify(message, signature):
    """Verifies a signature using the public key."""
    message_hash = int(hashlib.sha256(message.encode()).hexdigest(), 16) % n
    decrypted_hash = pow(signature, e, n)
    return decrypted_hash == message_hash