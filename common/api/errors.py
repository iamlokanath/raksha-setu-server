class ApiError(Exception):
    def __init__(self, status: int, code: str, details: list | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.details = details or []
