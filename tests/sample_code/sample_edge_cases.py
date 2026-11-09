def empty_func():
    pass

def no_doc(x):
    return x * 2

class Outer:
    class Inner:
        def method(self):
            pass

def outer():
    def inner():
        return 42
    return inner

multiply = lambda x, y: x * y

def try_except_func():
    try:
        x = 1 / 0
    except ZeroDivisionError:
        x = 0
    finally:
        pass
    return x

def match_case_func(status: int):
    match status:
        case 200:
            return "OK"
        case 404:
            return "Not Found"
        case _:
            return "Unknown"

def kwargs_func(*args, **kwargs):
    pass
