# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Modulo di Cloud Object Storage Permanente (AWS S3 / Supabase Storage) + DuckDB httpfs
per la piattaforma FIR GPS Analytics.

Disaccoppia il codice applicativo dai dati (Parquet, SQLite GymAware e JSON di configurazione),
prevenendo qualsiasi perdita di dati (Data Loss) ad ogni nuovo deploy (git push) su Streamlit Cloud.
"""

import os
import io
import json
import shutil
import sqlite3
import tempfile
from typing import Optional, Dict, Any, Callable
import pandas as pd

try:
    import streamlit as st
except ImportError:
    st = None

try:
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import ClientError
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
DEFAULT_BUCKET_NAME = "fir-gps-storage"

# Valori segnaposto da ignorare se non ancora compilati dall'utente
_PLACEHOLDER_VALUES = {
    "",
    "your-aws-access-key-id",
    "your-aws-secret-access-key",
    "inserisci-access-key-id",
    "inserisci-secret-access-key",
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
    """Legge manualmente .streamlit/secrets.toml se eseguito fuori dal contesto runtime Streamlit."""
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
                    # Parser minimale key = "value" per compatibilità Python < 3.11
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


def get_cloud_config() -> Dict[str, Any]:
    """
    Recupera le credenziali Cloud Object Storage da:
    1. Variabili d'ambiente (os.environ)
    2. st.secrets (Streamlit Cloud Secrets / .streamlit/secrets.toml)
    3. Fallback lettura diretta .streamlit/secrets.toml

    Supporta sia AWS S3 (o storage S3-compatibile come Supabase S3 / Cloudflare R2)
    sia Supabase Storage REST API.
    """
    secrets_dict: Dict[str, Any] = {}

    # 1. Carica da file locale di fallback
    local_toml = _read_local_toml_fallback()
    if isinstance(local_toml, dict):
        secrets_dict.update(local_toml)

    # 2. Carica da st.secrets se disponibile
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
        " supabase_service_key",
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

    return {
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


# ==============================================================================
# CLIENT S3 (BOTO3) E SUPABASE STORAGE
# ==============================================================================
_S3_CLIENT_CACHE = None
_SUPABASE_CLIENT_CACHE = None
_BUCKET_VERIFIED = set()


def get_s3_client():
    """Restituisce il client boto3 S3 configurato."""
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
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    }
    if cfg["aws_endpoint_url"]:
        kwargs["endpoint_url"] = cfg["aws_endpoint_url"]

    _S3_CLIENT_CACHE = boto3.client(**kwargs)
    return _S3_CLIENT_CACHE


def get_supabase_client():
    """Restituisce il client Supabase Storage configurato."""
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
    """Verifica che il bucket remoto esista (e lo crea se possibile su Supabase/S3)."""
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
            _BUCKET_VERIFIED.add(cache_key)
            return True
        except Exception:
            try:
                if cfg["aws_region"] and cfg["aws_region"] != "us-east-1":
                    s3.create_bucket(
                        Bucket=bucket,
                        CreateBucketConfiguration={"LocationConstraint": cfg["aws_region"]},
                    )
                else:
                    s3.create_bucket(Bucket=bucket)
                _BUCKET_VERIFIED.add(cache_key)
                return True
            except Exception:
                # Anche se head_bucket/create_bucket non sono permessi dalla policy IAM,
                # l'utente potrebbe avere permessi s3:GetObject e s3:PutObject sul bucket.
                _BUCKET_VERIFIED.add(cache_key)
                return True

    elif cfg["provider"] == "supabase":
        sb = get_supabase_client()
        if not sb:
            return False
        try:
            buckets = sb.storage.list_buckets()
            existing_names = [ getattr(b, "name", None) or (b.get("name") if isinstance(b, dict) else None) for b in (buckets or []) ]
            if bucket not in existing_names:
                sb.storage.create_bucket(bucket, options={"public": False})
            _BUCKET_VERIFIED.add(cache_key)
            return True
        except Exception:
            _BUCKET_VERIFIED.add(cache_key)
            return True

    return False


# ==============================================================================
# OPERAZIONI DI BASSO LIVELLO SU CLOUD OBJECT STORAGE (DOWNLOAD / UPLOAD FILE)
# ==============================================================================
def download_cloud_object_to_file(remote_key: str, dest_local_path: str) -> bool:
    """
    Scarica un file dal bucket remoto (S3 o Supabase Storage) nel percorso locale specificato.
    Ritorna True se il download è riuscito, False se il file non esiste o in caso di errore.
    """
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
    """
    Carica (o sovrascrive in modalità atomica/upsert) un file locale sul bucket remoto (S3 o Supabase Storage).
    """
    if not os.path.exists(local_src_path):
        return False

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
            s3.upload_file(
                local_src_path,
                bucket,
                remote_key,
                ExtraArgs={"ContentType": content_type},
            )
            return True
        except Exception:
            return False

    elif cfg["provider"] == "supabase":
        sb = get_supabase_client()
        if not sb:
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
        except Exception:
            return False

    return False


# ==============================================================================
# 2. CONNESSIONE DUCKDB CON ESTENSIONE HTTPFS (QUERY DIRETTE SU PARQUET REMOTI)
# ==============================================================================
def get_duckdb_cloud_connection():
    """
    Crea e restituisce una connessione DuckDB configurata con l'estensione `httpfs`
    per interrogare direttamente i file `.parquet` ospitati su Cloud Object Storage
    tramite protocollo `s3://` o `https://`.
    """
    if not HAS_DUCKDB:
        return None

    cfg = get_cloud_config()
    con = duckdb.connect(database=":memory:")

    try:
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")
    except Exception:
        # In ambienti in cui httpfs è già pre-installato o bloccato in scrittura, tenta solo LOAD
        try:
            con.execute("LOAD httpfs;")
        except Exception:
            pass

    if cfg["has_s3"]:
        region = cfg["aws_region"] or "eu-central-1"
        ak = cfg["aws_access_key_id"].replace("'", "''")
        sk = cfg["aws_secret_access_key"].replace("'", "''")
        con.execute(f"SET s3_region='{region}';")
        con.execute(f"SET s3_access_key_id='{ak}';")
        con.execute(f"SET s3_secret_access_key='{sk}';")

        if cfg["aws_endpoint_url"]:
            # Gestione endpoint S3 custom (es. Supabase S3 Storage, Cloudflare R2, MinIO)
            ep = cfg["aws_endpoint_url"].replace("https://", "").replace("http://", "").rstrip("/")
            con.execute(f"SET s3_endpoint='{ep}';")
            con.execute("SET s3_url_style='path';")
            con.execute("SET s3_use_ssl=true;")

    return con


def query_remote_parquet_duckdb(table_name: str, sql_where: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    Interroga direttamente il file Parquet remoto tramite DuckDB + `httpfs`:
        `SELECT * FROM read_parquet('s3://<BUCKET_NAME>/<table_name>.parquet')`
    Se il provider è Supabase REST (senza chiavi S3), genera un URL firmato HTTPS
    e lo interroga tramite DuckDB `read_parquet('https://...')`.
    """
    if not HAS_DUCKDB:
        return None

    cfg = get_cloud_config()
    if not cfg["enabled"]:
        return None

    remote_key = f"{table_name}.parquet"
    bucket = cfg["bucket_name"]
    where_clause = f" WHERE {sql_where}" if sql_where else ""

    con = get_duckdb_cloud_connection()
    if con is None:
        return None

    try:
        if cfg["has_s3"]:
            s3_uri = f"s3://{bucket}/{remote_key}"
            query = f"SELECT * FROM read_parquet('{s3_uri}'){where_clause}"
            df = con.execute(query).df()
            return df

        elif cfg["has_supabase"]:
            sb = get_supabase_client()
            if sb is not None:
                signed = sb.storage.from_(bucket).create_signed_url(remote_key, 60)
                signed_url = None
                if isinstance(signed, dict):
                    signed_url = signed.get("signedURL") or signed.get("signedUrl")
                if signed_url:
                    query = f"SELECT * FROM read_parquet('{signed_url}'){where_clause}"
                    df = con.execute(query).df()
                    return df
    except Exception:
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass

    return None


