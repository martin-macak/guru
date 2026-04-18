"""User domain."""


class UserBase:
    def greet(self) -> str:
        return "hi"


class UserService(UserBase):
    def login(self, user: str, pw: str) -> bool:
        return True

    def deprecated_fn(self) -> None:
        pass
