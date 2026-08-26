"""Tests L2 — store-safety / concurrence / corruption / snapshot hybride (Memory-11).

Tests ADDITIFS. Aucun code de production modifié.

Concurrence INTER-process (niveau obligatoire) = VRAIS sous-processus, jamais de
threads. Un unique test dédié à la couche INTRA-process (RLock process-local partagé
par chemin canonique) utilise volontairement des threads, car il teste exclusivement
cette couche et ne remplace en rien les tests à deux vrais sous-processus.

Synchronisation explicite par fichier-barrière (attente bornée), timeouts bornés,
rc des subprocess vérifiés, cleanup/kill borné.
"""
from __future__ import annotations
import json, os, subprocess, sys, threading, time
from pathlib import Path
import pytest

import scc_brainai_memory.core.locking as locking
from scc_brainai_memory.core.config import MemoryConfig
from scc_brainai_memory.core.errors import MemoryCorruption
from scc_brainai_memory.core.locking import LockTimeout, LockUnavailable, StoreLock
from scc_brainai_memory.retention import RetentionPolicy
from scc_brainai_memory.store import BrainMemoryStore

SRC = str(Path(locking.__file__).resolve().parents[2])   # .../11_BRAINAI_MEMORY/src
SUB_TIMEOUT = 30
BARRIER = 20.0


def _env():
    e = os.environ.copy()
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    e["PYTHONPATH"] = SRC + os.pathsep + e.get("PYTHONPATH", "")
    return e


