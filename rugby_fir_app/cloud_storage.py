# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Modulo di Cloud Object Storage (AWS S3 / Supabase Storage) con Architettura "Local Mirroring"
e query DuckDB locali ad altissima velocità per la piattaforma FIR GPS Analytics.

Architettura:
1. LOCAL MIRRORING ALL'AVVIO (`sync_remote_to_local()`):
   - All'avvio dell'applicazione (o dopo un deploy/riavvio del container), verifica se i file
     `.parquet`, `.sqlite` e `.json` sono già presenti nella cartella locale `/tmp_data`
     (sincronizzata con `data/`).
   - Se mancano (es. post-deploy), li scarica UNA SOLA VOLTA dal bucket remoto (S3 / Supabase).
2. ZERO LATENZA DI RETE IN LETTURA:
   - Tutte le letture e le query analitiche di DuckDB / Pandas puntano ESCLUSIVAMENTE ai file
     Parquet/SQLite/JSON locali scaricati su disco. Nessuna chiamata di rete viene eseguita
     durante la navigazione tra le pagine o i cambi di filtro.
3. WRITE-THROUGH IN INGESTION:
   - Quando l'Admin importa un nuovo CSV o modifica un dato (GPS, GymAware, Roster, Raduni, 23),
     il sistema aggiorna immediatamente il file locale su disco, esegue `upload_file` (upsert)
     verso il bucket remoto S3/Supabase come backup permanente e invoca `st.cache_data.clear()`.
