def blind_message(message_hash, r, e, n):
    return (message_hash * pow(r, e, n)) % n

def unblind_signature(signed_blind, r, n):
    return (signed_blind * pow(r, -1, n)) % n
