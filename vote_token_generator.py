import secrets
import hashlib

if __name__ == "__main__":
    vote_token = secrets.randbits(256)
    hashed_token = hashlib.sha256(str(vote_token).encode()).hexdigest()

    print("Vote Token:", vote_token)
    print("SHA-256 Hash:", hashed_token)
