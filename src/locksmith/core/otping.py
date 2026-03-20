import pyotp
import qrcode
from PIL import ImageQt
from PySide6.QtGui import QPixmap
from keri import help

from locksmith.db.basing import OTPSecrets, OTPSecret

logger = help.ogler.getLogger(__name__)

def generate_otp_secret() -> str:
    """Generate a random base32 OTP secret using pyotp."""
    return pyotp.random_base32()

def create_totp_uri(secret: str, vault_name: str, issuer: str = "Locksmith Vault") -> str:
    """Create TOTP provisioning URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=vault_name, issuer_name=issuer)

def generate_qr_pixmap(uri: str, size: int = 300) -> QPixmap:
    """
    Generate QR code as QPixmap (in-memory, never saved to disk).
    
    Args:
        uri: The content to encode in the QR code (OTP provisioning URI)
        size: Width/Height of the resulting image in pixels
        
    Returns:
        QPixmap containing the QR code
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)

    # Create PIL image
    pil_image = qr.make_image(fill_color="black", back_color="#F8F9FF")
    
    # Resize if needed (though box_size usually controls this)
    if pil_image.size != (size, size):
        pil_image = pil_image.resize((size, size), resample=0)

    # Convert PIL image to QPixmap directly
    # ImageQt.ImageQt(image) returns a QImage-compatible object
    qimage = ImageQt.ImageQt(pil_image)
    pixmap = QPixmap.fromImage(qimage)
    
    return pixmap

def verify_otp(secret: str, code: str) -> bool:
    """
    Verify an OTP code against a secret.
    
    Args:
        secret: The base32 secret key
        code: The OTP code to verify
        
    Returns:
        True if the code is valid, False otherwise
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code)

def has_otp_configured(vault_name: str, db_path: str | None = None) -> bool:
    """
    Check if a vault has OTP configured in OTPSecrets database.
    
    Args:
        vault_name: Name of the vault
        db_path: Optional path to database directory (usually LocksmithConfig.base)
        
    Returns:
        True if OTP secret exists for vault
    """
    otp_db = None
    try:
        otp_db = OTPSecrets(headDirPath=db_path)
        return otp_db.otpSecrets.get(keys=(vault_name,)) is not None
    except Exception as e:
        logger.error(f"Error checking OTP configuration for {vault_name}: {e}")
        return False
    finally:
        if otp_db is not None:
            otp_db.close()

def get_otp_secret(vault_name: str, db_path: str | None = None) -> str | None:
    """
    Retrieve OTP secret for a vault if configured.
    
    Args:
        vault_name: Name of the vault
        db_path: Optional path to database directory
        
    Returns:
        Secret string if found, None otherwise
    """
    otp_db = None
    try:
        otp_db = OTPSecrets(headDirPath=db_path)
        record = otp_db.otpSecrets.get(keys=(vault_name,))
        return record.secret if record else None
    except Exception as e:
        logger.error(f"Error retrieving OTP secret for {vault_name}: {e}")
        return None
    finally:
        if otp_db is not None:
            otp_db.close()

def save_otp_secret(vault_name: str, secret: str, db_path: str | None = None) -> None:
    """
    Save OTP secret to OTPSecrets database.
    
    Args:
        vault_name: Name of the vault
        secret: Base32 secret string
        db_path: Optional path to database directory
    """
    otp_db = None
    try:
        otp_db = OTPSecrets(headDirPath=db_path)
        record = OTPSecret(vault=vault_name, secret=secret)
        otp_db.otpSecrets.pin(keys=(vault_name,), val=record)
        logger.info(f"Saved OTP secret for vault: {vault_name}")
    except Exception as e:
        logger.error(f"Error saving OTP secret for {vault_name}: {e}")
        raise
    finally:
        if otp_db is not None:
            otp_db.close()