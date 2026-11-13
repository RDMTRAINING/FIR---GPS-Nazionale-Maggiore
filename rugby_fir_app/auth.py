# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
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
                "has_accepted_terms": True,
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
                "has_accepted_terms": False,
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
                if "has_accepted_terms" not in u:
                    u["has_accepted_terms"] = True if (u.get("role") == "admin" and u.get("is_primary")) else False
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
            "has_accepted_terms": bool(matched.get("has_accepted_terms", False)),
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
        "has_accepted_terms": False,
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

    return False, "Utente non trovato."


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




def accept_terms(username: str) -> bool:
    """Aggiorna il flag has_accepted_terms a True e registra il timestamp di accettazione nel database utenti."""
    u_clean = username.strip().lower()
    users = get_users()
    for u in users:
        if u["username"].lower() == u_clean or u.get("email", "").lower() == u_clean:
            u["has_accepted_terms"] = True
            u["terms_accepted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_users(users)
            return True
    return False


def reset_terms_acceptance(username: str) -> bool:
    """Permette all'amministratore di richiedere una nuova accettazione dei termini a un utente."""
    u_clean = username.strip().lower()
    users = get_users()
    for u in users:
        if u["username"].lower() == u_clean or u.get("email", "").lower() == u_clean:
            u["has_accepted_terms"] = False
            u["terms_accepted_at"] = None
            _save_users(users)
            return True
    return False


def render_terms_agreement_page(t: dict, user_info: dict):
    """
    Renderizza il Clickwrap Agreement obbligatorio al primo accesso per Staff Tecnico e Medico.
    Blocca l'accesso a tutta la piattaforma finché l'utente non scarica/legge l'Atto di Nomina,
    accetta la checkbox vincolante e clicca su 'Accedi alla Piattaforma'.
    """
    import streamlit as st
    try:
        from config import get_logo_base64
    except ImportError:
        from rugby_fir_app.config import get_logo_base64

    b64_logo = get_logo_base64()
    logo_img_html = (
        f'<img src="data:image/png;base64,{b64_logo}" style="height:76px; width:auto; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.35));" alt="FIR Logo">'
        if b64_logo
        else '<div style="width:68px; height:68px; border-radius:50%; background:#0066B2; border:2.5px solid #D4AF37; display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-weight:800; font-size:1.4rem;">FIR</div>'
    )

    _, col_center, _ = st.columns([1, 3.2, 1])

    with col_center:
        st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #002B49 0%, #0066B2 100%); border-radius:16px 16px 0 0; padding:24px 28px 20px 28px; text-align:center; border:1px solid rgba(212,175,55,0.4); border-bottom:3px solid #D4AF37; box-shadow:0 8px 24px rgba(0,43,73,0.35);">
                <div style="display:flex; justify-content:center; margin-bottom:12px;">
                    {logo_img_html}
                </div>
                <div style="font-size:0.75rem; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; color:#D4AF37; margin-bottom:4px;">
                    FEDERAZIONE ITALIANA RUGBY &bull; AREA PERFORMANCE & GPS
                </div>
                <div style="font-size:1.55rem; font-weight:800; letter-spacing:-0.02em; color:#FFFFFF; margin:0;">
                    FIR GPS PLATFORM
                </div>
                <div style="font-size:0.86rem; color:#93C5FD; font-weight:600; margin-top:4px;">
                    Accreditamento Staff Tecnico & Medico &bull; Conformità GDPR & Proprietà Intellettuale
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container():
            st.markdown(
                """
                <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:none; border-radius:0 0 16px 16px; padding:30px 32px 24px 32px; box-shadow:0 12px 28px rgba(15,23,42,0.08); margin-bottom:16px;">
                    <div style="font-size:1.24rem; font-weight:800; color:#002B49; margin-bottom:12px; border-bottom:2px solid #E2E8F0; padding-bottom:8px;">
                        Termini d'Uso, Riservatezza e Proprietà Intellettuale
                    </div>
                    <p style="font-size:0.88rem; color:#334155; line-height:1.6; margin-bottom:16px;">
                        Benvenuto nella Piattaforma Analytics della Nazionale Italiana Rugby. L'accesso a questo sistema è strettamente personale e riservato ai membri dello Staff Tecnico e Medico autorizzati. Prima di procedere, ti invitiamo a leggere e accettare le seguenti condizioni operative:
                    </p>
                    <div style="background:#F8FAFC; border-left:4px solid #0066B2; padding:14px 16px; border-radius:0 8px 8px 0; margin-bottom:14px;">
                        <div style="font-size:0.92rem; font-weight:700; color:#002B49; margin-bottom:4px;">
                            1. Proprietà Intellettuale e Licenza d'Uso
                        </div>
                        <div style="font-size:0.84rem; color:#475569; line-height:1.55;">
                            Questa piattaforma web, incluse le architetture di database, le logiche di calcolo del microciclo, gli algoritmi di mapping e le interfacce, costituisce <b>tecnologia proprietaria esclusiva di Riccardo Di Maio (RDM)</b>. Il sistema è concesso in mero utilizzo funzionale temporaneo. È severamente vietato riprodurre, copiare, analizzare (reverse engineering) o cedere l'accesso a terze parti senza l'esplicita autorizzazione dell'autore.
                        </div>
                    </div>
                    <div style="background:#F8FAFC; border-left:4px solid #D4AF37; padding:14px 16px; border-radius:0 8px 8px 0; margin-bottom:14px;">
                        <div style="font-size:0.92rem; font-weight:700; color:#002B49; margin-bottom:4px;">
                            2. Trattamento dei Dati Sensibili (GDPR)
                        </div>
                        <div style="font-size:0.84rem; color:#475569; line-height:1.55;">
                            Il database contiene categorie particolari di dati personali (Art. 9 Reg. UE 2016/679), tra cui parametri fisici e metriche di prestazione degli atleti. L'utente si impegna a trattare i dati esclusivamente per finalità tecniche e mediche, e a non diffonderli al di fuori degli ambienti protetti della F.I.R.
                        </div>
                    </div>
                    <div style="background:#F8FAFC; border-left:4px solid #E11D48; padding:14px 16px; border-radius:0 8px 8px 0; margin-bottom:18px;">
                        <div style="font-size:0.92rem; font-weight:700; color:#002B49; margin-bottom:4px;">
                            3. Sicurezza delle Credenziali
                        </div>
                        <div style="font-size:0.84rem; color:#475569; line-height:1.55;">
                            L'utente è l'unico responsabile della segretezza della propria password. Eventuali Data Breach derivanti da gestione negligente del proprio account ricadranno sotto la responsabilità dell'utente stesso.
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Download documento PDF Atto di Nomina
            doc_path = os.path.join(os.path.dirname(__file__), "assets", "Atto_Nomina_Privacy_FIR_RDM_v2.pdf")
            if os.path.exists(doc_path):
                with open(doc_path, "rb") as f_pdf:
                    pdf_data = f_pdf.read()
                st.download_button(
                    label="📄 Scarica l'Atto di Nomina completo per i dettagli sulla Privacy",
                    data=pdf_data,
                    file_name="Atto_Nomina_Privacy_FIR_RDM_v2.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="btn_download_atto_nomina_pdf",
                )
            else:
                st.info("Atto di Nomina Privacy e IP in fase di caricamento negli asset di sistema.")

            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

            # Checkbox obbligatoria con stringa esatta
            chk_label = "Dichiaro di aver letto, compreso e accettato i Termini d'Uso, i vincoli di Proprietà Intellettuale (Tecnologia RDM) e le direttive sulla Privacy dei dati."
            accepted = st.checkbox(chk_label, key="chk_clickwrap_terms")

            st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

            col_btn1, col_btn2 = st.columns([3, 1.2])
            with col_btn1:
                btn_confirm = st.button("Accedi alla Piattaforma", type="primary", use_container_width=True, disabled=not accepted, key="btn_confirm_clickwrap")
                if btn_confirm:
                    if accepted:
                        uname = user_info.get("username", "")
                        accept_terms(uname)
                        if "current_user" in st.session_state:
                            st.session_state["current_user"]["has_accepted_terms"] = True
                        st.success("Accettazione registrata con successo! Accesso alla piattaforma in corso...")
                        st.rerun()
                    else:
                        st.warning("È obbligatorio spuntare la casella di accettazione prima di accedere alla piattaforma.")

            with col_btn2:
                if st.button("Esci / Logout", type="secondary", use_container_width=True, key="btn_logout_from_terms"):
                    st.session_state["authenticated"] = False
                    st.session_state.pop("current_user", None)
                    st.session_state.pop("user_role", None)
                    st.rerun()

            st.markdown(
                """
                <div style="text-align:center; padding-top:18px; font-size:0.72rem; color:#94A3B8;">
                    MOV3 S.r.l. - Tutti i diritti riservati
                </div>
                """,
                unsafe_allow_html=True,
            )
