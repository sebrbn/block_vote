import token

from flask import Flask, render_template, request, session, redirect, url_for
from blockchain import Blockchain
import random
import time
import argparse
import ast        # Safely converts string inputs back to math tuples
import hashlib    # For Cryptographic Hashing
import secrets    # For generating high-entropy dynamic keys
import re
import ipaddress

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
student_db={}
ADMIN_PIN = "123456"           # The secret admin password (change this to whatever you want)
candidates_list = []       # Dynamic list of candidates
# Add this to your global variables
pending_signature_requests = {} # { user_id: blinded_message }
signed_blinded_votes = {}       # { user_id: admin_signature }

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
    user_id = request.form['userid'].strip().upper() # Clean the input and make it uppercase
    
    # 🛑 SECURITY CHECK: Validate RSET UID format (U + exactly 7 digits)
    # ^ means start of string, U is the letter, \d{7} means 7 numbers, $ means end of string
    if not re.match(r'^U\d{7}$', user_id):
        return render_template('login.html', otp_sent=False, error="Invalid UID! Format must be 'U' followed by 7 numbers (e.g., U2303181).")
    
    def send_otp():
        user_id = request.form['userid'].strip().upper()
    
    # 1. Check Format (From our last step)
    if not re.match(r'^U\d{7}$', user_id):
        return render_template('login.html', otp_sent=False, error="Invalid UID! Format must be 'U' followed by 7 numbers (e.g., U2303181).")
    
    # 🛑 2. NEW SECURITY CHECK: Has the student already voted?
    if student_db.get(user_id, {}).get('voted') == True:
        print(f"⛔ Blocked login attempt: {user_id} already voted.")
        return render_template('login.html', otp_sent=False, error="Access Denied: You have already cast your vote!")
    
    # 3. Generate Mock OTP
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

