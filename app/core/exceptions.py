class AppError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class InvalidParams(AppError):
    code, status_code = "INVALID_PARAMS", 400


class Unauthorized(AppError):
    code, status_code = "UNAUTHORIZED", 401


class RateLimited(AppError):
    code, status_code = "RATE_LIMITED", 429


class UnexpectedFormat(AppError):
    code, status_code = "SILOGTRAN_UNEXPECTED_FORMAT", 502


class SessionUnavailable(AppError):
    code, status_code = "SILOGTRAN_SESSION_UNAVAILABLE", 503


class SilogtranTimeout(AppError):
    code, status_code = "SILOGTRAN_TIMEOUT", 504


class WafChallenge(AppError):
    code, status_code = "SILOGTRAN_WAF_CHALLENGE", 503
