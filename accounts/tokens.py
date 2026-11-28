from django.contrib.auth.tokens import PasswordResetTokenGenerator


class AccountVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return f'{super()._make_hash_value(user, timestamp)}{user.is_active}'


account_verification_token = AccountVerificationTokenGenerator()
