class Response:
    # lightweight response
    def __init__(self, data, headers=None, status=None):
        self.data = data
        self.headers = headers or {}
        self.status = status or 200
        self.code = self.status_code = status
