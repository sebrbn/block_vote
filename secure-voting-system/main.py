from admin.shamir import generate_shares, reconstruct_secret
from auth.vote_token import generate_vote_token
from crypto.hash_utils import sha256_hash
from crypto.blind_signature import blind_message, unblind_signature
from admin.blind_sign import sign_blinded_hash
from admin.rsa_keys import n, e, d

# ---------------- Day 1 ----------------
MASTER_SECRET = 987654321
shares = generate_shares(MASTER_SECRET)

recovered = reconstruct_secret(shares[:3])
assert recovered == MASTER_SECRET
print("✅ Admin server started (3 admins verified)")

# ---------------- Day 2 ----------------
vote_token = generate_vote_token()
hashed = sha256_hash(vote_token) % n

r = 7  # blinding factor
blinded = blind_message(hashed, r, e, n)
signed_blind = sign_blinded_hash(blinded, d, n)
signature = unblind_signature(signed_blind, r, n)

verified = pow(signature, e, n)
assert verified == hashed
print("✅ Vote token signed anonymously and verified")