"""

import os
import json
import time
import logging
import shutil
import sqlite3
import tempfile
from typing import Optional, Dict, Any, Callable, List
import pandas as pd

_logger = logging.getLogger("fir_cloud")
_LAST_CLOUD_ERROR: str = ""


def get_last_cloud_error() -> str:
    """Restituisce l'ultimo errore Cloud registrato (stringa vuota se l'ultima operazione è riuscita)."""
    return _LAST_CLOUD_ERROR

try:
    import streamlit as st
except ImportError:
    st = None

try:
    import boto3
    from botocore.config import Config as BotoConfig
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TMP_DATA_DIR = os.path.join(BASE_DIR, "tmp_data")
SYNC_MARKER_FILE = os.path.join(TMP_DATA_DIR, ".cloud_sync_initialized")

DEFAULT_BUCKET_NAME = "fir-gps-storage"

# Elenco completo dei file dati gestiti dal Local Mirroring
MANAGED_PARQUET_TABLES: List[str] = [
    "gps_history",
    "players",
    "player_aliases",
    "camps",
    "camp_players",
    "matches",
    "match_lineups",
    "oval_matches",
    "club_mappings",
    "gps_records",
    "drills_master",
    "drills_players_detail",
    "drills_roles_summary",
]

# Tabelle anagrafiche/convocati/formazioni critiche: mai sovrascritte da boot/bulk sync
# e sempre sottoposte a snapshot di backup automatico sul Cloud prima di ogni modifica.
PROTECTED_ROSTER_TABLES = {
    "camps",
    "camp_players",
    "matches",
    "match_lineups",
    "players",
}

MANAGED_JSON_FILES: List[str] = [
    "fir_session_types.json",
    "session_player_status.json",
    "session_timelines.json",
    "app_config.json",
    "player_photos.json",
    "users.json",
]

_PLACEHOLDER_VALUES = {
    "",
    "your-aws-access-key-id",
    "your-aws-secret-access-key",
    "inserisci-access-key-id",
    "inserisci-secret-access-key",
    "inserisci_aws_access_key_id",
    "inserisci_aws_secret_access_key",
    "inserisci_supabase_service_role_key",
    "mio-bucket",
    "your-supabase-url",
    "your-supabase-service-role-key",
    "none",
    "null",
}


def _is_valid_secret(val: Optional[str]) -> bool:
    if not val or not isinstance(val, str):
        return False
    clean = val.strip()
    if not clean or clean.lower() in _PLACEHOLDER_VALUES:
        return False
    if clean.startswith("INSERISCI_") or clean.startswith("YOUR_"):
        return False
    return True


def _read_local_toml_fallback() -> Dict[str, Any]:
    """Legge manualmente .streamlit/secrets.toml se eseguito fuori dal runtime Streamlit."""
    candidates = [
        os.path.join(BASE_DIR, ".streamlit", "secrets.toml"),
        os.path.join(os.path.dirname(BASE_DIR), ".streamlit", "secrets.toml"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                try:
                    import tomllib
                    with open(path, "rb") as f:
                        return tomllib.load(f)
                except ImportError:
                    out = {}
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or line.startswith("["):
                                continue
                            if "=" in line:
                                k, v = line.split("=", 1)
                                out[k.strip()] = v.strip().strip('"').strip("'")
                    return out
            except Exception:
                pass
    return {}


_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def get_cloud_config() -> Dict[str, Any]:
    """Recupera e memorizza in memoria la configurazione Cloud Object Storage (S3 o Supabase)."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    secrets_dict: Dict[str, Any] = {}
    local_toml = _read_local_toml_fallback()
    if isinstance(local_toml, dict):
        secrets_dict.update(local_toml)

    if st is not None:
        try:
            for k in st.secrets:
                val = st.secrets[k]
                if isinstance(val, dict) or hasattr(val, "items"):
                    for sub_k, sub_v in val.items():
                        secrets_dict[sub_k] = sub_v
                        secrets_dict[f"{k}.{sub_k}"] = sub_v
                else:
                    secrets_dict[k] = val
        except Exception:
            pass

    def _get_key(*names: str, default: str = "") -> str:
        for n in names:
            env_val = os.environ.get(n)
            if _is_valid_secret(env_val):
                return env_val.strip()
            sec_val = secrets_dict.get(n)
            if _is_valid_secret(str(sec_val) if sec_val is not None else ""):
                return str(sec_val).strip()
        return default

    aws_access_key = _get_key("AWS_ACCESS_KEY_ID", "aws_access_key_id", "S3_ACCESS_KEY_ID")
    aws_secret_key = _get_key("AWS_SECRET_ACCESS_KEY", "aws_secret_access_key", "S3_SECRET_ACCESS_KEY")
    aws_region = _get_key("AWS_REGION", "AWS_DEFAULT_REGION", "aws_region", default="eu-central-1")
    aws_endpoint = _get_key("AWS_ENDPOINT_URL", "S3_ENDPOINT_URL", "aws_endpoint_url", default="")

    supabase_url = _get_key("SUPABASE_URL", "supabase_url")
    supabase_key = _get_key(
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "supabase_service_key",
        "SUPABASE_KEY",
        "supabase_key",
    )

    bucket_name = _get_key("BUCKET_NAME", "S3_BUCKET_NAME", "SUPABASE_BUCKET_NAME", "bucket_name", default=DEFAULT_BUCKET_NAME)

    has_s3 = bool(aws_access_key and aws_secret_key and HAS_BOTO3)
    has_supabase = bool(supabase_url and supabase_key and HAS_SUPABASE)

    provider = "none"
    if has_s3:
        provider = "s3"
    elif has_supabase:
        provider = "supabase"

    _CONFIG_CACHE = {
        "enabled": provider != "none",
        "provider": provider,
        "has_s3": has_s3,
        "has_supabase": has_supabase,
        "bucket_name": bucket_name,
        "aws_access_key_id": aws_access_key,
        "aws_secret_access_key": aws_secret_key,
        "aws_region": aws_region,
        "aws_endpoint_url": aws_endpoint,
        "supabase_url": supabase_url,
        "supabase_key": supabase_key,
    }
    return _CONFIG_CACHE


def is_cloud_enabled() -> bool:
    """Restituisce True se è configurato un provider Cloud Object Storage (S3 o Supabase)."""
    return bool(get_cloud_config().get("enabled", False))


# ==============================================================================
# CLIENT S3 (BOTO3) E SUPABASE STORAGE
# ==============================================================================
_S3_CLIENT_CACHE = None
_SUPABASE_CLIENT_CACHE = None
_BUCKET_VERIFIED = set()


