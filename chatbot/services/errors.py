"""Provider-independent failures shared by existing chatbot clients and views."""


class AIServiceError(Exception):
    pass


class AIRateLimitError(AIServiceError):
    pass
