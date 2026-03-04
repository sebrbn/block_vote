from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from functools import wraps
from blockchain import Blockchain
import requests
import random
import os
import sys
import argparse
import threading
import time
import socket

# IMPORT YOUR ENCRYPTED MODULES (Assuming they are in the same directory)
import rsa_signature
import blind_signature

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

app = Flask(__name__, template_folder=resource_path('templates'))
app.secret_key = os.urandom(24)

# ----------------------------------------------------------------
# P2P NETWORK CONFIGURATION & STATE
# ----------------------------------------------------------------
vote_chain = Blockchain()
is_election_active = False
valid_shares_collected = set() # To track consensus on Shamir shares
candidates = ["Alice", "Bob"]  # Default list

# Define this node's identity
# ----------------------------------------------------------------
# CRYPTOGRAPHIC AUTHENTICATION
# ----------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Security Upgrade: Only allow access from the local machine (Admin's PC)
        # request.remote_addr will be '127.0.0.1' if accessed locally
        if request.remote_addr not in ['127.0.0.1', 'localhost']:
            return "403 Forbidden: Admin Panel is restricted to local access only.", 403
            
        if not session.get('is_admin'):
            return redirect(url_for('admin_login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login_page():
    if request.method == 'POST':
        # RSA Signature Authentication
        # The admin "signs" a challenge string with their private key
        challenge = session.get('auth_challenge', 'admin-auth-demo')
        signature = int(request.form.get('signature', '0'))
        
        if rsa_signature.verify(challenge, signature):
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid RSA Signature", 401
            
    # Generate a challenge
    session['auth_challenge'] = f"auth-{random.randint(1000, 9999)}"
    return render_template('admin_login.html', challenge=session['auth_challenge'])

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('home'))

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", type=int, default=5000, help="Port to run the node on")
args = parser.parse_args()
PORT = args.port

# In a real setup, each Admin would have their own unique share
MY_SHARE = ( (PORT % 10) + 1, 123456789 + (PORT % 10) ) 

# Helper: Broadcast to all registered peers
def broadcast(endpoint, data):
    for node in list(vote_chain.nodes):
        try:
            requests.post(f"http://{node}{endpoint}", json=data, timeout=1)
        except:
            print(f"Failed to broadcast to {node}")

# ----------------------------------------------------------------
# AUTO-DISCOVERY (P2P ZERO-CONF) - SECURED
# ----------------------------------------------------------------
DISCOVERY_PORT = 5005
DISCOVERY_MAGIC = "BLOCKVOTE_NODE"
SHARED_SECRET = os.getenv('ADMIN_TOKEN', 'admin-secret-123')

def discovery_broadcast_task():
    """Broadcasts this node's presence with a shared secret."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # Allow multiple instances on same machine to share discovery port
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except:
        pass
    message = f"{DISCOVERY_MAGIC}:{PORT}:{SHARED_SECRET}".encode()
    print(f"[*] Secured discovery broadcaster started on port {DISCOVERY_PORT}")
    while True:
        try:
            sock.sendto(message, ('<broadcast>', DISCOVERY_PORT))
            time.sleep(10)
        except Exception as e:
            print(f"[!] Broadcast error: {e}")
            time.sleep(10)

def discovery_listener_task():
    """Listens for authorized nodes on the local network."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Allow multiple instances on same machine to bind to 5005
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except:
        pass
    sock.bind(('', DISCOVERY_PORT))
    print(f"[*] Secured discovery listener active on port {DISCOVERY_PORT}")
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = data.decode()
            if message.startswith(DISCOVERY_MAGIC):
                parts = message.split(':')
                if len(parts) == 3 and parts[2] == SHARED_SECRET:
                    remote_port = parts[1]
                    remote_node = f"{addr[0]}:{remote_port}"
                    if remote_node not in vote_chain.nodes and remote_node != f"127.0.0.1:{PORT}":
                        print(f"[*] Discovered authorized node: {remote_node}")
                        vote_chain.register_node(remote_node)
                        try:
                            my_ip = socket.gethostbyname(socket.gethostname())
                            # Ensure we don't recursive-register ourselves and cause loops
                            if remote_node != f"{my_ip}:{PORT}":
                                requests.post(f"http://{remote_node}/nodes/register", 
                                              json={"nodes": [f"{my_ip}:{PORT}"], "is_handshake": True}, 
                                              timeout=2)
                        except:
                            pass
                else:
                    print(f"[!] Unauthorized discovery attempt from {addr[0]}")
        except Exception as e:
            print(f"[!] Listener error: {e}")

# Start discovery threads
threading.Thread(target=discovery_broadcast_task, daemon=True).start()
threading.Thread(target=discovery_listener_task, daemon=True).start()

# ----------------------------------------------------------------
# AUTO-MINER BACKGROUND TASK
# ----------------------------------------------------------------
def auto_miner_task():
    """Background thread that mines blocks based on mempool size or time."""
    print(f"[*] Auto-miner thread started on Node {PORT}")
    while True:
        try:
            time.sleep(10) # Run check every 10 seconds
            
            if not is_election_active:
                continue

            pending_count = len(vote_chain.pending_transactions)
            last_block_time = vote_chain.last_block['timestamp']
            time_since_last = time.time() - last_block_time

            # TRIGGERS:
            # 1. Threshold: 3 or more transactions
            # 2. Time: More than 60 seconds since last block
            if pending_count > 0:
                if pending_count >= 3 or time_since_last >= 60:
                    print(f"[*] Triggering auto-mine: {pending_count} txs, {int(time_since_last)}s since last block.")
                    block = vote_chain.mine_pending_transactions()
                    if block:
                        print(f"[*] Successfully mined block {block['index']}. Broadcasting...")
                        broadcast('/blocks/receive', block)
        except Exception as e:
            print(f"[!] Auto-miner error: {e}")

# Start the miner thread
miner_thread = threading.Thread(target=auto_miner_task, daemon=True)
miner_thread.start()

# ----------------------------------------------------------------
# 1. VOTER ENDPOINTS (THIN CLIENT)
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
    session['mock_otp'] = str(otp)
    print(f"\n[OTP] Node {PORT} -> {user_id}: {otp}\n")
    return render_template('login.html', otp_sent=True)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    user_otp = request.form['otp']
    if user_otp == session.get('mock_otp'):
        session['user_id'] = session.get('temp_user_id')
        return redirect(url_for('dashboard'))
    return render_template('login.html', otp_sent=True, error="Invalid OTP.")

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template('dashboard.html', user=session['user_id'], election_active=is_election_active, candidates=candidates)

@app.route('/generate_token', methods=['POST'])
def generate_token():
    if not is_election_active:
        return "Election is locked.", 403
    token = vote_token_generator.generate_token()
    session['token'] = token
    return render_template('vote.html', token=token, candidates=candidates)

@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    if not is_election_active:
        return "Election is locked.", 403
        
    vote_choice = request.form['candidate']
    if vote_choice not in candidates:
        return "Invalid candidate.", 400

    token = session.get('token')
    if not token:
        return "Missing token. Please generate one first.", 400
    
    # Custom Crypto Logic (Blind Signatures)
    # The Authority (Admin) signs the voter's TOKEN, not their choice.
    # This allows the token to be verified on-chain without linking to the ID.
    
    # FOR DEMO: The server does the full pipeline to show logic
    blinded_token, r_factor = blind_signature.blind_message(token)
    signed_blinded = blind_signature.sign_blinded_message(blinded_token)
    signature = blind_signature.unblind_signature(signed_blinded, r_factor)
    
    # 1. Add locally to mempool with the unblinded signature of the token
    added = vote_chain.add_transaction(token, vote_choice, signature)
    
    # 2. Broadcast transaction with signature
    if added:
        broadcast('/transactions/receive', {'token': token, 'vote': vote_choice, 'signature': signature})
        return render_template('success.html', status="Vote Received")
        
    return "Invalid Signature or Double Voting!", 400

# ----------------------------------------------------------------
# 2. P2P & CONSENSUS ENDPOINTS (ADMIN TO ADMIN)
# ----------------------------------------------------------------
@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    nodes = request.json.get('nodes')
    is_handshake = request.json.get('is_handshake', False)
    
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400
        
    for node in nodes:
        if node != f"127.0.0.1:{PORT}":
            vote_chain.register_node(node)
            # If this wasn't already a back-and-forth handshake, initiate one
            if not is_handshake:
                try:
                    my_ip = socket.gethostbyname(socket.gethostname())
                    requests.post(f"http://{node}/nodes/register", 
                                  json={"nodes": [f"{my_ip}:{PORT}"], "is_handshake": True}, 
                                  timeout=2)
                except:
                    pass
                    
    return jsonify({'message': 'New nodes have been added', 'total_nodes': list(vote_chain.nodes)}), 201

@app.route('/transactions/receive', methods=['POST'])
def receive_transaction():
    data = request.get_json()
    token = data.get('token')
    vote = data.get('vote')
    signature = data.get('signature', 0)
    
    vote_chain.add_transaction(token, vote, signature)
    return "Transaction received", 201

@app.route('/blocks/receive', methods=['POST'])
def receive_block():
    block = request.get_json()
    if block['index'] == len(vote_chain.chain) + 1:
        if vote_chain.valid_chain(vote_chain.chain + [block]):
            vote_chain.chain.append(block)
            # Remove transactions from mempool that were included in the block
            block_tokens = [tx['token'] for tx in block['transactions']]
            vote_chain.pending_transactions = [tx for tx in vote_chain.pending_transactions if tx['token'] not in block_tokens]
            return "Block added", 201
    return "Block rejected or out of sync", 400

@app.route('/chain')
def full_chain():
    return jsonify({
        'chain': vote_chain.chain,
        'length': len(vote_chain.chain)
    }), 200

@app.route('/nodes/resolve')
def consensus():
    replaced = vote_chain.resolve_conflicts()
    if replaced:
        return jsonify({'message': 'Our chain was replaced', 'new_chain': vote_chain.chain}), 200
    return jsonify({'message': 'Our chain is authoritative', 'chain': vote_chain.chain}), 200

# ----------------------------------------------------------------
# 3. CANDIDATE MANAGEMENT
# ----------------------------------------------------------------
@app.route('/admin/add_candidate', methods=['POST'])
@admin_required
def add_candidate():
    new_candidate = request.form['name']
    if new_candidate and new_candidate not in candidates:
        candidates.append(new_candidate)
        broadcast('/p2p/sync_candidates', {'candidates': candidates})
        return redirect(url_for('admin_dashboard'))
    return "Invalid candidate or already exists", 400

@app.route('/p2p/sync_candidates', methods=['POST'])
def sync_candidates():
    global candidates
    remote_candidates = request.json.get('candidates')
    if remote_candidates:
        # Merge or replace (here we replace for the simplest P2P propagation)
        candidates = list(set(candidates + remote_candidates))
    return "Candidates synced", 200

# ----------------------------------------------------------------
# 4. SHAMIR DISTRIBUTED ACTIVATION
# ----------------------------------------------------------------
@app.route('/admin/submit_share', methods=['POST'])
@admin_required
def submit_share():
    global is_election_active
    share_input = request.form['share']
    try:
        share = tuple(map(int, share_input.split(',')))
        valid_shares_collected.add(share)
        broadcast('/p2p/sync_shares', {'share': share})
        if len(valid_shares_collected) >= 3:
            is_election_active = True
        return redirect(url_for('admin_dashboard'))
    except:
        return "Invalid Share Format", 400

@app.route('/p2p/sync_shares', methods=['POST'])
def sync_shares():
    global is_election_active
    share_data = request.json.get('share')
    if share_data:
        valid_shares_collected.add(tuple(share_data))
        if len(valid_shares_collected) >= 3:
            is_election_active = True
        return "Share synced", 200
    return "Malformed share data", 400

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin.html', active=is_election_active, shares_count=len(valid_shares_collected), peers=list(vote_chain.nodes), candidates=candidates)

@app.route('/mine', methods=['POST'])
@admin_required
def manual_mine():
    """Manual trigger still available in Admin dashboard."""
    block = vote_chain.mine_pending_transactions()
    if block:
        broadcast('/blocks/receive', block)
        return "Block mined and broadcasted!"
    return "No transactions to mine."

@app.route('/explorer/data')
def explorer_data():
    return jsonify({
        'chain': vote_chain.chain,
        'peers': list(vote_chain.nodes),
        'is_active': is_election_active,
        'candidates': candidates
    })

@app.route('/explorer')
def explorer():
    return render_template('explorer.html', chain=vote_chain.chain)

@app.route('/results')
def results():
    """Aggregates all votes from the blockchain and displays live results."""
    votes = {}
    for block in vote_chain.chain:
        for tx in block['transactions']:
            candidate = tx['vote'].get('candidate')
            if candidate:
                votes[candidate] = votes.get(candidate, 0) + 1
    
    # Calculate total for percentages
    total_votes = sum(votes.values())
    return render_template('results.html', votes=votes, total=total_votes)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=PORT, use_reloader=False) # Reloader can spawn double threads