def get_s3_client():
    global _S3_CLIENT_CACHE
    if _S3_CLIENT_CACHE is not None:
        return _S3_CLIENT_CACHE

    cfg = get_cloud_config()
    if not cfg["has_s3"]:
        return None

    kwargs: Dict[str, Any] = {
        "service_name": "s3",
        "aws_access_key_id": cfg["aws_access_key_id"],
        "aws_secret_access_key": cfg["aws_secret_access_key"],
        "region_name": cfg["aws_region"],
        "config": BotoConfig(
            signature_version="s3v4",
            connect_timeout=8,
            read_timeout=25,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    }
    if cfg["aws_endpoint_url"]:
        kwargs["endpoint_url"] = cfg["aws_endpoint_url"]

    _S3_CLIENT_CACHE = boto3.client(**kwargs)
    return _S3_CLIENT_CACHE


def get_supabase_client():
    global _SUPABASE_CLIENT_CACHE
    if _SUPABASE_CLIENT_CACHE is not None:
        return _SUPABASE_CLIENT_CACHE

    cfg = get_cloud_config()
    if not cfg["has_supabase"]:
        return None

    try:
        _SUPABASE_CLIENT_CACHE = create_client(cfg["supabase_url"], cfg["supabase_key"])
        return _SUPABASE_CLIENT_CACHE
    except Exception:
        return None


def _ensure_bucket_exists(cfg: Dict[str, Any]) -> bool:
    bucket = cfg["bucket_name"]
    cache_key = f"{cfg['provider']}:{bucket}"
    if cache_key in _BUCKET_VERIFIED:
        return True

    if cfg["provider"] == "s3":
        s3 = get_s3_client()
        if not s3:
            return False
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            try:
                if cfg["aws_region"] and cfg["aws_region"] != "us-east-1":
                    s3.create_bucket(
                        Bucket=bucket,
                        CreateBucketConfiguration={"LocationConstraint": cfg["aws_region"]},
                    )
                else:
                    s3.create_bucket(Bucket=bucket)
            except Exception:
                pass
        _BUCKET_VERIFIED.add(cache_key)
        return True

    elif cfg["provider"] == "supabase":
        sb = get_supabase_client()
        if not sb:
            return False
        try:
            buckets = sb.storage.list_buckets()
            existing_names = [
                getattr(b, "name", None) or (b.get("name") if isinstance(b, dict) else None)
                for b in (buckets or [])
            ]
            if bucket not in existing_names:
                sb.storage.create_bucket(bucket, options={"public": False})
        except Exception:
            pass
        _BUCKET_VERIFIED.add(cache_key)
        return True

    return False


def download_cloud_object_to_file(remote_key: str, dest_local_path: str) -> bool:
    """Scarica un singolo file dal bucket remoto nel percorso locale specificato."""
    cfg = get_cloud_config()
    if not cfg["enabled"]:
        return False

    _ensure_bucket_exists(cfg)
    bucket = cfg["bucket_name"]

    if cfg["provider"] == "s3":
        s3 = get_s3_client()
        if not s3:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(dest_local_path)), exist_ok=True)
            s3.download_file(bucket, remote_key, dest_local_path)
            return os.path.exists(dest_local_path) and os.path.getsize(dest_local_path) > 0
        except Exception:
            return False

    elif cfg["provider"] == "supabase":
        sb = get_supabase_client()
        if not sb:
            return False
        try:
            res_bytes = sb.storage.from_(bucket).download(remote_key)
            if res_bytes:
                os.makedirs(os.path.dirname(os.path.abspath(dest_local_path)), exist_ok=True)
                with open(dest_local_path, "wb") as f:
                    f.write(res_bytes)
                return True
        except Exception:
            return False

    return False


