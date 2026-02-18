import secrets
import hashlib

def generate_token():
    """Generates a unique 256-bit voting token."""
    vote_token = secrets.randbits(256)
    return str(vote_token)

def hash_token(token):
    """Returns the SHA-256 hash of the token."""
    return hashlib.sha256(token.encode()).hexdigest()

if __name__ == "__main__":
    t = generate_token()
    print("Token:", t)
    print("Hash:", hash_token(t))