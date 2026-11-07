"""业务异常：services 层抛出，main.py 统一转成 HTTP 响应"""


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(ServiceError):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, 404)


class ConflictError(ServiceError):
    def __init__(self, message: str = "操作冲突"):
        super().__init__(message, 409)
