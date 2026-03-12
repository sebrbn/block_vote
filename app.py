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
import requests
from flask import jsonify
import smtplib
import os
from email.mime.text import MIMEText

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
candidates_list = []       # Dynamic list of candidates
# Add this to your global variables
pending_signature_requests = {} # { user_id: blinded_message }
signed_blinded_votes = {}       # { user_id: admin_signature }
# Global list to hold live admin notifications for the dashboard
admin_notifications = []

# --- SMTP2GO CONFIGURATION ---
# 🛡️ Securely loading from .env or environment
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

load_env()

SMTP_SERVER = "mail.smtp2go.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

def send_otp_email(receiver_id, otp):
    """Sends a real OTP email via SMTP2GO"""
    receiver_email = f"{receiver_id.lower()}@rajagiri.edu.in"
    msg = MIMEText(f"Your BlockVote Authentication OTP is: {otp}\n\nThis code is required for secure ballot access. Do not share it.")
    msg['Subject'] = 'BlockVote | Secure OTP Challenge'
    msg['From'] = f"BlockVote Secure Portal <{SMTP_USER}>"
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"📧 [GOSSIP] Real email sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"❌ SMTP ERROR: Failed to send email to {receiver_email}: {e}")
        return False

# ----------------------------------------------------------------
# 1. AUTHENTICATION ROUTES (OTP SYSTEM)
# ----------------------------------------------------------------
@app.route('/')
def home():
    if session.get('is_admin'):
        return redirect(url_for('admin_page'))
    
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', otp_sent=False)

@app.route('/send_otp', methods=['POST'])
def send_otp():
    user_id = request.form['userid'].strip().upper()
    
    # 🛑 1. SECURITY CHECK: Validate RSET UID format (U + exactly 7 digits)
    if not re.match(r'^U\d{7}$', user_id):
        return render_template('login.html', otp_sent=False, error="Invalid UID! Format must be 'U' followed by 7 numbers (e.g., U2303181).")
    
    # 🛑 2. SECURITY CHECK: Conflict of Interest (No Admins/Nodes)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    clean_ip = client_ip.split(':')[0] # Remove port if present
    
    is_admin_ip = clean_ip in [n.split(':')[0] for n in vote_chain.nodes] or clean_ip in submitted_ips or clean_ip in ['127.0.0.1', 'localhost']
    if is_admin_ip:
         print(f"⛔ Blocked OTP request from Admin/Node IP: {clean_ip}")
         return render_template('login.html', otp_sent=False, error="Access Denied: Conflict of Interest. Administrators and Nodes are prohibited from voting.")
    
    # 🛑 2. NEW SECURITY CHECK: Has the student already voted?
    if student_db.get(user_id, {}).get('voted') == True:
        print(f"⛔ Blocked login attempt: {user_id} already voted.")
        return render_template('login.html', otp_sent=False, error="Access Denied: You have already cast your vote!")
    
    # 3. Generate Mock OTP
    otp = random.randint(1000, 9999)
    session['temp_user_id'] = user_id
    otp_storage[user_id] = otp
    
    # 4. Attempt Real Email Send
    email_success = send_otp_email(user_id, otp)
    
    # 5. Fallback for Debugging (still print to terminal if email fails)
    if not email_success:
        print(f"\n⚠️ SMTP FALLBACK: OTP for {user_id} is >> {otp} <<")
    
    return render_template('login.html', otp_sent=True, email_status=email_success)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    user_otp = request.form['otp']
    user_id = session.get('temp_user_id')
    
    if user_id in otp_storage and str(otp_storage[user_id]) == user_otp:
        session.clear()
        session['user_id'] = user_id
        del otp_storage[user_id]
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html', otp_sent=True, error="Invalid OTP! Check terminal.")

@app.route('/api/notifications')
def get_notifications():
    """Admin endpoint to fetch and clear new notifications"""
    global admin_notifications
    if not session.get('is_admin'):
        return jsonify([]) # Security: Only admins can fetch this

    # Grab the current notifications and immediately clear the list
    current_notifs = admin_notifications.copy()
    admin_notifications.clear()
    
    return jsonify(current_notifs)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ----------------------------------------------------------------