@app.route('/voter_registry')
def voter_registry():
    """Secure Admin View of the Student Database"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    # 🛑 SECURITY CHECK: Network Fencing (LAN Only)
    try:
        if not ipaddress.ip_address(client_ip).is_private:
            return "<h1>🚫 Access Denied</h1><p>Registry is strictly restricted to local network admins.</p>", 403
    except ValueError:
        pass

    return render_template('registry.html', database=student_db)

@app.route('/generate_token', methods=['POST'])
def generate_token():
    if not is_election_active:
         return "<h1>🚫 Election Not Started!</h1><p>Admin must reconstruct keys first.</p><a href='/dashboard'>Back</a>"

    # 1. Grab the real IP (Proxy-safe for Ngrok/LAN)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    # 🛑 2. SECURITY CHECK: Prevent Admins from generating a voting token
    if client_ip in submitted_ips:
        return """
        <div style='text-align: center; padding: 50px; font-family: sans-serif;'>
            <h1 style='color: #d9534f;'>🚫 Access Denied: Conflict of Interest</h1>
            <p>Your device's IP address is registered as an Election Administrator.</p>
            <p>To maintain election integrity, administrators are strictly prohibited from casting a vote.</p>
            <a href='/dashboard' style='color: #0275d8; text-decoration: none; font-weight: bold;'>Return to Dashboard</a>
        </div>
        """, 403

    # 3. If they pass the check, generate the token
    token = vote_token_generator.generate_token() 
    session['token'] = token
    return render_template('vote.html', token=token, candidates=candidates_list)
# ----------------------------------------------------------------
# 3. VOTING & MINING
# ----------------------------------------------------------------
@app.route('/request_signature', methods=['POST'])
def request_signature():
    user_id = session.get('user_id')
    vote_choice = request.form.get('candidate')

    if not user_id or not vote_choice:
        return redirect(url_for('home'))

    # 1. Blind the vote
    blinded_vote, r_factor = blind_signature.blind_message(vote_choice)
    
    # 2. Give ONLY the blinded vote to the Admin queue
    pending_signature_requests[user_id] = {
        'blinded_vote': blinded_vote
    }
    
    # 3. Securely store the voter's secrets in their own session cookie
    session['r_factor'] = r_factor
    session['vote_choice'] = vote_choice
    
    # 4. Add to Registry as "Pending"
    if user_id not in student_db:
        student_db[user_id] = {'voted': False}
    
    # 5. THE FIX: Redirect them to the waiting room so they don't get stuck!
    return redirect(url_for('vote_status'))

@app.route('/vote_status')
def vote_status():
    """Voter Waiting Room"""
    user_id = session.get('user_id')
    
    if user_id in signed_blinded_votes:
        # Admin signed it! Show the final submit button.
        return """
        <div style="text-align:center; padding:50px; font-family:sans-serif;">
            <h1 style="color:#28a745;">✅ Admin Signature Received!</h1>
            <p>Your ballot has been authorized. Click below to unblind and mine the block.</p>
            <form action='/submit_to_blockchain' method='POST'>
                <button type='submit' style='padding:15px 30px; background:#007bff; color:white; border:none; font-size:18px; cursor:pointer;'>
                    Unblind & Mine Block
                </button>
            </form>
        </div>
        """
    elif user_id in pending_signature_requests:
        # Still waiting for admin
        return """
        <div style="text-align:center; padding:50px; font-family:sans-serif;">
            <h1>⏳ Waiting for Admin Authorization...</h1>
            <button onclick='location.reload()' style='padding:10px 20px; font-size:16px; cursor:pointer;'>
                Refresh Status
            </button>
        </div>
        """
    else:
        return redirect(url_for('dashboard'))

@app.route('/submit_to_blockchain', methods=['POST'])
def submit_to_blockchain():
    """Final Step: Unblind and Mine"""
    user_id = session.get('user_id')
    token = session.get('token')

    # 1. Grab Admin's Signature and Voter's Secrets
    signed_blinded = signed_blinded_votes.pop(user_id, None)
    r_factor = session.get('r_factor')
    vote_choice = session.get('vote_choice')

    if not signed_blinded or not r_factor:
        return "<h1>🚫 Error</h1><p>Missing signature or blinding factor.</p>", 400

    # 2. Cryptographic Unblinding
    signature = blind_signature.unblind_signature(signed_blinded, r_factor)

    # 3. Add to Blockchain and Mine
    vote_chain.add_transaction(token, {
        'candidate': vote_choice,
        'signature': signature
    })
    mined_block = vote_chain.mine_pending_transactions()

    # 4. Lock them out in the Registry
    student_db[user_id]['voted'] = True
    print(f"✅ SECURE LOG: Block mined for {user_id}. Vote locked.")

    return render_template('success.html', block=mined_block)
# ----------------------------------------------------------------
# 4. ADMIN & SHAMIR'S MULTI-SIG WORKFLOW
# ----------------------------------------------------------------
@app.route('/setup')
def setup_page():
    """Renders the offline setup page with Network Fencing"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    # 🛑 SECURITY CHECK: Network Fencing
    try:
        if not ipaddress.ip_address(client_ip).is_private:
            return """
            <div style='text-align: center; padding: 50px; font-family: sans-serif;'>
                <h1 style='color: #d9534f;'>🚫 Access Denied: Out of Network</h1>
                <p>The Trusted Setup Ceremony must be performed on the secure local network.</p>
                <p>Public access to key generation is strictly prohibited.</p>
            </div>
            """, 403
    except ValueError:
        pass # Failsafe for weird IP formats

    return render_template('setup.html', generated=generated_shares, active=is_election_active)


@app.route('/generate_setup', methods=['POST'])
def generate_setup():
    """Phase 1: Trusted Setup Ceremony (Dynamic Secret)"""
    global generated_shares, submitted_shares, submitted_ips, is_election_active, stored_secret_hash
    
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    # 🛑 SECURITY CHECK: Network Fencing for the actual generation action
    try:
        if not ipaddress.ip_address(client_ip).is_private:
            return "Access Denied: You must be on the local secure network to generate keys.", 403
    except ValueError:
        pass

    submitted_shares.clear()
    submitted_ips.clear()
    is_election_active = False
    
    # Generate a random dynamic secret and ONLY save the hash
    dynamic_secret = secrets.randbelow(10**12)
    stored_secret_hash = hashlib.sha256(str(dynamic_secret).encode()).hexdigest()
    
    # Split the secret and destroy the original
    generated_shares = shamir_secret_sharing.generate_shares(dynamic_secret, total_shares=5, threshold=3)
    
    return redirect(url_for('setup_page'))

@app.route('/admin_login', methods=['POST'])
def admin_login():
    """Verifies the RSA Signature of the Challenge"""
    # 🛑 Network Fencing
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    try:
        if not ipaddress.ip_address(client_ip).is_private:
            return "Access Denied", 403
    except ValueError:
        pass

    challenge = session.get('login_challenge')
    sig_input = request.form.get('signature').strip()
    
    try:
        # The signature must be an integer for your RSA math to work
        signature_int = int(sig_input)
        
        # 🛡️ THIS IS WHERE YOUR RSA CODE AUTHENTICATES THE ADMIN
        if rsa_signature.verify(challenge, signature_int):
            session['is_admin'] = True
            print("✅ SECURE LOG: Admin authenticated via RSA Challenge-Response.")
            return redirect(url_for('admin_page'))
        else:
            return "<h1>🚫 Invalid RSA Signature</h1><a href='/admin'>Try Again</a>", 403
            
    except ValueError:
        return "<h1>🚫 Error: RSA Signature must be a number.</h1><a href='/admin'>Try Again</a>", 400
    
