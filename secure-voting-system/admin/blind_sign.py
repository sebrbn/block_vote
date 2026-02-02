def sign_blinded_hash(blinded_hash, d, n):
    return pow(blinded_hash, d, n)