def _spawn(script, *args):
    return subprocess.Popen([sys.executable, "-c", script, *[str(a) for a in args]],
                            env=_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _join(p, timeout=SUB_TIMEOUT):
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill(); p.communicate()
        raise AssertionError("subprocess timeout expired")
    return p.returncode, out, err


def _seq(entry_id):
    return int(entry_id.rsplit("_", 1)[-1], 16)


def _seed(config, n):
    """Installe un couple COHÉRENT journal+snapshot (n events) ; retourne les lignes journal."""
    s = BrainMemoryStore(config=config)
    for i in range(n):
        s.record_event("intent", {"i": i})
    return config.entries_path.read_text().splitlines()


def _write_journal(config, text):
    config.ensure_directories()
    config.entries_path.write_text(text, encoding="utf-8")


# --- sous-processus (autoload=False : chaque mutation reload sous lock, §7) ---
WORKER_WRITER = r'''
import sys, time
from pathlib import Path
from scc_brainai_memory.core.config import MemoryConfig
from scc_brainai_memory.store import BrainMemoryStore
data_dir, actor, count, go, deadline, kind = sys.argv[1:7]
count=int(count); deadline=float(deadline); end=time.monotonic()+deadline
while not Path(go).exists():
    if time.monotonic()>end: sys.exit(3)
    time.sleep(0.005)
store=BrainMemoryStore(config=MemoryConfig(data_dir=Path(data_dir)), autoload=False)
for i in range(count):
    if kind=="learning": store.add_learning(f"L-{actor}-{i}", tags=["learning"])
    else: store.record_event("intent", {"actor": actor, "i": i}, actor=actor)
sys.exit(0)
'''
WORKER_RETENTION = r'''
import sys, time
from pathlib import Path
from scc_brainai_memory.core.config import MemoryConfig
from scc_brainai_memory.store import BrainMemoryStore
from scc_brainai_memory.retention import RetentionPolicy
data_dir, go, passes, deadline = sys.argv[1:5]
passes=int(passes); deadline=float(deadline); end=time.monotonic()+deadline
while not Path(go).exists():
    if time.monotonic()>end: sys.exit(3)
    time.sleep(0.005)
store=BrainMemoryStore(config=MemoryConfig(data_dir=Path(data_dir)), autoload=False)
pol=RetentionPolicy(max_entries_per_kind=5, protected_kinds=["learning","preference"])
for _ in range(passes): store.apply_retention(pol)
sys.exit(0)
'''
WORKER_LOCKHOLDER = r'''
import sys, os, time, fcntl
from pathlib import Path
lock_path, ready, release, deadline = sys.argv[1:5]; deadline=float(deadline)
Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
fd=os.open(lock_path, os.O_CREAT|os.O_RDWR, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
Path(ready).write_text("1")
end=time.monotonic()+deadline
while not Path(release).exists():
    if time.monotonic()>end: break
    time.sleep(0.005)
fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd); sys.exit(0)
'''


class _DescClock:
    """Horloge décroissante : le dernier ID écrit reçoit le plus PETIT timestamp."""
    def __init__(self, start=50): self._v = start + 1
    def now(self):
        self._v -= 1
        return f"2026-07-06T00:00:{self._v:02d}+00:00"


class _SeqClock:
    def __init__(self): self._i = 0
    def now(self):
        self._i += 1
        return f"2026-07-06T00:00:{self._i:02d}+00:00"


# 1. CONCURRENCE RÉELLE INTER-PROCESS
def test_two_real_processes_no_lost_update_no_dup_id(tmp_path):
    data_dir = tmp_path / "data"; go = tmp_path / "go"; n = 25
    p1 = _spawn(WORKER_WRITER, data_dir, "alice", n, go, BARRIER, "event")
    p2 = _spawn(WORKER_WRITER, data_dir, "bob", n, go, BARRIER, "event")
    go.write_text("go")
    rc1, _, e1 = _join(p1); rc2, _, e2 = _join(p2)
    assert rc1 == 0, e1.decode(); assert rc2 == 0, e2.decode()
    store = BrainMemoryStore(config=MemoryConfig(data_dir=data_dir))
    ids = [e.id for e in store.entries]
    assert len(ids) == 2 * n
    assert len(set(ids)) == len(ids)
    assert store.audit()["integrity"]["ok"] is True
    by_actor = {s.actor: s for s in store.sessions()}
    assert set(by_actor) == {"alice", "bob"}
    assert (set(by_actor["alice"].entry_ids) | set(by_actor["bob"].entry_ids)) == set(ids)
    assert not (set(by_actor["alice"].entry_ids) & set(by_actor["bob"].entry_ids))


# 1-bis. VERROU INTRA-PROCESS PARTAGÉ PAR CHEMIN CANONIQUE (threads — cette couche uniquement)
def test_intra_process_lock_shared_by_canonical_path(config):
    config.ensure_directories()
    lp = config.lock_path
    a_ready = threading.Event(); a_release = threading.Event(); errors = []

    def hold_a():
        try:
            with StoreLock(lp, timeout=5):
                a_ready.set()
                a_release.wait(timeout=10)
        except Exception as ex:  # pragma: no cover
            errors.append(("A", repr(ex)))

    ta = threading.Thread(target=hold_a); ta.start()
    try:
        assert a_ready.wait(timeout=5), "A n'a pas acquis le verrou"
        with pytest.raises(LockTimeout):
            with StoreLock(lp, timeout=0.3):
                pass
    finally:
        a_release.set(); ta.join(timeout=10)
    assert not ta.is_alive()
    assert errors == []
    with StoreLock(lp, timeout=5):
        pass


def test_canonical_key_stable_across_symlink_and_parent_creation(tmp_path):
    """Invariant §5 niveau-1 : la clé canonique (donc le RLock partagé) est STABLE quelle que
    soit l'existence préalable du parent et à travers un symlink/alias. Régression du défaut où
    ``_canonical`` gardait le chemin BRUT quand le parent n'existait pas encore.

    Sans le correctif : ``a`` (via symlink, parent absent) et ``b`` (via chemin réel) obtenaient
    des clés distinctes -> RLock distincts -> la réentrance ``with a: with b:`` ouvrait un 2e fd
    et un ``flock`` sur le MÊME inode détenu par ``a`` -> self-deadlock -> LockTimeout.
    """
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    lp_link = link / "sub" / "brain_memory.lock"
    lp_real = real / "sub" / "brain_memory.lock"

    # 1. Construire AVANT existence du parent.
    a = StoreLock(lp_link, timeout=2.0)
    b = StoreLock(lp_real, timeout=2.0)

    assert a.canonical == b.canonical
    assert a._entry is b._entry

    # 2. Créer explicitement le parent, sans passer par StoreLock.
    (real / "sub").mkdir(parents=True)

    # 3. Construire APRÈS création et vérifier la stabilité.
    c = StoreLock(lp_real, timeout=2.0)

    assert c.canonical == a.canonical
    assert c._entry is a._entry

    # 4. Seulement maintenant tester la réentrance.
    with a:
        with b:
            pass


# 2. LOCK FAIL-CLOSED (inter-process réel via subprocess)
def test_lock_timeout_via_real_subprocess_no_mutation(config, tmp_path):
    ready = tmp_path / "ready"; release = tmp_path / "release"
    config.ensure_directories()
    holder = _spawn(WORKER_LOCKHOLDER, config.lock_path, ready, release, 20)
    rc = None
    try:
        end = time.monotonic() + 15
        while not ready.exists():
            assert time.monotonic() < end, "lockholder READY timeout"
            assert holder.poll() is None, "lockholder mort prématurément"
            time.sleep(0.005)
        store = BrainMemoryStore(config=config); store.lock_timeout = 0.3
        with pytest.raises(LockTimeout):
            store.record_event("intent", {"x": 1})
        assert not config.entries_path.exists()
    finally:
        release.write_text("1")
        rc, _, err = _join(holder)
    assert rc == 0, err.decode()


def test_lock_unavailable_fail_closed(config, monkeypatch):
    monkeypatch.setattr(locking, "_HAVE_FCNTL", False)
    store = BrainMemoryStore(config=config)
    with pytest.raises(LockUnavailable):
        store.record_event("intent", {"x": 1})
    assert not config.entries_path.exists()


# §6. ATOMIC WRITE — échec AVANT replace ne détruit pas la cible, aucun temp résiduel
def test_atomic_write_failure_before_replace_preserves_target(tmp_path, monkeypatch):
    from scc_brainai_memory.core import atomicio
    target = tmp_path / "f.txt"
    target.write_text("OLD", encoding="utf-8")

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(atomicio.os, "replace", boom)
    with pytest.raises(OSError):
        atomicio.atomic_write_text(target, "NEW")
    assert target.read_text(encoding="utf-8") == "OLD"
    leftovers = [p.name for p in tmp_path.iterdir()
                 if p.name.startswith("f.txt.") and p.name.endswith(".tmp")]
    assert leftovers == []


# 3. CORRUPTION JOURNAL
def test_corruption_invalid_middle_line(config):
    lines = _seed(config, 3)
    _write_journal(config, "\n".join(lines[:1] + ["{ not json"] + lines[1:]) + "\n")
    with pytest.raises(MemoryCorruption):
        BrainMemoryStore(config=config)


def test_corruption_last_line_complete_invalid_with_newline(config):
    lines = _seed(config, 2)
    _write_journal(config, "\n".join(lines) + "\n{ not json }\n")
    with pytest.raises(MemoryCorruption):
        BrainMemoryStore(config=config)


def test_corruption_hash_break_even_last_line(config):
    lines = _seed(config, 2)
    obj = json.loads(lines[-1]); obj["data"] = {"i": "TAMPERED"}
    tampered = json.dumps(obj, ensure_ascii=False)
    _write_journal(config, "\n".join(lines[:-1]) + "\n" + tampered)   # dernière ligne parseable, hash rompu, SANS \n
    with pytest.raises(MemoryCorruption):
        BrainMemoryStore(config=config)


def test_truncated_last_line_without_newline_bounded_recovery(config):
    lines = _seed(config, 3)
    _write_journal(config, "\n".join(lines[:-1]) + "\n" + '{"id": "mem_00000')
    store = BrainMemoryStore(config=config)
    assert store.truncated_tail is True
    assert len(store.entries) == 2
    assert store.audit()["integrity"]["ok"] is True


def test_invalid_sessions_snapshot_fail_closed(config):
    _seed(config, 2)
    config.sessions_path.write_text("{ not json\n", encoding="utf-8")
    with pytest.raises(MemoryCorruption):
        BrainMemoryStore(config=config)


# 4. TRUNCATION REPAIR (gouverné sous lock ; jamais en load)
def test_truncation_repaired_only_under_governed_mutation(config):
    lines = _seed(config, 2)
    _write_journal(config, "\n".join(lines) + "\n" + '{"id": "mem_00000')
    before = config.entries_path.read_bytes()
    s1 = BrainMemoryStore(config=config)
    assert s1.truncated_tail is True
    assert config.entries_path.read_bytes() == before
    s1.record_event("intent", {"after": True})
    s2 = BrainMemoryStore(config=config)
    assert s2.truncated_tail is False
    text = config.entries_path.read_text(); assert text.endswith("\n")
    for ln in text.splitlines():
        json.loads(ln)
    assert len(s2.entries) == 3
    assert s2.audit()["integrity"]["ok"] is True


# 5. SNAPSHOT HYBRIDE / LIFECYCLE
def test_lifecycle_authoritative_and_reconciled(config):
    store = BrainMemoryStore(config=config, clock=_SeqClock())
    s = store.open_session(actor="frederique", meta={"origin": "cli"})
    e = store.record_event("intent", {"q": "x"}, session_id=s.id, actor="frederique")
    closed = store.close_session(s.id, summary="fini")
    r = BrainMemoryStore(config=config); rs = r.get_session(s.id)
    assert rs.status == "closed"
    assert rs.summary == "fini"
    assert rs.meta == {"origin": "cli"}
    assert rs.actor == "frederique"
    assert rs.started_at == s.started_at
    assert rs.updated_at == closed.updated_at and rs.updated_at != e.timestamp
    assert rs.entry_ids == [e.id]


def test_snapshot_phantom_entry_id_reconciled(config):
    store = BrainMemoryStore(config=config)
    s = store.open_session(actor="a")
    e = store.record_event("intent", {"i": 0}, session_id=s.id, actor="a")
    sess = json.loads(config.sessions_path.read_text().splitlines()[0])
    sess["entry_ids"] = list(sess["entry_ids"]) + ["mem_ffffffffffff"]
    config.sessions_path.write_text(json.dumps(sess, ensure_ascii=False) + "\n", encoding="utf-8")
    r = BrainMemoryStore(config=config)
    assert r.reconciliation_required is True
    assert r.get_session(s.id).entry_ids == [e.id]


def test_journal_session_absent_from_snapshot_fail_closed(config):
    store = BrainMemoryStore(config=config)
    store.record_event("intent", {"i": 0})
    config.sessions_path.write_text("", encoding="utf-8")
    with pytest.raises(MemoryCorruption):
        BrainMemoryStore(config=config)


# 6. RETENTION / IDENTITÉ (l'ID max EST purgé ; état X restaure journal+snapshot)
def test_retention_purges_high_id_and_no_reuse(config, tmp_path):
    store = BrainMemoryStore(config=config, clock=_DescClock(start=50))
    for i in range(8):
        store.record_event("intent", {"i": i})
    pre_ids = [e.id for e in store.entries]
    pre_max = max(_seq(x) for x in pre_ids)
    pre_id_max = max(pre_ids, key=_seq)
    pre_journal = config.entries_path.read_bytes()
    pre_sessions = config.sessions_path.read_bytes()
    report = store.apply_retention(RetentionPolicy(max_entries_per_kind=2))
    assert report["purged"] == 6
    assert pre_id_max in report["ids_purged"]
    r = BrainMemoryStore(config=config)
    ret = [e for e in r.entries if e.subtype == "retention"]; assert len(ret) == 1
    assert _seq(ret[0].id) > pre_max
    new = r.record_event("intent", {"after": True})
    assert _seq(new.id) > _seq(ret[0].id) and new.id not in set(pre_ids)
    assert r.audit()["integrity"]["ok"] is True
    old = MemoryConfig(data_dir=tmp_path / "old"); old.ensure_directories()
    old.entries_path.write_bytes(pre_journal); old.sessions_path.write_bytes(pre_sessions)
    so = BrainMemoryStore(config=old)
    assert so.audit()["integrity"]["ok"] is True
    newo = so.record_event("intent", {"after_old": True})
    assert _seq(newo.id) > pre_max


# Crash boundary réel : sessions persistées PUIS échec avant journal final
def test_retention_crash_boundary_sessions_ok_journal_fails(config, monkeypatch):
    store = BrainMemoryStore(config=config)
    for i in range(8):
        store.record_event("intent", {"i": i})
    pre_ids = [e.id for e in store.entries]; pre_max = max(_seq(x) for x in pre_ids)
    pre_journal = config.entries_path.read_bytes()

    def boom():
        raise RuntimeError("crash avant commit journal final")

    monkeypatch.setattr(store, "_persist_entries_atomic", boom)
    with pytest.raises(RuntimeError):
        store.apply_retention(RetentionPolicy(max_entries_per_kind=2))
    assert config.entries_path.read_bytes() == pre_journal
    r = BrainMemoryStore(config=config)
    assert len(r.entries) == 8
    assert r.reconciliation_required is True
    assert r.audit()["integrity"]["ok"] is True
    new = r.record_event("intent", {"after": True})
    assert _seq(new.id) > pre_max and new.id not in set(pre_ids)


# 7. RETENTION CONCURRENTE — écritures PROTÉGÉES (learning), assertions exactes
def test_retention_concurrent_writer_protected_no_lost_update(tmp_path):
    data_dir = tmp_path / "data"; go = tmp_path / "go"
    seed = BrainMemoryStore(config=MemoryConfig(data_dir=data_dir))
    for i in range(10):
        seed.record_event("intent", {"seed": i})
    n = 30
    pw = _spawn(WORKER_WRITER, data_dir, "carol", n, go, BARRIER, "learning")
    pr = _spawn(WORKER_RETENTION, data_dir, go, 5, BARRIER)
    go.write_text("go")
    rcw, _, ew = _join(pw); rcr, _, er = _join(pr)
    assert rcw == 0, ew.decode(); assert rcr == 0, er.decode()
    store = BrainMemoryStore(config=MemoryConfig(data_dir=data_dir))
    ids = [e.id for e in store.entries]
    assert len(set(ids)) == len(ids)
    assert store.audit()["integrity"]["ok"] is True
    learn = [e for e in store.entries if e.kind == "learning"]
    stmts = {e.data.get("statement") for e in learn}
    assert len(learn) == n
    assert stmts == {f"L-carol-{i}" for i in range(n)}


# 8. RÉGRESSION / COMPAT
def test_ensure_default_session_compat_governed(config):
    store = BrainMemoryStore(config=config)
    s1 = store._ensure_default_session("frederique")
    assert s1.id.startswith("ses_")
    r = BrainMemoryStore(config=config)
    assert r.get_session(s1.id) is not None
    assert store._ensure_default_session("frederique").id == s1.id


def test_kernel_recorder_cross_module_compat(config, kernel_response):
    from scc_brainai_memory.recorder import KernelRecorder
    store = BrainMemoryStore(config=config)
    out = KernelRecorder(store).record_response(kernel_response)
    assert out and "events" in out
    assert store.counts().get("event", 0) >= 1
