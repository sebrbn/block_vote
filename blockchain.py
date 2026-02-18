import hashlib
import json
import time
import proof_of_work  

class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.create_block(previous_hash='0', nonce=100)

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
        last_block = self.last_block
        block_data = json.dumps(self.pending_transactions, sort_keys=True)
        
        # Calls the NEW function structure in proof_of_work.py
        nonce = proof_of_work.mine(block_data, difficulty=4)
        
        previous_hash = self.hash(last_block)
        block = self.create_block(nonce, previous_hash)
        return block