def upload_file_to_cloud_object(local_src_path: str, remote_key: str, content_type: str = "application/octet-stream") -> bool:
    """Carica (sovrascrive in upsert) un file locale verso il bucket remoto S3/Supabase con retry automatico e logging."""
    global _LAST_CLOUD_ERROR
    _LAST_CLOUD_ERROR = ""

    if not os.path.exists(local_src_path):
        _LAST_CLOUD_ERROR = f"File locale non trovato: {local_src_path}"
        return False

    cfg = get_cloud_config()
    if not cfg["enabled"]:
        return False

    _ensure_bucket_exists(cfg)
    bucket = cfg["bucket_name"]

    for attempt in range(2):
        if cfg["provider"] == "s3":
            s3 = get_s3_client()
            if not s3:
                _LAST_CLOUD_ERROR = "Client S3 non inizializzato"
                return False
            try:
                s3.upload_file(
                    local_src_path,
                    bucket,
                    remote_key,
                    ExtraArgs={"ContentType": content_type},
                )
                return True
            except Exception as exc:
                _LAST_CLOUD_ERROR = f"Errore upload S3 ({remote_key}): {exc}"
                _logger.warning("%s (tentativo %d/2)", _LAST_CLOUD_ERROR, attempt + 1)

        elif cfg["provider"] == "supabase":
            sb = get_supabase_client()
            if not sb:
                _LAST_CLOUD_ERROR = "Client Supabase non inizializzato"
                return False
            try:
                with open(local_src_path, "rb") as f:
                    data_bytes = f.read()
                sb.storage.from_(bucket).upload(
                    path=remote_key,
                    file=data_bytes,
                    file_options={"content-type": content_type, "upsert": "true"},
                )
                return True
            except Exception as exc:
                _LAST_CLOUD_ERROR = f"Errore upload Supabase ({remote_key}): {exc}"
                _logger.warning("%s (tentativo %d/2)", _LAST_CLOUD_ERROR, attempt + 1)
        else:
            return False

        if attempt == 0:
            time.sleep(0.6)

    return False


def pull_single_file_from_cloud(remote_filename: str, local_fallback_path: Optional[str] = None) -> bool:
    """Scarica l'ultima versione di un singolo file dal Cloud in tmp_data/ (e data/) per prevenire sovrascritture concorrenti."""
    cfg = get_cloud_config()
    if not cfg["enabled"]:
        return False
    os.makedirs(TMP_DATA_DIR, exist_ok=True)
    tmp_dest = os.path.join(TMP_DATA_DIR, remote_filename)
    ok = download_cloud_object_to_file(remote_filename, tmp_dest)
    if ok and local_fallback_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(local_fallback_path)), exist_ok=True)
            shutil.copy2(tmp_dest, local_fallback_path)
        except Exception as exc:
            _logger.warning("Impossibile allineare %s: %s", local_fallback_path, exc)
    return ok


# ==============================================================================
# TASK 1: LOCAL MIRRORING ALL'AVVIO (`sync_remote_to_local()`)
# ==============================================================================
_PROCESS_SYNC_DONE = False


def get_local_mirror_path(filename: str) -> str:
    """
    Restituisce il percorso locale in `tmp_data/{filename}`.
    Se non esiste ancora in `tmp_data` ma esiste in `data/`, lo copia in `tmp_data`.
    """
    os.makedirs(TMP_DATA_DIR, exist_ok=True)
    tmp_p = os.path.join(TMP_DATA_DIR, filename)
    data_p = os.path.join(DATA_DIR, filename)
    if not os.path.exists(tmp_p) and os.path.exists(data_p):
        try:
            shutil.copy2(data_p, tmp_p)
        except Exception:
            return data_p
    return tmp_p


