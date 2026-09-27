"""Users and the identities they sign in with.

Anyone may sign in with Google or GitHub (ADR-0006): the first time an identity signs in,
it becomes a new user; after that it is always that user. Two identities are never taken
for one user on their own, not even with the same email address; a signed-in user links
another identity by hand. The only gate is against throwaway accounts: a GitHub account
must be a year old, and a Google account's email address verified. A banned user's
identities cannot sign in.

Users can delete themselves, and with them everything of theirs, for good: signing in
with the same identity afterwards makes a new user.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from eidolon.call import Calls
from eidolon.clock import Clock
from eidolon.identity import Identity
from eidolon.memory import Memories
from eidolon.store import IdentityTaken, SignInMethod, Store, User

MIN_GITHUB_ACCOUNT_AGE = timedelta(days=365)
"""How old a GitHub account must be to sign in with."""

Refusal = Literal["too_new", "email_unverified", "banned", "taken", "already_linked"]
"""Why an identity may not sign in, or be linked:

- `too_new`: a GitHub account less than a year old
- `email_unverified`: a Google account whose email address is not verified
- `banned`: it belongs to a banned user
- `taken`: (linking) it belongs to another user
- `already_linked`: (linking) the user already signs in with another identity there
"""


class SignInRefused(Exception):
    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason)
        self.reason: Refusal = reason


@dataclass
class Accounts:
    store: Store
    clock: Clock
    memories: Memories
    calls: Calls

    def sign_in(self, identity: Identity) -> User:
        """The user this identity signs in as, made the first time. Raises SignInRefused."""
        self._check(identity)
        user_id = self.store.user_signing_in_with(identity.provider, identity.subject)
        if user_id is None:
            try:
                return self.store.create_user_signing_in_with(
                    identity.display_name, self._method(identity)
                )
            except IdentityTaken:  # signed in twice at once; the other made the user
                user_id = self.store.user_signing_in_with(identity.provider, identity.subject)
                assert user_id is not None
        user = self.store.get_user(user_id)
        if user.banned_at is not None:
            raise SignInRefused("banned")
        self.store.update_sign_in_method(
            identity.provider, identity.subject, identity.display_name, identity.email
        )
        return user

    def link(self, user_id: str, identity: Identity) -> None:
        """Let the user sign in with this identity too; nothing happens if they already do.
        Raises SignInRefused."""
        self._check(identity)
        owner = self.store.user_signing_in_with(identity.provider, identity.subject)
        if owner == user_id:
            return
        if owner is not None:
            raise SignInRefused("taken")
        if any(m.provider == identity.provider for m in self.store.sign_in_methods(user_id)):
            raise SignInRefused("already_linked")
        try:
            self.store.add_sign_in_method(user_id, self._method(identity))
        except IdentityTaken:
            raise SignInRefused("taken") from None

    async def delete(self, user_id: str) -> None:
        """Delete the user and all their data (see `Store.delete_user`), signing them out
        everywhere and hanging up their calls."""
        await self.calls.hang_up(user_id)
        await self.memories.forget(user_id)
        self.store.delete_user(user_id)
        await self.calls.hang_up(user_id)  # any placed while memory was settling

    def _check(self, identity: Identity) -> None:
        if identity.provider == "github" and (
            identity.created_at is None
            or self.clock() - identity.created_at < MIN_GITHUB_ACCOUNT_AGE
        ):
            raise SignInRefused("too_new")
        if identity.provider == "google" and not identity.email_verified:
            raise SignInRefused("email_unverified")

    def _method(self, identity: Identity) -> SignInMethod:
        return SignInMethod(
            identity.provider,
            identity.subject,
            identity.display_name,
            identity.email,
            self.clock().isoformat(),
        )
