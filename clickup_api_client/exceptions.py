class ClickupClientError(Exception):
    def __init__(
            self,
            error_message,
            status_code=None,
            data=None,
    ):
        self.status_code = status_code
        self.error_message = error_message
        self.data = data

    def __str__(self):
        if self.status_code:
            return "(%s) %s" % (self.status_code, self.error_message)
        else:
            return self.error_message
