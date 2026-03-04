"""Steganographic watermarking using zero-width Unicode, linguistic fingerprinting, and whitespace patterns."""

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Dict, List, Optional, Tuple


ZERO_WIDTH_CHARS = {
    '0': '\u200b',  # Zero-width space
    '1': '\u200c',  # Zero-width non-joiner
}

_ZERO_WIDTH_CHARS_SET = frozenset(['\u200b', '\u200c', '\u200d', '\u2060', '\ufeff'])
ZERO_WIDTH_SPACE = '\u200b'
ZERO_WIDTH_NON_JOINER = '\u200c'
ZERO_WIDTH_JOINER = '\u200d'
WORD_JOINER = '\u2060'
WATERMARK_START = '\ufeff'
WATERMARK_END = '\u2060'

_ZERO_WIDTH_REMOVAL_PATTERN = re.compile(r'[\ufeff\u2060\u200b\u200c\u200d]')

SYNONYMS = {
    "important": ["significant", "crucial", "vital", "essential", "critical"],
    "big": ["large", "huge", "substantial", "considerable", "major"],
    "small": ["little", "tiny", "minor", "slight", "modest"],
    "good": ["great", "excellent", "fine", "positive", "favorable"],
    "bad": ["poor", "negative", "unfavorable", "adverse", "harmful"],
    "fast": ["quick", "rapid", "swift", "speedy", "prompt"],
    "slow": ["gradual", "unhurried", "leisurely", "sluggish", "delayed"],
    "help": ["assist", "aid", "support", "facilitate", "enable"],
    "show": ["display", "demonstrate", "reveal", "indicate", "present"],
    "make": ["create", "produce", "generate", "form", "build"],
    "use": ["utilize", "employ", "apply", "leverage", "harness"],
    "get": ["obtain", "acquire", "receive", "gain", "secure"],
    "see": ["observe", "notice", "view", "perceive", "witness"],
    "know": ["understand", "recognize", "realize", "comprehend", "grasp"],
    "think": ["believe", "consider", "assume", "suppose", "reckon"],
    "want": ["desire", "wish", "seek", "prefer", "require"],
    "need": ["require", "necessitate", "demand", "call for", "warrant"],
    "start": ["begin", "commence", "initiate", "launch", "kick off"],
    "end": ["finish", "conclude", "complete", "terminate", "wrap up"],
    "very": ["extremely", "highly", "quite", "particularly", "especially"],
    "also": ["additionally", "furthermore", "moreover", "besides", "too"],
    "however": ["nevertheless", "nonetheless", "yet", "still", "though"],
    "because": ["since", "as", "due to", "given that", "owing to"],
    "about": ["regarding", "concerning", "relating to", "with respect to", "on"],
}

_WORD_PATTERNS: Dict[str, re.Pattern] = {
    word: re.compile(r'\b' + word + r'\b', re.IGNORECASE)
    for word in SYNONYMS
}

_SYNONYM_PATTERNS: Dict[str, re.Pattern] = {}
for word, syns in SYNONYMS.items():
    for syn in syns:
        _SYNONYM_PATTERNS[syn] = re.compile(r'\b' + re.escape(syn) + r'\b', re.IGNORECASE)

_WORD_MD5_HASHES: Dict[str, int] = {
    word: int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
    for word in SYNONYMS
}


@dataclass
class WatermarkData:
    peer_id: str
    timestamp: str
    depth: int
    content_hash: str
    fingerprint_seed: int
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict) -> "WatermarkData":
        return WatermarkData(**data)


@dataclass
class ExtractionResult:
    success: bool
    peer_id: Optional[str] = None
    confidence: float = 0.0
    method: str = ""
    original_content: Optional[str] = None
    watermark_data: Optional[WatermarkData] = None
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        if self.watermark_data:
            result['watermark_data'] = self.watermark_data.to_dict()
        return result


def _string_to_bits(s: str) -> str:
    return ''.join(format(byte, '08b') for byte in s.encode('utf-8'))


def _bits_to_string(bits: str) -> str:
    chars = []
    for i in range(0, len(bits), 8):
        byte = bits[i:i+8]
        if len(byte) == 8:
            chars.append(chr(int(byte, 2)))
    return ''.join(chars)