def sync_remote_to_local(force: bool = False) -> Dict[str, Any]:
    """
    Inizializza il Local Mirroring all'avvio dell'applicazione:
    - Verifica se i file `.parquet`, `.sqlite` e `.json` esistono nella cartella locale `/tmp_data`
      (e se il marker `.cloud_sync_initialized` è già presente).
    - Se mancano (es. subito dopo un deploy o riavvio del container su Streamlit Cloud) o se `force=True`,
      scarica i file dal bucket remoto in `/tmp_data` e allinea anche `data/`.
    - Durante tutta la successiva esecuzione dell'app, questa funzione ritorna istantaneamente
      in 0 ms senza effettuare alcuna chiamata di rete.
    """
    global _PROCESS_SYNC_DONE
    if _PROCESS_SYNC_DONE and not force and os.path.exists(SYNC_MARKER_FILE):
        return {"status": "cached_local", "downloaded": []}

    os.makedirs(TMP_DATA_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    all_files = [f"{t}.parquet" for t in MANAGED_PARQUET_TABLES] + MANAGED_JSON_FILES + [
        "rugby_database.sqlite",
        "gymaware_data.parquet",
    ]

    # Se il marker esiste su disco e non è richiesto force, verifica comunque eventuali nuovi file mancanti in TMP_DATA_DIR
    if not force and os.path.exists(SYNC_MARKER_FILE):
        missing_files = [
            fn for fn in all_files
            if not (os.path.exists(os.path.join(TMP_DATA_DIR, fn)) and os.path.getsize(os.path.join(TMP_DATA_DIR, fn)) > 0)
        ]
        if not missing_files:
            _PROCESS_SYNC_DONE = True
            return {"status": "already_synced_on_disk", "downloaded": []}
        target_files = missing_files
    else:
        target_files = all_files

    cfg = get_cloud_config()
    downloaded = []

    for fname in target_files:
        tmp_dest = os.path.join(TMP_DATA_DIR, fname)
        data_dest = os.path.join(DATA_DIR, fname)

        # Se non forzato e il file è già stato scaricato in TMP_DATA_DIR, salta il download
        if not force and os.path.exists(tmp_dest) and os.path.getsize(tmp_dest) > 0:
            continue

        pulled = False
        if cfg["enabled"]:
            pulled = download_cloud_object_to_file(fname, tmp_dest)
            if pulled:
                downloaded.append(fname)
                # Allinea anche la cartella data/ locale
                try:
                    shutil.copy2(tmp_dest, data_dest)
                except Exception:
                    pass

        # Se non era presente sul Cloud (o download fallito), usa la copia di baseline in data/ SOLO localmente.
        # MAI sovrascrivere il Cloud con data/ durante il boot sync, per evitare di ripristinare baseline Git obsolete.
        if not pulled and os.path.exists(data_dest):
            try:
                shutil.copy2(data_dest, tmp_dest)
            except Exception:
                pass
            if cfg["enabled"]:
                _logger.warning("Download Cloud fallito o assente per %s: uso fallback locale senza sovrascrivere il Cloud.", fname)

    # Allinea la tabella SQLite GymAware dal parquet scaricato se più aggiornato
    try:
        tmp_gym_pq = os.path.join(TMP_DATA_DIR, "gymaware_data.parquet")
        tmp_sqlite = os.path.join(TMP_DATA_DIR, "rugby_database.sqlite")
        data_sqlite = os.path.join(DATA_DIR, "rugby_database.sqlite")
        if os.path.exists(tmp_gym_pq):
            df_gym = pd.read_parquet(tmp_gym_pq)
            if not df_gym.empty:
                for sq_path in (tmp_sqlite, data_sqlite):
                    conn = sqlite3.connect(sq_path)
                    try:
                        df_gym.to_sql("gymaware_data", conn, if_exists="replace", index=False)
                        conn.commit()
                    finally:
                        conn.close()
    except Exception:
        pass

    try:
        with open(SYNC_MARKER_FILE, "w", encoding="utf-8") as f:
            f.write("synced")
    except Exception:
        pass

    _PROCESS_SYNC_DONE = True
    return {"status": "synced_from_cloud", "downloaded": downloaded}


# ==============================================================================
# LETTURA LOCALE VELOCE TRAMITE DUCKDB / PANDAS (ZERO LATENZA DI RETE)
# ==============================================================================
def query_local_parquet_duckdb(local_parquet_path: str, sql_where: Optional[str] = None) -> pd.DataFrame:
    """
    Esegue una query analitica DuckDB direttamente sul file Parquet LOCALE scaricato.
    Non apre mai connessioni di rete `s3://` o `httpfs` durante la lettura.
    """
    if not os.path.exists(local_parquet_path):
        return pd.DataFrame()

    if HAS_DUCKDB and sql_where:
        con = duckdb.connect(database=":memory:")
        try:
            safe_path = local_parquet_path.replace("'", "''")
            q = f"SELECT * FROM read_parquet('{safe_path}') WHERE {sql_where}"
            return con.execute(q).df()
        except Exception:
            pass
        finally:
            try:
                con.close()
            except Exception:
                pass

    try:
        return pd.read_parquet(local_parquet_path)
    except Exception:
        return pd.DataFrame()


def load_parquet_with_cloud_sync(table_name: str, local_fallback_path: str) -> pd.DataFrame:
    """
    Carica la tabella `.parquet` dal mirror locale (`/tmp_data` o `data/`) a latenza zero.
    Se l'app è appena stata avviata e `/tmp_data` non è ancora inizializzata, esegue
    una sola volta `sync_remote_to_local()`.
    """
    if not _PROCESS_SYNC_DONE:
        sync_remote_to_local(force=False)

    fname = f"{table_name}.parquet"
    mirror_path = get_local_mirror_path(fname)
    if os.path.exists(mirror_path):
        try:
            return query_local_parquet_duckdb(mirror_path)
        except Exception as exc:
            _logger.warning("Errore lettura mirror %s: %s", mirror_path, exc)

    if os.path.exists(local_fallback_path):
        return query_local_parquet_duckdb(local_fallback_path)

    return pd.DataFrame()


def _backup_protected_table_on_cloud(table_name: str, fname: str) -> None:
    """Salva uno snapshot della versione Cloud corrente prima di sovrascrivere una tabella protetta."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            prev_local = os.path.join(tmpdir, fname)
            if download_cloud_object_to_file(fname, prev_local):
                upload_file_to_cloud_object(
                    prev_local,
                    f"backups/{table_name}_prev.parquet",
                    content_type="application/octet-stream",
                )
                day_tag = time.strftime("%Y%m%d")
                upload_file_to_cloud_object(
                    prev_local,
                    f"backups/{table_name}_{day_tag}.parquet",
                    content_type="application/octet-stream",
                )
    except Exception as exc:
        _logger.warning("Snapshot backup Cloud fallito per %s: %s", table_name, exc)


def save_parquet_with_cloud_sync(table_name: str, df: pd.DataFrame, local_fallback_path: str) -> bool:
    """
    Logica Write-Through per Data Ingestion / Modifica Tabelle:
    1. Aggiorna prima il file Parquet LOCALE (in `/tmp_data` e in `data/`).
    2. Esegue `upload_file` (sovrascrittura) verso il bucket remoto S3/Supabase come backup.
    """
    fname = f"{table_name}.parquet"
    mirror_path = os.path.join(TMP_DATA_DIR, fname)
    os.makedirs(TMP_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(local_fallback_path)), exist_ok=True)

    # Protezione anti-cancellazione accidentale per tabelle convocati/formazioni/roster
    if table_name in PROTECTED_ROSTER_TABLES and (df is None or df.empty):
        existing_ref = mirror_path if os.path.exists(mirror_path) else local_fallback_path
        if os.path.exists(existing_ref) and os.path.getsize(existing_ref) > 0:
            _logger.error("Bloccato salvataggio DataFrame vuoto su tabella protetta %s.", table_name)
            return False

    cfg = get_cloud_config()
    if cfg["enabled"] and table_name in PROTECTED_ROSTER_TABLES:
        _backup_protected_table_on_cloud(table_name, fname)

    # 1. Aggiorna immediatamente i file Parquet locali
    df.to_parquet(mirror_path, index=False)
    try:
        shutil.copy2(mirror_path, local_fallback_path)
    except Exception:
        df.to_parquet(local_fallback_path, index=False)

    # 2. Backup sul bucket remoto S3/Supabase
    if cfg["enabled"]:
        return upload_file_to_cloud_object(mirror_path, fname, content_type="application/octet-stream")
    return True


def ingest_and_append_remote_parquet(
    table_name: str,
    new_rows_df: pd.DataFrame,
    local_fallback_path: str,
    merge_fn: Optional[Callable[[pd.DataFrame, pd.DataFrame], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Pipeline di Data Ingestion veloce (Local-First + Cloud Backup):
    1. Legge il file Parquet locale già sincronizzato in `/tmp_data`.
    2. Appende e deduplica i nuovi dati tramite `merge_fn`.
    3. Aggiorna prima il file Parquet locale (`/tmp_data` e `data/`).
    4. Esegue `upload_file` (sovrascrittura) verso il bucket remoto S3/Supabase.
    """
    if not _PROCESS_SYNC_DONE:
        sync_remote_to_local(force=False)

    fname = f"{table_name}.parquet"
    # Pull-Before-Write: scarica l'ultima versione remota prima di appendere/unire per prevenire lost update concorrenti
    pull_single_file_from_cloud(fname, local_fallback_path)
    mirror_path = get_local_mirror_path(fname)

    existing_df = pd.DataFrame()
    if os.path.exists(mirror_path):
        try:
            existing_df = pd.read_parquet(mirror_path)
        except Exception:
            existing_df = pd.DataFrame()
    elif os.path.exists(local_fallback_path):
        try:
            existing_df = pd.read_parquet(local_fallback_path)
        except Exception:
            existing_df = pd.DataFrame()

    if merge_fn is not None:
        result = merge_fn(existing_df, new_rows_df)
        combined_df = result.get("combined_df", existing_df)
    else:
        combined_df = pd.concat([existing_df, new_rows_df], ignore_index=True)
        result = {
            "combined_df": combined_df,
            "inserted": len(new_rows_df),
            "duplicates": 0,
            "duplicate_df": pd.DataFrame(),
            "total": len(new_rows_df),
        }

    # Salva prima in locale e poi effettua upload_file sul bucket remoto
    cloud_ok = save_parquet_with_cloud_sync(table_name, combined_df, local_fallback_path)
    result["cloud_ok"] = bool(cloud_ok)
    if not cloud_ok and get_cloud_config().get("enabled"):
        result["cloud_error"] = get_last_cloud_error()
    return result


# ==============================================================================
# GESTIONE LOCALE + BACKUP REMOTO PER GYMAWARE (SQLITE) E FILE JSON
# ==============================================================================
def pull_gymaware_from_cloud(sqlite_path: str, force: bool = False) -> bool:
    """
    In modalità Local Mirroring, i dati GymAware sono già sincronizzati all'avvio
    da `sync_remote_to_local()`. Se `force=True`, riscarica da Cloud.
    """
    if not _PROCESS_SYNC_DONE or force:
        sync_remote_to_local(force=force)
    return True


def push_gymaware_to_cloud(sqlite_path: str) -> bool:
    """
    Quando viene caricato o modificato un dato GymAware:
    1. Aggiorna il file Parquet/SQLite locale in `/tmp_data` e `data/`.
    2. Esegue l'upload verso il bucket remoto S3/Supabase.
    """
    if not os.path.exists(sqlite_path):
        return False

    os.makedirs(TMP_DATA_DIR, exist_ok=True)
    tmp_gym_pq = os.path.join(TMP_DATA_DIR, "gymaware_data.parquet")
    tmp_sqlite = os.path.join(TMP_DATA_DIR, "rugby_database.sqlite")

    try:
        conn = sqlite3.connect(sqlite_path)
        try:
            df_gym = pd.read_sql_query("SELECT * FROM gymaware_data", conn)
        finally:
            conn.close()

        df_gym.to_parquet(tmp_gym_pq, index=False)
        if os.path.abspath(sqlite_path) != os.path.abspath(tmp_sqlite):
            try:
                shutil.copy2(sqlite_path, tmp_sqlite)
            except Exception:
                pass

        cfg = get_cloud_config()
        if cfg["enabled"]:
            ok_pq = upload_file_to_cloud_object(tmp_gym_pq, "gymaware_data.parquet", content_type="application/octet-stream")
            upload_file_to_cloud_object(sqlite_path, "rugby_database.sqlite", content_type="application/octet-stream")
            return ok_pq
        return True
    except Exception:
        return False


def load_json_with_cloud_sync(remote_filename: str, local_path: str, default_factory=dict):
    """Legge il file JSON direttamente dal disco locale (già sincronizzato all'avvio)."""
    if not _PROCESS_SYNC_DONE:
        sync_remote_to_local(force=False)

    mirror_path = get_local_mirror_path(remote_filename)
    for p in (mirror_path, local_path):
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return default_factory()


def save_json_with_cloud_sync(remote_filename: str, local_path: str, data: Any) -> bool:
    """
    Salva il file JSON prima sul disco locale (`/tmp_data` e `data/`)
    e poi esegue `upload_file` verso il bucket remoto.
    """
    os.makedirs(TMP_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    mirror_path = os.path.join(TMP_DATA_DIR, remote_filename)

    try:
        with open(mirror_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            shutil.copy2(mirror_path, local_path)
        except Exception:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        cfg = get_cloud_config()
        if cfg["enabled"]:
            return upload_file_to_cloud_object(mirror_path, remote_filename, content_type="application/json")
        return True
    except Exception:
        return False


def sync_all_local_data_to_cloud(data_dir: str = DATA_DIR, include_protected: bool = False) -> Dict[str, Any]:
    """Carica manualmente tutti i file locali verso il bucket remoto S3/Supabase.
    Preferisce i file in `TMP_DATA_DIR` (dati live) rispetto a `data_dir` (baseline Git) e
    protegge `PROTECTED_ROSTER_TABLES` da sovrascritture accidentali se `include_protected=False`.
    """
    cfg = get_cloud_config()
    if not cfg["enabled"]:
        return {"ok": False, "reason": "Cloud storage non configurato", "uploaded": []}

    uploaded = []
    skipped_protected = []
    errors = []

    if not os.path.exists(data_dir):
        return {"ok": False, "reason": f"Directory {data_dir} non trovata", "uploaded": []}

    protected_filenames = {f"{t}.parquet" for t in PROTECTED_ROSTER_TABLES}

    for fname in sorted(os.listdir(data_dir)):
        tmp_candidate = os.path.join(TMP_DATA_DIR, fname)
        data_candidate = os.path.join(data_dir, fname)
        fpath = tmp_candidate if os.path.isfile(tmp_candidate) and os.path.getsize(tmp_candidate) > 0 else data_candidate
        if not os.path.isfile(fpath):
            continue
        if fname.endswith(".parquet") or fname.endswith(".json") or fname.endswith(".sqlite"):
            if not include_protected and fname in protected_filenames:
                with tempfile.TemporaryDirectory() as tmpdir:
                    if download_cloud_object_to_file(fname, os.path.join(tmpdir, fname)):
                        skipped_protected.append(fname)
                        continue
            ctype = "application/json" if fname.endswith(".json") else "application/octet-stream"
            # Aggiorna anche tmp_data
            try:
                os.makedirs(TMP_DATA_DIR, exist_ok=True)
                if os.path.abspath(fpath) != os.path.abspath(tmp_candidate):
                    shutil.copy2(fpath, tmp_candidate)
            except Exception:
                pass
            if upload_file_to_cloud_object(fpath, fname, content_type=ctype):
                uploaded.append(fname)
            else:
                errors.append(fname)

            if fname == "rugby_database.sqlite":
                if push_gymaware_to_cloud(fpath):
                    uploaded.append("gymaware_data.parquet")

    return {
        "ok": len(errors) == 0,
        "provider": cfg["provider"],
        "bucket": cfg["bucket_name"],
        "uploaded": uploaded,
        "skipped_protected": skipped_protected,
        "errors": errors,
    }
