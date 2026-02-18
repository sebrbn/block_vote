import random

PRIME = 208351617316091241234326746312124448251235562226470491514186331217050270460481

def generate_polynomial(secret, degree):
    return [secret] + [random.randint(1, PRIME - 1) for _ in range(degree)]

def evaluate_polynomial(poly, x):
    result = 0
    for i, coef in enumerate(poly):
        result = (result + coef * pow(x, i, PRIME)) % PRIME
    return result

def generate_shares(secret, total_shares=5, threshold=3):
    poly = generate_polynomial(secret, threshold - 1)
    return [(i, evaluate_polynomial(poly, i)) for i in range(1, total_shares + 1)]

def reconstruct_secret(shares):
    secret = 0
    for i, (xi, yi) in enumerate(shares):
        num, den = 1, 1
        for j, (xj, _) in enumerate(shares):
            if i != j:
                num = (num * (-xj)) % PRIME
                den = (den * (xi - xj)) % PRIME
        secret = (secret + yi * num * pow(den, -1, PRIME)) % PRIME
    return secret