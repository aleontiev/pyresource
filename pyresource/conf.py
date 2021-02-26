class Settings:
    def __init__(self, values):
        self._values = self.upper(values)

    def upper(self, config):
        return {k.upper(): v for k, v in config.items()}

    def configure(self, news, replace=False):
        news = self.upper(news)

        if replace:
            self._values = news
        else:
            self._values.update(news)

    def __getattr__(self, key):
        key = key.upper()
        return self._values.get(key)

defaults = {
    # PAGE_SIZE: default number of records per page
    'page_size': 50,
    # PAGE_TOTAL: whether or not total counts are returned
    #   in pagination metadata
    'page_total': True,
    # ENGINE: default resource engine
    'engine': 'django',
    # DEFAULT_FIELD_CAN: default field permissions
    'field_can': {
        'get': True,
        'set': True,
        'add': False,
        'prefetch': False
    },
    # ATOMIC: whether or not actions are meant to be performed
    # in a transaction or with transaction-like mechanics
    # (commit on success, rollback on failure)
    # if this is set to False, partial error responses may occur
    'atomic': True
}
settings = Settings(defaults)

def configure(news, replace=False):
    global settings
    return settings.configure(news, replace=replace)