def _encode_zero_width(data: str) -> str:
    bits = _string_to_bits(data)
    encoded_bits = [ZERO_WIDTH_CHARS[bit] for bit in bits]
    return WATERMARK_START + ''.join(encoded_bits) + WATERMARK_END


def _decode_zero_width(text: str) -> Optional[str]:
    start_idx = text.find(WATERMARK_START)
    end_idx = text.find(WATERMARK_END)
    
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return None
    
    watermark_section = text[start_idx + 1:end_idx]
    bits_list = []
    for char in watermark_section:
        if char == ZERO_WIDTH_SPACE:
            bits_list.append('0')
        elif char == ZERO_WIDTH_NON_JOINER:
            bits_list.append('1')
    
    if len(bits_list) < 8:
        return None
    
    bits = ''.join(bits_list)
    bits = bits[:len(bits) - (len(bits) % 8)]
    
    try:
        return _bits_to_string(bits)
    except Exception:
        return None


@lru_cache(maxsize=256)
def _get_fingerprint_seed(peer_id: str) -> int:
    return int(hashlib.sha256(peer_id.encode()).hexdigest()[:8], 16)


def _apply_linguistic_fingerprint(content: str, seed: int) -> str:
    result = content
    for word, synonyms in SYNONYMS.items():
        pattern = _WORD_PATTERNS[word]
        word_hash = _WORD_MD5_HASHES[word]
        
        def replace_func(match, syns=synonyms, w_hash=word_hash):
            idx = (seed + w_hash) % len(syns)
            replacement = syns[idx]
            original = match.group(0)
            if original.isupper():
                return replacement.upper()
            elif original[0].isupper():
                return replacement.capitalize()
            return replacement
        
        result = pattern.sub(replace_func, result)
    return result


def _detect_linguistic_fingerprint(content: str, candidate_peer_ids: List[str]) -> Optional[Tuple[str, float]]:
    best_match = None
    best_score = 0.0
    
    synonyms_found: Dict[str, bool] = {}
    for syn, pattern in _SYNONYM_PATTERNS.items():
        synonyms_found[syn.lower()] = bool(pattern.search(content))
    
    for peer_id in candidate_peer_ids:
        seed = _get_fingerprint_seed(peer_id)
        matches = 0
        total = 0
        
        for word, synonyms in SYNONYMS.items():
            word_hash = _WORD_MD5_HASHES[word]
            expected_idx = (seed + word_hash) % len(synonyms)
            expected_synonym = synonyms[expected_idx]
            
            if synonyms_found.get(expected_synonym.lower(), False):
                matches += 1
            
            for syn in synonyms:
                if synonyms_found.get(syn.lower(), False):
                    total += 1
                    break
        
    if best_match and best_score > 0.3 and total >= 2:
        return best_match, best_score
    return None


def _add_whitespace_fingerprint(content: str, peer_id: str) -> str:
    seed = _get_fingerprint_seed(peer_id)
    lines = content.split('\n')
    result_lines = []
    for i, line in enumerate(lines):
        trailing = (seed + i) % 3
        result_lines.append(line + ' ' * trailing)
    return '\n'.join(result_lines)


def _detect_whitespace_fingerprint(content: str, candidate_peer_ids: List[str]) -> Optional[Tuple[str, float]]:
    lines = content.split('\n')
    if len(lines) < 3:
        return None
        
    trailing_pattern = []
    for line in lines:
        trailing = len(line) - len(line.rstrip(' '))
        trailing_pattern.append(trailing % 3)
    
    best_match = None
    best_score = 0.0
    
    for peer_id in candidate_peer_ids:
        seed = _get_fingerprint_seed(peer_id)
        matches = sum(1 for i, t in enumerate(trailing_pattern) if t == (seed + i) % 3)
        score = matches / max(len(trailing_pattern), 1)
        if score > best_score:
            best_score = score
            best_match = peer_id
    
    if best_match and best_score > 0.5:
        return best_match, best_score
    return None


