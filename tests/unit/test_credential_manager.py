# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import pytest

cryptography = pytest.importorskip('cryptography')
keyring = pytest.importorskip('keyring')

import types

import utils.credential_manager as cm_mod
from utils.credential_manager import CredentialManager


class FakeKeyring:
    def __init__(self):
        self._store = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) in self._store:
            del self._store[(service, username)]
        else:
            raise Exception('not found')


def test_store_get_delete_with_fake_keyring(monkeypatch):
    fake = FakeKeyring()
    # Monkeypatch the keyring module used inside credential_manager
    monkeypatch.setattr(cm_mod, 'keyring', fake)
    cm = CredentialManager()
    # Ensure key was created in fake keyring
    assert fake.get_password(cm.SERVICE_NAME, cm.KEY_NAME) is not None

    service = 'ibm_quantum'
    token = 'MYTOKEN'
    cm.store_credential(service, token, metadata={'instance': 'ibm-q/open/main'})
    got = cm.get_credential(service)
    assert got == token

    # With metadata
    meta = cm.get_credential_with_metadata(service)
    assert meta and meta['credential'] == token

    cm.delete_credential(service)
    assert cm.get_credential(service) is None
