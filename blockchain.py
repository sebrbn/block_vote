import hashlib
import json
import time
from urllib.parse import urlparse
import proof_of_work  
import blind_signature

class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.nodes = set() # Neighbors: e.g., '192.168.1.10:5000'
        
        # Genesis Block (Hardcoded timestamp for consistency across nodes)
        genesis = {
            'index': 1,
            'timestamp': 1600000000.0,
            'transactions': [],
            'nonce': 100,
            'previous_hash': '0',
        }
        self.chain.append(genesis)

    def register_node(self, address):
        """Add a new node to the list of neighboring nodes."""
        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('Invalid URL')

    def create_block(self, nonce, previous_hash=None):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'transactions': self.pending_transactions,
            'nonce': nonce,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }
        self.pending_transactions = []
        self.chain.append(block)
        return block

    def add_transaction(self, token, vote_data, signature):
        """
        Adds a transaction to the mempool if:
        1. Token hasn't voted before.
        2. Signature is valid (Blind RSA verification).
        """
        # 1. Verify Signature
        if not blind_signature.verify_signature(token, signature):
            print(f"[!] Invalid Authority Signature for token {token[:10]}...")
            return False

        # 2. Prevent double voting: Check chain and mempool
        for block in self.chain:
            for tx in block['transactions']:
                if tx['token'] == token:
                    return False
        for tx in self.pending_transactions:
            if tx['token'] == token:
                if tx['token'] == token:
                    return False
                
        self.pending_transactions.append({
            'token': token,
            'vote': vote_data,
            'signature': signature
        })
        return True

    @property
    def last_block(self):
        return self.chain[-1]

    @staticmethod
    def hash(block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def valid_chain(self, chain):
        """Validate an entire blockchain's hashes and PoW."""
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            if block['previous_hash'] != self.hash(last_block):
                return False
            
            # Verify PoW (Difficulty 4)
            block_data = json.dumps(block['transactions'], sort_keys=True)
            text = f"{block_data}{block['nonce']}".encode()
            if not hashlib.sha256(text).hexdigest().startswith("0000"):
                return False

            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        """Consensus Algorithm: Replace chain with longest valid one in the network."""
        import requests
        new_chain = None
        max_length = len(self.chain)

        for node in self.nodes:
            try:
                response = requests.get(f'http://{node}/chain', timeout=2)
                if response.status_code == 200:
                    length = response.json()['length']
                    chain = response.json()['chain']
                    if length > max_length and self.valid_chain(chain):
                        max_length = length
                        new_chain = chain
            except:
                continue

        if new_chain:
            self.chain = new_chain
            self.pending_transactions = [] # Clean mempool
            return True
        return False

    def mine_pending_transactions(self):
        if not self.pending_transactions:
            return None
        last_block = self.last_block
        block_data = json.dumps(self.pending_transactions, sort_keys=True)
        nonce = proof_of_work.mine(block_data, difficulty=4)
        previous_hash = self.hash(last_block)
        block = self.create_block(nonce, previous_hash)
        return block