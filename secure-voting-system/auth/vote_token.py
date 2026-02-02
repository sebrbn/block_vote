import secrets

def generate_vote_token():
    return secrets.randbits(256)
