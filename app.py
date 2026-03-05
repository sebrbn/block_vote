from flask import Flask, render_template, request, session, redirect, url_for
from blockchain import Blockchain
import random
import time
import argparse

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
admin_shares = []
is_election_active = False
otp_storage = {}  # Stores OTPs temporarily

# ----------------------------------------------------------------
# 1. AUTHENTICATION ROUTES (OTP SYSTEM)
# ----------------------------------------------------------------
@app.route('/')
def home():
    # If already logged in, go to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', otp_sent=False)

@app.route('/network')
def network_page():
    return render_template('network.html', port=request.host.split(':')[-1])

@app.route('/send_otp', methods=['POST'])
def send_otp():
    user_id = request.form['userid']
    
    # Generate Mock OTP
    otp = random.randint(1000, 9999)
    session['temp_user_id'] = user_id
    otp_storage[user_id] = otp
    
    # SIMULATE EMAIL SENDING
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
        # Cleanup OTP
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

    # 1. Blind Signature
    blinded_vote, r_factor = blind_signature.blind_message(vote_choice)
    
    # 2. Admin Sign (Simulated)
    signed_blinded = blind_signature.sign_blinded_message(blinded_vote)
    
    # 3. Unblind
    signature = blind_signature.unblind_signature(signed_blinded, r_factor)

    # 4. Add to Blockchain Pool
    vote_chain.add_transaction(token, {
        'candidate': vote_choice,
        'signature': signature
    })

    # 5. Mine Block (Proof of Work)
    mined_block = vote_chain.mine_pending_transactions()

    return render_template('success.html', block=mined_block)

# ----------------------------------------------------------------
# 4. ADMIN & SHAMIR'S SECRET SHARING
# ----------------------------------------------------------------
@app.route('/admin')
def admin_page():
    return render_template('admin.html', shares=admin_shares, active=is_election_active)

@app.route('/initialize_keys', methods=['POST'])
def initialize_keys():
    global admin_shares
    secret = 123456789
    admin_shares = shamir_secret_sharing.generate_shares(secret, total_shares=5, threshold=3)
    return redirect(url_for('admin_page'))

@app.route('/reconstruct_key', methods=['POST'])
def reconstruct_key():
    global is_election_active
    if len(admin_shares) < 3:
        return "Not enough shares!"
        
    recovered_secret = shamir_secret_sharing.reconstruct_secret(admin_shares[:3])
    
    if recovered_secret == 123456789:
        is_election_active = True
        return "<h1>✅ Key Reconstructed! Election Started.</h1><a href='/admin'>Back</a>"
    else:
        return "❌ Failed."

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
@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    """Endpoint for a node to tell us it exists"""
    values = request.get_json()
    nodes = values.get('nodes')

    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        vote_chain.register_node(node)

    return {"message": "New nodes have been added", "total_nodes": list(vote_chain.nodes)}, 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    """Endpoint to trigger the consensus algorithm and sync the chain"""
    replaced = vote_chain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced by a longer one from the network.',
            'new_chain': vote_chain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative (already up to date).',
            'chain': vote_chain.chain
        }

    return response, 200

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    
    # host='0.0.0.0' allows external connections if you're testing across multiple computers
    app.run(host='0.0.0.0', port=args.port, debug=True)