import hashlib

p, q = 61, 53
n = p * q
phi = (p - 1) * (q - 1)
e = 17
d = pow(e, -1, phi)

if __name__ == "__main__":
    message = "ADMIN_APPROVED"
    message_hash = int(hashlib.sha256(message.encode()).hexdigest(), 16) % n

    signature = pow(message_hash, d, n)
    verified = pow(signature, e, n)

    print("RSA Signature Valid:", verified == message_hash)
