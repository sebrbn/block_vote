import hashlib
import random
import math

# RSA Parameters (Small keys for demo speed)
p, q = 61, 53
n = p * q
phi = (p - 1) * (q - 1)
e = 17
d = pow(e, -1, phi)

def blind_message(message):
    """
    Blinds a message (Vote Token) so the Admin can sign it without seeing it.
    Returns: (blinded_message, r_factor)
    """
    message_hash = int(hashlib.sha256(message.encode()).hexdigest(), 16) % n
    
    # Generate random factor r coprime to n
    r = random.randint(2, n - 1)
    while math.gcd(r, n) != 1:
        r = random.randint(2, n - 1)
        
    blinded = (message_hash * pow(r, e, n)) % n
    return blinded, r

def sign_blinded_message(blinded_message):
    """Admin signs the blinded message using private key d."""
    return pow(blinded_message, d, n)

def unblind_signature(signed_blinded, r):
    """User removes the blinding factor to get the valid signature."""
    return (signed_blinded * pow(r, -1, n)) % n

def verify_signature(message, signature):
    """Verifies if a signature is valid for a message."""
    message_hash = int(hashlib.sha256(message.encode()).hexdigest(), 16) % n
    check = pow(signature, e, n)
    return check == message_hash