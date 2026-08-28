"""
Services package.

The service layer contains all business logic.
Services receive repository instances via dependency injection
and are called by API route handlers.

Services must never import from app.api or app.repositories directly
via global imports — receive them as constructor arguments instead.

Pattern (Milestone 3+):
    class UserService:
        def __init__(self, user_repo: UserRepository) -> None:
            self.user_repo = user_repo

        async def create_user(self, data: UserCreate) -> User:
            ...
"""