@app.route('/admin')
def admin_page():
    """Renders the live election console"""
    # Grabs the real public IP from Ngrok, or falls back to the normal IP if Ngrok isn't used
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    try:
        if not ipaddress.ip_address(client_ip).is_private:
            return """
            <div style='text-align: center; padding: 50px; font-family: sans-serif;'>
                <h1 style='color: #d9534f;'>🚫 Access Denied: Out of Network</h1>
                <p>Admin access is strictly restricted to the local secure network.</p>
                <p>Please connect to the authorized Wi-Fi network to continue.</p>
            </div>
            """, 403
    except ValueError:
        pass # Failsafe just in case a weird IP format comes through

    if not session.get('is_admin'):
        # 1. Generate a random 8-character hex challenge
        challenge = secrets.token_hex(4)
        session['login_challenge'] = challenge
        
            # 2. Show the Challenge-Response UI
        return f"""
        <div style='text-align: center; padding: 50px; font-family: sans-serif;'>
            <h2>🔐 RSA Zero-Knowledge Login</h2>
            <p>To prove your identity, sign this random challenge using your offline private key:</p>
            <div style='margin: 20px;'>
                <strong>Server Challenge:</strong><br>
                <code style='display: inline-block; margin-top: 10px; font-size: 24px; background: #eee; padding: 10px 15px; border-radius: 5px; border: 1px solid #ccc;'>{challenge}</code>
            </div>
            <form action='/admin_login' method='POST'>
                <input type='text' name='signature' placeholder='Enter numeric RSA Signature' required style='padding: 10px; width: 300px; font-family: monospace; text-align: center;'>
                <br><br>
                <button type='submit' style='padding: 10px 20px; background: #28a745; color: white; border: none; font-weight: bold; cursor: pointer; border-radius: 5px;'>
                    Verify RSA Signature
                </button>
            </form>
        </div>
        """

    return render_template(
        'admin.html', 
        submitted_count=len(submitted_shares), 
        active=is_election_active,
        candidates=candidates_list,  # Pass the candidates to the HTML
        error=None,
        pending_requests=pending_signature_requests
    )

@app.route('/admin/sign_ballot/<user_id>', methods=['POST'])
def admin_sign_ballot(user_id):
    """Admin Phase: Manually authorize a blinded ballot"""
    if not session.get('is_admin'):
        return "Unauthorized", 403
    
    # THE FIX: Use .pop() instead of .get() to REMOVE them from the queue
    request_data = pending_signature_requests.pop(user_id, None)
    
    if request_data:
        # 🖋️ Perform the Cryptographic Blind Signature!
        signature = blind_signature.sign_blinded_message(request_data['blinded_vote'])
        
        # Move it to the 'Signed' dictionary so the voter can claim it
        signed_blinded_votes[user_id] = signature
        
        print(f"✅ SECURE LOG: Admin successfully signed blinded ballot for {user_id}")
        
    # Refresh the dashboard (and now the table will be empty!)
    return redirect(url_for('admin_page'))

@app.route('/add_candidate', methods=['POST'])
def add_candidate():
    # 🛑 Security Checks
    if not session.get('is_admin'):
        return "Unauthorized", 403
        
    new_candidate = request.form.get('candidate_name').strip()
    
    # Don't add blank names or duplicates
    if new_candidate and new_candidate not in candidates_list:
        candidates_list.append(new_candidate)
        print(f"✅ Added Candidate: {new_candidate}")
        
    return redirect(url_for('admin_page'))

@app.route('/submit_share', methods=['POST'])
def submit_share():
    """Phase 2: Admins submit their individual shares with strict IP validation"""
    global is_election_active
    error_msg = None
    # Grabs the real public IP from Ngrok, or falls back to the normal IP if Ngrok isn't used
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    if not ipaddress.ip_address(client_ip).is_private:
        return "Access Denied: You must be on the local secure network to submit shares.", 403
    
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
        error=error_msg,
        candidates=candidates_list, # Make sure candidates are passed too!
        pending_requests=pending_signature_requests
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