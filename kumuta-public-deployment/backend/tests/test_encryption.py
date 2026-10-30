import os
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken
from app import gemini


class EncryptionSecurityTests(unittest.TestCase):
    def test_missing_encryption_key_fails_fast(self):
        with patch.dict(os.environ, {'API_KEY_ENCRYPTION_KEY': ''}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                gemini.cipher()
            self.assertIn('Set API_KEY_ENCRYPTION_KEY', str(ctx.exception))

    def test_invalid_encryption_key_fails_fast(self):
        with patch.dict(os.environ, {'API_KEY_ENCRYPTION_KEY': 'not-a-valid-fernet-key'}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                gemini.cipher()
            self.assertIn('Set API_KEY_ENCRYPTION_KEY', str(ctx.exception))

    def test_single_key_encryption_decryption(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {'API_KEY_ENCRYPTION_KEY': key}, clear=False):
            c = gemini.cipher()
            ciphertext = c.encrypt(b'my-secret-gemini-key')
            decrypted = c.decrypt(ciphertext)
            self.assertEqual(decrypted, b'my-secret-gemini-key')

    def test_multi_key_backward_compatibility_rotation(self):
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()

        # Encrypt with old key
        with patch.dict(os.environ, {'API_KEY_ENCRYPTION_KEY': old_key}, clear=False):
            old_ciphertext = gemini.cipher().encrypt(b'old-production-api-key')

        # Rotate key using comma-separated: new_key, old_key
        with patch.dict(os.environ, {'API_KEY_ENCRYPTION_KEY': f'{new_key},{old_key}'}, clear=False):
            rot_cipher = gemini.cipher()
            # Old ciphertext decrypts smoothly without data loss
            self.assertEqual(rot_cipher.decrypt(old_ciphertext), b'old-production-api-key')

            # New ciphertext is encrypted using new_key
            new_ciphertext = rot_cipher.encrypt(b'new-user-api-key')
            self.assertEqual(rot_cipher.decrypt(new_ciphertext), b'new-user-api-key')

            # Verify new_ciphertext can be decrypted by new_key standalone
            with patch.dict(os.environ, {'API_KEY_ENCRYPTION_KEY': new_key}, clear=False):
                self.assertEqual(gemini.cipher().decrypt(new_ciphertext), b'new-user-api-key')

    def test_invalid_token_handling(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {'API_KEY_ENCRYPTION_KEY': key}, clear=False):
            c = gemini.cipher()
            with self.assertRaises(InvalidToken):
                c.decrypt(b'gAAAAABcorruptedTokenHere1234567890')


if __name__ == '__main__':
    unittest.main()
