"""Генерация самоподписанного TLS-сертификата (учебный вариант): RSA-2048, SHA-256, 1 год."""
import datetime
import ipaddress
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app import config


def generate(force=False):
    config.CERT_DIR.mkdir(exist_ok=True)
    cert_p, key_p = config.CERT_DIR / "server.crt", config.CERT_DIR / "server.key"
    if cert_p.exists() and key_p.exists() and not force:
        return cert_p, key_p
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vkusno i bystro (study)"),
                      x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256()))
    key_p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                        serialization.NoEncryption()))
    os.chmod(key_p, 0o600)
    cert_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print("Сертификат создан:", cert_p)
    return cert_p, key_p


if __name__ == "__main__":
    generate(force=True)
