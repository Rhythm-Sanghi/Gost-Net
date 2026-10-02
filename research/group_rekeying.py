"""
Gost-Net - Logical Key Hierarchy (LKH) Scalable Tactical Rekeying Tree
Phase 15 Subsystem: Scalable group key management for dynamic tactical squads and detachments
operating in hostile off-grid environments. Implements a balanced binary key tree where
leaves are individual squad members and the root holds the Group Session Key.
Supports O(log N) member join and compromise eviction rekeying protocols, enforcing strict
forward secrecy (evicted nodes cannot decipher future traffic) and backward secrecy (joined
nodes cannot decipher past operational logs).
"""

import os
import hashlib
import hmac
import json
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass
class LKHNode:
    node_id: int
    key: bytes
    is_leaf: bool = False
    member_id: Optional[str] = None
    left_child: Optional[int] = None
    right_child: Optional[int] = None
    parent_id: Optional[int] = None


@dataclass
class RekeyMessage:
    target_node_id: int
    encrypted_key: bytes
    nonce: bytes
    enc_by_node_id: int


class LogicalKeyHierarchy:
    """
    Logical Key Hierarchy (LKH) key tree manager for tactical squad group rekeying.
    Scales rekeying bandwidth to O(log2 N) encryptions upon member eviction or joining.
    """

    def __init__(self, root_id: int = 1):
        self.nodes: Dict[int, LKHNode] = {}
        self.member_to_leaf: Dict[str, int] = {}
        self.root_id = root_id
        self._next_internal_id = root_id
        
        # Initialize root node with fresh 32-byte group key
        root_key = os.urandom(32)
        self.nodes[self.root_id] = LKHNode(node_id=self.root_id, key=root_key, is_leaf=False)

    @property
    def group_key(self) -> bytes:
        """Returns the current operational group session key located at root."""
        return self.nodes[self.root_id].key

    def get_member_path_node_ids(self, member_id: str) -> List[int]:
        """Returns ordered list of node IDs from member leaf to root."""
        leaf_id = self.member_to_leaf.get(member_id)
        if leaf_id is None:
            return []
        path = []
        curr = leaf_id
        while curr is not None:
            path.append(curr)
            curr = self.nodes[curr].parent_id
        return path

    def get_member_key_ring(self, member_id: str) -> Dict[int, bytes]:
        """Returns the collection of keys known to a specific member (its path to root)."""
        path_ids = self.get_member_path_node_ids(member_id)
        return {nid: self.nodes[nid].key for nid in path_ids if nid in self.nodes}

    def _find_insertion_parent(self) -> int:
        """Finds an available leaf or unbalanced node to attach a new member."""
        if len(self.member_to_leaf) == 0:
            return self.root_id

        # BFS to find the first leaf node that can be split into an internal node
        queue = [self.root_id]
        while queue:
            nid = queue.pop(0)
            node = self.nodes[nid]
            if node.left_child is None or node.right_child is None:
                return nid
            queue.append(node.left_child)
            queue.append(node.right_child)
        return self.root_id

    def add_member(self, member_id: str, leaf_key: Optional[bytes] = None) -> Tuple[Dict[int, bytes], List[RekeyMessage]]:
        """
        Adds a new member to the squad tree.
        Updates group key and all ancestor keys (backward secrecy).
        Returns:
            (member_initial_path_keys, rekey_messages_for_existing_members)
        """
        if member_id in self.member_to_leaf:
            raise ValueError(f"Member '{member_id}' is already registered in LKH.")

        leaf_key = leaf_key or os.urandom(32)
        new_leaf_id = max(self.nodes.keys(), default=0) + 1

        if len(self.member_to_leaf) == 0:
            # First member directly attaches as child of root
            leaf_node = LKHNode(
                node_id=new_leaf_id,
                key=leaf_key,
                is_leaf=True,
                member_id=member_id,
                parent_id=self.root_id
            )
            self.nodes[new_leaf_id] = leaf_node
            self.nodes[self.root_id].left_child = new_leaf_id
            self.member_to_leaf[member_id] = new_leaf_id
            return ({self.root_id: self.group_key, new_leaf_id: leaf_key}, [])

        # Split an existing leaf to attach the new member
        # Find first existing leaf
        target_leaf_id = next(iter(self.member_to_leaf.values()))
        # Choose the leaf with minimum depth
        target_leaf_id = min(self.member_to_leaf.values(), key=lambda lid: len(self.get_member_path_node_ids(self.nodes[lid].member_id or "")))
        old_leaf = self.nodes[target_leaf_id]
        old_member = old_leaf.member_id

        # Create new internal node replacing old_leaf
        new_internal_id = max(self.nodes.keys()) + 1
        new_internal_key = os.urandom(32)
        
        # New leaf for the joining member
        new_member_leaf_id = new_internal_id + 1
        new_member_leaf = LKHNode(
            node_id=new_member_leaf_id,
            key=leaf_key,
            is_leaf=True,
            member_id=member_id,
            parent_id=new_internal_id
        )

        # Move old leaf under new internal node
        old_parent_id = old_leaf.parent_id
        old_leaf.parent_id = new_internal_id

        # The new internal node takes old_leaf's spot
        new_internal_node = LKHNode(
            node_id=new_internal_id,
            key=new_internal_key,
            is_leaf=False,
            left_child=target_leaf_id,
            right_child=new_member_leaf_id,
            parent_id=old_parent_id
        )

        if old_parent_id is not None and old_parent_id in self.nodes:
            parent = self.nodes[old_parent_id]
            if parent.left_child == target_leaf_id:
                parent.left_child = new_internal_id
            elif parent.right_child == target_leaf_id:
                parent.right_child = new_internal_id

        self.nodes[new_internal_id] = new_internal_node
        self.nodes[new_member_leaf_id] = new_member_leaf
        self.member_to_leaf[member_id] = new_member_leaf_id

        # Backward Secrecy: Refresh all keys from new_internal_id up to root
        rekey_messages: List[RekeyMessage] = []
        curr_id = new_internal_id
        while curr_id is not None:
            node = self.nodes[curr_id]
            old_k = node.key
            new_k = os.urandom(32)
            node.key = new_k

            # Encrypt new_k for left child and right child
            if node.left_child and node.left_child in self.nodes:
                c_key = self.nodes[node.left_child].key
                msg = self._encrypt_rekey(target_nid=curr_id, new_key=new_k, enc_key=c_key, enc_by_nid=node.left_child)
                rekey_messages.append(msg)
            if node.right_child and node.right_child in self.nodes:
                c_key = self.nodes[node.right_child].key
                msg = self._encrypt_rekey(target_nid=curr_id, new_key=new_k, enc_key=c_key, enc_by_nid=node.right_child)
                rekey_messages.append(msg)

            curr_id = node.parent_id

        # Compile path keys for the new member
        new_member_path_keys = self.get_member_key_ring(member_id)
        return (new_member_path_keys, rekey_messages)

    def evict_member(self, member_id: str) -> List[RekeyMessage]:
        """
        Evicts a member from the squad tree (e.g. captured or compromised device).
        Rotates all keys along the evicted member's path up to the root (forward secrecy).
        Generates O(log N) rekey broadcast messages that only valid remaining members can decrypt.
        """
        if member_id not in self.member_to_leaf:
            raise KeyError(f"Member '{member_id}' not found in LKH tree.")

        leaf_id = self.member_to_leaf.pop(member_id)
        leaf = self.nodes.pop(leaf_id)
        parent_id = leaf.parent_id

        if parent_id is None or parent_id not in self.nodes:
            # Only root left
            self.nodes[self.root_id].key = os.urandom(32)
            return []

        parent = self.nodes[parent_id]
        sibling_id = parent.right_child if parent.left_child == leaf_id else parent.left_child

        # Sibling promotes to replace parent
        grandparent_id = parent.parent_id
        if sibling_id and sibling_id in self.nodes:
            sibling = self.nodes[sibling_id]
            sibling.parent_id = grandparent_id
            if grandparent_id is not None and grandparent_id in self.nodes:
                gp = self.nodes[grandparent_id]
                if gp.left_child == parent_id:
                    gp.left_child = sibling_id
                elif gp.right_child == parent_id:
                    gp.right_child = sibling_id
            elif parent_id == self.root_id:
                # Sibling becomes root
                self.root_id = sibling_id
                sibling.parent_id = None
        self.nodes.pop(parent_id, None)

        # Forward Secrecy: Regenerate keys along path from promoted sibling/grandparent up to root
        rekey_messages: List[RekeyMessage] = []
        curr_id = sibling_id if sibling_id else grandparent_id

        while curr_id is not None and curr_id in self.nodes:
            node = self.nodes[curr_id]
            # Root or internal node gets fresh key
            new_k = os.urandom(32)
            node.key = new_k

            # Encrypt with left child key and right child key so all remaining subtrees can decrypt
            if node.left_child and node.left_child in self.nodes:
                k_left = self.nodes[node.left_child].key
                rekey_messages.append(self._encrypt_rekey(node.node_id, new_k, k_left, node.left_child))
            if node.right_child and node.right_child in self.nodes:
                k_right = self.nodes[node.right_child].key
                rekey_messages.append(self._encrypt_rekey(node.node_id, new_k, k_right, node.right_child))

            curr_id = node.parent_id

        return rekey_messages

    @staticmethod
    def _encrypt_rekey(target_nid: int, new_key: bytes, enc_key: bytes, enc_by_nid: int) -> RekeyMessage:
        """Encrypts new key using AES-256-GCM under key enc_key."""
        aesgcm = AESGCM(enc_key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, new_key, str(target_nid).encode())
        return RekeyMessage(
            target_node_id=target_nid,
            encrypted_key=ct,
            nonce=nonce,
            enc_by_node_id=enc_by_nid
        )

    @staticmethod
    def process_rekey_message(msg: RekeyMessage, member_keys: Dict[int, bytes]) -> Optional[Tuple[int, bytes]]:
        """
        Processes a received rekey broadcast message on a client device.
        If member holds enc_by_node_id key, decrypts and returns (target_node_id, new_key).
        """
        if msg.enc_by_node_id not in member_keys:
            return None
        enc_key = member_keys[msg.enc_by_node_id]
        try:
            aesgcm = AESGCM(enc_key)
            new_key = aesgcm.decrypt(msg.nonce, msg.encrypted_key, str(msg.target_node_id).encode())
            return (msg.target_node_id, new_key)
        except Exception:
            return None

    def encrypt_group_message(self, plaintext: bytes) -> Dict[str, Any]:
        """Encrypts a multicast broadcast message under the active group key."""
        aesgcm = AESGCM(self.group_key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext, b"LKH_GROUP_PAYLOAD")
        return {
            "root_id": self.root_id,
            "nonce": nonce.hex(),
            "ciphertext": ct.hex()
        }

    @staticmethod
    def decrypt_group_message(packet: Dict[str, Any], key: bytes) -> bytes:
        """Decrypts a multicast message using the recipient's known group key."""
        aesgcm = AESGCM(key)
        nonce = bytes.fromhex(packet["nonce"])
        ct = bytes.fromhex(packet["ciphertext"])
        return aesgcm.decrypt(nonce, ct, b"LKH_GROUP_PAYLOAD")
