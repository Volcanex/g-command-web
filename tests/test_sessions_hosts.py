from pages.sessions import api as sessions_api  # noqa: E402


def test_unset_is_local_only():
    assert sessions_api._hosts("") == {"local": None}


def test_first_host_is_local_and_the_rest_go_over_ssh():
    hosts = sessions_api._hosts("h, b=b.example.com, c")
    assert hosts == {"h": None, "b": "b.example.com", "c": "c"}


def test_names_that_cannot_go_in_a_url_are_dropped():
    assert sessions_api._hosts("h,bad/name=x,b") == {"h": None, "b": "b"}
