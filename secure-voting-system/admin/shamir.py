import random

PRIME = 208351617316091241234326746312124448251235562226470491514186331217050270460481

def generate_shares(secret, threshold=3, total=5):
    coeffs = [secret] + [random.randint(1, PRIME - 1) for _ in range(threshold - 1)]

    def polynomial(x):
        return sum(coeffs[i] * pow(x, i, PRIME) for i in range(threshold)) % PRIME

    return [(i, polynomial(i)) for i in range(1, total + 1)]

def reconstruct_secret(shares):
    secret = 0
    for j, (xj, yj) in enumerate(shares):
        num, den = 1, 1
        for i, (xi, _) in enumerate(shares):
            if i != j:
                num = (num * (-xi)) % PRIME
                den = (den * (xj - xi)) % PRIME
        secret += yj * num * pow(den, -1, PRIME)
    return secret % PRIME
