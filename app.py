from flask import Flask, render_template, request, session, redirect, url_for
from blockchain import Blockchain
import random
import time
import argparse
import ast        # Safely converts string inputs back to math tuples
import hashlib    # For Cryptographic Hashing
import secrets    # For generating high-entropy dynamic keys

# IMPORT YOUR EXISTING ALGORITHMS
import vote_token_generator
import blind_signature
import rsa_signature
import shamir_secret_sharing 

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# Initialize the Blockchain
vote_chain = Blockchain()

# GLOBAL VARIABLES
generated_shares = []       # Stores the 5 shares for demo purposes (Setup Phase)
submitted_shares = set()    # Pool to collect shares from different admins
submitted_ips = set()       # NEW: To track which IPs have submitted shares (Prevents duplicates)
is_election_active = False
otp_storage = {}            # Stores OTPs temporarily
stored_secret_hash = None   # NEW: Stores only the hash, never the secret!

# ----------------------------------------------------------------
# 1. AUTHENTICATION ROUTES (OTP SYSTEM)
# ----------------------------------------------------------------
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', otp_sent=False)

@app.route('/send_otp', methods=['POST'])
def send_otp():
    user_id = request.form['userid']
    otp = random.randint(1000, 9999)
    session['temp_user_id'] = user_id
    otp_storage[user_id] = otp
    
    print(f"\n{'='*40}")
    print(f"📧 [EMAIL SENT] OTP for {user_id} is >> {otp} <<")
    print(f"{'='*40}\n")
    
    return render_template('login.html', otp_sent=True)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    user_otp = request.form['otp']
    user_id = session.get('temp_user_id')
    
    if user_id in otp_storage and str(otp_storage[user_id]) == user_otp:
        session['user_id'] = user_id
        del otp_storage[user_id]
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html', otp_sent=True, error="Invalid OTP! Check terminal.")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ----------------------------------------------------------------
# 2. VOTER DASHBOARD & TOKEN GENERATION
# ----------------------------------------------------------------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template('dashboard.html', user=session['user_id'])

@app.route('/generate_token', methods=['POST'])
def generate_token():
    if not is_election_active:
         return "<h1>🚫 Election Not Started!</h1><p>Admin must reconstruct keys first.</p><a href='/dashboard'>Back</a>"

    token = vote_token_generator.generate_token() 
    session['token'] = token
    return render_template('vote.html', token=token)

# ----------------------------------------------------------------
# 3. VOTING & MINING
# ----------------------------------------------------------------
@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    vote_choice = request.form['candidate']
    token = session.get('token')

    if not token:
        return redirect(url_for('home'))

    blinded_vote, r_factor = blind_signature.blind_message(vote_choice)
    signed_blinded = blind_signature.sign_blinded_message(blinded_vote)
    signature = blind_signature.unblind_signature(signed_blinded, r_factor)

    vote_chain.add_transaction(token, {
        'candidate': vote_choice,
        'signature': signature
    })

    mined_block = vote_chain.mine_pending_transactions()
    return render_template('success.html', block=mined_block)

# ----------------------------------------------------------------
# 4. ADMIN & SHAMIR'S MULTI-SIG WORKFLOW
# ----------------------------------------------------------------
@app.route('/setup')
def setup_page():
    """Renders the offline setup page"""
    return render_template('setup.html', generated=generated_shares, active=is_election_active)

@app.route('/generate_setup', methods=['POST'])
def generate_setup():
    """Phase 1: Trusted Setup Ceremony (Dynamic Secret)"""
    global generated_shares, submitted_shares, submitted_ips, is_election_active, stored_secret_hash
    
    submitted_shares.clear()
    submitted_ips.clear()
    is_election_active = False
    
    # Generate a random dynamic secret and ONLY save the hash
    dynamic_secret = secrets.randbelow(10**12)
    stored_secret_hash = hashlib.sha256(str(dynamic_secret).encode()).hexdigest()
    
    # Split the secret and destroy the original
    generated_shares = shamir_secret_sharing.generate_shares(dynamic_secret, total_shares=5, threshold=3)
    
    return redirect(url_for('setup_page'))

@app.route('/admin')
def admin_page():
    """Renders the live election console"""
    return render_template(
        'admin.html', 
        submitted_count=len(submitted_shares), 
        active=is_election_active,
        error=None
    )

@app.route('/submit_share', methods=['POST'])
def submit_share():
    """Phase 2: Admins submit their individual shares with strict IP validation"""
    global is_election_active
    error_msg = None
    
    if is_election_active:
        return redirect(url_for('admin_page'))
        
    share_input = request.form.get('share_input')
    client_ip = request.remote_addr  # Grab the device's IP address
    
    try:
        parsed_share = ast.literal_eval(share_input)
        
        # 1. SECURITY CHECK: Has this device already submitted a share?
        if client_ip in submitted_ips:
            error_msg = f"Access Denied: A share was already submitted from this device ({client_ip})."
            
        # 2. Strict Format Check
        elif not (isinstance(parsed_share, tuple) and len(parsed_share) == 2):
            error_msg = "Invalid format! Must be a tuple like (1, 12345...)"
            
        # 3. Cryptographic Verification (Is it a real share?)
        elif parsed_share not in generated_shares:
            error_msg = "Fake Share Detected! This share does not belong to the current election."
            
        # 4. If it passes all checks, add it to the pool AND record the IP
        else:
            submitted_shares.add(parsed_share)
            submitted_ips.add(client_ip) # Lock out this IP from submitting again
            
            # Check threshold
            if len(submitted_shares) >= 3:
                shares_list = list(submitted_shares)[:3]
                recovered_secret = shamir_secret_sharing.reconstruct_secret(shares_list)
                
                recovered_hash = hashlib.sha256(str(recovered_secret).encode()).hexdigest()
                
                if recovered_hash == stored_secret_hash:
                    is_election_active = True
                    print("\n✅ THRESHOLD MET: Hashes match! Election Unlocked!\n")
                    return redirect(url_for('admin_page'))
                else:
                    error_msg = "Critical Error: Key reconstruction failed hash verification."
                    
    except Exception as e:
        error_msg = "Invalid input! Please paste the exact tuple format."

    return render_template(
        'admin.html', 
        submitted_count=len(submitted_shares), 
        active=is_election_active,
        error=error_msg
    )

# ----------------------------------------------------------------
# 5. BLOCKCHAIN EXPLORER
# ----------------------------------------------------------------
@app.route('/chain')
def get_chain():
    return {'chain': vote_chain.chain, 'length': len(vote_chain.chain)}

@app.route('/explorer')
def explorer():
    return render_template('explorer.html', chain=vote_chain.chain)

# ----------------------------------------------------------------
# 6. P2P NETWORKING ROUTES
# ----------------------------------------------------------------
@app.route('/network')
def network_page():
    return render_template('network.html', port=request.host.split(':')[-1])

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400
    for node in nodes:
        vote_chain.register_node(node)
    return {"message": "New nodes have been added", "total_nodes": list(vote_chain.nodes)}, 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = vote_chain.resolve_conflicts()
    if replaced:
        response = {'message': 'Our chain was replaced by a longer one from the network.', 'new_chain': vote_chain.chain}
    else:
        response = {'message': 'Our chain is authoritative (already up to date).', 'chain': vote_chain.chain}
    return response, 200

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    app.run(host='0.0.0.0', port=args.port, debug=True)