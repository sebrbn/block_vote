import rsa_signature

print("====================================")
print(" 🛡️  OFFLINE RSA ADMIN WALLET  🛡️ ")
print("====================================")

# Grab the challenge from the user
challenge = input("Enter the Server Challenge (from the website): ").strip()

# Use YOUR code to sign it
signature = rsa_signature.sign(challenge)

print("\n[+] RSA Signature Generated:")
print(f"👉 {signature} 👈")
print("====================================")
print("Copy the number above and paste it into the website.")