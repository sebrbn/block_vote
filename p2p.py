import socket
import threading
import json
import requests

class P2PNode:
    def __init__(self, host, port, blockchain_node):
        self.host = host
        self.port = port
        self.blockchain_node = blockchain_node # The Blockchain instance
        self.peers = set() # Set of (host, port) tuples
        self.local_share = None # The cryptographic share held by this node

    def add_peer(self, host, port):
        if (host, port) != (self.host, self.port):
            self.peers.add((host, port))

    def broadcast(self, message_type, data):
        """Broadcast a message to all known peers."""
        message = {"type": message_type, "data": data}
        for peer_host, peer_port in self.peers:
            try:
                url = f"http://{peer_host}:{peer_port}/p2p/receive"
                requests.post(url, json=message, timeout=1)
            except Exception as e:
                print(f"Failed to broadcast to {peer_host}:{peer_port}: {e}")

    def request_shares(self):
        """Request Shamir shares from all known peers."""
        shares = []
        if self.local_share:
            shares.append(self.local_share)
            
        for peer_host, peer_port in self.peers:
            try:
                url = f"http://{peer_host}:{peer_port}/p2p/get_share"
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    share_data = response.json().get('share')
                    if share_data:
                        shares.append(tuple(share_data))
            except Exception as e:
                print(f"Failed to get share from {peer_host}:{peer_port}: {e}")
        return shares

    def sync_with_peers(self):
        """Request the chain from peers and update if they have a longer valid one."""
        for peer_host, peer_port in self.peers:
            try:
                url = f"http://{peer_host}:{peer_port}/chain"
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    remote_chain = response.json()['chain']
                    self.blockchain_node.resolve_conflicts(remote_chain)
            except Exception as e:
                print(f"Failed to sync with {peer_host}:{peer_port}: {e}")
