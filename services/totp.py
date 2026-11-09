"""Two-Factor Authentication (2FA) Engine using Time-based One-Time Passwords (TOTP).

Compliant with RFC 6238 and compatible with Google Authenticator, Microsoft Authenticator,
Apple Passwords, Authy, and other standard OTP apps.
"""

import os
import time
import struct
import hmac
import hashlib
import base64
import urllib.parse
import io
import qrcode


def generate_totp_secret(length: int = 20) -> str:
    """Generate a random Base32-encoded 160-bit secret key."""
    random_bytes = os.urandom(length)
    return base64.b32encode(random_bytes).decode('ascii').replace('=', '')


def get_totp_code(secret_b32: str, intervals_no: int = None, time_step: int = 30, digits: int = 6) -> str:
    """Compute the current 6-digit TOTP code for a given secret key according to RFC 6238."""
    if intervals_no is None:
        intervals_no = int(time.time()) // time_step

    # Pad Base32 string with '=' if necessary
    secret_clean = secret_b32.strip().replace(" ", "").upper()
    padding = (8 - len(secret_clean) % 8) % 8
    key = base64.b32decode(secret_clean + ('=' * padding), casefold=True)

    msg = struct.pack(">Q", intervals_no)
    h = hmac.new(key, msg, hashlib.sha1).digest()

    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str, window: int = 1, time_step: int = 30) -> bool:
    """Verify a user-provided 6-digit TOTP code against the secret key.
    
    Accepts codes within +-window time steps to account for minor clock drift.
    """
    if not secret_b32 or not code:
        return False

    code = str(code).strip()
    if len(code) != 6 or not code.isdigit():
        return False

    curr_interval = int(time.time()) // time_step
    for offset in range(-window, window + 1):
        if get_totp_code(secret_b32, curr_interval + offset, time_step=time_step) == code:
            return True
    return False


def get_provisioning_uri(secret_b32: str, email: str, issuer_name: str = "Atlas Finance") -> str:
    """Generate standard otpauth:// URL for scanning into authenticator apps."""
    secret_clean = secret_b32.strip().replace(" ", "").upper()
    encoded_issuer = urllib.parse.quote(issuer_name)
    encoded_label = urllib.parse.quote(f"{issuer_name}:{email}")
    return f"otpauth://totp/{encoded_label}?secret={secret_clean}&issuer={encoded_issuer}&algorithm=SHA1&digits=6&period=30"


def generate_qr_data_uri(provisioning_uri: str) -> str:
    """Generate an inline base64 PNG data-URI of the QR code for instant HTML rendering."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode('ascii')
    return f"data:image/png;base64,{b64_str}"
