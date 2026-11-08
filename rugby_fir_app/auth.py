import os
import json
import hashlib
import secrets
import smtplib
from urllib.parse import quote
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional, List, Dict, Tuple

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
MAIL_CONFIG_FILE = os.path.join(DATA_DIR, "mail_config.json")


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def generate_temp_password(prefix: str = "Fir2026") -> str:
    """Genera una password provvisoria sicura, leggibile e conforme ai criteri di sicurezza (es. Fir2026#7k9x)."""
    chars = "abcdefghjkmnpqrstuvwxyz23456789"
    suffix = "".join(secrets.choice(chars) for _ in range(4))
    return f"{prefix}#{suffix}"


def get_mail_config() -> Dict:
    """Restituisce la configurazione email e portale di riferimento."""
    default_config = {
        "sender_email": "gps.performance@federugby.it",
        "sender_name": "FIR Area Performance & GPS",
        "app_url": "https://gps.federugby.it",
        "smtp_enabled": False,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "use_tls": True,
    }
    if os.path.exists(MAIL_CONFIG_FILE):
        try:
            with open(MAIL_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_config.update(saved)
        except Exception:
            pass
    return default_config


def save_mail_config(config: Dict) -> bool:
    """Salva la configurazione email di riferimento."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(MAIL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def build_credentials_email(
    user_info: Dict,
    temp_pw: str,
    is_reset: bool = False,
    sender_email: str = None,
    app_url: str = None,
) -> Dict[str, str]:
    """Costruisce il template di testo email formattato e l'URL mailto: pronto per l'invio."""
    cfg = get_mail_config()
    ref_sender = (sender_email or cfg.get("sender_email") or "gps.performance@federugby.it").strip()
    ref_url = (app_url or cfg.get("app_url") or "https://gps.federugby.it").strip()

    full_name = user_info.get("full_name") or user_info.get("username") or "Membro Staff"
    to_email = user_info.get("email") or user_info.get("username") or ""
    username = user_info.get("username") or to_email
    role_str = "Amministratore (Full Access)" if user_info.get("role") == "admin" else "Visualizzatore (Consultazione & PDF)"

    if is_reset:
        subject = "Piattaforma FIR GPS Analytics • Nuove Credenziali di Accesso (Reset Password)"
        action_text = "è stata reimpostata la password per il tuo account di accesso"
    else:
        subject = "Piattaforma FIR GPS Analytics • Credenziali di Accesso Ufficiali"
        action_text = "è stato attivato il tuo nuovo account personale per l'accesso"

    body_text = (
        f"Gentile {full_name},\n\n"
        f"{action_text} alla piattaforma FIR GPS Analytics (Nazionale Maggiore & Franchigie Federali).\n\n"
        f"====================================================\n"
        f"DETTAGLI ACCOUNT E CREDENZIALI:\n"
        f"• Portale Web: {ref_url}\n"
        f"• Username (o Email): {username}\n"
        f"• Password Provvisoria: {temp_pw}\n"
        f"• Ruolo Assegnato: {role_str}\n"
        f"====================================================\n\n"
        f"INDICAZIONI AL PRIMO ACCESSO:\n"
        f"1. Collegati al portale FIR tramite il link sopra indicato.\n"
        f"2. Accedi inserendo il tuo Username o la tua Email e la Password Provvisoria.\n"
        f"3. Al primo accesso, per motivi di sicurezza, ti invitiamo a modificare la password\n"
        f"   impostandone una personale definitiva tramite il menu laterale '🔑 Cambio password'.\n\n"
        f"Per supporto tecnico o chiarimenti sui dati GPS puoi rispondere direttamente a questa email ({ref_sender}).\n\n"
        f"Cordiali saluti,\n"
        f"Federazione Italiana Rugby • Area Performance & GPS\n"
    )

    mailto_url = f"mailto:{to_email}?subject={quote(subject)}&body={quote(body_text)}"

    return {
        "to_email": to_email,
        "subject": subject,
        "body_text": body_text,
        "mailto_url": mailto_url,
    }


def send_smtp_email(to_email: str, subject: str, body_text: str) -> Tuple[bool, str]:
    """Invia direttamente una email tramite server SMTP se configurato."""
    cfg = get_mail_config()
    if not cfg.get("smtp_enabled") or not cfg.get("smtp_host"):
        return False, "Server SMTP non abilitato o non configurato nelle impostazioni."

    to_clean = to_email.strip()
    if not to_clean or "@" not in to_clean:
        return False, f"Indirizzo email destinatario non valido: '{to_email}'"

    sender = cfg.get("sender_email") or "gps.performance@federugby.it"
    sender_name = cfg.get("sender_name") or "FIR Area Performance"

    msg = MIMEText(body_text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to_clean

    host = cfg.get("smtp_host", "").strip()
    port = int(cfg.get("smtp_port") or 587)
    user = cfg.get("smtp_user", "").strip()
    pw = cfg.get("smtp_password", "").strip()
    use_tls = cfg.get("use_tls", True)

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                server.starttls()
        if user and pw:
            server.login(user, pw)
        server.sendmail(sender, [to_clean], msg.as_string())
        server.quit()
        return True, f"Email spedita con successo a {to_clean}!"
    except Exception as e:
        return False, f"Errore durante l'invio SMTP a {to_clean}: {e}"


def init_auth():
    """Inizializza il file degli utenti se non esiste, creando l'amministratore e un profilo staff di default."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        salt_admin = secrets.token_hex(16)
        salt_staff = secrets.token_hex(16)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        default_users = [
            {
                "username": "admin",
                "email": "admin@federugby.it",
                "full_name": "Amministratore FIR",
                "role": "admin",  # 'admin' o 'viewer'
                "salt": salt_admin,
                "password_hash": _hash_pw("fir_admin_2026", salt_admin),
                "created_at": now_str,
                "last_login": None,
                "is_primary": True,
                "must_change_password": False,
            },
            {
                "username": "staff_fir",
                "email": "staff_fir@federugby.it",
                "full_name": "Staff Tecnico Federale",
                "role": "viewer",
                "salt": salt_staff,
                "password_hash": _hash_pw("fir_staff_2026", salt_staff),
                "created_at": now_str,
                "last_login": None,
                "is_primary": False,
                "must_change_password": False,
            },
        ]
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_users, f, indent=2, ensure_ascii=False)