# 2. VOTER DASHBOARD & TOKEN GENERATION
# ----------------------------------------------------------------
@app.route('/dashboard')
def dashboard():
    if session.get('is_admin'):
        return """
        <div style='text-align: center; padding: 50px; font-family: sans-serif;'>
            <h1 style='color: #d9534f;'>🚫 Access Denied: Conflict of Interest</h1>
            <p>Your session is registered as an Election Administrator.</p>
            <p>Administrators are strictly prohibited from casting a vote.</p>
            <a href='/admin' style='color: #0275d8; text-decoration: none; font-weight: bold;'>Return to Admin Console</a>
        </div>
        """, 403
    
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template('dashboard.html', user=session['user_id'])

@app.route('/api/live_results')
def live_results():
    if not session.get('is_admin'):
        return jsonify({})
        
    tally = {}
    for block in vote_chain.chain:
        transactions = block.get('transactions', [])
        
        for tx in transactions:
            # 🎯 THE FIX: Reach into the 'vote' dictionary
            vote_data = tx.get('vote')
            
            if vote_data and isinstance(vote_data, dict):
                candidate = vote_data.get('candidate')
                if candidate:
                    tally[candidate] = tally.get(candidate, 0) + 1
            
            # Fallback: In case some blocks are structured differently
            elif isinstance(tx, dict) and tx.get('candidate'):
                candidate = tx.get('candidate')
                tally[candidate] = tally.get(candidate, 0) + 1
    
    print(f"📊 TALLY UPDATED: {tally}") 
    return jsonify(tally)

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
    if session.get('is_admin'):
        return "<h1>🚫 Access Denied</h1><p>Admins cannot generate voting tokens.</p>", 403
    
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
@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    user_id = session.get('user_id')
    vote_choice = request.form.get('candidate')
    token = session.get('token')

    if not user_id or not vote_choice or not token:
        return redirect(url_for('home'))

    # 🛡️ THE DOUBLE-SPENDING SHIELD
    # If the user is already in the DB and 'voted' is True, kill the process.
    if student_db.get(user_id, {}).get('voted'):
        return """
        <div style='text-align: center; padding: 50px; font-family: sans-serif;'>
            <h1 style='color: #d9534f;'>⚠️ Double-Vote Detected</h1>
            <p>Our ledger shows you have already cast a ballot. You cannot vote twice.</p>
            <a href='/logout'>Logout</a>
        </div>
        """, 403

    if not is_election_active:
        return "Error: Election is locked.", 403

    # --- 🤖 AUTOMATION ---
    blinded_vote, r_factor = blind_signature.blind_message(vote_choice)
    signed_blinded = blind_signature.sign_blinded_message(blinded_vote)
    signature = blind_signature.unblind_signature(signed_blinded, r_factor)

    # 4. Add and Mine
    vote_chain.add_transaction(token, {
        'candidate': vote_choice,
        'signature': signature
    })
    mined_block = vote_chain.mine_pending_transactions()

    # 5. Lock the voter in the Registry IMMEDIATELY
    if user_id not in student_db:
        student_db[user_id] = {}
    student_db[user_id]['voted'] = True
    
    # 6. Push to Dashboard
    global admin_notifications
    admin_notifications.append(token)

    # 🔄 THE REDIRECT FIX: 
    # Instead of rendering a template (which causes the refresh bug), 
    # we redirect them to a static success page.
    return redirect(url_for('vote_success'))

@app.route('/vote_success')
def vote_success():
    user_id = session.get('user_id')
    if not user_id:
            return redirect(url_for('home'))

    # Get the latest block from the chain to display on success page
    latest_block = vote_chain.chain[-1] if vote_chain.chain else None
    return render_template('success.html', block=latest_block)


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

    return render_template('setup.html', generated=generated_shares, shares=submitted_shares, active=is_election_active, stored_secret_hash=stored_secret_hash)

@app.route('/results')
def voter_results():
    # Voters can see the results, but they don't get the Admin controls
    return render_template('voter_results.html', candidates=candidates_list)

@app.route('/admin/logout')
def admin_logout():
    # Clear the admin-specific session data
    session.pop('is_admin', None)
    session.pop('admin_user', None) # if you stored their name
    # Or just session.clear() to be safe
    print("🔒 Admin session cleared.")
    return redirect(url_for('home'))

