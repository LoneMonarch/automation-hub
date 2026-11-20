"""Use OS credential storage; never fall back to plaintext files."""
import sys


def backend():
    if sys.platform == 'win32':
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()
    if sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
        return Keyring()
    raise RuntimeError('Credential storage requires Windows or macOS.')


def save(account, password):
    backend().set_password('AutomationHub.Help2Rent', account, password)


def read(account):
    return backend().get_password('AutomationHub.Help2Rent', account) or ''
