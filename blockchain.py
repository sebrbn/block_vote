import hashlib
import json
import time
import requests
from urllib.parse import urlparse
import proof_of_work 

class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.nodes = set() # NEW: Keeps track of neighbor nodes
        
        # Create Genesis Block
        self.create_block(previous_hash='0', nonce=100)

    # --- NEW P2P METHODS ---
    def register_node(self, address):
        """Add a new node to the list of nodes (e.g. 'http://127.0.0.1:5001')"""
        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            self.nodes.add(parsed_url.path)
        else:
            raise ValueError('Invalid URL')

    def valid_chain(self, chain):
        """Determine if a given blockchain is valid"""
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            # Check that the hash of the block is correct
            if block['previous_hash'] != self.hash(last_block):
                return False
            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        Consensus Algorithm: Resolves conflicts by replacing our chain with the longest one in the network.
        Returns True if our chain was replaced, False if not.
        """
        neighbors = self.nodes
        new_chain = None
        max_length = len(self.chain) # We only care about chains longer than ours

        # Grab and verify the chains from all the nodes in our network
        for node in neighbors:
            try:
                response = requests.get(f'http://{node}/chain')
                if response.status_code == 200:
                    length = response.json()['length']
                    chain = response.json()['chain']

                    # Check if the length is longer and the chain is valid
                    if length > max_length and self.valid_chain(chain):
                        max_length = length
                        new_chain = chain
            except:
                pass # If a node is down, just skip it

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False

    # --- EXISTING METHODS ---
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

    def add_transaction(self, token, encrypted_vote):
        self.pending_transactions.append({
            'token': token,
            'vote': encrypted_vote
        })
        return self.last_block['index'] + 1

    @property
    def last_block(self):
        return self.chain[-1]

    @staticmethod
    def hash(block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def mine_pending_transactions(self):
    # Create a new block with the pending transactions
        new_block = {
        'index': len(self.chain),
        'timestamp': time.time(),
        'transactions': self.pending_transactions,
        'proof': 100, # or your POW result
        'previous_hash': self.hash(self.chain[-1])
    }
    
    # IMPORTANT: Does it actually append?
        self.chain.append(new_block)
    
    # Clear the pending list
        self.pending_transactions = []
        return new_block