@app.route('/api/public_results')
def public_results():
    """A public version of the tally for the voter dashboard"""
    tally = {}
    for block in vote_chain.chain:
        transactions = block.get('transactions', [])
        for tx in transactions:
            # Reusing the 'deep nested' logic we fixed earlier
            vote_data = tx.get('vote')
            if vote_data and isinstance(vote_data, dict):
                candidate = vote_data.get('candidate')
                if candidate:
                    tally[candidate] = tally.get(candidate, 0) + 1
            elif isinstance(tx, dict) and tx.get('candidate'):
                candidate = tx.get('candidate')
                tally[candidate] = tally.get(candidate, 0) + 1
    return jsonify(tally)

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
            session.clear()
            session['is_admin'] = True
            print("✅ SECURE LOG: Admin authenticated via RSA Challenge-Response.")
            return redirect(url_for('admin_page'))
        else:
            return render_template('admin_login.html', challenge=challenge, error="Invalid RSA Signature. Verification failed.")
            
    except ValueError:
        return render_template('admin_login.html', challenge=challenge, error="RSA Signature must be a numeric value.")
    
@app.route('/admin')
def admin_page():
    """Renders the live election console"""
    error = request.args.get('error')
    
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
        return render_template('admin_login.html', challenge=challenge)

    return render_template(
        'admin.html', 
        submitted_count=len(submitted_shares), 
        active=is_election_active,
        candidates=candidates_list,
        error=error,
        sig_requests=pending_signature_requests,
        database=student_db,
        nodes=list(vote_chain.nodes),
        shares=submitted_shares,
        stored_secret_hash=stored_secret_hash
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
    # Use consistent client_ip logic (handling proxies if necessary)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    try:
        parsed_share = ast.literal_eval(share_input)
        
        # 1. SECURITY CHECK: Has this device already submitted a share?
        if client_ip in submitted_ips:
            error_msg = f"Access Denied: A share was already submitted from this device ({client_ip})."
            
        # 2. Strict Format Check
        elif not (isinstance(parsed_share, tuple) and len(parsed_share) == 2):
            error_msg = "Invalid format! Must be a tuple like (1, 12345...)"
            
        # 3. Cryptographic Verification (Only if this node was the generator)
        elif generated_shares and parsed_share not in generated_shares:
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
        error_msg = f"Invalid input! Error: {e}"

    if error_msg:
        return redirect(url_for('admin_page', error=error_msg))
    
    return redirect(url_for('admin_page'))

# ----------------------------------------------------------------
# 5. BLOCKCHAIN EXPLORER
# ----------------------------------------------------------------
@app.route('/chain')
def get_chain():
    return {'chain': vote_chain.chain, 'length': len(vote_chain.chain)}

@app.route('/explorer')
def explorer():
    if not session.get('is_admin'):
        return """
        <div style='text-align: center; padding: 50px; font-family: sans-serif;'>
            <h1 style='color: #d9534f;'>🚫 Access Denied</h1>
            <p>The blockchain ledger is strictly restricted to Election Administrators.</p>
            <a href='/'>Return to Home</a>
        </div>
        """, 403
    return render_template('explorer.html', chain=vote_chain.chain)

# ----------------------------------------------------------------
# 6. P2P NETWORKING ROUTES
# ----------------------------------------------------------------
@app.route('/network')
def network_page():
    return render_template('network.html', nodes=list(vote_chain.nodes))

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    if request.content_type == 'application/json':
        values = request.get_json()
        nodes = values.get('nodes')
    else:
        nodes = request.form.get('nodes')
        if nodes:
            nodes = [nodes] # If single string from form
            
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400
        
    for node in nodes:
        vote_chain.register_node(node)
        
    if request.content_type == 'application/json':
        return {"message": "New nodes have been added", "total_nodes": list(vote_chain.nodes)}, 201
    return redirect(url_for('network_page'))

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = vote_chain.resolve_conflicts()
    if replaced:
        response = {'message': 'Our chain was replaced by a longer one from the network.', 'new_chain': vote_chain.chain}
    else:
        response = {'message': 'Our chain is authoritative (already up to date).', 'chain': vote_chain.chain}
    return response, 200

@app.route('/election/state', methods=['GET'])
def get_election_state():
    """Returns the current global election configuration for P2P syncing."""
    return jsonify({
        "is_active": is_election_active,
        "candidates": candidates_list,
        "secret_hash": stored_secret_hash,
        "shares": list(submitted_shares),
        "registry": student_db
    }), 200

@app.route('/nodes/ping', methods=['GET'])
def node_ping():
    """Simple health check endpoint for P2P neighbors."""
    return jsonify({"status": "online", "timestamp": time.time()}), 200

@app.route('/nodes/state/sync', methods=['GET'])
def sync_election_state():
    """Pulls election configuration from peers and merges it into local memory."""
    global candidates_list, submitted_shares, stored_secret_hash, is_election_active, student_db
    
    sync_occurred = False
    dead_nodes = []
    
    for node in list(vote_chain.nodes):
        try:
            # Increased timeout to 3s for slower local networks
            resp = requests.get(f"http://{node}/election/state", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                
                # 1. Merge Candidates
                for peer_candidate in data.get('candidates', []):
                    if peer_candidate not in candidates_list:
                        candidates_list.append(peer_candidate)
                        sync_occurred = True
                
                # 2. Sync Secret Hash (only if we don't have one)
                if not stored_secret_hash and data.get('secret_hash'):
                    stored_secret_hash = data.get('secret_hash')
                    sync_occurred = True
                
                # 3. Merge Shares
                for peer_share in data.get('shares', []):
                    share_tuple = tuple(peer_share)
                    if share_tuple not in submitted_shares:
                        submitted_shares.add(share_tuple)
                        sync_occurred = True
                        print(f"📥 GOSSIP: Synchronized new share {share_tuple} from {node}")
                
                # 4. Merge Voter Registry (student_db)
                peer_registry = data.get('registry', {})
                for uid, info in peer_registry.items():
                    if uid not in student_db:
                        student_db[uid] = info
                        sync_occurred = True
                        print(f"📥 GOSSIP: Registered new voter {uid} from {node}")
                    else:
                        # If peer says they voted, we must believe it (strictly additive security)
                        if info.get('voted') and not student_db[uid].get('voted'):
                            student_db[uid]['voted'] = True
                            sync_occurred = True
                            print(f"📥 GOSSIP: Updated voting status for {uid} from {node}")
            else:
                dead_nodes.append(node)
        except Exception as e:
            print(f"⚠️ Sync failed for node {node}: {e}")
            dead_nodes.append(node)

    # Clean up dead nodes from the chain's node list
    for node in dead_nodes:
        if node in vote_chain.nodes:
            vote_chain.nodes.remove(node)
            print(f"🗑️ Pruned dead node from mesh (timeout or 404): {node}")

    # 4. Auto-Unlock Check
    if not is_election_active and len(submitted_shares) >= 3 and stored_secret_hash:
        try:
            # Attempt reconstruction to verify local integrity
            shares_list = list(submitted_shares)[:3]
            recovered_secret = shamir_secret_sharing.reconstruct_secret(shares_list)
            if hashlib.sha256(str(recovered_secret).encode()).hexdigest() == stored_secret_hash:
                is_election_active = True
                sync_occurred = True
        except:
            pass

    return jsonify({
        "message": "State sync complete",
        "sync_occurred": sync_occurred,
        "active": is_election_active,
        "shares_count": len(submitted_shares)
    }), 200

@app.route('/nodes/discover', methods=['GET'])
def discover_peers():
    """Autonomous P2P Discovery: Scans the local /24 subnet for other BlockVote nodes."""
    import socket
    import threading
    
    discovered_nodes = []
    
    # Identify local IP and subnet
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    if local_ip == "127.0.0.1":
        return {"message": "Could not identify local network for scanning.", "discovered_count": 0}, 400

    ip_prefix = ".".join(local_ip.split('.')[:-1]) + "."
    current_port = request.host.split(':')[-1] if ':' in request.host else '5000'
    
    def scan_ip(offset):
        target_ip = f"{ip_prefix}{offset}"
        if target_ip == local_ip:
            return
        
        target_url = f"http://{target_ip}:{current_port}"
        try:
            # We check if the node is a BlockVote instance by hitting /chain
            resp = requests.get(f"{target_url}/chain", timeout=0.1)
            if resp.status_code == 200:
                discovered_nodes.append(target_url)
                vote_chain.register_node(target_url)
        except:
            pass

    threads = []
    for i in range(1, 255):
        t = threading.Thread(target=scan_ip, args=(i,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    if discovered_nodes:
        return {
            "message": f"Discovery complete. Found {len(discovered_nodes)} peers: {', '.join(discovered_nodes)}",
            "discovered_count": len(discovered_nodes),
            "nodes": discovered_nodes
        }, 200
    
    return {"message": "No new mesh peers found on local subnet.", "discovered_count": 0}, 200

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    app.run(host='0.0.0.0', port=args.port, debug=True)