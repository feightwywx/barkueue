def match_topic(pattern: str, topic: str) -> bool:
    """AMQP-style topic matching with * (one segment) and # (zero or more).

    Examples:
        match_topic("order.*", "order.created")      # True
        match_topic("order.*", "order.created.log")   # False
        match_topic("order.#", "order.a.b.c")         # True
        match_topic("#", "anything.here")             # True
        match_topic("order.created", "order.created") # True
    """
    pat = pattern.split(".")
    top = topic.split(".")

    def _match(pi: int, ti: int) -> bool:
        while pi < len(pat):
            if pat[pi] == "#":
                # match zero or more segments, greedy from the end
                return any(
                    _match(pi + 1, ti + n)
                    for n in range(len(top) - ti, -1, -1)
                )
            if ti >= len(top):
                return False
            if pat[pi] != "*" and pat[pi] != top[ti]:
                return False
            pi += 1
            ti += 1
        return ti == len(top)

    return _match(0, 0)
