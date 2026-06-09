from barkueue import Application, app


class TestAppFactory:
    def test_returns_application(self):
        a = app(sources=[])
        assert isinstance(a, Application)

    def test_second_call_returns_same_instance(self):
        a1 = app(sources=[])
        a2 = app(sources=[])
        assert a1 is a2
