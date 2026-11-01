"""Signed hash chain over successive source packets.

This module wraps ``tp.provenance`` without modifying it. Every manifest produced by
``ChainedSource`` carries ``prev_hash``, the hash of the previous manifest together with its
signature. Because ``prev_hash`` is inside the signed manifest, an attacker cannot delete,
reorder or splice packets without either breaking a signature or leaving a visible gap.

Chain states reported by ``ChainedGround.verify`` in ``result['chain']``:

* ``START``  - first packet seen for this key (trust on first use).
* ``OK``     - the packet links to the last accepted packet.
* ``GAP``    - packets are missing between the last accepted packet and this one
               (loss, deletion or a deliberate drop).
* ``FORK``   - the counter is consecutive but the link does not match: two different
               manifests claim the same predecessor (signer equivocation or a forged link).
* ``ABSENT`` - the manifest carries no chain field (unchained source).
* ``N/A``    - the packet was not eligible for a chain check (invalid signature or replay).

The deterministic evidence rule from the project is preserved: a chain problem can only
raise the alert level, never lower it.
"""
import hashlib

from tp.provenance import Ground, Source, canonical, decide

GENESIS = '0' * 64
LEVELS = {'TRUSTED': 0, 'SUSPICIOUS': 1, 'COMPROMISED': 2}


def link_hash(manifest, signature_hex):
    """Hash that the next packet must reference as ``prev_hash``."""
    return hashlib.sha256(canonical(manifest) + bytes.fromhex(signature_hex)).hexdigest()


class ChainedSource(Source):
    """A source whose manifests are linked into a signed hash chain."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ``None`` means the previous link is unknown (for example, state lost after an upgrade).
        # The next packet is then sent without ``prev_hash`` and the chain restarts from it.
        self.head = GENESIS

    def acquire(self, arr, meta):
        pkg = super().acquire(arr, meta)
        if self.head is not None:
            pkg['manifest']['prev_hash'] = self.head
            pkg['signature'] = self._sk.sign(canonical(pkg['manifest'])).hex()
        self.head = link_hash(pkg['manifest'], pkg['signature'])
        return pkg


class ChainedGround(Ground):
    """Ground station that also checks the hash chain of each trusted source."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.heads = {}  # key_id -> link hash of the last accepted packet

    def verify(self, pkg):
        manifest = pkg.get('manifest') or {}
        key_id = manifest.get('key_id')
        previous_counter = self.last_counter.get(key_id, 0)
        result = super().verify(pkg)
        result['chain'] = 'N/A'
        if result['provenance'] != 'VALID' or result['replay']:
            return result
        link = link_hash(manifest, pkg['signature'])
        self._check_chain(result, key_id, manifest.get('prev_hash'), manifest['counter'], previous_counter, link)
        return result

    def _check_chain(self, result, key_id, prev_hash, counter, previous_counter, link):
        """Set ``result['chain']`` for an accepted packet and advance the stored head."""
        if prev_hash is None:
            result['chain'] = 'ABSENT'
        elif key_id not in self.heads:
            result['chain'] = 'START'
        elif prev_hash == self.heads[key_id]:
            result['chain'] = 'OK'
        elif counter > previous_counter + 1:
            result['chain'] = 'GAP'
            result['reasons'].append(f'chain gap: {counter - previous_counter - 1} packet(s) missing before this one')
        else:
            result['chain'] = 'FORK'
            result['reasons'].append('chain fork: the packet does not link to the last accepted packet')
        # Resynchronise on the newest validly signed packet so one loss does not poison the rest.
        self.heads[key_id] = link


def decide_chained(ver, score, t_low, t_high):
    """Trust decision that adds chain evidence to ``tp.provenance.decide``.

    GAP raises the status to at least SUSPICIOUS and FORK to COMPROMISED.
    """
    status, reasons = decide(ver, score, t_low, t_high)
    chain = ver.get('chain')
    floor = {'GAP': 'SUSPICIOUS', 'FORK': 'COMPROMISED'}.get(chain)
    if floor and LEVELS[floor] > LEVELS[status]:
        status = floor
    return status, reasons