def get_users() -> List[Dict]:
    init_auth()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
            # Garantisci retrocompatibilità se mancano campi email o must_change_password
            changed = False
            for u in users:
                if "email" not in u:
                    u_nm = u.get("username", "")
                    u["email"] = u_nm if "@" in u_nm else f"{u_nm}@federugby.it"
                    changed = True
                if "must_change_password" not in u:
                    u["must_change_password"] = False
                    changed = True
            if changed:
                _save_users(users)
            return users
    except Exception:
        return []


def _save_users(users: List[Dict]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def verify_user(username: str, password: str) -> Optional[Dict]:
    """
    Verifica le credenziali di accesso.
    Consente l'accesso inserendo indifferentemente lo Username o l'Indirizzo Email.
    Se corrette restituisce i dati utente e aggiorna last_login.
    """
    u_clean = username.strip().lower()
    pw_clean = password.strip()
    if not u_clean or not pw_clean:
        return None

    users = get_users()
    matched = None
    for u in users:
        curr_u = str(u.get("username") or "").strip().lower()
        curr_e = str(u.get("email") or "").strip().lower()
        if curr_u == u_clean or curr_e == u_clean:
            expected_hash = _hash_pw(pw_clean, u["salt"])
            if secrets.compare_digest(u["password_hash"], expected_hash):
                matched = u
                u["last_login"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break

    if matched:
        _save_users(users)
        return {
            "username": matched["username"],
            "email": matched.get("email") or f"{matched['username']}@federugby.it",
            "full_name": matched["full_name"],
            "role": matched["role"],
            "created_at": matched["created_at"],
            "last_login": matched.get("last_login"),
            "is_primary": matched.get("is_primary", False),
            "must_change_password": matched.get("must_change_password", False),
        }
    return None


def create_user(
    username: str,
    full_name: str,
    role: str,
    password: str,
    email: str = None,
    must_change_password: bool = True,
) -> Tuple[bool, str]:
    """Crea un nuovo profilo utente con password (provvisoria o definitiva) assegnata dall'admin."""
    u_clean = username.strip().lower()
    fn_clean = full_name.strip()
    pw_clean = password.strip()
    em_clean = (email.strip().lower() if email else "")

    if not em_clean and "@" in u_clean:
        em_clean = u_clean
    if not u_clean and em_clean:
        u_clean = em_clean

    if not u_clean or len(u_clean) < 3:
        return False, "Lo username o l'email deve contenere almeno 3 caratteri."
    if not fn_clean:
        # Se nome assente, auto-deduci dal prefisso email
        base_name = u_clean.split("@")[0].replace(".", " ").replace("_", " ").title()
        fn_clean = base_name if base_name else "Membro Staff"
    if not pw_clean or len(pw_clean) < 6:
        return False, "La password deve contenere almeno 6 caratteri."
    if role not in ("admin", "viewer"):
        return False, "Ruolo non valido (seleziona Amministratore o Visualizzatore)."

    users = get_users()
    for u in users:
        if u.get("username", "").lower() == u_clean:
            return False, f"Lo username '{u_clean}' è già utilizzato da un altro utente."
        if em_clean and u.get("email", "").lower() == em_clean:
            return False, f"L'indirizzo email '{em_clean}' è già associato a un altro profilo."

    salt = secrets.token_hex(16)
    new_user = {
        "username": u_clean,
        "email": em_clean or (u_clean if "@" in u_clean else f"{u_clean}@federugby.it"),
        "full_name": fn_clean,
        "role": role,
        "salt": salt,
        "password_hash": _hash_pw(pw_clean, salt),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_login": None,
        "is_primary": False,
        "must_change_password": bool(must_change_password),
    }
    users.append(new_user)
    _save_users(users)
    return True, f"Utente '{u_clean}' creato con successo!"


def batch_create_users(
    entries: List[Dict],
    default_role: str = "viewer",
) -> Tuple[int, List[Dict], List[str]]:
    """
    Crea massivamente account multipli (es. 15+ account per staff o giocatori).
    Restituisce: (numero_creati, lista_utenti_creati_con_password_provvisoria, lista_errori).
    """
    created_list = []
    error_list = []
    success_count = 0

    for idx, item in enumerate(entries, start=1):
        raw_email = str(item.get("email") or item.get("username") or "").strip()
        if not raw_email:
            continue

        em_clean = raw_email.lower()
        raw_name = str(item.get("full_name") or item.get("name") or "").strip()
        if not raw_name:
            # Ricava nome pulito dalla parte prima della @ (es. mario.rossi -> Mario Rossi)
            name_part = em_clean.split("@")[0].replace(".", " ").replace("_", " ").title()
            raw_name = name_part if name_part else "Staff Tecnico"

        role = str(item.get("role") or default_role).strip().lower()
        if role not in ("admin", "viewer"):
            role = "viewer"

        # Password provvisoria fornita o auto-generata
        pw = str(item.get("password") or "").strip()
        if not pw or len(pw) < 6:
            pw = generate_temp_password()

        ok, msg = create_user(
            username=em_clean,
            full_name=raw_name,
            role=role,
            password=pw,
            email=em_clean,
            must_change_password=True,
        )

        if ok:
            success_count += 1
            u_info = {
                "username": em_clean,
                "email": em_clean,
                "full_name": raw_name,
                "role": role,
                "temp_password": pw,
            }
            # Pre-calcola email pronto all'uso
            em_payload = build_credentials_email(u_info, pw, is_reset=False)
            u_info["subject"] = em_payload["subject"]
            u_info["body_text"] = em_payload["body_text"]
            u_info["mailto_url"] = em_payload["mailto_url"]
            created_list.append(u_info)
        else:
            error_list.append(f"Riga {idx} ({em_clean}): {msg}")

    return success_count, created_list, error_list


def change_user_password(username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
    """Permette a qualsiasi utente autenticato di modificare la propria password."""
    u_clean = username.strip().lower()
    pw_old = old_password.strip()
    pw_new = new_password.strip()

    if not pw_new or len(pw_new) < 6:
        return False, "La nuova password deve contenere almeno 6 caratteri."
    if pw_old == pw_new:
        return False, "La nuova password deve essere diversa dalla precedente."

    users = get_users()
    for u in users:
        if u["username"].lower() == u_clean or u.get("email", "").lower() == u_clean:
            if not secrets.compare_digest(u["password_hash"], _hash_pw(pw_old, u["salt"])):
                return False, "La password attuale non è corretta."
            new_salt = secrets.token_hex(16)
            u["salt"] = new_salt
            u["password_hash"] = _hash_pw(pw_new, new_salt)
            u["must_change_password"] = False
            _save_users(users)
            return True, "Password modificata con successo!"

    return False, "Utente non trovato."


def admin_reset_password(username: str, new_password: str) -> Tuple[bool, str]:
    """Permette all'amministratore di reimpostare manualmente la password di qualsiasi utente."""
    u_clean = username.strip().lower()
    pw_new = new_password.strip()
    if not pw_new or len(pw_new) < 6:
        return False, "La password deve contenere almeno 6 caratteri."

    users = get_users()
    for u in users:
        if u["username"].lower() == u_clean or u.get("email", "").lower() == u_clean:
            new_salt = secrets.token_hex(16)
            u["salt"] = new_salt
            u["password_hash"] = _hash_pw(pw_new, new_salt)
            u["must_change_password"] = True
            _save_users(users)
            return True, f"Password dell'utente '{u_clean}' reimpostata con successo!"

    return False, "Utente non trovato."


def admin_reset_password_auto(username: str, must_change_password: bool = True) -> Tuple[bool, str, str]:
    """Reimposta automaticamente la password generando una nuova password provvisoria sicura."""
    u_clean = username.strip().lower()
    temp_pw = generate_temp_password()

    users = get_users()
    for u in users:
        if u["username"].lower() == u_clean or u.get("email", "").lower() == u_clean:
            new_salt = secrets.token_hex(16)
            u["salt"] = new_salt
            u["password_hash"] = _hash_pw(temp_pw, new_salt)
            u["must_change_password"] = bool(must_change_password)
            _save_users(users)
            return True, f"Password provvisoria generata con successo per '{u_clean}'!", temp_pw

    return False, "Utente non trovato.", ""


def admin_update_user_role(username: str, new_role: str) -> Tuple[bool, str]:
    """Modifica il ruolo di un utente (admin / viewer)."""
    if new_role not in ("admin", "viewer"):
        return False, "Ruolo non valido."
    u_clean = username.strip().lower()
    users = get_users()
    for u in users:
        if u["username"].lower() == u_clean or u.get("email", "").lower() == u_clean:
            if u.get("is_primary") and new_role != "admin":
                return False, "Non è possibile rimuovere i permessi di amministrazione all'account admin principale."
            u["role"] = new_role
            _save_users(users)
            return True, f"Ruolo di '{u_clean}' aggiornato a '{new_role}'."
    return False, "Utente non trovato."


def admin_delete_user(username: str, current_username: str) -> Tuple[bool, str]:
    """Elimina un profilo utente. Non è possibile eliminare se stessi o l'admin principale."""
    u_clean = username.strip().lower()
    c_clean = current_username.strip().lower()

    if u_clean == c_clean:
        return False, "Non puoi eliminare il tuo stesso account mentre sei autenticato."

    users = get_users()
    for u in users:
        if u["username"].lower() == u_clean or u.get("email", "").lower() == u_clean:
            if u.get("is_primary"):
                return False, "Non è possibile eliminare l'account amministratore di default."
            users.remove(u)
            _save_users(users)
            return True, f"Utente '{u_clean}' eliminato definitivamente."

    return False, "Utente non trovato."
