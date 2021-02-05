class Response:
    # lightweight response
    def __init__(self, data, headers=None, code=None):
        self.data = data
        self.headers = headers or {}
        self.code = code or 200
