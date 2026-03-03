from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from blockchain import Blockchain
import requests
import random
import os
import sys
import argparse
import threading
import time

# IMPORT YOUR ENCRYPTED MODULES (Assuming they are in the same directory)
import vote_token_generator
import blind_signature
import rsa_signature
import shamir_secret_sharing 

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ----------------------------------------------------------------
# P2P NETWORK CONFIGURATION & STATE
# ----------------------------------------------------------------
vote_chain = Blockchain()
is_election_active = False
valid_shares_collected = set() # To track consensus on Shamir shares

# Define this node's identity
parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", type=int, default=5000, help="Port to run the node on")
args = parser.parse_args()
PORT = args.port

# In a real setup, each Admin would have their own unique share
MY_SHARE = ( (PORT % 10) + 1, 123456789 + (PORT % 10) ) 

# Helper: Broadcast to all registered peers
def broadcast(endpoint, data):
    for node in vote_chain.nodes:
        try:
            requests.post(f"http://{node}{endpoint}", json=data, timeout=1)
        except:
            print(f"Failed to broadcast to {node}")

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
    return render_template('dashboard.html', user=session['user_id'], election_active=is_election_active)

@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    if not is_election_active:
        return "Election is locked.", 403
        
    vote_choice = request.form['candidate']
    token = session.get('token') or vote_token_generator.generate_token()
    
    # Custom Crypto Logic (Blind Signatures)
    blinded_vote, r_factor = blind_signature.blind_message(vote_choice)
    signed_blinded = blind_signature.sign_blinded_message(blinded_vote)
    signature = blind_signature.unblind_signature(signed_blinded, r_factor)
    
    vote_data = {'candidate': vote_choice, 'signature': signature}
    
    # 1. Add locally to mempool
    added = vote_chain.add_transaction(token, vote_data)
    
    # 2. Broadcast transaction to all other Admin Nodes
    if added:
        broadcast('/transactions/receive', {'token': token, 'vote': vote_data})
        # Mining now happens asynchronously in the background thread
        return render_template('success.html', status="Vote Received")
        
    return "Duplicate transaction or error.", 400

# ----------------------------------------------------------------
# 2. P2P & CONSENSUS ENDPOINTS (ADMIN TO ADMIN)
# ----------------------------------------------------------------
@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    nodes = request.json.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400
    for node in nodes:
        vote_chain.register_node(node)
    return jsonify({'message': 'New nodes have been added', 'total_nodes': list(vote_chain.nodes)}), 201

@app.route('/transactions/receive', methods=['POST'])
def receive_transaction():
    data = request.get_json()
    vote_chain.add_transaction(data['token'], data['vote'])
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
# 3. SHAMIR DISTRIBUTED ACTIVATION
# ----------------------------------------------------------------
@app.route('/admin/submit_share', methods=['POST'])
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
    valid_shares_collected.add(tuple(share_data))
    if len(valid_shares_collected) >= 3:
        is_election_active = True
    return "Share synced", 200

@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html', active=is_election_active, shares_count=len(valid_shares_collected), peers=list(vote_chain.nodes))

@app.route('/mine', methods=['POST'])
def manual_mine():
    """Manual trigger still available in Admin dashboard."""
    block = vote_chain.mine_pending_transactions()
    if block:
        broadcast('/blocks/receive', block)
        return "Block mined and broadcasted!"
    return "No transactions to mine."

@app.route('/explorer')
def explorer():
    return render_template('explorer.html', chain=vote_chain.chain)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=PORT, use_reloader=False) # Reloader can spawn double threads