class SteganoEngine:
    """Steganographic watermarking using zero-width Unicode, linguistic fingerprinting, and whitespace."""
    
    def __init__(self):
        self._known_peers: List[str] = []
    
    def register_peer(self, peer_id: str):
        if peer_id not in self._known_peers:
            self._known_peers.append(peer_id)
    
    def embed_watermark(
        self,
        content: str,
        peer_id: str,
        depth: int = 0,
        timestamp: Optional[str] = None,
        use_zero_width: bool = True,
        use_linguistic: bool = True,
        use_whitespace: bool = True
    ) -> str:
        from datetime import datetime, timezone
        
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        fingerprint_seed = _get_fingerprint_seed(peer_id)
        
        watermark_data = WatermarkData(
            peer_id=peer_id,
            timestamp=timestamp,
            depth=depth,
            content_hash=content_hash,
            fingerprint_seed=fingerprint_seed
        )
        
        result = content
        
        if use_linguistic:
            result = _apply_linguistic_fingerprint(result, fingerprint_seed)
        
        if use_whitespace:
            result = _add_whitespace_fingerprint(result, peer_id)
        
        if use_zero_width:
            watermark_json = json.dumps(watermark_data.to_dict())
            encoded_watermark = _encode_zero_width(watermark_json)
            first_space = result.find(' ')
            if first_space > 0:
                result = result[:first_space] + encoded_watermark + result[first_space:]
            else:
                result = result + encoded_watermark
        
        self.register_peer(peer_id)
        return result
    
    def extract_watermark(
        self,
        content: str,
        candidate_peers: Optional[List[str]] = None
    ) -> ExtractionResult:
        candidates = candidate_peers or self._known_peers
        
        decoded = _decode_zero_width(content)
        if decoded:
            try:
                watermark_dict = json.loads(decoded)
                watermark_data = WatermarkData.from_dict(watermark_dict)
                original = self._remove_zero_width(content)
                return ExtractionResult(
                    success=True,
                    peer_id=watermark_data.peer_id,
                    confidence=1.0,
                    method="zero_width",
                    original_content=original,
                    watermark_data=watermark_data
                )
            except (json.JSONDecodeError, KeyError):
                pass
        
        if candidates:
            linguistic_result = _detect_linguistic_fingerprint(content, candidates)
            if linguistic_result:
                peer_id, confidence = linguistic_result
                return ExtractionResult(
                    success=True,
                    peer_id=peer_id,
                    confidence=confidence,
                    method="linguistic",
                    original_content=content
                )
        
        if candidates:
            whitespace_result = _detect_whitespace_fingerprint(content, candidates)
            if whitespace_result:
                peer_id, confidence = whitespace_result
                return ExtractionResult(
                    success=True,
                    peer_id=peer_id,
                    confidence=confidence,
                    method="whitespace",
                    original_content=content
                )
        
        return ExtractionResult(
            success=False,
            confidence=0.0,
            method="none",
            original_content=content
        )
    
    def _remove_zero_width(self, content: str) -> str:
        return _ZERO_WIDTH_REMOVAL_PATTERN.sub('', content)
    
    def strip_all_watermarks(self, content: str) -> str:
        """Remove zero-width chars and whitespace patterns (cannot reverse linguistic fingerprinting)."""
        result = self._remove_zero_width(content)
        lines = result.split('\n')
        return '\n'.join(line.rstrip() for line in lines)
    
    def verify_watermark(self, content: str, expected_peer_id: str) -> bool:
        result = self.extract_watermark(content, [expected_peer_id])
        return result.success and result.peer_id == expected_peer_id
    
    def get_visible_diff(self, original: str, watermarked: str) -> str:
        """Show difference between original and watermarked content (reveals invisible characters)."""
        diff = []
        for i, (o, w) in enumerate(zip(original.ljust(len(watermarked)), 
                                        watermarked.ljust(len(original)))):
            if o != w:
                diff.append(f"Position {i}: '{o}' ({ord(o) if o.strip() else 'space'}) -> "
                           f"'{w}' ({ord(w) if w.strip() else 'space'})")
        return '\n'.join(diff) if diff else "No visible differences"


def embed_invisible_watermark(content: str, peer_id: str, depth: int = 0) -> str:
    engine = SteganoEngine()
    return engine.embed_watermark(content, peer_id, depth)


def extract_invisible_watermark(content: str, candidate_peers: List[str]) -> Optional[str]:
    engine = SteganoEngine()
    result = engine.extract_watermark(content, candidate_peers)
    return result.peer_id if result.success else None

