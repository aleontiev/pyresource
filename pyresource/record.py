class Record(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return super().__getattribute__(name)
