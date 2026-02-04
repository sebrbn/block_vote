import hashlib
import random
import math

# RSA parameters (demo)
p, q = 61, 53
n = p * q
phi = (p - 1) * (q - 1)
e = 17
d = pow(e, -1, phi)

def blind_message(message_hash, r):
    return (message_hash * pow(r, e, n)) % n

def unblind_signature(signed_blinded, r):
    return (signed_blinded * pow(r, -1, n)) % n

if __name__ == "__main__":
    message = "VOTE_FOR_ALICE"
    message_hash = int(hashlib.sha256(message.encode()).hexdigest(), 16) % n

    r = random.randint(2, n - 1)
    while math.gcd(r, n) != 1:
        r = random.randint(2, n - 1)

    blinded = blind_message(message_hash, r)
    signed_blinded = pow(blinded, d, n)
    signature = unblind_signature(signed_blinded, r)

    verified = pow(signature, e, n)

    print("Original Hash:", message_hash)
    print("Signature Valid:", verified == message_hash)