# ==============================================================================
# 3. MODULO DI FETCHING & INGESTION PARQUET (CON FILE TEMPORANEO ATOMICO)
# ==============================================================================
# Cache di sessione per evitare download ripetuti ad ogni rerun della stessa pagina
_CLOUD_PARQUET_SYNC_TS: Dict[str, float] = {}


def load_parquet_with_cloud_sync(table_name: str, local_fallback_path: str) -> pd.DataFrame:
    """
    Legge una tabella `.parquet` garantendo la persistenza Cloud:
    1. Se il Cloud Storage è attivo:
       - Tenta la lettura diretta dal Cloud tramite DuckDB `httpfs` (`s3://bucket/{table_name}.parquet`)
         oppure scaricando il `.parquet` remoto in un file temporaneo.
       - Se il file esiste sul Cloud, aggiorna la cache locale e restituisce il DataFrame.
       - Se il file NON esiste ancora sul Cloud ma esiste in locale (`data/{table_name}.parquet`),
         esegue il bootstrap automatico caricando il file locale sul bucket remoto.
    2. Se il Cloud Storage non è ancora configurato, legge dal file locale `local_fallback_path`.
    """
    cfg = get_cloud_config()
    remote_key = f"{table_name}.parquet"

    if cfg["enabled"]:
        # 1a. Tentativo query diretta DuckDB httpfs (es. SELECT * FROM read_parquet('s3://...'))
        df_remote = query_remote_parquet_duckdb(table_name)
        if df_remote is not None:
            # Sincronizza anche la copia di cache locale per performance e resilienza
            try:
                os.makedirs(os.path.dirname(os.path.abspath(local_fallback_path)), exist_ok=True)
                df_remote.to_parquet(local_fallback_path, index=False)
            except Exception:
                pass
            return df_remote

        # 1b. Fallback download tramite client boto3 / Supabase su file temporaneo
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{table_name}.parquet")
        os.close(tmp_fd)
        try:
            downloaded = download_cloud_object_to_file(remote_key, tmp_path)
            if downloaded:
                df_dl = pd.read_parquet(tmp_path)
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(local_fallback_path)), exist_ok=True)
                    shutil.copy2(tmp_path, local_fallback_path)
                except Exception:
                    pass
                return df_dl
            else:
                # Il file non è ancora presente sul bucket remoto:
                # se abbiamo una baseline locale, effettuiamo il seed automatico sul Cloud
                if os.path.exists(local_fallback_path):
                    upload_file_to_cloud_object(local_fallback_path, remote_key, content_type="application/octet-stream")
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    # Fallback locale
    if os.path.exists(local_fallback_path):
        try:
            return pd.read_parquet(local_fallback_path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def save_parquet_with_cloud_sync(table_name: str, df: pd.DataFrame, local_fallback_path: str) -> bool:
    """
    Salva e sovrascrive un DataFrame su file `.parquet` applicando il flusso Cloud:
    a) Scrive il Parquet aggiornato in un file temporaneo locale (`tempfile`).
    b) Effettua l'upload (sovrascrittura) del Parquet aggiornato direttamente sul bucket remoto.
    c) Aggiorna la copia di cache locale (`local_fallback_path`).
    d) Elimina il file temporaneo locale (`os.unlink`).
    """
    remote_key = f"{table_name}.parquet"
    cfg = get_cloud_config()

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{table_name}_upload.parquet")
    os.close(tmp_fd)

    uploaded_ok = False
    try:
        # Scrive prima sul file temporaneo tramite DuckDB o Pandas/PyArrow
        df.to_parquet(tmp_path, index=False)

        # Aggiorna copia locale di cache
        try:
            os.makedirs(os.path.dirname(os.path.abspath(local_fallback_path)), exist_ok=True)
            shutil.copy2(tmp_path, local_fallback_path)
        except Exception:
            df.to_parquet(local_fallback_path, index=False)

        # Upload diretto al bucket remoto (S3 / Supabase Storage)
        if cfg["enabled"]:
            uploaded_ok = upload_file_to_cloud_object(
                tmp_path,
                remote_key,
                content_type="application/octet-stream",
            )
    finally:
        # d) Elimina sempre il file temporaneo locale
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    return uploaded_ok


def ingest_and_append_remote_parquet(
    table_name: str,
    new_rows_df: pd.DataFrame,
    local_fallback_path: str,
    merge_fn: Optional[Callable[[pd.DataFrame, pd.DataFrame], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Flusso transazionale di Data Ingestion (Task 3):
    Quando l'Admin carica nuovi CSV/XLSX tramite il pannello di controllo:
      a) Scarica temporaneamente il Parquet remoto (`s3://bucket/{table_name}.parquet`).
      b) Appende/unisce i nuovi dati tramite Pandas/DuckDB (applicando deduplicazione se prevista).
      c) Effettua l'upload (sovrascrittura) del Parquet aggiornato direttamente sul bucket remoto.
      d) Elimina i file temporanei locali.
    """
    cfg = get_cloud_config()
    remote_key = f"{table_name}.parquet"

    tmp_down_fd, tmp_down_path = tempfile.mkstemp(suffix=f"_{table_name}_remote_in.parquet")
    os.close(tmp_down_fd)
    tmp_up_fd, tmp_up_path = tempfile.mkstemp(suffix=f"_{table_name}_remote_out.parquet")
    os.close(tmp_up_fd)

    try:
        # a) Scarica temporaneamente il Parquet remoto (o usa la baseline locale se primo avvio)
        existing_df = pd.DataFrame()
        if cfg["enabled"] and download_cloud_object_to_file(remote_key, tmp_down_path):
            try:
                if HAS_DUCKDB:
                    con = duckdb.connect(database=":memory:")
                    existing_df = con.execute(f"SELECT * FROM read_parquet('{tmp_down_path}')").df()
                    con.close()
                else:
                    existing_df = pd.read_parquet(tmp_down_path)
            except Exception:
                existing_df = pd.read_parquet(tmp_down_path)
        elif os.path.exists(local_fallback_path):
            try:
                existing_df = pd.read_parquet(local_fallback_path)
            except Exception:
                existing_df = pd.DataFrame()

        # b) Appende i nuovi dati tramite funzione di merge/dedup o concatenazione DuckDB/Pandas
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

        # c) Salva sul file temporaneo di output e sovrascrive il Parquet sul bucket remoto
        combined_df.to_parquet(tmp_up_path, index=False)

        # Aggiorna copia locale di lavoro
        try:
            os.makedirs(os.path.dirname(os.path.abspath(local_fallback_path)), exist_ok=True)
            shutil.copy2(tmp_up_path, local_fallback_path)
        except Exception:
            combined_df.to_parquet(local_fallback_path, index=False)

        if cfg["enabled"]:
            upload_file_to_cloud_object(tmp_up_path, remote_key, content_type="application/octet-stream")

        return result

    finally:
        # d) Elimina i file temporanei locali
        for p in (tmp_down_path, tmp_up_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass


# ==============================================================================
# SINCRONIZZAZIONE DATABASE GYMAWARE (SQLITE + PARQUET REMOTO)
# ==============================================================================
_GYMAWARE_PULL_DONE = False


def pull_gymaware_from_cloud(sqlite_path: str, force: bool = False) -> bool:
    """
    Scarica temporaneamente il database GymAware (`gymaware_data.parquet` o `rugby_database.sqlite`)
    dal bucket remoto e riallinea il database SQLite locale in modo che nessuna sessione VBT
    venga mai persa dopo un git push / redeploy.
    """
    global _GYMAWARE_PULL_DONE
    if _GYMAWARE_PULL_DONE and not force:
        return True

    cfg = get_cloud_config()
    if not cfg["enabled"]:
        return False

    tmp_fd, tmp_parquet = tempfile.mkstemp(suffix="_gymaware_remote.parquet")
    os.close(tmp_fd)

    try:
        if download_cloud_object_to_file("gymaware_data.parquet", tmp_parquet):
            remote_df = pd.read_parquet(tmp_parquet)
            if not remote_df.empty:
                os.makedirs(os.path.dirname(os.path.abspath(sqlite_path)), exist_ok=True)
                conn = sqlite3.connect(sqlite_path)
                try:
                    # Legge eventuali dati già presenti localmente per fare unione senza perdite
                    try:
                        local_df = pd.read_sql_query("SELECT * FROM gymaware_data", conn)
                    except Exception:
                        local_df = pd.DataFrame()

                    if not local_df.empty and len(local_df) > len(remote_df):
                        # Unisce preservando tutti i record unici
                        dedup_cols = [c for c in ["athlete_name", "date", "exercise", "set_id", "row_type", "rep_number", "mean_velocity"] if c in remote_df.columns and c in local_df.columns]
                        merged = pd.concat([remote_df, local_df], ignore_index=True)
                        if dedup_cols:
                            merged = merged.drop_duplicates(subset=dedup_cols, keep="first").reset_index(drop=True)
                        merged["id"] = range(1, len(merged) + 1)
                        merged.to_sql("gymaware_data", conn, if_exists="replace", index=False)
                    else:
                        remote_df.to_sql("gymaware_data", conn, if_exists="replace", index=False)
                    conn.commit()
                finally:
                    conn.close()
                _GYMAWARE_PULL_DONE = True
                return True
        else:
            # Se sul Cloud non esiste ancora gymaware_data.parquet ma esiste il DB locale, esegue il seed
            if os.path.exists(sqlite_path):
                push_gymaware_to_cloud(sqlite_path)
                _GYMAWARE_PULL_DONE = True
                return True
    except Exception:
        pass
    finally:
        if os.path.exists(tmp_parquet):
            try:
                os.unlink(tmp_parquet)
            except Exception:
                pass

    return False


def push_gymaware_to_cloud(sqlite_path: str) -> bool:
    """
    Esporta la tabella `gymaware_data` dal database SQLite in un file temporaneo `.parquet`,
    lo carica sul bucket remoto (`gymaware_data.parquet` + `rugby_database.sqlite`)
    ed elimina il file temporaneo locale.
    """
    cfg = get_cloud_config()
    if not cfg["enabled"] or not os.path.exists(sqlite_path):
        return False

    tmp_fd, tmp_parquet = tempfile.mkstemp(suffix="_gymaware_upload.parquet")
    os.close(tmp_fd)

    try:
        conn = sqlite3.connect(sqlite_path)
        try:
            df_gym = pd.read_sql_query("SELECT * FROM gymaware_data", conn)
        finally:
            conn.close()

        df_gym.to_parquet(tmp_parquet, index=False)
        ok_pq = upload_file_to_cloud_object(tmp_parquet, "gymaware_data.parquet", content_type="application/octet-stream")
        # Carica anche lo snapshot SQLite completo
        upload_file_to_cloud_object(sqlite_path, "rugby_database.sqlite", content_type="application/octet-stream")
        return ok_pq
    except Exception:
        return False
    finally:
        if os.path.exists(tmp_parquet):
            try:
                os.unlink(tmp_parquet)
            except Exception:
                pass


# ==============================================================================
# SINCRONIZZAZIONE FILE JSON DI CONFIGURAZIONE (TIPOLOGIE SEDUTE, TIMELINE, STATI)
# ==============================================================================
_JSON_SYNCED_KEYS = set()


def load_json_with_cloud_sync(remote_filename: str, local_path: str, default_factory=dict):
    """
    Carica un file JSON sincronizzandolo dal bucket remoto (al primo accesso per sessione)
    o eseguendo il seed sul bucket se non ancora presente sul Cloud.
    """
    cfg = get_cloud_config()
    if cfg["enabled"] and remote_filename not in _JSON_SYNCED_KEYS:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{remote_filename}")
        os.close(tmp_fd)
        try:
            if download_cloud_object_to_file(remote_filename, tmp_path):
                with open(tmp_path, "r", encoding="utf-8") as f:
                    remote_data = json.load(f)
                os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
                shutil.copy2(tmp_path, local_path)
                _JSON_SYNCED_KEYS.add(remote_filename)
                return remote_data
            elif os.path.exists(local_path):
                upload_file_to_cloud_object(local_path, remote_filename, content_type="application/json")
                _JSON_SYNCED_KEYS.add(remote_filename)
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_factory()


def save_json_with_cloud_sync(remote_filename: str, local_path: str, data: Any) -> bool:
    """
    Salva un dizionario/lista in formato JSON su un file temporaneo, aggiorna il file locale,
    carica la versione aggiornata sul bucket Cloud e rimuove il file temporaneo.
    """
    cfg = get_cloud_config()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{remote_filename}")
    os.close(tmp_fd)

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        shutil.copy2(tmp_path, local_path)

        if cfg["enabled"]:
            _JSON_SYNCED_KEYS.add(remote_filename)
            return upload_file_to_cloud_object(tmp_path, remote_filename, content_type="application/json")
        return True
    except Exception:
        return False
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def sync_all_local_data_to_cloud(data_dir: str = DATA_DIR) -> Dict[str, Any]:
    """
    Funzione di utilità per allineare/esportare su Cloud Object Storage tutti i file
    `.parquet`, `.sqlite` e `.json` presenti nella directory `data/`.
    """
    cfg = get_cloud_config()
    if not cfg["enabled"]:
        return {"ok": False, "reason": "Cloud storage non configurato", "uploaded": []}

    uploaded = []
    errors = []

    if not os.path.exists(data_dir):
        return {"ok": False, "reason": f"Directory {data_dir} non trovata", "uploaded": []}

    for fname in sorted(os.listdir(data_dir)):
        fpath = os.path.join(data_dir, fname)
        if not os.path.isfile(fpath):
            continue
        if fname.endswith(".parquet") or fname.endswith(".json") or fname.endswith(".sqlite"):
            ctype = "application/json" if fname.endswith(".json") else "application/octet-stream"
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
        "errors": errors,
    }
