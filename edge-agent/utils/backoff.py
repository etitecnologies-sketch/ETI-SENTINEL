import time
import functools

def retry(max_retries=5, backoff_base=2):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        delay = min(60, backoff_base ** attempt)
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
