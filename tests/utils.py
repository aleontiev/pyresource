class Request:
    def __init__(self, user=None):
        self.user = user


class Fixture:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
